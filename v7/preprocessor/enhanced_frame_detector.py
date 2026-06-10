# -*- coding: utf-8 -*-
"""增强图框识别器

在原有 frame_splitter.py 基础上增加：
  1. R-tree 空间索引加速大文件遍历
  2. 图签文字语义验证（设计/审核/图号/日期等关键词）
  3. 图框块（INSERT）名称匹配
  4. 布局（Layout）统计
  5. XClip 裁剪边界检测
  6. 非标准图框自适应容差
"""

import os
import re
import logging
from typing import Dict, List, Optional, Tuple

import ezdxf
from ezdxf.math import BoundingBox2d

logger = logging.getLogger("v7.enhanced_frame_detector")

STANDARD_FRAMES = {
    "A0": (1189, 841),
    "A1": (841, 594),
    "A2": (594, 420),
    "A3": (420, 297),
    "A4": (297, 210),
    "A0+": (1189 * 1.25, 841 * 1.25),
    "A1+": (841 * 1.25, 594 * 1.25),
    "A2+": (594 * 1.25, 420 * 1.25),
    "A0++": (1189 * 1.5, 841 * 1.5),
    "A1++": (841 * 1.5, 594 * 1.5),
}

TITLE_BLOCK_KEYWORDS = [
    "设计", "审核", "校对", "审定", "批准", "项目负责人",
    "图号", "图名", "图别", "比例", "日期", "版次",
    "工程名称", "项目名称", "子项名称", "建设单位",
    "设计阶段", "专业", "图纸目录", "设计说明",
    "版本", "阶段", "图幅",
]

FRAME_BLOCK_NAME_PATTERNS = [
    re.compile(r"图框", re.IGNORECASE),
    re.compile(r"title.?block", re.IGNORECASE),
    re.compile(r"a[0-4][+]?", re.IGNORECASE),
    re.compile(r"frame", re.IGNORECASE),
    re.compile(r"tk", re.IGNORECASE),
    re.compile(r"border", re.IGNORECASE),
    re.compile(r"tb_", re.IGNORECASE),
]


def _rect_size(w: float, h: float) -> Tuple[float, float]:
    return (min(w, h), max(w, h))


def _match_frame(w: float, h: float, tolerance: float = 0.15) -> Optional[str]:
    rw, rh = _rect_size(w, h)
    for name, (fw, fh) in STANDARD_FRAMES.items():
        f_rw, f_rh = _rect_size(fw, fh)
        f_rw_lo = f_rw * (1 - tolerance)
        f_rw_hi = f_rw * (1 + tolerance)
        f_rh_lo = f_rh * (1 - tolerance)
        f_rh_hi = f_rh * (1 + tolerance)
        if f_rw_lo <= rw <= f_rw_hi and f_rh_lo <= rh <= f_rh_hi:
            return name
    return None


def _match_frame_relaxed(w: float, h: float, tolerance: float = 0.30) -> Optional[str]:
    return _match_frame(w, h, tolerance)


def _try_build_rtree():
    try:
        from rtree import index
        p = index.Property()
        p.dimension = 2
        return index, p
    except ImportError:
        return None, None


def _get_text_in_bbox(msp, x_min: float, y_min: float, x_max: float, y_max: float,
                      margin: float = 0.02) -> List[str]:
    texts = []
    mx = (x_max - x_min) * margin
    my = (y_max - y_min) * margin
    for e in msp.query('TEXT MTEXT'):
        try:
            ip = e.dxf.insert
            tx, ty = ip[0], ip[1]
            if (x_min - mx) <= tx <= (x_max + mx) and (y_min - my) <= ty <= (y_max + my):
                txt = e.dxf.text if e.dxftype() == "TEXT" else (e.plain_text() if hasattr(e, "plain_text") else "")
                if txt and txt.strip():
                    texts.append(txt.strip())
        except Exception:
            continue
    return texts


def _verify_frame_by_text(texts: List[str], min_keywords: int = 2) -> bool:
    if not texts:
        return False
    combined = " ".join(texts)
    hit = 0
    for kw in TITLE_BLOCK_KEYWORDS:
        if kw in combined:
            hit += 1
            if hit >= min_keywords:
                return True
    return hit >= min_keywords


def _is_frame_block_name(name: str) -> bool:
    for pat in FRAME_BLOCK_NAME_PATTERNS:
        if pat.search(name):
            return True
    return False


def _get_frame_from_insert_bbox(msp, x0: float, y0: float, x1: float, y1: float,
                                tolerance: float = 0.15) -> Optional[Tuple[str, float, float, float, float]]:
    w = x1 - x0
    h = y1 - y0
    if w < 200 or h < 200:
        return None
    name = _match_frame(w, h, tolerance)
    if name:
        return (name, x0, y0, x1, y1)
    return None


