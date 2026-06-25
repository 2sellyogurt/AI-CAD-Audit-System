# -*- coding: utf-8 -*-
"""图纸文本提取器 + 分类器 + 坐标映射器

v7.0核心预处理管线：
  1. ezdxf提取TEXT/MTEXT实体（原始文本+坐标+图层）
  2. 按图号前缀分类到专业
  3. 建立轴线坐标映射
  4. 生成文本路径上下文（供Agent审查）
"""

from __future__ import annotations

import os
import re
import json
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from v7.constants import DISCIPLINE_KEYWORDS as _CONSTANTS_KEYWORDS

logger = logging.getLogger("v7.preprocessor")


@dataclass
class TextEntity:
    entity_id: str
    raw_text: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    layer: str = ""
    entity_type: str = ""
    file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "raw_text": self.raw_text,
            "x": self.x, "y": self.y, "z": self.z,
            "layer": self.layer,
            "entity_type": self.entity_type,
            "file": self.file,
        }


@dataclass
class DrawingInfo:
    file_path: str
    readable_name: str
    discipline: str = "unknown"
    content_disciplines: List[str] = field(default_factory=list)
    drawing_type: str = "unknown"
    floor: str = ""
    drawing_number: str = ""
    text_entities: List[TextEntity] = field(default_factory=list)
    text_content: str = ""
    png_path: str = ""
    png_paths: List[str] = field(default_factory=list)
    extraction_ok: bool = True
    extraction_error: str = ""


CLASSIFICATION_RULES = {
    "building": ["建施", "建筑", "总图", "总说明", "平面", "立面", "节点", "门窗", "幕墙", "装饰", "pl", "lm", "jd", "mc", "mq"],
    "structure": ["结施", "结构", "基础", "配筋", "桩基", "预制", "埋件", "g", "jc", "pj", "zj"],
    "hvac": ["暖施", "暖通", "空调", "通风", "供暖", "防排烟", "nt", "kt", "tf"],
    "plumbing": ["水施", "给排水", "给水", "排水", "消火栓", "喷淋", "海绵", "ss", "gs", "ps"],
    "electrical": ["电施", "电气", "配电", "照明", "防雷", "弱电", "变配电", "ds", "pd", "zm"],
    "fire": ["消施", "消防", "防火", "报警", "灭火", "xf", "fh"],
    "landscape": ["绿施", "景观", "绿化", "园林", "种植", "乔木", "灌木", "铺装", "园路", "水景", "ls", "lh", "yl"],
    "foundation_pit": ["基坑", "支护", "降水", "边坡", "锚杆", "土钉", "排桩", "地下连续墙", "jp", "zh"],
    "curtain_wall": ["幕墙", "玻璃幕墙", "石材幕墙", "铝板", "cw", "mq"],
    "decoration": ["装饰", "装修", "精装", "室内", "吊顶", "墙面", "地面", "zs", "zx"],
}

# 内容级关键字（用于提取文本后的二次分类）— 从 constants.py 加载，避免硬编码
CONTENT_CLASSIFICATION_KEYWORDS = _CONSTANTS_KEYWORDS

PREFIX_SCORE = 10
GENERIC_SCORE = 1

# 专业优先级（数字越小优先级越高）- 解决关键字冲突
DISCIPLINE_PRIORITY = {
    "foundation_pit": 1,
    "curtain_wall": 2,
    "decoration": 3,
    "fire": 4,
    "landscape": 5,
    "hvac": 6,
    "plumbing": 7,
    "electrical": 8,
    "structure": 9,
    "building": 10,
}


def simple_text_lines(text_content: str) -> List[Any]:
    """将纯文本切分为模拟 TextEntity 列表，供内容分类使用。"""
    class _SimpleEntity:
        def __init__(self, text: str):
            self.raw_text = text
    return [_SimpleEntity(line.strip()) for line in text_content.split("\n") if line.strip()]


