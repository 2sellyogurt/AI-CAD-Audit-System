# -*- coding: utf-8 -*-
"""PIL原生DXF渲染器

从第一性原理出发：ezdxf解析 + PIL绘图 + CJK字体 = 零新依赖的CAD→PNG。
跳过PyMuPDF重型引擎，牺牲精度换取3-5倍速度提升。
"""

import os
import logging
from typing import Optional

import ezdxf
from PIL import Image, ImageDraw

from .cad_printer import _load_cjk_font

logger = logging.getLogger("v7.pil_renderer")

RENDER_DPI = 120


def _compute_bounding_box(msp, blocks=None, margin: float = 0.05):
    xs, ys = [], []

    def _add_point(px, py):
        xs.append(px)
        ys.append(py)

    def _add_points(pts):
        for p in pts:
            if len(p) >= 2:
                xs.append(p[0])
                ys.append(p[1])

    for e in msp:
        try:
            etype = e.dxftype()
            if etype == "LINE":
                _add_point(e.dxf.start[0], e.dxf.start[1])
                _add_point(e.dxf.end[0], e.dxf.end[1])
            elif etype == "LWPOLYLINE":
                _add_points(e.get_points())
            elif etype == "POLYLINE":
                _add_points([(v.dxf.location[0], v.dxf.location[1])
                             for v in e.vertices if hasattr(v.dxf, "location")])
            elif etype == "CIRCLE":
                cx, cy, r = e.dxf.center[0], e.dxf.center[1], e.dxf.radius
                _add_point(cx - r, cy - r)
                _add_point(cx + r, cy + r)
            elif etype == "ARC":
                cx, cy = e.dxf.center[0], e.dxf.center[1]
                r = e.dxf.radius
                sa, ea = e.dxf.start_angle, e.dxf.end_angle
                import math as _math
                for a in [sa, ea]:
                    _add_point(cx + r * _math.cos(_math.radians(a)),
                               cy + r * _math.sin(_math.radians(a)))
            elif etype == "TEXT":
                _add_point(e.dxf.insert[0], e.dxf.insert[1])
            elif etype == "MTEXT":
                _add_point(e.dxf.insert[0], e.dxf.insert[1])
            elif etype == "INSERT":
                ip = e.dxf.insert
                _add_point(ip[0], ip[1])
            elif etype == "POINT":
                loc = e.dxf.location
                _add_point(loc[0], loc[1])
            elif etype == "SPLINE":
                try:
                    ctrl_pts = e.control_points
                    if ctrl_pts:
                        _add_points([(p[0], p[1]) for p in ctrl_pts])
                    else:
                        fit_pts = e.fit_points
                        if fit_pts:
                            _add_points([(p[0], p[1]) for p in fit_pts])
                except Exception:
                    pass
            elif etype == "ELLIPSE":
                cx, cy = e.dxf.center[0], e.dxf.center[1]
                mx = e.dxf.major_axis[0]
                my = e.dxf.major_axis[1]
                _mx, _my = mx, my
                r_major = (_mx * _mx + _my * _my) ** 0.5
                _add_point(cx - r_major, cy - r_major)
                _add_point(cx + r_major, cy + r_major)
            elif etype == "HATCH":
                try:
                    for path in e.paths:
                        for seg in path:
                            if hasattr(seg, 'vertices'):
                                _add_points([(v[0], v[1]) for v in seg.vertices])
                except Exception:
                    pass
        except Exception:
            continue

    if not xs:
        return None
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if x_max <= x_min or y_max <= y_min:
        return None
    dx = (x_max - x_min) * margin
    dy = (y_max - y_min) * margin
    return (x_min - dx, y_min - dy, x_max + dx, y_max + dy)


def _check_image_whiteness(img_path: str) -> bool:
    try:
        import numpy as np
        arr = np.array(Image.open(img_path).convert("L"))
        if arr.size == 0:
            return True
        dark_pixels = (arr < 200).sum()
        return dark_pixels < 50
    except Exception:
        return False