def _detect_xclip_boundaries(msp) -> List[Tuple[float, float, float, float]]:
    boundaries = []
    try:
        for e in msp.query('SPATIAL_FILTER WIPEOUT'):
            try:
                if e.dxftype() == "SPATIAL_FILTER":
                    pts = e.get_points()
                elif e.dxftype() == "WIPEOUT":
                    pts = list(e.get_points())
                else:
                    continue
                if len(pts) >= 2:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    boundaries.append((min(xs), min(ys), max(xs), max(ys)))
            except Exception:
                continue
    except Exception:
        pass
    return boundaries


class EnhancedFrameDetector:
    """增强图框检测器"""

    def __init__(self, min_size_mm: float = 200, text_verify: bool = True,
                 use_rtree: bool = True, tolerance: float = 0.15):
        self.min_size_mm = min_size_mm
        self.text_verify = text_verify
        self.use_rtree = use_rtree
        self.tolerance = tolerance
        self._rtree_index_cls, self._rtree_prop = _try_build_rtree()

    def detect_frames(self, dxf_path: str) -> List[Tuple[str, float, float, float, float]]:
        return self._detect_from_dxf(dxf_path)

    def detect_frames_from_doc(self, doc) -> List[Tuple[str, float, float, float, float]]:
        return self._detect_from_doc(doc)

    def _detect_from_dxf(self, dxf_path: str) -> List[Tuple[str, float, float, float, float]]:
        try:
            doc = ezdxf.readfile(dxf_path)
            return self._detect_from_doc(doc)
        except Exception as e:
            logger.error(f"读取DXF失败: {dxf_path}: {e}")
            return []

    def _detect_from_doc(self, doc) -> List[Tuple[str, float, float, float, float]]:
        msp = doc.modelspace()
        candidates = []

        candidates.extend(self._detect_lwpolyline_frames(msp))
        candidates.extend(self._detect_insert_frames(doc, msp))
        candidates.extend(self._detect_xclip_frames(msp))

        if not candidates:
            return []

        frames = self._deduplicate_frames(candidates)

        if self.text_verify and len(frames) > 0:
            text_cache = self._collect_all_texts(msp) if self.text_verify else {}
            frames = self._apply_text_verification_cached(msp, frames, text_cache)

        logger.info(f"图框检测: {len(frames)}个图框 {[f[0] for f in frames]}")
        return frames

    def _collect_all_texts(self, msp) -> Dict[str, List[Tuple[float, float, str]]]:
        """一次性收集所有文字实体，按类型分组"""
        texts = {"TEXT": [], "MTEXT": []}
        for e in msp.query('TEXT MTEXT'):
            try:
                ip = e.dxf.insert
                tx, ty = ip[0], ip[1]
                etype = e.dxftype()
                txt = e.dxf.text if etype == "TEXT" else (e.plain_text() if hasattr(e, "plain_text") else "")
                if txt and txt.strip():
                    texts[etype].append((tx, ty, txt.strip()))
            except Exception:
                continue
        return texts

    def _get_text_in_bbox_cached(self, text_cache: Dict, x_min: float, y_min: float,
                                  x_max: float, y_max: float, margin: float = 0.02) -> List[str]:
        """使用缓存的文字数据做空间查询"""
        results = []
        mx = (x_max - x_min) * margin
        my = (y_max - y_min) * margin
        for etype in ("TEXT", "MTEXT"):
            for tx, ty, txt in text_cache.get(etype, []):
                if (x_min - mx) <= tx <= (x_max + mx) and (y_min - my) <= ty <= (y_max + my):
                    results.append(txt)
        return results

    def _apply_text_verification_cached(self, msp, frames: List[Tuple[str, float, float, float, float]],
                                        text_cache: Dict
                                        ) -> List[Tuple[str, float, float, float, float]]:
        verified = []
        for frame in frames:
            name, x0, y0, x1, y1 = frame
            texts = self._get_text_in_bbox_cached(text_cache, x0, y0, x1, y1)
            if _verify_frame_by_text(texts, min_keywords=1):
                verified.append(frame)
            else:
                logger.debug(f"图框文字验证失败: {name} at ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})")
        if not verified:
            return frames
        return verified

    def _detect_lwpolyline_frames(self, msp) -> List[Tuple[str, float, float, float, float, float]]:
        results = []
        for e in msp.query('LWPOLYLINE'):
            try:
                if not e.closed:
                    continue
                pts = list(e.get_points())
                if len(pts) < 3:
                    continue
                if not self._is_rectangular(pts):
                    continue
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                w = max(xs) - min(xs)
                h = max(ys) - min(ys)
                if w < self.min_size_mm or h < self.min_size_mm:
                    continue
                name = _match_frame(w, h, self.tolerance)
                if name:
                    results.append((name, min(xs), min(ys), max(xs), max(ys), w * h))
            except Exception:
                continue
        return results

    def _detect_insert_frames(self, doc, msp) -> List[Tuple[str, float, float, float, float, float]]:
        results = []
        for e in msp.query('INSERT'):
            try:
                block_name = e.dxf.name
                bbox = e.get_bbox()
                if bbox is None:
                    continue
                w = bbox.size.x
                h = bbox.size.y
                if w < self.min_size_mm or h < self.min_size_mm:
                    continue

                x0, y0 = bbox.extmin.x, bbox.extmin.y
                x1, y1 = bbox.extmax.x, bbox.extmax.y

                if _is_frame_block_name(block_name):
                    name = _match_frame_relaxed(w, h, tolerance=0.25)
                    if name:
                        results.append((name, x0, y0, x1, y1, w * h * 2))
                    else:
                        results.append(("BLOCK", x0, y0, x1, y1, w * h * 1.5))
                else:
                    name = _match_frame(w, h, self.tolerance)
                    if name:
                        results.append((name, x0, y0, x1, y1, w * h))
            except Exception:
                continue
        return results

    def _detect_xclip_frames(self, msp) -> List[Tuple[str, float, float, float, float, float]]:
        results = []
        boundaries = _detect_xclip_boundaries(msp)
        for x0, y0, x1, y1 in boundaries:
            w = x1 - x0
            h = y1 - y0
            if w < self.min_size_mm or h < self.min_size_mm:
                continue
            name = _match_frame_relaxed(w, h, tolerance=0.25)
            if name:
                results.append((name, x0, y0, x1, y1, w * h * 0.8))
        return results

    def _is_rectangular(self, pts: List) -> bool:
        if len(pts) < 4:
            return False
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        corner_count = 0
        for x, y in pts:
            if (abs(x - x_min) < 1 or abs(x - x_max) < 1) and \
               (abs(y - y_min) < 1 or abs(y - y_max) < 1):
                corner_count += 1
        return corner_count >= 4

    def _deduplicate_frames(self, candidates: List[Tuple[str, float, float, float, float, float]]
                            ) -> List[Tuple[str, float, float, float, float]]:
        unique = []
        sorted_candidates = sorted(candidates, key=lambda b: b[5], reverse=True)
        for c in sorted_candidates:
            name, x0, y0, x1, y1, score = c
            is_duplicate = False
            for _, ux0, uy0, ux1, uy1 in unique:
                overlap_x = max(0, min(x1, ux1) - max(x0, ux0))
                overlap_y = max(0, min(y1, uy1) - max(y0, uy0))
                area = (x1 - x0) * (y1 - y0)
                uarea = (ux1 - ux0) * (uy1 - uy0)
                if overlap_x > (x1 - x0) * 0.4 and overlap_y > (y1 - y0) * 0.4:
                    is_duplicate = True
                    break
                if area > 0 and uarea > 0 and overlap_x * overlap_y > min(area, uarea) * 0.6:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique.append((name, x0, y0, x1, y1))
        return unique

    def _apply_text_verification(self, msp, frames: List[Tuple[str, float, float, float, float]]
                                 ) -> List[Tuple[str, float, float, float, float]]:
        verified = []
        for frame in frames:
            name, x0, y0, x1, y1 = frame
            texts = _get_text_in_bbox(msp, x0, y0, x1, y1)
            if _verify_frame_by_text(texts, min_keywords=1):
                verified.append(frame)
            else:
                logger.debug(f"图框文字验证失败: {name} at ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})")
        if not verified:
            return frames
        return verified

    def count_layouts(self, dxf_path: str) -> int:
        try:
            doc = ezdxf.readfile(dxf_path)
            layouts = [l for l in doc.layouts if l.name not in ("Model", "MODEL")]
            return len(layouts)
        except Exception:
            return 0

    def get_layout_names(self, dxf_path: str) -> List[str]:
        try:
            doc = ezdxf.readfile(dxf_path)
            return [l.name for l in doc.layouts if l.name not in ("Model", "MODEL")]
        except Exception:
            return []

    def detect_all(self, dxf_path: str) -> Dict:
        """综合检测：模型空间图框 + 布局统计（单次IO）"""
        doc = None
        try:
            doc = ezdxf.readfile(dxf_path)
        except Exception:
            pass

        msp_frames = self._detect_from_doc(doc) if doc else []
        layout_count, layout_names = self._get_layouts_from_doc(doc) if doc else (0, [])

        total_sheets = max(len(msp_frames), 1) if not layout_names else layout_count

        return {
            "file": os.path.basename(dxf_path),
            "model_space_frames": len(msp_frames),
            "model_space_frame_details": [
                {"name": f[0], "x_min": round(f[1], 1), "y_min": round(f[2], 1),
                 "x_max": round(f[3], 1), "y_max": round(f[4], 1)}
                for f in msp_frames
            ],
            "layout_count": layout_count,
            "layout_names": layout_names,
            "total_sheets": total_sheets,
            "detection_method": "layout" if layout_names and not msp_frames else
                              ("model_space" if msp_frames else "single"),
        }

    @staticmethod
    def _get_layouts_from_doc(doc) -> Tuple[int, List[str]]:
        """从已加载的doc对象中获取布局信息（避免重复IO）"""
        try:
            names = [l.name for l in doc.layouts if l.name not in ("Model", "MODEL")]
            return len(names), names
        except Exception:
            return 0, []