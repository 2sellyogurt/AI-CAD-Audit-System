# -*- coding: utf-8 -*-
"""CAD→PNG批量打印模块

调用本地安装的AutoCAD进行命令行批量打印。
支持 AutoCAD 2018+ / 中望CAD / 浩辰CAD。
"""

import os
import sys
import subprocess
import logging
import time
from typing import List, Optional, Tuple
from .cad_utils import find_autocad

logger = logging.getLogger("v7.cad_print")


def create_print_script(dxf_path: str, output_png: str, dpi: int = 300) -> str:
    """生成AutoCAD批量打印脚本(SCR格式)。"""
    os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)
    abs_dxf = os.path.abspath(dxf_path).replace("\\", "/")
    abs_png = os.path.abspath(output_png).replace("\\", "/")

    script = f"""
FILEDIA 0
CMDDIA 0
_OPEN "{abs_dxf}"
_ZOOM _E
_PLOT
YES
Model
PNG (Portable Network Graphics)
{abs_png}
Millimeters
LANDSCAPE
NO
EXTENTS
FIT
CENTER
YES
monochrome.ctb
YES
NO
NO
NO
YES
_CLOSE
Y
FILEDIA 1
CMDDIA 1
"""
    return script.strip()


def _write_scr_utf8(script_path: str, content: str) -> None:
    """写入SCR脚本。AutoCAD 2021+支持UTF-8带BOM的SCR文件。"""
    with open(script_path, "w", encoding="utf-8-sig") as f:
        f.write(content)


def print_drawing_autocad(dxf_path: str, output_png: str,
                          dpi: int = 300, timeout: int = 120) -> bool:
    """调用AutoCAD命令行打印单张图纸为PNG。

    Returns: True if success.
    """
    acad = find_autocad()
    if not acad:
        logger.error("未找到已安装的AutoCAD")
        return False

    script_content = create_print_script(dxf_path, output_png, dpi)
    script_path = os.path.join(os.path.dirname(output_png),
                               "_acad_print.scr")
    _write_scr_utf8(script_path, script_content)

    try:
        result = subprocess.run(
            [acad, "/b", script_path, "/nologo"],
            capture_output=True, text=True, timeout=timeout
        )
        if os.path.exists(output_png) and os.path.getsize(output_png) > 0:
            logger.info(f"打印成功: {os.path.basename(output_png)}")
            return True
        else:
            logger.error(f"打印失败(无输出文件): {os.path.basename(dxf_path)}")
            if result.stderr:
                logger.error(f"  stderr: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"打印超时: {os.path.basename(dxf_path)}")
        return False
    except Exception as e:
        logger.error(f"打印异常: {e}")
        return False
    finally:
        try:
            os.remove(script_path)
        except Exception as e:
            logger.debug(f"清理打印脚本失败: {script_path}, {e}")


_CJK_FONT_CANDIDATES = [
    "simhei.ttf",
    "simsun.ttc",
    "msyh.ttc",
    "msyhbd.ttc",
    "simkai.ttf",
    "simfang.ttf",
    "NotoSansCJK-Regular.ttc",
    "NotoSansSC-Regular.otf",
    "NotoSerifCJK-Regular.ttc",
    "wqy-microhei.ttc",
    "wqy-zenhei.ttc",
    "SourceHanSansSC-Regular.otf",
]


def _find_font_paths() -> List[str]:
    """发现可用的CJK字体文件路径。"""
    paths = []

    project_fonts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "fonts"
    )
    if os.path.isdir(project_fonts_dir):
        for name in _CJK_FONT_CANDIDATES:
            p = os.path.join(project_fonts_dir, name)
            if os.path.isfile(p):
                paths.append(p)

    for name in _CJK_FONT_CANDIDATES:
        p = os.path.join(project_fonts_dir, name) if os.path.isdir(project_fonts_dir) else ""
        if p and os.path.isfile(p):
            continue
        win_fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
        fp = os.path.join(win_fonts, name)
        if os.path.isfile(fp):
            paths.append(fp)

    return paths


