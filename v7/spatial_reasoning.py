# -*- coding: utf-8 -*-
"""跨图纸空间推理引擎 —— 从"查标注"到"找矛盾"的跃迁
v2.0: 楼层感知 + 标高解析 + Z轴推断
"""

import os, sys, glob, re, json, hashlib, traceback, logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import ezdxf
import numpy as np
from rtree import index as rtree_index
from shapely.geometry import box as shapely_box, LineString
from sklearn.cluster import DBSCAN

try:
    import yaml
    _config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    with open(_config_path, "r", encoding="utf-8") as _f:
        _config = yaml.safe_load(_f)
except FileNotFoundError:
    _config = {}
except Exception as e:
    logging.getLogger("v7.spatial").warning(f"加载配置文件失败: {str(e)}")
    _config = {}


# ── 楼层名称 → 数字映射 ──
FLOOR_MAP = _config.get("floor_map", {
    "地下一层": -1, "地下二层": -2, "地下三层": -3, "地下室": -1,
    "一层": 1, "二层": 2, "三层": 3, "四层": 4, "五层": 5,
    "六层": 6, "七层": 7, "八层": 8, "九层": 9, "十层": 10,
    "十一层": 11, "十二层": 12, "十三层": 13, "十四层": 14, "十五层": 15,
    "屋檐层": 16, "屋顶层": 13, "屋顶": 13, "屋面": 13, "设备层": 50,
    "架空层": 1, "夹层": 0.5, "B1F": -1, "B2F": -2, "B3F": -3,
    "1F": 1, "2F": 2, "3F": 3, "4F": 4, "5F": 5, "6F": 6, "7F": 7,
    "8F": 8, "9F": 9, "10F": 10, "11F": 11, "12F": 12, "13F": 13,
    "RF": 13, "BF": -1, "B1": -1, "B2": -2,
})

# ── 楼层标注正则 ──
FLOOR_PATTERNS = [
    (re.compile(r"(地[下上]?[一二三四五六七八九十]+层|B\d+F?|[一二三四五六七八九十]+\s*F|屋顶层?|屋面|设备层|架空层|夹层|RF|B[1-3]|BF)"), "zh"),
    (re.compile(r"(\d+)\s*F"), "digit_f"),
    (re.compile(r"([一二三四五六七八九十]+)\s*层"), "chinese"),
]


def parse_floor(text: str) -> Optional[float]:
    """从文本中提取楼层号"""
    text = text.strip().replace(" ", "").replace(" ", "").replace(" ", "")
    if len(text) > 50:
        return None
    sorted_keys = sorted(FLOOR_MAP.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key not in text:
            continue
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in key)
        if has_chinese:
            return FLOOR_MAP[key]
        idx = text.index(key)
        before_ok = idx == 0 or not (text[idx-1].isalpha() or text[idx-1].isdigit())
        after_ok = (idx + len(key) == len(text) or
                    not (text[idx+len(key)].isalpha() or text[idx+len(key)].isdigit()))
        if before_ok and after_ok:
            return FLOOR_MAP[key]
    m = re.match(r"^(\d+)F$", text)
    if m:
        return float(m.group(1))
    m = re.match(r"^B(\d+)F?$", text)
    if m:
        return -float(m.group(1))
    return None


def floor_label(fl: Optional[float]) -> str:
    """楼层数字→可读标签"""
    if fl is None:
        return "?"
    if fl >= 99:
        return "RF(屋顶)"
    if fl == 50:
        return "设备层"
    if fl == 0.5:
        return "夹层"
    if fl < 0:
        return f"B{int(abs(fl))}F"
    return f"{int(fl)}F"


