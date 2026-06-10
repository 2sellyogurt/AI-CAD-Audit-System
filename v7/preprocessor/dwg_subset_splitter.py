# -*- coding: utf-8 -*-
"""DXF子图拆分器

根据检测到的图框边界，将多图幅DXF拆分为独立DXF文件。
每张子图仅包含对应图框范围内的实体，保留图层、线型、样式等元数据。

实现原理：
  1. 读取源DXF，遍历所有实体
  2. 对每个图框，判定实体是否在范围内（含边界穿越容差）
  3. 创建新DXF，复制范围内的实体及相关表定义
  4. 输出独立DXF文件，命名规则：原文件名_帧序号_帧名称.dxf
"""

import os
import copy
import logging
from typing import Any, Dict, List, Optional, Tuple

import ezdxf
from ezdxf.math import BoundingBox2d

logger = logging.getLogger("v7.dwg_subset_splitter")

ENTITY_TYPES_TO_COPY = {
    "LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "ELLIPSE",
    "SPLINE", "TEXT", "MTEXT", "INSERT", "DIMENSION", "HATCH",
    "SOLID", "TRACE", "3DFACE", "POINT", "MLINE", "RAY", "XLINE",
    "LEADER", "MLEADER", "IMAGE", "WIPEOUT", "ATTDEF",
}

BLOCK_ENTITY_TYPES = {
    "LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "ELLIPSE",
    "SPLINE", "TEXT", "MTEXT", "INSERT", "HATCH", "SOLID", "TRACE",
    "3DFACE", "POINT", "ATTDEF",
}


def _entity_bbox(entity) -> Optional[Tuple[float, float, float, float]]:
    try:
        etype = entity.dxftype()
        if etype == "LINE":
            sx, sy = entity.dxf.start[0], entity.dxf.start[1]
            ex, ey = entity.dxf.end[0], entity.dxf.end[1]
            return (min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey))
        elif etype == "LWPOLYLINE":
            pts = list(entity.get_points())
            if not pts:
                return None
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return (min(xs), min(ys), max(xs), max(ys))
        elif etype == "POLYLINE":
            pts = [(v.dxf.location[0], v.dxf.location[1])
                   for v in entity.vertices if hasattr(v.dxf, "location")]
            if not pts:
                return None
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return (min(xs), min(ys), max(xs), max(ys))
        elif etype == "CIRCLE":
            cx, cy, r = entity.dxf.center[0], entity.dxf.center[1], entity.dxf.radius
            return (cx - r, cy - r, cx + r, cy + r)
        elif etype == "ARC":
            cx, cy, r = entity.dxf.center[0], entity.dxf.center[1], entity.dxf.radius
            return (cx - r, cy - r, cx + r, cy + r)
        elif etype in ("TEXT", "MTEXT", "ATTDEF"):
            ip = entity.dxf.insert
            return (ip[0], ip[1], ip[0], ip[1])
        elif etype == "INSERT":
            bbox = entity.get_bbox()
            if bbox:
                return (bbox.extmin.x, bbox.extmin.y, bbox.extmax.x, bbox.extmax.y)
            ip = entity.dxf.insert
            return (ip[0], ip[1], ip[0], ip[1])
        elif etype == "DIMENSION":
            try:
                dp = entity.dxf.defpoint
                tp = entity.dxf.text_midpoint if hasattr(entity.dxf, "text_midpoint") else dp
                return (min(dp[0], tp[0]), min(dp[1], tp[1]),
                        max(dp[0], tp[0]), max(dp[1], tp[1]))
            except Exception:
                return None
        elif etype == "HATCH":
            try:
                paths = entity.paths
                all_pts = []
                for path in paths:
                    for seg in path:
                        if hasattr(seg, 'start'):
                            all_pts.append((seg.start[0], seg.start[1]))
                        if hasattr(seg, 'end'):
                            all_pts.append((seg.end[0], seg.end[1]))
                if all_pts:
                    xs = [p[0] for p in all_pts]
                    ys = [p[1] for p in all_pts]
                    return (min(xs), min(ys), max(xs), max(ys))
            except Exception:
                pass
            return None
        elif etype == "POINT":
            loc = entity.dxf.location
            return (loc[0], loc[1], loc[0], loc[1])
        elif etype == "ELLIPSE":
            cx, cy = entity.dxf.center[0], entity.dxf.center[1]
            rx = entity.dxf.major_axis[0] if hasattr(entity.dxf, "major_axis") else 100
            ry = entity.dxf.minor_axis[0] if hasattr(entity.dxf, "minor_axis") else 100
            rx = abs(rx) if rx else 100
            ry = abs(ry) if ry else 100
            return (cx - rx, cy - ry, cx + rx, cy + ry)
        elif etype == "SPLINE":
            try:
                ctrl_pts = entity.control_points
                if ctrl_pts:
                    xs = [p[0] for p in ctrl_pts]
                    ys = [p[1] for p in ctrl_pts]
                    return (min(xs), min(ys), max(xs), max(ys))
            except Exception:
                pass
            return None
        elif etype == "SOLID":
            pts = [entity.dxf.get(f"vtx{i}") for i in range(4)
                   if entity.dxf.hasattr(f"vtx{i}")]
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                return (min(xs), min(ys), max(xs), max(ys))
            return None
        elif etype == "IMAGE":
            ip = entity.dxf.insert
            sz = entity.dxf.u_pixel_size if hasattr(entity.dxf, "u_pixel_size") else 100
            return (ip[0], ip[1], ip[0] + sz, ip[1] + sz)
        elif etype == "WIPEOUT":
            try:
                pts = list(entity.get_points())
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    return (min(xs), min(ys), max(xs), max(ys))
            except Exception:
                pass
            return None
        return None
    except Exception:
        return None


