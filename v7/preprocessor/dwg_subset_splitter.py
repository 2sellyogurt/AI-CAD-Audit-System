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
            except Exception as e:
                logger.debug(f"DIMENSION包围盒计算失败: {e}")
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
            except Exception as e:
                logger.debug(f"HATCH包围盒计算失败: {e}")
            return None
        elif etype == "POINT":
            loc = entity.dxf.location
            return (loc[0], loc[1], loc[0], loc[1])
        elif etype == "ELLIPSE":
            cx, cy = entity.dxf.center[0], entity.dxf.center[1]
            if hasattr(entity.dxf, "major_axis") and entity.dxf.major_axis:
                # major_axis 是向量，使用模长
                rx = (entity.dxf.major_axis[0]**2 + entity.dxf.major_axis[1]**2)**0.5
            else:
                rx = 100
            if hasattr(entity.dxf, "minor_axis") and entity.dxf.minor_axis:
                # minor_axis 是向量，使用模长
                ry = (entity.dxf.minor_axis[0]**2 + entity.dxf.minor_axis[1]**2)**0.5
            else:
                ry = 100
            rx = rx if rx else 100
            ry = ry if ry else 100
            return (cx - rx, cy - ry, cx + rx, cy + ry)
        elif etype == "SPLINE":
            try:
                ctrl_pts = entity.control_points
                if ctrl_pts:
                    xs = [p[0] for p in ctrl_pts]
                    ys = [p[1] for p in ctrl_pts]
                    return (min(xs), min(ys), max(xs), max(ys))
            except Exception as e:
                logger.debug(f"SPLINE包围盒计算失败: {e}")
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
            if hasattr(entity, 'get_bbox'):
                try:
                    bbox = entity.get_bbox()
                    if bbox is not None:
                        return (bbox.extmin.x, bbox.extmin.y, bbox.extmax.x, bbox.extmax.y)
                except Exception as e:
                    logger.debug(f"IMAGE包围盒计算失败: {e}")
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
            except Exception as e:
                logger.debug(f"WIPEOUT包围盒计算失败: {e}")
            return None
        return None
    except Exception as e:
        logger.debug(f"实体包围盒计算失败: {e}")
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


def _copy_table_defs(source_doc, target_doc, table_name: str, copy_attrs: bool = False):
    """通用表格定义复制函数
    
    Args:
        source_doc: 源文档
        target_doc: 目标文档
        table_name: 表格名称 ('layers', 'linetypes', 'styles', 'dimstyles')
        copy_attrs: 是否复制额外属性 (仅 layers 需要 color/linetype)
    """
    try:
        source_table = getattr(source_doc, table_name)
        target_table = getattr(target_doc, table_name)
        
        for item in source_table:
            if item.dxf.name not in target_table:
                new_item = target_table.new(name=item.dxf.name)
                if copy_attrs and table_name == "layers":
                    try:
                        new_item.dxf.color = item.dxf.color
                    except Exception as e:
                        logger.debug(f"图层属性复制失败(color): {e}")
                    try:
                        new_item.dxf.linetype = item.dxf.linetype
                    except Exception as e:
                        logger.debug(f"图层属性复制失败(linetype): {e}")
    except Exception as e:
        logger.debug(f"表格定义复制失败: {e}")


def _copy_layer_defs(source_doc, target_doc):
    _copy_table_defs(source_doc, target_doc, "layers", copy_attrs=True)


def _copy_linetype_defs(source_doc, target_doc):
    _copy_table_defs(source_doc, target_doc, "linetypes")


def _copy_text_styles(source_doc, target_doc):
    _copy_table_defs(source_doc, target_doc, "styles")


def _copy_dim_styles(source_doc, target_doc):
    _copy_table_defs(source_doc, target_doc, "dimstyles")


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
                        tgt_entity = src_entity.copy()
                        tgt_block.add_entity(tgt_entity)
                    except Exception as e:
                        logger.debug(f"图块实体复制失败: {e}")
                        continue
            except Exception as e:
                logger.debug(f"图块定义复制失败: {e}")
                continue
    except Exception as e:
        logger.debug(f"图块列表复制失败: {e}")
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
                        new_entity = e.copy()
                        target_msp.add_entity(new_entity)
                        entity_count += 1
                        if etype == "INSERT":
                            used_blocks.add(e.dxf.name)
                    except Exception as e2:
                        logger.debug(f"实体复制失败: {e2}")
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
        except Exception as e:
            logger.warning(f"全量复制失败: {e}")

    return results


def split_single_dxf(dxf_path: str, output_dir: str) -> List[str]:
    src_copy = os.path.join(output_dir, os.path.basename(dxf_path))
    try:
        doc = ezdxf.readfile(dxf_path)
        doc.saveas(src_copy)
        return [src_copy]
    except Exception as e:
        logger.warning(f"单文件保存失败: {dxf_path}, {e}")
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
        except Exception as e:
            logger.debug(f"获取布局列表失败: {e}")
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

            # M-28修复：对于多布局文件，只复制布局视口引用的实体
            # 而不是整个模型空间，避免不同布局内容混在一起
            try:
                src_layout = source_doc.layouts.get(layout_name)
                if src_layout is not None:
                    # 获取布局的视口
                    viewports = [e for e in src_layout if e.dxftype() == "VIEWPORT"]
                    if viewports:
                        # 有视口，只复制视口范围内的模型空间实体
                        for vp in viewports:
                            if hasattr(vp.dxf, 'view_center_point') and hasattr(vp.dxf, 'view_height'):
                                vp_center = vp.dxf.view_center_point
                                vp_height = vp.dxf.view_height
                                # 计算视口范围（简化处理）
                                vp_width = vp_height * (vp.dxf.width / vp.dxf.height) if hasattr(vp.dxf, 'width') and hasattr(vp.dxf, 'height') else vp_height
                                vp_min_x = vp_center[0] - vp_width / 2
                                vp_max_x = vp_center[0] + vp_width / 2
                                vp_min_y = vp_center[1] - vp_height / 2
                                vp_max_y = vp_center[1] + vp_height / 2

                                # 复制视口范围内的模型空间实体
                                source_msp = source_doc.modelspace()
                                for e in source_msp:
                                    etype = e.dxftype()
                                    if etype not in ENTITY_TYPES_TO_COPY:
                                        continue
                                    try:
                                        # 简单检查实体是否在视口范围内
                                        if hasattr(e.dxf, 'insert'):
                                            ex, ey = e.dxf.insert[0], e.dxf.insert[1]
                                            if vp_min_x <= ex <= vp_max_x and vp_min_y <= ey <= vp_max_y:
                                                target_msp.add_entity(copy.deepcopy(e))
                                                entity_count += 1
                                                if etype == "INSERT":
                                                    used_blocks.add(e.dxf.name)
                                        elif hasattr(e.dxf, 'center'):
                                            ex, ey = e.dxf.center[0], e.dxf.center[1]
                                            if vp_min_x <= ex <= vp_max_x and vp_min_y <= ey <= vp_max_y:
                                                target_msp.add_entity(copy.deepcopy(e))
                                                entity_count += 1
                                                if etype == "INSERT":
                                                    used_blocks.add(e.dxf.name)
                                    except Exception as e:
                                        logger.debug(f"视口实体复制失败: {e}")
                                        continue

                    # 复制布局空间（paper space）的实体
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
                        except Exception as e:
                            logger.debug(f"布局空间实体复制失败: {e}")
                            continue
            except Exception as e:
                logger.warning(f"处理布局 {layout_name} 失败: {e}")

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