def _expand_insert_entities(msp, blocks, max_depth=2, max_total=100000):
    """将INSERT图块展开为平铺实体列表，应用变换矩阵。"""
    expanded = []
    _expand_inserts(msp, blocks, expanded, 0, max_depth,
                    1.0, 1.0, 0.0, 0.0, 0.0, max_total)
    return expanded


def _expand_inserts(entities, blocks, result, depth, max_depth,
                    sx, sy, rot, dx, dy, max_total):
    if depth > max_depth or len(result) >= max_total:
        return
    import math as _math
    cos_r = _math.cos(rot)
    sin_r = _math.sin(rot)
    for e in entities:
        try:
            et = e.dxftype()
            if et == "INSERT":
                block_name = e.dxf.name
                if block_name in blocks:
                    blk = blocks[block_name]
                    ip = e.dxf.insert
                    nsx = e.dxf.xscale if hasattr(e.dxf, 'xscale') else 1.0
                    nsy = e.dxf.yscale if hasattr(e.dxf, 'yscale') else 1.0
                    nr = e.dxf.rotation * _math.pi / 180.0 if hasattr(e.dxf, 'rotation') else 0.0
                    ndx = ip[0]
                    ndy = ip[1]
                    _expand_inserts(blk, blocks, result, depth + 1, max_depth,
                                    sx * nsx, sy * nsy, rot + nr,
                                    dx + ndx * sx * cos_r - ndy * sy * sin_r,
                                    dy + ndx * sx * sin_r + ndy * sy * cos_r)
            else:
                result.append((e, sx, sy, cos_r, sin_r, dx, dy))
        except Exception:
            continue