def _load_cjk_font(size: int = 16) -> Tuple[object, str]:
    """加载CJK友好字体，按优先级尝试多来源。
    返回 (font_object, font_source_name)。
    """
    from PIL import ImageFont

    font_paths = _find_font_paths()
    for fp in font_paths:
        try:
            font = ImageFont.truetype(fp, size)
            logger.debug(f"CJK字体加载成功: {os.path.basename(fp)} ({size}px)")
            return font, os.path.basename(fp)
        except Exception as e:
            logger.debug(f"CJK字体加载失败: {fp}, {e}")
            continue

    for name in _CJK_FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(name, size)
            logger.debug(f"CJK字体加载成功(系统路径): {name}")
            return font, name
        except Exception as e:
            logger.debug(f"CJK字体加载失败(系统路径): {name}, {e}")
            continue

    try:
        font = ImageFont.load_default()
        logger.warning("CJK字体未找到，使用Pillow默认字体（中文可能显示为方块）")
        return font, "default"
    except Exception as e:
        logger.warning(f"无可用字体，文本渲染将缺失: {e}")
        return None, "none"


def print_alternative_pillow(dxf_path: str, output_png: str) -> bool:
    """备用方案：使用ezdxf+Pillow渲染纯文本标注（非CAD精度）。

    不依赖AutoCAD，输出的是文本标注截图而非真实CAD视图。
    仅在AutoCAD不可用时使用。
    """
    try:
        from PIL import Image, ImageDraw
        import ezdxf
    except ImportError:
        return False

    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        texts = []
        for e in msp:
            if e.dxftype() in ("TEXT", "MTEXT"):
                text = e.dxf.text if hasattr(e.dxf, "text") else ""
                if text and text.strip():
                    insert = e.dxf.insert
                    texts.append((insert[0], insert[1], text.strip()[:50]))

        if not texts:
            return False

        texts.sort(key=lambda t: t[1], reverse=True)

        img_w, img_h = 2400, 3200
        img = Image.new("RGB", (img_w, img_h), "white")
        draw = ImageDraw.Draw(img)

        font, font_source = _load_cjk_font(16)
        if font is None:
            return False

        margin = 20
        y_pos = margin
        for x, y, text in texts[:200]:
            draw.text((margin, y_pos), f"[{x:.0f},{y:.0f}] {text}", fill="black", font=font)
            y_pos += 22
            if y_pos > img_h - margin:
                break

        os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)
        img.save(output_png, "PNG")
        logger.info(f"备用渲染PNG成功({font_source}): {os.path.basename(output_png)}")
        return True
    except Exception as e:
        logger.warning(f"备用渲染PNG失败: {e}")
        return False


def print_drawing_ezdxf(dxf_path: str, output_png: str, dpi: int = 150) -> bool:
    """使用ezdxf+PyMuPDF渲染DXF为PNG。零依赖AutoCAD，直接解析CAD图形。"""
    try:
        file_mb = os.path.getsize(dxf_path) / (1024 * 1024)
        timeout = 60 if file_mb < 30 else (90 if file_mb < 80 else 180)
        os.makedirs(os.path.dirname(output_png) or ".", exist_ok=True)
        result = subprocess.run(
            [sys.executable, "-m", "ezdxf", "draw", "-o", output_png, dxf_path],
            capture_output=True, text=True, timeout=timeout
        )
        if os.path.exists(output_png) and os.path.getsize(output_png) > 0:
            logger.info(f"ezdxf渲染成功: {os.path.basename(output_png)} ({os.path.getsize(output_png)} bytes, {file_mb:.0f}MB)")
            return True
        else:
            return False
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        logger.warning(f"ezdxf渲染失败: {dxf_path}, {e}")
        return False


def print_drawing_smart(dxf_path: str, output_png: str) -> bool:
    """智能渲染双策略。

    1. PIL原生渲染 (ezdxf解析+PIL绘图, ~2-5s, <30MB)
    2. Pillow文字标注图 (仅TEXT/MTEXT, ~3-10s, 通用备选)
    
    ezdxf matplotlib后端已禁用(太慢, ~60-250s/文件)。
    """
    from .pil_renderer import render_dxf_pil

    result = render_dxf_pil(dxf_path, output_png)
    if result:
        return True

    return print_alternative_pillow(dxf_path, output_png)