class DrawingExtractor:
    _MAX_CACHE_SIZE = 100

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._classification_rules = CLASSIFICATION_RULES
        self._content_classification_rules = dict(CONTENT_CLASSIFICATION_KEYWORDS)
        if config:
            custom = config.get("cad", {}).get("classification_rules", {})
            if custom:
                self._classification_rules.update(custom)
        self._text_cache: Dict[str, str] = {}
        self._cache_order: List[str] = []

    def _file_hash(self, dxf_path: str) -> str:
        if not os.path.exists(dxf_path):
            return ""
        try:
            h = hashlib.md5()
            with open(dxf_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            logger.debug(f"计算文件哈希失败: {dxf_path}, {e}")
            return ""

    def _cache_key(self, dxf_path: str) -> str:
        if not os.path.exists(dxf_path):
            return ""
        return f"{os.path.getsize(dxf_path)}_{self._file_hash(dxf_path)[:16]}"

    def _cached_text(self, cache_key: str) -> Optional[str]:
        return self._text_cache.get(cache_key)

    def _set_cache(self, cache_key: str, text: str):
        if cache_key in self._text_cache:
            self._cache_order.remove(cache_key)
        elif len(self._text_cache) >= self._MAX_CACHE_SIZE:
            oldest_key = self._cache_order.pop(0)
            del self._text_cache[oldest_key]
        self._text_cache[cache_key] = text
        self._cache_order.append(cache_key)

    def extract_text_from_dxf(self, dxf_path: str, existing_doc=None) -> List[TextEntity]:
        try:
            import ezdxf
            if existing_doc is not None:
                doc = existing_doc
            else:
                doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
            entities = []
            for e in msp:
                if e.dxftype() not in ("TEXT", "MTEXT"):
                    continue
                text = e.dxf.text if hasattr(e.dxf, "text") else e.plain_text() if hasattr(e, "plain_text") else ""
                if not text or not text.strip():
                    continue
                cleaned = self._clean_text(text.strip())
                if len(cleaned) < 2:
                    continue

                insert = e.dxf.insert if hasattr(e.dxf, "insert") else (0, 0, 0)
                entities.append(TextEntity(
                    entity_id=e.dxf.handle if hasattr(e.dxf, "handle") else str(id(e)),
                    raw_text=cleaned,
                    x=insert[0], y=insert[1], z=insert[2] if len(insert) > 2 else 0,
                    layer=e.dxf.layer if hasattr(e.dxf, "layer") else "",
                    entity_type=e.dxftype(),
                    file=os.path.basename(dxf_path),
                ))
            logger.info(f"从{os.path.basename(dxf_path)}提取了{len(entities)}个文本实体")
            return entities
        except Exception as e:
            logger.error(f"DXF解析失败: {dxf_path}: {e}")
            return []

    @staticmethod
    def _clean_text(text: str) -> str:
        replacements = {
            "%%132": "Φ", "%%133": "φ", "%%134": "±", "%%135": "°",
            "%%p": "±", "%%d": "°", "%%c": "Φ", "%%u": "", "%%o": "",
            "\\P": "\n",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r'\\[A-Za-z]+\|[^;]*;', '', text)
        text = re.sub(r'\\[A-Za-z]+;', '', text)
        text = re.sub(r'\{[^}]*\\[A-Za-z]+\.[0-9]+;[^}]*\}', '', text)
        text = re.sub(r'\{\\[WH][0-9.]+;', '', text)
        text = re.sub(r'\{\\f[^}]*\}', '', text)
        text = re.sub(r'\{[^}]*\}', '', text)
        text = re.sub(r'\\pi\d+[.,]\d+;', '', text)
        text = re.sub(r'\\[A-Za-z]+\d+[.,]\d*;', '', text)
        text = re.sub(r'[{}]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    PREFIX_KEYWORDS = {"建施", "结施", "暖施", "水施", "电施", "消施",
                       "电气", "给排水", "暖通", "建筑", "结构", "消防",
                       "总图", "总说明", "基础", "配筋", "预制", "埋件", "桩基"}
    DISCIPLINE_PREFIXES = {"电气": "electrical", "电施": "electrical",
                           "给排水": "plumbing", "水施": "plumbing",
                           "暖通": "hvac", "暖施": "hvac",
                           "建筑": "building", "建施": "building",
                           "结构": "structure", "结施": "structure",
                           "消防": "fire", "消施": "fire"}

    def classify(self, file_name: str) -> str:
        name_lower = os.path.splitext(file_name)[0].lower()
        scores: Dict[str, int] = {}
        for discipline, keywords in self._classification_rules.items():
            for kw in keywords:
                if kw.lower() in name_lower:
                    is_prefix = kw in self.PREFIX_KEYWORDS or kw.endswith("施")
                    weight = PREFIX_SCORE if is_prefix else GENERIC_SCORE
                    scores[discipline] = scores.get(discipline, 0) + weight
        if scores:
            max_score = max(scores.values())
            top_disciplines = [d for d, s in scores.items() if s == max_score]
            if len(top_disciplines) == 1:
                return top_disciplines[0]
            return min(top_disciplines, key=lambda d: DISCIPLINE_PRIORITY.get(d, 999))
        return "unknown"

    def extract_axis_markers(self, entities: List[TextEntity]) -> Dict[str, List[float]]:
        axis_x_pattern = re.compile(r'^(\d{1,3})$')
        axis_y_pattern = re.compile(r'^([A-HJ-NP-Za-hj-np-z]|[①-⑩])$')
        axes: Dict[str, List[float]] = {"x": [], "y": []}
        for e in entities:
            text = e.raw_text.strip().replace(" ", "").replace("\n", "")
            if not text or len(text) > 3:
                continue
            if axis_x_pattern.match(text) and len(text) <= 3:
                axes["x"].append(e.x)
            elif axis_y_pattern.match(text) and len(text) == 1:
                axes["y"].append(e.y)
        if axes["x"]:
            axes["x"] = sorted(set(axes["x"]))[:200]
        if axes["y"]:
            axes["y"] = sorted(set(axes["y"]))[:200]
        return axes

    def infer_discipline_from_entities(
        self, entities: List[TextEntity], file_name: str = ""
    ) -> str:
        """从图纸文本实体推断专业归属（返回最佳匹配专业）。"""
        text_content = " ".join(e.raw_text for e in entities[:500])
        scores: Dict[str, int] = {}
        for discipline, keywords in self._classification_rules.items():
            score = sum(1 for kw in keywords if kw in text_content)
            if score > 0:
                scores[discipline] = score
        if scores:
            max_score = max(scores.values())
            top_disciplines = [d for d, s in scores.items() if s == max_score]
            if len(top_disciplines) == 1:
                return top_disciplines[0]
            return min(top_disciplines, key=lambda d: DISCIPLINE_PRIORITY.get(d, 999))
        return "unknown"

    def infer_all_disciplines_from_entities(
        self, entities: List[Any], file_name: str = ""
    ) -> List[str]:
        """从图纸文本实体推断所有可能的专业归属（对抗不规范命名）。

        返回所有匹配到内容关键字的专业列表，供 filter_drawings 做回退匹配。
        """
        if not entities:
            return []
        text_content = " ".join(
            e.raw_text if hasattr(e, 'raw_text') else str(e)
            for e in entities[:500]
        )
        scores: Dict[str, int] = {}
        # 使用内容级关键字（更丰富的专业术语）
        keywords_map = getattr(self, '_content_classification_rules', CONTENT_CLASSIFICATION_KEYWORDS)
        for discipline, keywords in keywords_map.items():
            score = sum(1 for kw in keywords if kw in text_content)
            if score >= 2:  # 至少匹配2个内容关键字才算
                scores[discipline] = score
        if not scores:
            # 回退到文件名级关键字
            for discipline, keywords in self._classification_rules.items():
                score = sum(1 for kw in keywords if kw in text_content)
                if score >= 2:
                    scores[discipline] = score
        if scores:
            # 按得分降序返回所有匹配专业
            sorted_disc = sorted(scores.items(), key=lambda x: -x[1])
            logger.debug(
                f"内容分类[{file_name}]: "
                + ", ".join(f"{d}={s}" for d, s in sorted_disc)
            )
            return [d for d, _ in sorted_disc]
        return []

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，防止路径注入攻击"""
        # 移除路径分隔符和特殊字符
        sanitized = re.sub(r'[\\/:*?"<>|]', '_', filename)
        # 移除开头的点和空格
        sanitized = sanitized.lstrip('. ')
        # 限制长度
        if len(sanitized) > 200:
            name, ext = os.path.splitext(sanitized)
            sanitized = name[:190] + ext
        return sanitized or "unnamed"

    def process_drawing(self, dxf_path: str, png_output_dir: str = "") -> DrawingInfo:
        from .cad_printer import print_drawing_smart
        from .frame_splitter import split_drawing

        file_name = os.path.basename(dxf_path)
        sanitized_name = self._sanitize_filename(file_name)
        info = DrawingInfo(
            file_path=dxf_path,
            readable_name=sanitized_name,
            discipline=self.classify(sanitized_name),
        )

        cache_key = self._cache_key(dxf_path)
        cached = self._cached_text(cache_key)

        try:
            if cached:
                info.text_content = cached
                info.text_entities = []
                info.extraction_ok = True
                logger.info(f"缓存命中: {file_name}")
            else:
                import ezdxf as _ezdxf
                try:
                    doc = _ezdxf.readfile(dxf_path)
                except IOError as e:
                    logger.warning(f"DXF文件读取失败(IO错误): {dxf_path}, {e}")
                    doc = None
                except Exception as e:
                    logger.warning(f"DXF文件解析失败: {dxf_path}, {e}")
                    doc = None

                if doc is None:
                    info.extraction_ok = False
                    info.extraction_error = "DXF读取失败"
                    return info

                entities = self.extract_text_from_dxf(dxf_path, existing_doc=doc)
                if not entities:
                    info.extraction_ok = False
                    info.extraction_error = "未提取到文本实体"
                else:
                    info.text_entities = entities
                    info.text_content = "\n".join(e.raw_text for e in entities)
                    self._set_cache(cache_key, info.text_content)
                    info.extraction_ok = True

                if png_output_dir:
                    base = os.path.splitext(sanitized_name)[0]
                    png_path = os.path.join(png_output_dir, f"{base}.png")
                    os.makedirs(png_output_dir, exist_ok=True)
                    from .pil_renderer import render_dxf_pil
                    ok = render_dxf_pil(dxf_path, png_path, existing_doc=doc)
                    if not ok:
                        from .cad_printer import print_alternative_pillow
                        ok = print_alternative_pillow(dxf_path, png_path)
                    if ok:
                        info.png_path = png_path
                        info.png_paths = [png_path]

            # 【对抗性增强】始终执行内容级二次分类
            entities_for_classify = info.text_entities or []
            if not entities_for_classify and info.text_content:
                from v7.preprocessor.drawing_extractor import simple_text_lines
                entities_for_classify = simple_text_lines(info.text_content)
            info.content_disciplines = self.infer_all_disciplines_from_entities(
                entities_for_classify, file_name
            )
            # 如果文件名分类为 unknown 或内容分类更可靠，用内容分类结果纠正
            content_disc = self.infer_discipline_from_entities(
                entities_for_classify, file_name
            )
            if info.discipline == "unknown" and content_disc != "unknown":
                logger.info(
                    f"内容级分类修正: {file_name} "
                    f"{info.discipline}→{content_disc} ({info.content_disciplines})"
                )
                info.discipline = content_disc
            elif info.discipline != "unknown" and content_disc != info.discipline:
                logger.info(
                    f"内容级分类补充: {file_name} "
                    f"文件名={info.discipline}, 内容匹配={info.content_disciplines}"
                )

            if not info.drawing_number:
                info.drawing_number = self._extract_drawing_number(file_name, info.text_entities or [])
                info.floor = self._extract_floor(file_name)

        except (IOError, ValueError, TypeError) as e:
            info.extraction_ok = False
            info.extraction_error = str(e)
            logger.error(f"处理图纸失败: {dxf_path}, {e}")

        return info

    @staticmethod
    def _extract_drawing_number(file_name: str, entities: List[TextEntity]) -> str:
        patterns = [
            r'(建施|结施|暖施|水施|电施|消施)[-_\s]*(\d+)',
            r'图号[:：]\s*([A-Za-z0-9\-_]+)',
        ]
        for pat in patterns:
            match = re.search(pat, file_name)
            if match:
                return match.group(0)
        for e in entities[:50]:
            for pat in patterns:
                match = re.search(pat, e.raw_text)
                if match:
                    return match.group(0)
        return ""

    @staticmethod
    def _extract_floor(file_name: str) -> str:
        floor_patterns = [
            (r'(一|二|三|四|五|六|七|八|九|十)\s*层', None),
            (r'(\d+)\s*[Ff]', None),
            (r'(地下室|地下一层|地下二层)', None),
            (r'B(\d+)', None),
            (r'(屋面|屋顶)', None),
        ]
        for pat, _ in floor_patterns:
            match = re.search(pat, file_name)
            if match:
                return match.group(0)
        return ""

    def find_dxf_files(self, dxf_dir: str = None) -> List[str]:
        """递归查找DXF/DWG文件路径列表。

        Args:
            dxf_dir: 搜索目录，默认从 config_loader 读取 V7_INPUT_DIR

        Returns:
            DXF/DWG文件绝对路径列表
        """
        if dxf_dir is None:
            from v7.config_loader import get_config
            dxf_dir = str(get_config().input_dir)
        if not os.path.isdir(dxf_dir):
            logger.warning(f"DXF目录不存在: {dxf_dir}")
            return []
        results = []
        for root, _dirs, files in os.walk(dxf_dir):
            for f in files:
                if f.lower().endswith((".dxf", ".dwg")):
                    results.append(os.path.join(root, f))
        logger.info(f"找到 {len(results)} 个DXF/DWG文件 (目录: {dxf_dir})")
        return results

    def process_directory(self, dxf_dir: str) -> List[DrawingInfo]:
        results = []
        for f in os.listdir(dxf_dir):
            if f.lower().endswith((".dxf", ".dwg")):
                info = self.process_drawing(os.path.join(dxf_dir, f))
                results.append(info)
        logger.info(f"目录处理完成: {len(results)}个文件, "
                     f"文本提取成功{sum(1 for r in results if r.extraction_ok)}个")
        return results

    def save_text_json(self, info: DrawingInfo, output_dir: str) -> str:
        os.makedirs(output_dir, exist_ok=True)
        base = os.path.splitext(info.readable_name)[0]
        path = os.path.join(output_dir, f"{base}_text.json")
        data = {
            "file": info.readable_name,
            "discipline": info.discipline,
            "floor": info.floor,
            "drawing_number": info.drawing_number,
            "entity_count": len(info.text_entities),
            "extraction_ok": info.extraction_ok,
            "text_content": info.text_content,
            "entities": [e.to_dict() for e in info.text_entities],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