def _is_entity_in_frame(entity_bbox: Tuple[float, float, float, float],
                        frame_bounds: Tuple[float, float, float, float],
                        margin: float = 0.0) -> bool:
    ex0, ey0, ex1, ey1 = entity_bbox
    fx0, fy0, fx1, fy1 = frame_bounds
    fx0 -= margin
    fy0 -= margin
    fx1 += margin
    fy1 += margin

    if ex1 < fx0 or ex0 > fx1 or ey1 < fy0 or ey0 > fy1:
        return False

    overlap_x = max(0, min(ex1, fx1) - max(ex0, fx0))
    overlap_y = max(0, min(ey1, fy1) - max(ey0, fy0))
    entity_w = ex1 - ex0
    entity_h = ey1 - ey0

    if entity_w < 0.01 and entity_h < 0.01:
        return fx0 <= ex0 <= fx1 and fy0 <= ey0 <= fy1

    if entity_w < 0.01:
        return overlap_y > entity_h * 0.3
    if entity_h < 0.01:
        return overlap_x > entity_w * 0.3

    return overlap_x > entity_w * 0.2 and overlap_y > entity_h * 0.2


def _copy_layer_defs(source_doc, target_doc):
    try:
        for layer in source_doc.layers:
            if layer.dxf.name not in target_doc.layers:
                new_layer = target_doc.layers.new(name=layer.dxf.name)
                try:
                    new_layer.dxf.color = layer.dxf.color
                except Exception:
                    pass
                try:
                    new_layer.dxf.linetype = layer.dxf.linetype
                except Exception:
                    pass
    except Exception:
        pass


def _copy_linetype_defs(source_doc, target_doc):
    try:
        for lt in source_doc.linetypes:
            if lt.dxf.name not in target_doc.linetypes:
                try:
                    target_doc.linetypes.new(name=lt.dxf.name)
                except Exception:
                    pass
    except Exception:
        pass


def _copy_text_styles(source_doc, target_doc):
    try:
        for style in source_doc.styles:
            if style.dxf.name not in target_doc.styles:
                try:
                    target_doc.styles.new(name=style.dxf.name)
                except Exception:
                    pass
    except Exception:
        pass


def _copy_block_defs(source_doc, target_doc, used_blocks: set):
    try:
        for block_name in used_blocks:
            if block_name in target_doc.blocks:
                continue
            try:
                src_block = source_doc.blocks.get(block_name)
                if src_block is None:
                    continue
                tgt_block = target_doc.blocks.new(name=block_name)
                for src_entity in src_block:
                    try:
                        src_etype = src_entity.dxftype()
                        if src_etype not in BLOCK_ENTITY_TYPES:
                            continue
                        tgt_block.add_entity(copy.deepcopy(src_entity))
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass


def _copy_dim_styles(source_doc, target_doc):
    try:
        for dimstyle in source_doc.dimstyles:
            if dimstyle.dxf.name not in target_doc.dimstyles:
                try:
                    target_doc.dimstyles.new(name=dimstyle.dxf.name)
                except Exception:
                    pass
    except Exception:
        pass