def parse_elevation(text: str) -> Optional[float]:
    """从文本中提取标高值（米）"""
    patterns = [
        re.compile(r"标高\s*[:：]?\s*([+-]?\d+\.?\d*)\s*m", re.IGNORECASE),
        re.compile(r"洞底标高\s*[:：]?\s*([+-]?\d+\.?\d*)\s*m", re.IGNORECASE),
        re.compile(r"标高\s*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"H\s*=\s*([+-]?\d+\.?\d*)\s*m?", re.IGNORECASE),
        re.compile(r"([+-]\d+\.?\d*)\s*m\s*[安高装]", re.IGNORECASE),
        re.compile(r"风口\s*([+-]\d+\.?\d*)\s*m", re.IGNORECASE),
        re.compile(r"[,，]\s*([+-]\d+\.?\d*)\s*m", re.IGNORECASE),
        re.compile(r"([+-]\d+\.?\d*)\s*m$", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(text)
        if m:
            return float(m.group(1))
    return None


@dataclass
class FloorLabel:
    """楼层标签"""
    x: float
    y: float
    floor: float
    text: str
    drawing_name: str


@dataclass
class ElevationTag:
    """标高标注"""
    x: float
    y: float
    elevation: float
    text: str
    drawing_name: str


@dataclass
class SpatialEntity:
    """空间实体：带类型、坐标、楼层、标高"""
    entity_type: str
    discipline: str
    drawing_name: str
    layer: str = ""
    x_min: float = 0.0
    y_min: float = 0.0
    x_max: float = 0.0
    y_max: float = 0.0
    floor_level: Optional[float] = None
    z_bottom: Optional[float] = None
    z_top: Optional[float] = None
    text_content: str = ""
    dimensions: str = ""


class SpatialIndex:
    """两级R-Tree空间索引：楼层→专业（纯内存，过滤非空间实体）"""
    _NON_SPATIAL = frozenset(["text", "line", "arc"])

    def __init__(self, memory=False):
        self.floor_discipline_idx: Dict[Tuple[float, str], rtree_index.Index] = {}
        self._entity_map: Dict[int, SpatialEntity] = {}
        self._next_id = 0
        self._entities_by_type: Dict[str, List[SpatialEntity]] = {}

    def build(self, entities: List[SpatialEntity]):
        for e in entities:
            if e.entity_type in self._NON_SPATIAL:
                continue
            eid = self._next_id
            self._next_id += 1
            self._entity_map[eid] = e
            fl = e.floor_level or 0
            key = (fl, e.discipline)
            if key not in self.floor_discipline_idx:
                self.floor_discipline_idx[key] = rtree_index.Index()
            self.floor_discipline_idx[key].insert(eid, (e.x_min, e.y_min, e.x_max, e.y_max))
            self._entities_by_type.setdefault(e.entity_type, []).append(e)

    def get_entities_by_type(self, entity_type: str) -> List[SpatialEntity]:
        return self._entities_by_type.get(entity_type, [])

    def query_cross_candidates(self, floor_id: float, source_disc: str,
                                target_discs: List[str]) -> List[Tuple[SpatialEntity, SpatialEntity]]:
        candidates = []
        src_idx = self.floor_discipline_idx.get((floor_id, source_disc))
        if not src_idx:
            return candidates
        for target_disc in target_discs:
            tgt_idx = self.floor_discipline_idx.get((floor_id, target_disc))
            if not tgt_idx:
                continue
            for src_eid in src_idx.intersection(src_idx.bounds, objects=False):
                src_bbox = src_idx.bounds(src_eid)
                hits = list(tgt_idx.intersection(src_bbox, objects=False))
                for tgt_eid in hits[:500]:
                    se = self._entity_map.get(src_eid)
                    te = self._entity_map.get(tgt_eid)
                    if se and te and se.drawing_name != te.drawing_name:
                        candidates.append((se, te))
        return candidates

    def get_entities(self, floor_id: float, discipline: str) -> List[SpatialEntity]:
        key = (floor_id, discipline)
        idx = self.floor_discipline_idx.get(key)
        if not idx:
            return []
        return [self._entity_map[eid] for eid in idx.intersection(idx.bounds, objects=False)]

    def query_bbox_overlap(self, floor_id: float, disc_a: str, disc_b: str) -> List[Tuple[SpatialEntity, SpatialEntity]]:
        candidates = []
        idx_a = self.floor_discipline_idx.get((floor_id, disc_a))
        idx_b = self.floor_discipline_idx.get((floor_id, disc_b))
        if not idx_a or not idx_b:
            return candidates
        seen = set()
        for eid_a in idx_a.intersection(idx_a.bounds, objects=False):
            ent_a = self._entity_map.get(eid_a)
            if not ent_a:
                continue
            for eid_b in idx_b.intersection((ent_a.x_min, ent_a.y_min, ent_a.x_max, ent_a.y_max), objects=False):
                if eid_a == eid_b:
                    continue
                ent_b = self._entity_map.get(eid_b)
                if not ent_b or ent_a.drawing_name == ent_b.drawing_name:
                    continue
                pair_key = (min(eid_a, eid_b), max(eid_a, eid_b))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                candidates.append((ent_a, ent_b))
        return candidates


class ConflictDeduplicator:
    """DBSCAN空间聚类：实体对冲突 → 物理冲突簇"""
    def __init__(self, spatial_tolerance: float = 500.0):
        self.tol = spatial_tolerance

    def deduplicate(self, conflicts: List[Dict]) -> List[Dict]:
        if not conflicts:
            return []
        groups = defaultdict(list)
        for c in conflicts:
            key = (c.get("type", ""), c.get("floor"))
            groups[key].append(c)

        clusters = []
        for (ctype, floor), group in groups.items():
            if len(group) <= 1:
                clusters.extend(group)
                continue
            pts = []
            valid = []
            for g in group:
                desc = g.get("description", "")
                parts = desc.split("区域")
                if len(parts) >= 2:
                    rest = parts[1]
                else:
                    rest = desc
                xs = re.findall(r"(\d+)mm", rest)
                if len(xs) >= 2:
                    pts.append([float(xs[0]), float(xs[1])])
                else:
                    idx = desc.find("区域")
                    region_text = desc[idx+2:].strip() if idx > 0 else desc
                    h = int(hashlib.md5(region_text.encode()).hexdigest(), 16) % 10000
                    pts.append([float(h), 0.0])
                valid.append(g)
            if len(pts) < 2:
                clusters.extend(group)
                continue
            arr = np.array(pts)
            clusterer = DBSCAN(eps=self.tol, min_samples=1).fit(arr)
            for label in set(clusterer.labels_):
                mask = clusterer.labels_ == label
                cluster_confs = [valid[i] for i in range(len(valid)) if mask[i]]
                if not cluster_confs:
                    continue
                representative = dict(cluster_confs[0])
                if len(cluster_confs) > 1:
                    drawings = set()
                    for cc in cluster_confs:
                        for part in cc.get("involved", "").split("|"):
                            drawings.add(part.strip())
                    representative["involved"] = " | ".join(sorted(drawings)[:4])
                    representative["description"] = (
                        representative["description"].split("区域")[0]
                        + f"区域({len(cluster_confs)}个相邻冲突聚合)"
                    )
                    representative["duplicate_count"] = len(cluster_confs)
                clusters.append(representative)
        return clusters


class SpatialAnalyzer:

    def __init__(self, dxf_dir: str):
        self.dxf_dir = dxf_dir
        self.entities: List[SpatialEntity] = []
        self.floor_labels: List[FloorLabel] = []
        self.elevation_tags: List[ElevationTag] = []
        self.drawings: Dict[str, str] = {}
        self.spatial_index: Optional[SpatialIndex] = None
        self._cache_dir = os.path.realpath(
            os.path.join(os.path.dirname(dxf_dir) if dxf_dir else ".", ".dxf_cache")
        )
        os.makedirs(self._cache_dir, exist_ok=True)
        logging.basicConfig(
            filename=os.path.join(self._cache_dir, "error.log"),
            level=logging.WARNING,
            format="%(asctime)s [%(levelname)s] %(message)s"
        )
        self._logger = logging.getLogger("SpatialAnalyzer")

    @property
    def cache_dir(self) -> str:
        """公开的缓存目录路径。"""
        return self._cache_dir

    def _classify_entity(self, et: str, dxf_entity, discipline: str, name: str) -> Optional[SpatialEntity]:
        layer = dxf_entity.dxf.layer if hasattr(dxf_entity.dxf, 'layer') else ""
        layer_lower = layer.lower()

        if et == "LINE":
            x1, y1 = dxf_entity.dxf.start[0], dxf_entity.dxf.start[1]
            x2, y2 = dxf_entity.dxf.end[0], dxf_entity.dxf.end[1]
            if abs(x2-x1) < 5 and abs(y2-y1) < 5:
                return None
            length = np.sqrt((x2-x1)**2 + (y2-y1)**2)

            etype = None
            if any(k in layer_lower for k in ('airduct', '风管', '送风', '排风', '排烟', '回风', '新风', '空调', 'vent', 'exhaust', 'cuch-air')):
                etype = "duct"
            elif any(k in layer_lower for k in ('pipe', '管', 'water', '给水', '排水', '消防', '喷淋', '雨水', '污水', '冷', '热', '废水', 'cuch-pipe')):
                etype = "pipe"
            elif any(k in layer_lower for k in ('beam', '梁', 'beam_', '梁_')):
                if not any(k in layer_lower for k in ('pipe', '管', 'duct', '风管', 'cable', '标注', 'dim', 'text')):
                    etype = "beam"
            if etype is None and any(k in layer_lower for k in ('column', '柱', 'col_', '柱_')):
                etype = "column"
            if etype is None and any(k in layer_lower for k in ('wall', '墙', 'wall_', '墙_')):
                etype = "wall"
            if etype is None:
                if discipline == "building":
                    etype = "wall" if length > 2000 else "line"
                elif discipline == "plumbing":
                    etype = "pipe" if length > 300 else "line"
                elif discipline == "hvac":
                    etype = "duct" if length > 300 else "line"
                elif discipline == "structure":
                    etype = "beam" if length > 500 else "structure_member"
                elif discipline == "electrical":
                    etype = "line"
                else:
                    etype = "beam" if length > 2000 else "line"
            return SpatialEntity(
                entity_type=etype, discipline=discipline, drawing_name=name, layer=layer,
                x_min=min(x1, x2), y_min=min(y1, y2), x_max=max(x1, x2), y_max=max(y1, y2))

        elif et == "LWPOLYLINE":
            pts = list(dxf_entity.get_points())
            if len(pts) < 2:
                return None
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)

            if any(k in layer_lower for k in ('airduct', '风管', '送风', '排风', '排烟', '回风', '新风', 'cuch-air')):
                return SpatialEntity(entity_type="duct", discipline=discipline, drawing_name=name, layer=layer,
                                     x_min=min(xs), y_min=min(ys), x_max=max(xs), y_max=max(ys))
            if any(k in layer_lower for k in ('pipe', '管', 'water', '给水', '排水', '消防', '喷淋', '雨水', '污水', 'cuch-pipe')):
                return SpatialEntity(entity_type="pipe", discipline=discipline, drawing_name=name, layer=layer,
                                     x_min=min(xs), y_min=min(ys), x_max=max(xs), y_max=max(ys))
            if w < 2000 and h < 2000 and w > 50 and h > 50:
                return SpatialEntity(entity_type="column", discipline=discipline, drawing_name=name, layer=layer,
                                     x_min=min(xs), y_min=min(ys), x_max=max(xs), y_max=max(ys))
            return SpatialEntity(
                entity_type="wall" if discipline == "building" else "structure_member",
                discipline=discipline, drawing_name=name, layer=layer,
                x_min=min(xs), y_min=min(ys), x_max=max(xs), y_max=max(ys))

        elif et == "TEXT" or et == "MTEXT":
            try:
                txt = dxf_entity.plain_text() if hasattr(dxf_entity, 'plain_text') else (
                    dxf_entity.dxf.text if et == "TEXT" else dxf_entity.text)
            except Exception:
                txt = dxf_entity.dxf.text if et == "TEXT" else ""
            if not txt or not txt.strip():
                return None
            ip = dxf_entity.dxf.insert
            return SpatialEntity(entity_type="text", discipline=discipline, drawing_name=name,
                                 x_min=ip[0], y_min=ip[1], x_max=ip[0], y_max=ip[1],
                                 text_content=txt.strip()[:200])

        elif et == "CIRCLE":
            cx, cy, r = dxf_entity.dxf.center[0], dxf_entity.dxf.center[1], dxf_entity.dxf.radius
            if r < 10 or r > 5000:
                return None
            if any(k in layer_lower for k in ('pipe', '管', 'duct', '风管', 'water')):
                return SpatialEntity(entity_type="pipe", discipline=discipline, drawing_name=name,
                                     x_min=cx-r, y_min=cy-r, x_max=cx+r, y_max=cy+r)
            return SpatialEntity(entity_type="column" if r < 600 else "opening",
                                 discipline=discipline, drawing_name=name,
                                 x_min=cx-r, y_min=cy-r, x_max=cx+r, y_max=cy+r)

        elif et == "ARC":
            cx, cy, r = dxf_entity.dxf.center[0], dxf_entity.dxf.center[1], dxf_entity.dxf.radius
            return SpatialEntity(entity_type="arc", discipline=discipline, drawing_name=name, layer=layer,
                                 x_min=cx-r, y_min=cy-r, x_max=cx+r, y_max=cy+r)

        return None

    def extract_from_dxf(self, dxf_path: str, discipline: str):
        name = os.path.basename(dxf_path).replace(".dxf", "")
        try:
            doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
        except Exception as e:
            self._logger.error(f"DXF读取失败: {dxf_path}\n{traceback.format_exc()}")
            return

        self.drawings[name] = discipline

        for e in msp:
            try:
                et = e.dxftype()

                if et in ("TEXT", "MTEXT"):
                    try:
                        txt = e.plain_text() if hasattr(e, 'plain_text') else (
                            e.dxf.text if et == "TEXT" else e.text)
                    except Exception:
                        txt = ""
                    if not txt or not txt.strip():
                        continue
                    txt = txt.strip()

                    floor = parse_floor(txt)
                    if floor is not None:
                        ip = e.dxf.insert
                        self.floor_labels.append(FloorLabel(
                            x=ip[0], y=ip[1], floor=floor, text=txt[:60], drawing_name=name))

                    elev = parse_elevation(txt)
                    if elev is not None:
                        ip = e.dxf.insert
                        self.elevation_tags.append(ElevationTag(
                            x=ip[0], y=ip[1], elevation=elev, text=txt[:60], drawing_name=name))

                entity = self._classify_entity(et, e, discipline, name)
                if entity:
                    self.entities.append(entity)
            except Exception as exc:
                self._logger.warning(f"实体处理异常: {name} type={e.dxftype() if hasattr(e,'dxftype') else '?'} err={exc}")

    def extract_all(self):
        dxfs = sorted(glob.glob(os.path.join(self.dxf_dir, "*.dxf")), key=os.path.getsize)

        from v7.preprocessor.drawing_extractor import DrawingExtractor
        ext = DrawingExtractor()

        HVAC_PREFIXES = {"h-", "h_", "nt-", "nt_", "暖通", "hvac", "air", "duct", "xr-a", "xr_"}
        STRUCT_PREFIXES = {"s-", "s_", "结施", "结构", "基础", "配筋", "桩基", "预制", "埋件", "g-", "g_"}
        PLUMB_PREFIXES = {"水施", "给排水", "给水", "排水", "消火栓", "喷淋", "ss-", "ss_", "p-", "p_"}
        ELEC_PREFIXES = {"电施", "电气", "配电", "照明", "防雷", "弱电", "变配电", "ds-", "ds_", "e-", "e_"}

        def classify_enhanced(name):
            name_lower = name.lower()
            if any(k in name_lower for k in HVAC_PREFIXES):
                return "hvac"
            if any(k in name_lower for k in STRUCT_PREFIXES):
                return "structure"
            if any(k in name_lower for k in PLUMB_PREFIXES):
                return "plumbing"
            if any(k in name_lower for k in ELEC_PREFIXES):
                return "electrical"
            disc = ext.classify(name)
            if disc == "unknown":
                disc = "building"
            return disc

        for dxf in dxfs:
            name = os.path.basename(dxf)
            file_mb = os.path.getsize(dxf) / 1e6
            if file_mb > 150:
                self._logger.info(f"跳过(>150MB): {name[:50]} ({file_mb:.1f}MB)")
                continue

            fingerprint = hashlib.md5(f"{os.path.getmtime(dxf)}:{os.path.getsize(dxf)}:{dxf}".encode()).hexdigest()[:16]
            cache_file = os.path.join(self._cache_dir, f"{fingerprint}.json")
            cached = False
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r", encoding="utf-8") as cf:
                        cache_data = json.load(cf)
                    for e_data in cache_data.get("entities", []):
                        self.entities.append(SpatialEntity(**e_data))
                    for fl_data in cache_data.get("floor_labels", []):
                        self.floor_labels.append(FloorLabel(**fl_data))
                    for et_data in cache_data.get("elevation_tags", []):
                        self.elevation_tags.append(ElevationTag(**et_data))
                    cached = True
                except Exception as e:
                    self._logger.warning(f"缓存加载失败: {cache_file} err={e}")

            if not cached:
                discipline = classify_enhanced(name)
                before = len(self.entities)
                before_fl = len(self.floor_labels)
                before_et = len(self.elevation_tags)
                self.extract_from_dxf(dxf, discipline)
                cache_data = {
                    "entities": [{"entity_type": e.entity_type, "discipline": e.discipline,
                                  "drawing_name": e.drawing_name, "layer": e.layer,
                                  "x_min": e.x_min, "y_min": e.y_min, "x_max": e.x_max,
                                  "y_max": e.y_max, "floor_level": e.floor_level,
                                  "z_bottom": e.z_bottom, "z_top": e.z_top,
                                  "text_content": e.text_content}
                                 for e in self.entities[before:]],
                    "floor_labels": [{"x": fl.x, "y": fl.y, "floor": fl.floor, "text": fl.text,
                                      "drawing_name": fl.drawing_name} for fl in self.floor_labels[before_fl:]],
                    "elevation_tags": [{"x": et.x, "y": et.y, "elevation": et.elevation,
                                        "text": et.text, "drawing_name": et.drawing_name}
                                       for et in self.elevation_tags[before_et:]]
                }
                os.makedirs(self._cache_dir, exist_ok=True)
                try:
                    with open(cache_file, "w", encoding="utf-8") as cf:
                        json.dump(cache_data, cf, ensure_ascii=False, indent=2)
                except Exception as e:
                    self._logger.warning(f"缓存保存失败: {cache_file} err={e}")
        self._assign_floor_levels()

        self.spatial_index = SpatialIndex()
        self.spatial_index.build(self.entities)

        return len(self.entities)

    def _assign_floor_levels(self):
        """将空间实体与楼层标签关联，推断Z轴信息（KDTree加速+跳过text实体）"""
        if not self.floor_labels:
            for e in self.entities:
                e.floor_level = 0
            return

        from scipy.spatial import KDTree

        floor_by_dwg = {}
        for fl in self.floor_labels:
            floor_by_dwg.setdefault(fl.drawing_name, []).append(fl)
        floor_kdt = {}
        for dwg, labels in floor_by_dwg.items():
            pts = np.array([[fl.x, fl.y] for fl in labels])
            floor_kdt[dwg] = (KDTree(pts), labels)

        global_pts = np.array([[fl.x, fl.y] for fl in self.floor_labels])
        global_kdt = KDTree(global_pts)

        elev_by_dwg = {}
        for et in self.elevation_tags:
            elev_by_dwg.setdefault(et.drawing_name, []).append(et)
        elev_kdt = {}
        for dwg, tags in elev_by_dwg.items():
            pts = np.array([[et.x, et.y] for et in tags])
            elev_kdt[dwg] = (KDTree(pts), tags)

        assigned = 0
        no_floor = 0
        skipped_text = 0

        pts_batch = []
        entities_batch = []
        for e in self.entities:
            if e.entity_type == "text":
                skipped_text += 1
                continue
            pts_batch.append([(e.x_min + e.x_max) / 2, (e.y_min + e.y_max) / 2])
            entities_batch.append(e)

        pts_arr = np.array(pts_batch)
        for i, e in enumerate(entities_batch):
            cx, cy = pts_arr[i][0], pts_arr[i][1]
            pt = np.array([[cx, cy]])

            kdt_info = floor_kdt.get(e.drawing_name)
            if kdt_info:
                kdt, labels = kdt_info
                dist, idx = kdt.query(pt, k=1)
                nearest_floor = labels[idx[0]].floor
                d = float(dist[0])
            else:
                dist, idx = global_kdt.query(pt, k=1)
                nearest_floor = self.floor_labels[idx[0]].floor
                d = float(dist[0])

            if d < 50000:
                e.floor_level = nearest_floor
                assigned += 1
            else:
                e.floor_level = 0
                no_floor += 1

            kdt_info2 = elev_kdt.get(e.drawing_name)
            if kdt_info2:
                kdt2, tags2 = kdt_info2
                elev_dist, elev_idx = kdt2.query(pt, k=1)
                if float(elev_dist[0]) < 10000:
                    e.z_bottom = tags2[elev_idx[0]].elevation * 1000
                    e.z_top = e.z_bottom + 500

        if assigned > 0 or skipped_text > 0:
            self._logger.info(f"楼层关联: {assigned}个实体已分配楼层, {no_floor}个未分配, {skipped_text}个text已跳过")

    def _same_floor(self, e1: SpatialEntity, e2: SpatialEntity) -> bool:
        if e1.floor_level is None or e2.floor_level is None:
            return True
        return abs(e1.floor_level - e2.floor_level) < 0.5

    def find_cross_floor_conflicts(self) -> List[Dict]:
        if self.spatial_index is None:
            self.spatial_index = SpatialIndex()
            self.spatial_index.build(self.entities)

        conflicts = []
        si = self.spatial_index

        all_floors = set()
        discs_by_floor = {}
        for e in self.entities:
            fl = e.floor_level or 0
            all_floors.add(fl)
            discs_by_floor.setdefault(fl, set()).add(e.discipline)

        n_floors = len(all_floors)
        for fi, fl_id in enumerate(sorted(all_floors)):
            discs = discs_by_floor.get(fl_id, set())
            has_struct = "structure" in discs or "building" in discs
            has_hvac = "hvac" in discs
            has_plumbing = "plumbing" in discs

            if has_struct and has_hvac:
                conflicts.extend(self._detect_beam_duct_rtree(si, fl_id))
                conflicts.extend(self._detect_column_pipe_rtree(si, fl_id))
                conflicts.extend(self._detect_duct_wall_rtree(si, fl_id))
            if has_struct and has_plumbing:
                conflicts.extend(self._detect_beam_pipe_rtree(si, fl_id))
            if has_hvac and has_plumbing:
                conflicts.extend(self._detect_pipe_crossing_rtree(si, fl_id))

        if si:
            walls = si.get_entities_by_type("wall")
            columns = si.get_entities_by_type("column")
        else:
            walls = [e for e in self.entities if e.entity_type == "wall"]
            columns = [e for e in self.entities if e.entity_type == "column"]
        if walls:
            conflicts.extend(self._analyze_egress_width(walls, columns))

        return conflicts

    def _detect_beam_duct_rtree(self, si: SpatialIndex, fl_id: float) -> List[Dict]:
        conflicts = []
        beam_keys = [(fl_id, d) for d in ("structure", "building")]
        pairs = []
        for key in beam_keys:
            pairs.extend(si.query_bbox_overlap(fl_id, key[1], "hvac"))
        if not pairs:
            pairs.extend(si.query_bbox_overlap(fl_id, "structure", "building"))
        seen = set()
        for b, d in pairs:
            if b.entity_type not in ("beam", "structure_member") or d.entity_type != "duct":
                continue
            if b.drawing_name == d.drawing_name:
                continue
            xo = max(0, min(b.x_max, d.x_max) - max(b.x_min, d.x_min))
            yo = max(0, min(b.y_max, d.y_max) - max(b.y_min, d.y_min))
            if xo < 300 or yo < 300:
                continue
            key = (b.drawing_name, d.drawing_name, int((b.x_min+b.x_max)/2/1000), int((b.y_min+b.y_max)/2/1000))
            if key in seen:
                continue
            seen.add(key)
            cx = (max(b.x_min, d.x_min) + min(b.x_max, d.x_max)) / 2
            cy = (max(b.y_min, d.y_min) + min(b.y_max, d.y_max)) / 2
            axis = self._coord_to_axis(cx, cy)
            fl_info = f"，位于{floor_label(b.floor_level)}区域" if b.floor_level and b.floor_level > 0 else ""
            conflicts.append({
                "type": "beam_duct_overlap", "severity": "B",
                "description": f"结构梁（来自{b.drawing_name[:25]}）与风管（来自{d.drawing_name[:25]}）在{axis}区域存在{int(xo)}mm×{int(yo)}mm平面投影叠合{fl_info}",
                "risk": "梁与风管平面叠合，若需穿梁则破坏结构承载力。需结构专业确认梁预留洞位置及补强方案，或调整风管路由",
                "involved": f"结构梁图:{b.drawing_name[:30]} | 风管图:{d.drawing_name[:30]}",
                "std": "GB50010-2010 9.2.14（梁开洞限制）；GB51251-2017 4.4.8（排烟风管耐火要求）",
                "floor": b.floor_level
            })
        return conflicts

    def _detect_beam_pipe_rtree(self, si: SpatialIndex, fl_id: float) -> List[Dict]:
        conflicts = []
        pairs = si.query_bbox_overlap(fl_id, "structure", "plumbing")
        seen = set()
        for b, p in pairs:
            if b.entity_type not in ("beam", "structure_member") or p.entity_type != "pipe":
                continue
            xo = max(0, min(b.x_max, p.x_max) - max(b.x_min, p.x_min))
            yo = max(0, min(b.y_max, p.y_max) - max(b.y_min, p.y_min))
            if xo < 200 or yo < 200:
                continue
            key = (b.drawing_name, p.drawing_name, int((b.x_min+b.x_max)/2/1000), int((b.y_min+b.y_max)/2/1000))
            if key in seen:
                continue
            seen.add(key)
            cx = (max(b.x_min, p.x_min) + min(b.x_max, p.x_max)) / 2
            cy = (max(b.y_min, p.y_min) + min(b.y_max, p.y_max)) / 2
            axis = self._coord_to_axis(cx, cy)
            fl_info = f"，位于{floor_label(b.floor_level)}区域" if b.floor_level and b.floor_level > 0 else ""
            conflicts.append({
                "type": "beam_pipe_overlap", "severity": "B",
                "description": f"结构梁（来自{b.drawing_name[:25]}）与给排水管线（来自{p.drawing_name[:25]}）在{axis}区域存在{int(xo)}mm×{int(yo)}mm平面叠合{fl_info}",
                "risk": "管线与梁平面叠合，需确认标高关系，避免管线穿梁",
                "involved": f"梁图:{b.drawing_name[:30]} | 管线图:{p.drawing_name[:30]}",
                "std": "GB50010-2010 9.2.14（梁开洞限制）",
                "floor": b.floor_level
            })
        return conflicts

    def _detect_column_pipe_rtree(self, si: SpatialIndex, fl_id: float) -> List[Dict]:
        conflicts = []
        for disc in ("hvac", "plumbing"):
            pairs = si.query_bbox_overlap(fl_id, "building", disc)
            seen = set()
            for c, dp in pairs:
                if c.entity_type != "column":
                    continue
                if dp.entity_type not in ("duct", "pipe"):
                    continue
                xo = max(0, min(c.x_max, dp.x_max) - max(c.x_min, dp.x_min))
                yo = max(0, min(c.y_max, dp.y_max) - max(c.y_min, dp.y_min))
                if xo < 100 or yo < 100:
                    continue
                key = (c.drawing_name, dp.drawing_name, int((c.x_min+c.x_max)/2/500), int((c.y_min+c.y_max)/2/500))
                if key in seen:
                    continue
                seen.add(key)
                cx = (c.x_min + c.x_max) / 2
                cy = (c.y_min + c.y_max) / 2
                axis = self._coord_to_axis(cx, cy)
                dp_type = "风管" if dp.entity_type == "duct" else "管线"
                conflicts.append({
                    "type": "column_pipe_conflict", "severity": "B",
                    "description": f"柱（来自{c.drawing_name[:25]}）与{dp_type}（来自{dp.drawing_name[:25]}）在{axis}区域存在穿越",
                    "risk": "管线穿越柱子将破坏结构，需重新规划管线路径或柱预留套管",
                    "involved": f"柱图:{c.drawing_name[:30]} | {dp_type}图:{dp.drawing_name[:30]}",
                    "std": "GB50010-2010 6.4.12（柱开洞限制）",
                    "floor": c.floor_level
                })
        return conflicts

    def _detect_pipe_crossing_rtree(self, si: SpatialIndex, fl_id: float) -> List[Dict]:
        conflicts = []
        pairs = si.query_bbox_overlap(fl_id, "hvac", "plumbing")
        seen = set()
        for duct, pipe in pairs:
            if duct.entity_type != "duct" or pipe.entity_type != "pipe":
                continue
            xo = max(0, min(duct.x_max, pipe.x_max) - max(duct.x_min, pipe.x_min))
            yo = max(0, min(duct.y_max, pipe.y_max) - max(duct.y_min, pipe.y_min))
            if xo < 200 or yo < 200:
                continue
            key = (duct.drawing_name, pipe.drawing_name, int((duct.x_min+duct.x_max)/2/1000), int((duct.y_min+duct.y_max)/2/1000))
            if key in seen:
                continue
            seen.add(key)
            cx = (max(duct.x_min, pipe.x_min) + min(duct.x_max, pipe.x_max)) / 2
            cy = (max(duct.y_min, pipe.y_min) + min(duct.y_max, pipe.y_max)) / 2
            axis = self._coord_to_axis(cx, cy)
            fl_info = f"，{floor_label(duct.floor_level)}" if duct.floor_level is not None else ""
            conflicts.append({
                "type": "pipe_crossing", "severity": "B",
                "description": f"风管（来自{duct.drawing_name[:25]}）与给排水管线（来自{pipe.drawing_name[:25]}）在{axis}区域{fl_info}存在交叉",
                "risk": "风管与给排水管交叉需协调标高，风管优先在上方，排水管需保证坡度",
                "involved": f"风管图:{duct.drawing_name[:30]} | 给排水图:{pipe.drawing_name[:30]}",
                "std": "GB50015-2019 4.4.2（排水管坡度）；GB50242-2002 3.3.3（管线综合排布）",
                "floor": duct.floor_level
            })
        return conflicts

    def _detect_duct_wall_rtree(self, si: SpatialIndex, fl_id: float) -> List[Dict]:
        conflicts = []
        pairs = si.query_bbox_overlap(fl_id, "building", "hvac")
        seen = set()
        for w, d in pairs:
            if w.entity_type != "wall" or d.entity_type != "duct":
                continue
            xo = max(0, min(w.x_max, d.x_max) - max(w.x_min, d.x_min))
            yo = max(0, min(w.y_max, d.y_max) - max(w.y_min, d.y_min))
            if xo < 200 or yo < 200:
                continue
            key = (w.drawing_name, d.drawing_name, int((w.x_min+w.x_max)/2/1000), int((w.y_min+w.y_max)/2/1000))
            if key in seen:
                continue
            seen.add(key)
            cx = (max(w.x_min, d.x_min) + min(w.x_max, d.x_max)) / 2
            cy = (max(w.y_min, d.y_min) + min(w.y_max, d.y_max)) / 2
            axis = self._coord_to_axis(cx, cy)
            fl_info = f"，{floor_label(w.floor_level)}" if w.floor_level is not None else ""
            conflicts.append({
                "type": "duct_through_wall", "severity": "B",
                "description": f"风管/管线（来自{d.drawing_name[:25]}）与墙体（来自{w.drawing_name[:25]}）在{axis}区域{fl_info}存在穿墙交叉",
                "risk": "风管穿墙需预留套管并做防火封堵，未预留将导致后期开洞破坏墙体",
                "involved": f"墙体:{w.drawing_name[:30]} | 风管:{d.drawing_name[:30]}",
                "std": "GB50016-2014 6.3.5（防火封堵）；GB50243-2016 6.2.7（风管穿墙要求）",
                "floor": w.floor_level
            })
        return conflicts

    def _detect_beam_duct_overlap(self, beams, ducts_or_pipes, label="duct") -> List[Dict]:
        conflicts = []
        entity_label = "风管" if label == "duct" else "给排水管线"
        entity_label2 = "排烟风管" if label == "duct" else "管线"

        overlap_count = 0
        for b in beams[:300]:
            for d in ducts_or_pipes[:500]:
                if b.drawing_name == d.drawing_name:
                    continue
                if not self._same_floor(b, d):
                    continue

                x_overlap = max(0, min(b.x_max, d.x_max) - max(b.x_min, d.x_min))
                y_overlap = max(0, min(b.y_max, d.y_max) - max(b.y_min, d.y_min))

                if x_overlap > 300 and y_overlap > 300:
                    overlap_count += 1
                    if overlap_count <= 8:
                        cx = (max(b.x_min, d.x_min) + min(b.x_max, d.x_max)) / 2
                        cy = (max(b.y_min, d.y_min) + min(b.y_max, d.y_max)) / 2
                        axis = self._coord_to_axis(cx, cy)
                        floor_info = ""
                        if b.floor_level is not None and b.floor_level > 0:
                            floor_info = f"，位于{floor_label(b.floor_level)}区域"
                        conflicts.append({
                            "type": "beam_duct_overlap",
                            "severity": "A",
                            "description": f"结构梁（来自{b.drawing_name[:25]}）与{entity_label}（来自{d.drawing_name[:25]}）在{axis}区域存在{int(x_overlap)}mm×{int(y_overlap)}mm平面投影叠合{floor_info}",
                            "risk": f"梁与{entity_label2}平面叠合，若需穿梁则破坏结构承载力。需结构专业确认梁预留洞位置及补强方案，或调整{entity_label}路由",
                            "involved": f"结构梁图:{b.drawing_name[:30]} | {entity_label}图:{d.drawing_name[:30]}",
                            "std": "GB50010-2010 9.2.14（梁开洞限制）；GB51251-2017 4.4.8（排烟风管耐火要求）",
                            "floor": b.floor_level
                        })
        if overlap_count > 0:
            self._logger.info(f"梁-{entity_label}叠合: {overlap_count}个（已过滤跨楼层假冲突）")
        return conflicts

    def _detect_duct_through_wall(self, ducts, walls) -> List[Dict]:
        conflicts = []
        count = 0
        for w in walls[:300]:
            for d in ducts[:500]:
                if w.drawing_name == d.drawing_name:
                    continue
                if not self._same_floor(w, d):
                    continue

                x_overlap = max(0, min(w.x_max, d.x_max) - max(w.x_min, d.x_min))
                y_overlap = max(0, min(w.y_max, d.y_max) - max(w.y_min, d.y_min))

                if x_overlap > 200 and y_overlap > 200:
                    count += 1
                    if count <= 5:
                        cx = (max(w.x_min, d.x_min) + min(w.x_max, d.x_max)) / 2
                        cy = (max(w.y_min, d.y_min) + min(w.y_max, d.y_max)) / 2
                        axis = self._coord_to_axis(cx, cy)
                        floor_info = ""
                        if w.floor_level is not None:
                            floor_info = f"，{floor_label(w.floor_level)}"
                        conflicts.append({
                            "type": "duct_through_wall",
                            "severity": "B",
                            "description": f"风管/管线（来自{d.drawing_name[:25]}）与墙体（来自{w.drawing_name[:25]}）在{axis}区域{floor_info}存在穿墙交叉",
                            "risk": "风管穿墙需预留套管并做防火封堵，未预留将导致后期开洞破坏墙体",
                            "involved": f"墙体:{w.drawing_name[:30]} | 风管:{d.drawing_name[:30]}",
                            "std": "GB50016-2014 6.3.5（防火封堵）；GB50243-2016 6.2.7（风管穿墙要求）",
                            "floor": w.floor_level
                        })
        if count > 0:
            self._logger.info(f"风管穿墙: {count}个（已过滤跨楼层假冲突）")
        return conflicts

    def _detect_column_pipe_conflict(self, columns, ducts_or_pipes) -> List[Dict]:
        conflicts = []
        count = 0
        for col in columns[:300]:
            for dp in ducts_or_pipes[:500]:
                if col.drawing_name == dp.drawing_name:
                    continue
                if not self._same_floor(col, dp):
                    continue

                x_overlap = max(0, min(col.x_max, dp.x_max) - max(col.x_min, dp.x_min))
                y_overlap = max(0, min(col.y_max, dp.y_max) - max(col.y_min, dp.y_min))

                if x_overlap > 100 and y_overlap > 100:
                    count += 1
                    if count <= 5:
                        cx = (col.x_min + col.x_max) / 2
                        cy = (col.y_min + col.y_max) / 2
                        axis = self._coord_to_axis(cx, cy)
                        dp_type = "风管" if dp.entity_type == "duct" else "管线"
                        conflicts.append({
                            "type": "column_pipe_conflict",
                            "severity": "B",
                            "description": f"柱（来自{col.drawing_name[:25]}）与{dp_type}（来自{dp.drawing_name[:25]}）在{axis}区域存在穿越",
                            "risk": "管线穿越柱子将破坏结构，需重新规划管线路径或柱预留套管",
                            "involved": f"柱图:{col.drawing_name[:30]} | {dp_type}图:{dp.drawing_name[:30]}",
                            "std": "GB50010-2010 6.4.12（柱开洞限制）",
                            "floor": col.floor_level
                        })
        if count > 0:
            self._logger.info(f"柱-管线穿越: {count}个")
        return conflicts

    def _detect_pipe_crossing(self, ducts, pipes) -> List[Dict]:
        conflicts = []
        count = 0
        for duct in ducts[:300]:
            for pipe in pipes[:300]:
                if duct.drawing_name == pipe.drawing_name:
                    continue
                if not self._same_floor(duct, pipe):
                    continue

                x_overlap = max(0, min(duct.x_max, pipe.x_max) - max(duct.x_min, pipe.x_min))
                y_overlap = max(0, min(duct.y_max, pipe.y_max) - max(duct.y_min, pipe.y_min))

                if x_overlap > 200 and y_overlap > 200:
                    count += 1
                    if count <= 5:
                        cx = (max(duct.x_min, pipe.x_min) + min(duct.x_max, pipe.x_max)) / 2
                        cy = (max(duct.y_min, pipe.y_min) + min(duct.y_max, pipe.y_max)) / 2
                        axis = self._coord_to_axis(cx, cy)
                        floor_info = ""
                        if duct.floor_level is not None:
                            floor_info = f"，{floor_label(duct.floor_level)}"
                        conflicts.append({
                            "type": "pipe_crossing",
                            "severity": "B",
                            "description": f"风管（来自{duct.drawing_name[:25]}）与给排水管线（来自{pipe.drawing_name[:25]}）在{axis}区域{floor_info}存在交叉",
                            "risk": "风管与给排水管交叉需协调标高，风管优先在上方，排水管需保证坡度",
                            "involved": f"风管图:{duct.drawing_name[:30]} | 给排水图:{pipe.drawing_name[:30]}",
                            "std": "GB50015-2019 4.4.2（排水管坡度）；GB50242-2002 3.3.3（管线综合排布）",
                            "floor": duct.floor_level
                        })
        if count > 0:
            print(f"  风管-管线交叉: {count}个")
        return conflicts

    def _analyze_egress_width(self, walls, columns) -> List[Dict]:
        conflicts = []
        corridors = []
        for w in walls:
            dx = w.x_max - w.x_min
            dy = w.y_max - w.y_min
            if dx > 3000 and dy < 300:
                corridors.append(w)
            elif dy > 3000 and dx < 300:
                corridors.append(w)

        by_dwg = {}
        for c in corridors:
            by_dwg.setdefault(c.drawing_name, []).append(c)

        seen = set()
        for dwg_name, items in by_dwg.items():
            buckets = {}
            for w in items:
                cy_bucket = int((w.y_min + w.y_max) / 2 / 3000)
                buckets.setdefault(cy_bucket, []).append(w)

            for bucket_walls in buckets.values():
                n = len(bucket_walls)
                if n < 2:
                    continue
                for i in range(n):
                    for j in range(i + 1, n):
                        c1, c2 = bucket_walls[i], bucket_walls[j]
                        if c1.x_min < c2.x_min:
                            wa, wb = c1, c2
                        else:
                            wa, wb = c2, c1

                        dx = wb.x_min - wa.x_max
                        dy = abs(wa.y_min - wb.y_min)
                        wa_len = wa.x_max - wa.x_min
                        wb_len = wb.x_max - wb.x_min
                        if dx >= 1100 and dx <= 4400 and dy < 300 and wa_len >= 2000 and wb_len >= 2000:
                            cx = int((wa.x_max + wb.x_min) / 2 / 500)
                            cy_key = int((wa.y_min + wa.y_max) / 2 / 500)
                            dedup_key = (dwg_name, cx, cy_key)
                            if dedup_key in seen:
                                continue
                            seen.add(dedup_key)
                            conflicts.append({
                                "type": "egress_width",
                                "severity": "B",
                                "description": f"走廊墙间距{int(dx)}mm，折算净宽约{int(dx-100)}mm",
                                "risk": "疏散走道净宽不足，影响人员疏散时间，需复核消防疏散宽度要求",
                                "involved": f"{wa.drawing_name[:30]}",
                                "std": "GB50016-2014 5.5.18（疏散走道净宽）",
                                "floor": wa.floor_level
                            })

        return conflicts

    def _coord_to_axis(self, x, y):
        ax_idx = int((x - 5000) / 8000)
        ax = chr(65 + ax_idx) if 0 <= ax_idx <= 25 else '?'
        ay_idx = int((y - 5000) / 8000)
        ay = chr(65 + ay_idx) if 0 <= ay_idx <= 25 else '?'
        return f"{ax}{ay}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="空间分析工具")
    parser.add_argument("dxf_dir", nargs="?", default=".", help="DXF文件目录")
    args = parser.parse_args()
    analyzer = SpatialAnalyzer(args.dxf_dir)
    total = analyzer.extract_all()

    print(f"\n总实体: {total}")
    print(f"楼层标签: {len(analyzer.floor_labels)}")
    print(f"标高标注: {len(analyzer.elevation_tags)}")

    type_counts = defaultdict(int)
    disc_counts = defaultdict(int)
    floor_counts = defaultdict(int)
    for e in analyzer.entities:
        type_counts[e.entity_type] += 1
        disc_counts[e.discipline] += 1
        floor_counts[e.floor_level] += 1

    print(f"按类型: {dict(type_counts)}")
    print(f"按专业: {dict(disc_counts)}")
    print(f"按楼层: {dict(sorted(floor_counts.items()))}")

    print(f"\n提取的楼层标签(前20):")
    for fl in analyzer.floor_labels[:20]:
        print(f"  [{fl.drawing_name[:30]}] 楼层={fl.floor} text={fl.text[:50]}")

    print(f"\n提取的标高标注(前20):")
    for et in analyzer.elevation_tags[:20]:
        print(f"  [{et.drawing_name[:30]}] 标高={et.elevation}m text={et.text[:50]}")

    conflicts = analyzer.find_cross_floor_conflicts()
    print(f"\n===== 空间冲突分析结果 ({len(conflicts)}个) =====")

    severity_order = {"A": 0, "B": 1, "C": 2, "D": 3}
    conflicts.sort(key=lambda c: severity_order.get(c["severity"], 5))

    for c in conflicts:
        print(f"\n  [{c['severity']}] {c['type']}")
        print(f"  {c['description']}")
        print(f"  风险: {c['risk']}")
        print(f"  涉及图纸: {c['involved']}")
        print(f"  规范: {c['std']}")

    with open("spatial_conflicts.json", "w", encoding="utf-8") as f:
        json.dump(conflicts, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到 spatial_conflicts.json")