def render_dxf_pil(dxf_path: str, output_png: str, max_entities: int = 50000,
                   existing_doc=None, x_min=None, y_min=None, x_max=None, y_max=None) -> bool:
    try:
        file_mb = os.path.getsize(dxf_path) / (1024 * 1024)
        if file_mb > 80 and existing_doc is None:
            logger.info(f"文件过大({file_mb:.0f}MB)，跳过几何渲染，直接用文本方案: "
                        f"{os.path.basename(dxf_path)}")
            from .cad_printer import print_alternative_pillow
            return print_alternative_pillow(dxf_path, output_png)

        if existing_doc is not None:
            doc = existing_doc
        else:
            doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception:
        return False

    try:
        if x_min is None or y_min is None or x_max is None or y_max is None:
            bbox = _compute_bounding_box(msp, blocks=doc.blocks if hasattr(doc, 'blocks') else None)
            if bbox is None:
                logger.warning(f"包围盒计算失败(无可用几何实体): {os.path.basename(dxf_path)}")
                return False
            x_min, y_min, x_max, y_max = bbox
        dw = x_max - x_min
        dh = y_max - y_min
        if dw <= 0 or dh <= 0:
            logger.warning(f"包围盒尺寸无效(dw={dw:.1f}, dh={dh:.1f}): "
                           f"{os.path.basename(dxf_path)}")
            return False

        scale = RENDER_DPI / 25.4
        img_w = int(dw * scale)
        img_h = int(dh * scale)
        if img_w < 50 or img_h < 50:
            logger.warning(f"包围盒过小(dw={dw:.1f}mm, dh={dh:.1f}mm): "
                           f"{os.path.basename(dxf_path)}")
            return False

        img_w = max(min(img_w, 6000), 800)
        img_h = max(min(img_h, 4800), 600)

        img = Image.new("RGB", (img_w, img_h), "white")
        draw = ImageDraw.Draw(img)
        font, _ = _load_cjk_font(14)

        def tx(x):
            return (x - x_min) * scale

        def ty(y):
            return img_h - (y - y_min) * scale

        def _xfm(pt_x, pt_y):
            """应用INSERT变换后映射到像素坐标"""
            wx = dx + (pt_x * sx * cos_r - pt_y * sy * sin_r)
            wy = dy + (pt_x * sx * sin_r + pt_y * sy * cos_r)
            return tx(wx), ty(wy)

        entity_count = 0
        rendered_entities = list(msp)
        blocks = doc.blocks if hasattr(doc, 'blocks') else {}

        if blocks:
            try:
                expanded = _expand_insert_entities(msp, blocks)
                if expanded:
                    rendered_entities = expanded
            except Exception:
                pass

        for item in rendered_entities:
            if entity_count >= max_entities:
                break
            try:
                if isinstance(item, tuple):
                    e, sx, sy, cos_r, sin_r, dx, dy = item
                else:
                    e = item
                    sx, sy, cos_r, sin_r, dx, dy = 1.0, 1.0, 1.0, 0.0, 0.0, 0.0

                etype = e.dxftype()
                if etype == "LINE":
                    px1, py1 = _xfm(e.dxf.start[0], e.dxf.start[1])
                    px2, py2 = _xfm(e.dxf.end[0], e.dxf.end[1])
                    draw.line([(px1, py1), (px2, py2)], fill="black", width=1)
                    entity_count += 1
                elif etype == "CIRCLE":
                    cx, cy = _xfm(e.dxf.center[0], e.dxf.center[1])
                    r = e.dxf.radius * abs(sx) * scale
                    if r > 0.5:
                        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline="black", width=1)
                    entity_count += 1
                elif etype == "ARC":
                    cx, cy = _xfm(e.dxf.center[0], e.dxf.center[1])
                    r = e.dxf.radius * abs(sx) * scale
                    if r > 1:
                        a1, a2 = e.dxf.start_angle, e.dxf.end_angle
                        a1_t = 360 - a1
                        a2_t = 360 - a2
                        try:
                            draw.arc([(cx - r, cy - r), (cx + r, cy + r)],
                                     a1_t, a2_t, fill="black", width=1)
                        except Exception:
                            draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)],
                                         outline="black", width=1)
                    entity_count += 1
                elif etype in ("LWPOLYLINE", "POLYLINE"):
                    pts = []
                    if etype == "LWPOLYLINE":
                        pts = [_xfm(p[0], p[1]) for p in e.get_points()]
                    else:
                        pts = [_xfm(v.dxf.location[0], v.dxf.location[1])
                               for v in e.vertices if hasattr(v.dxf, "location")]
                    if len(pts) >= 2:
                        is_closed = e.closed if hasattr(e, 'closed') else False
                        if is_closed and len(pts) > 2:
                            pts = list(pts) + [pts[0]]
                        draw.line(pts, fill="black", width=1)
                    entity_count += 1
                elif etype == "TEXT":
                    x, y = _xfm(e.dxf.insert[0], e.dxf.insert[1])
                    text = e.dxf.text
                    if text and text.strip():
                        draw.text((x, y - 10), text.strip()[:80], fill="blue", font=font)
                    entity_count += 1
                elif etype == "MTEXT":
                    x, y = _xfm(e.dxf.insert[0], e.dxf.insert[1])
                    text = e.plain_text() if hasattr(e, "plain_text") else e.text
                    if text and text.strip():
                        clean = text.replace("\\P", "\n")[:200]
                        for line_idx, line_text in enumerate(clean.split("\n")[:10]):
                            draw.text((x, y - 10 + line_idx * 16), line_text.strip()[:80],
                                      fill="blue", font=font)
                    entity_count += 1
            except Exception:
                continue

        os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)
        img.save(output_png, "PNG")

        file_size = os.path.getsize(output_png)
        logger.info(f"PIL渲染完成: {os.path.basename(output_png)} "
                     f"({img_w}x{img_h}px, {entity_count}/{max_entities}实体, "
                     f"{file_size} bytes)")

        if _check_image_whiteness(output_png):
            logger.warning(f"PIL渲染结果空白，交由上层回退: "
                           f"{os.path.basename(output_png)}")
            return False

        return True

    except Exception as e:
        logger.error(f"PIL渲染失败: {e}")
        return False