def split_dxf_by_frames(dxf_path: str, frames: List[Tuple[str, float, float, float, float]],
                        output_dir: str, margin: float = 50.0) -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(dxf_path))[0]

    try:
        source_doc = ezdxf.readfile(dxf_path)
    except Exception as e:
        logger.error(f"读取DXF失败: {dxf_path}: {e}")
        return []

    source_msp = source_doc.modelspace()
    results = []

    for i, (frame_name, fx0, fy0, fx1, fy1) in enumerate(frames):
        frame_bounds = (fx0, fy0, fx1, fy1)
        frame_w = fx1 - fx0
        frame_h = fy1 - fy0

        out_name = f"{base}_F{i+1:02d}_{frame_name}"
        out_path = os.path.join(output_dir, f"{out_name}.dxf")

        try:
            target_doc = ezdxf.new(dxfversion=source_doc.dxfversion)
            target_msp = target_doc.modelspace()

            _copy_layer_defs(source_doc, target_doc)
            _copy_linetype_defs(source_doc, target_doc)
            _copy_text_styles(source_doc, target_doc)
            _copy_dim_styles(source_doc, target_doc)

            used_blocks = set()
            entity_count = 0

            for e in source_msp:
                etype = e.dxftype()
                if etype not in ENTITY_TYPES_TO_COPY:
                    continue

                ebbox = _entity_bbox(e)
                if ebbox is None:
                    continue

                if _is_entity_in_frame(ebbox, frame_bounds, margin=margin):
                    try:
                        target_msp.add_entity(copy.deepcopy(e))
                        entity_count += 1
                        if etype == "INSERT":
                            used_blocks.add(e.dxf.name)
                    except Exception:
                        continue

            _copy_block_defs(source_doc, target_doc, used_blocks)

            target_doc.saveas(out_path)

            file_kb = os.path.getsize(out_path) / 1024
            logger.info(f"子图拆分: {out_name} → {entity_count}实体, {file_kb:.0f}KB")
            results.append(out_path)

        except Exception as e:
            logger.error(f"子图拆分失败: {out_name}: {e}")
            continue

    if not results:
        src_copy = os.path.join(output_dir, f"{base}_full.dxf")
        try:
            source_doc.saveas(src_copy)
            results.append(src_copy)
            logger.info(f"无图框可拆，全量复制: {src_copy}")
        except Exception:
            pass

    return results


def split_single_dxf(dxf_path: str, output_dir: str) -> List[str]:
    src_copy = os.path.join(output_dir, os.path.basename(dxf_path))
    try:
        doc = ezdxf.readfile(dxf_path)
        doc.saveas(src_copy)
        return [src_copy]
    except Exception:
        return []


def split_dxf_by_layouts(dxf_path: str, output_dir: str,
                         layout_names: List[str] = None) -> List[str]:
    """按布局（Layout）拆分DXF文件

    每个布局（除Model外）生成一个独立的DXF文件。
    输出DXF包含全部模型空间实体 + 对应布局的图纸空间实体。

    Args:
        dxf_path: 源DXF文件路径
        output_dir: 输出目录
        layout_names: 要拆分的布局名称列表，None则拆分所有非Model布局

    Returns:
        输出DXF文件路径列表
    """
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(dxf_path))[0]

    try:
        source_doc = ezdxf.readfile(dxf_path)
    except Exception as e:
        logger.error(f"读取DXF失败: {dxf_path}: {e}")
        return []

    if layout_names is None:
        try:
            layout_names = [l.name for l in source_doc.layouts
                           if l.name not in ("Model", "MODEL")]
        except Exception:
            layout_names = []

    if not layout_names:
        return split_single_dxf(dxf_path, output_dir)

    results = []

    for i, layout_name in enumerate(layout_names):
        safe_name = layout_name.replace("/", "_").replace("\\", "_").replace(":", "_")
        out_name = f"{base}_L{i+1:02d}_{safe_name}"
        out_path = os.path.join(output_dir, f"{out_name}.dxf")

        try:
            target_doc = ezdxf.new(dxfversion=source_doc.dxfversion)
            target_msp = target_doc.modelspace()

            _copy_layer_defs(source_doc, target_doc)
            _copy_linetype_defs(source_doc, target_doc)
            _copy_text_styles(source_doc, target_doc)
            _copy_dim_styles(source_doc, target_doc)

            used_blocks = set()
            entity_count = 0

            source_msp = source_doc.modelspace()
            for e in source_msp:
                etype = e.dxftype()
                if etype not in ENTITY_TYPES_TO_COPY:
                    continue
                try:
                    target_msp.add_entity(copy.deepcopy(e))
                    entity_count += 1
                    if etype == "INSERT":
                        used_blocks.add(e.dxf.name)
                except Exception:
                    continue

            try:
                src_layout = source_doc.layouts.get(layout_name)
                if src_layout is not None:
                    tgt_layout = target_doc.layouts.new(layout_name)
                    for e in src_layout:
                        etype = e.dxftype()
                        if etype not in ENTITY_TYPES_TO_COPY:
                            continue
                        try:
                            tgt_layout.add_entity(copy.deepcopy(e))
                            entity_count += 1
                            if etype == "INSERT":
                                used_blocks.add(e.dxf.name)
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"布局实体复制警告: {layout_name}: {e}")

            _copy_block_defs(source_doc, target_doc, used_blocks)

            target_doc.saveas(out_path)

            file_kb = os.path.getsize(out_path) / 1024
            logger.info(f"布局拆分: {out_name} → {entity_count}实体, {file_kb:.0f}KB")
            results.append(out_path)

        except Exception as e:
            logger.error(f"布局拆分失败: {out_name}: {e}")
            continue

    if not results:
        return split_single_dxf(dxf_path, output_dir)

    return results