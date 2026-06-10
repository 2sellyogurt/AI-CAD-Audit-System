# -*- coding: utf-8 -*-
"""自适应网格切片器

将大幅面图纸PNG按像素密度自适应切分为网格子图，
每格独立送视觉LLM，避免缩略图丢失细节。
参考: projects/src/utils/adaptive_grid_ocr.py
"""

import gc
import os
import logging
import tempfile
from typing import List, Tuple

import cv2
import numpy as np

logger = logging.getLogger("v7.grid_splitter")

GRID_PIXEL_MAP = [
    (1_000_000, (4, 4)),
    (4_000_000, (6, 6)),
    (16_000_000, (8, 8)),
    (64_000_000, (12, 12)),
    (float("inf"), (18, 18)),
]


def _determine_grid_size(image_path: str) -> Tuple[int, int]:
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return (8, 8)
    h, w = img.shape[:2]
    pixels = w * h
    for limit, (rows, cols) in GRID_PIXEL_MAP:
        if pixels < limit:
            return (rows, cols)
    return (18, 18)


def _compute_text_density_map(image_path: str, grid_rows: int, grid_cols: int) -> np.ndarray:
    """生成文本密度热力图，标记每个网格的文字含量。"""
    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return np.ones((grid_rows, grid_cols))
        h, w = img.shape
        cell_h, cell_w = h // grid_rows, w // grid_cols
        density_map = np.zeros((grid_rows, grid_cols))

        for r in range(grid_rows):
            for c in range(grid_cols):
                y1, y2 = r * cell_h, min((r + 1) * cell_h, h)
                x1, x2 = c * cell_w, min((c + 1) * cell_w, w)
                cell = img[y1:y2, x1:x2]
                binary = cv2.threshold(cell, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
                text_pixel_ratio = np.count_nonzero(binary) / max(binary.size, 1)
                density_map[r, c] = text_pixel_ratio

        return density_map
    except Exception:
        return np.ones((grid_rows, grid_cols))


def split_to_grid(
    image_path: str,
    min_density: float = 0.005,
    output_dir: str = "",
) -> List[str]:
    """将图纸PNG切分为网格子图，跳过空白区域。

    Args:
        image_path: 原始PNG路径
        min_density: 最小文字密度阈值，低于此值的网格跳过
        output_dir: 输出目录，默认使用临时目录

    Returns:
        非空白网格的临时PNG文件路径列表
    """
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="grid_")

    img = cv2.imread(image_path)
    if img is None:
        logger.warning(f"无法读取图片: {image_path}")
        return [image_path]

    h, w = img.shape[:2]
    pixels = w * h
    rows, cols = _determine_grid_size(image_path)
    density_map = _compute_text_density_map(image_path, rows, cols)

    logger.debug(
        f"网格切分: {w}x{h}px ({pixels/1e6:.1f}MP) → {rows}x{cols}={rows*cols}格"
    )

    cell_h, cell_w = h // rows, w // cols
    grid_paths = []
    skipped = 0

    for r in range(rows):
        for c in range(cols):
            if density_map[r, c] < min_density:
                skipped += 1
                continue

            y1, y2 = r * cell_h, min((r + 1) * cell_h, h)
            x1, x2 = c * cell_w, min((c + 1) * cell_w, w)
            cell = img[y1:y2, x1:x2]

            _, tmp_path = tempfile.mkstemp(
                suffix=f"_r{r}c{c}.png", prefix="grid_", dir=output_dir
            )
            os.close(_)

            cv2.imwrite(tmp_path, cell, [cv2.IMWRITE_PNG_COMPRESSION, 3])
            grid_paths.append(tmp_path)

        if (r * cols + c + 1) % 5 == 0:
            gc.collect()

    logger.debug(
        f"网格切片完成: {len(grid_paths)}个有效网格, 跳过{skipped}个空白"
    )
    return grid_paths if grid_paths else [image_path]


def cleanup_grids(grid_paths: List[str]) -> None:
    for p in grid_paths:
        try:
            os.remove(p)
        except OSError:
            pass
