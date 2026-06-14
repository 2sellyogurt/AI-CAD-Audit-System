# -*- coding: utf-8 -*-
"""DXF图框自动识别与拆分

检测模型空间中的标准图框（LWPOLYLINE矩形），将多图幅DXF拆分为独立区域。
每张子图分别走渲染管线，视觉LLM逐张审图。
"""

import os
import logging
from typing import List, Optional, Tuple

import ezdxf

logger = logging.getLogger("v7.frame_splitter")

from .constants import STANDARD_FRAMES


def _rect_size(w: float, h: float) -> Tuple[float, float]:
    return (min(w, h), max(w, h))


def _match_frame(w: float, h: float, tolerance: float = 0.15) -> Optional[str]:
    rw, rh = _rect_size(w, h)
    for name, (fw, fh) in STANDARD_FRAMES.items():
        f_rw, f_rh = _rect_size(fw, fh)
        if abs(rw - f_rw) / max(f_rw, 1) < tolerance and abs(rh - f_rh) / max(f_rh, 1) < tolerance:
            return name
    return None


def detect_frames(dxf_path: str, min_size_mm: float = 200) -> List[Tuple[str, float, float, float, float]]:
    """检测DXF中的标准图框。

    Returns: [(frame_name, x_min, y_min, x_max, y_max), ...]
    """
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception as e:
        logger.warning(f"DXF文件读取失败: {dxf_path}, {e}")
        return []

    candidates = []
    for e in msp:
        try:
            if e.dxftype() == "LWPOLYLINE" and e.closed:
                pts = list(e.get_points())
                if len(pts) < 3:
                    continue
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                w = max(xs) - min(xs)
                h = max(ys) - min(ys)
                if w < min_size_mm or h < min_size_mm:
                    continue
                name = _match_frame(w, h)
                if name:
                    candidates.append((name, min(xs), min(ys), max(xs), max(ys), w * h))
            elif e.dxftype() == "INSERT":
                bbox = e.get_bbox()
                if bbox is None:
                    continue
                w = bbox.size.x
                h = bbox.size.y
                if w < min_size_mm or h < min_size_mm:
                    continue
                name = _match_frame(w, h, tolerance=0.2)
                if name:
                    x0, y0 = bbox.extmin.x, bbox.extmin.y
                    x1, y1 = bbox.extmax.x, bbox.extmax.y
                    candidates.append((name, x0, y0, x1, y1, w * h))
        except Exception as e:
            logger.debug(f"图块处理失败: {e}")
            continue

    if not candidates:
        return []

    blocks = set()
    for i, (name, x0, y0, x1, y1, area) in enumerate(candidates):
        score = area - (100000 if name == "A0" else 0) + (i * 0.001)
        blocks.add((name, x0, y0, x1, y1, score))

    unique = []
    sorted_blocks = sorted(blocks, key=lambda b: b[5], reverse=True)
    for b in sorted_blocks:
        name, x0, y0, x1, y1, score = b
        is_duplicate = False
        for _, ux0, uy0, ux1, uy1 in unique:
            overlap_x = max(0, min(x1, ux1) - max(x0, ux0))
            overlap_y = max(0, min(y1, uy1) - max(y0, uy0))
            if overlap_x > (x1 - x0) * 0.5 and overlap_y > (y1 - y0) * 0.5:
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append((name, x0, y0, x1, y1))

    logger.info(f"图框检测: {dxf_path} → {len(unique)}个图框 {[f[0] for f in unique]}")
    return unique


def split_drawing(dxf_path: str, output_dir: str) -> List[str]:
    """拆分为子PNG，每张对应一个图框。如未检测到图框则全图渲染。

    Returns: 子PNG路径列表
    """
    from .pil_renderer import render_dxf_pil

    frames = detect_frames(dxf_path)
    base = os.path.splitext(os.path.basename(dxf_path))[0]

    if len(frames) <= 1:
        png = os.path.join(output_dir, f"{base}.png")
        os.makedirs(output_dir, exist_ok=True)
        if render_dxf_pil(dxf_path, png):
            return [png]
        return []

    results = []
    for i, (name, x0, y0, x1, y1) in enumerate(frames):
        sub_png = os.path.join(output_dir, f"{base}_{name}_{i+1}.png")
        os.makedirs(output_dir, exist_ok=True)
        if render_dxf_pil(dxf_path, sub_png, x_min=x0, y_min=y0, x_max=x1, y_max=y1):
            results.append(sub_png)

    if not results:
        png = os.path.join(output_dir, f"{base}.png")
        if render_dxf_pil(dxf_path, png):
            return [png]

    return results
