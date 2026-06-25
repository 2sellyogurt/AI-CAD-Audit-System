# -*- coding: utf-8 -*-
"""PNG图纸增强器

在喂给视觉LLM之前对图纸截图进行预处理：
  1. 高斯去噪 → 2. LAB对比度增强 → 3. 亮度提升 → 4. 锐化
参考: projects/src/utils/image_preprocessor.py 的 OpenCV 增强管道
"""

import os
import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("v7.image_enhancer")

GAUSSIAN_KERNEL = 3
CONTRAST_FACTOR = 1.3
BRIGHTNESS_DELTA = 25
SHARPEN_KERNEL = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)


def enhance_png(
    input_path: str,
    output_path: Optional[str] = None,
    contrast: float = CONTRAST_FACTOR,
    brightness: float = BRIGHTNESS_DELTA,
) -> str:
    """对PNG图纸截图执行增强管道，返回输出路径。"""
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_enhanced{ext}"

    try:
        img = cv2.imread(input_path)
        if img is None:
            logger.warning(f"无法读取图片: {input_path}")
            return input_path

        img = cv2.GaussianBlur(img, (GAUSSIAN_KERNEL, GAUSSIAN_KERNEL), 0)

        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        l_channel = cv2.convertScaleAbs(l_channel, alpha=contrast, beta=0)
        img = cv2.merge([l_channel, a_channel, b_channel])
        img = cv2.cvtColor(img, cv2.COLOR_LAB2BGR)

        img = cv2.convertScaleAbs(img, alpha=1.0, beta=brightness)

        img = cv2.filter2D(img, -1, SHARPEN_KERNEL)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        cv2.imwrite(output_path, img, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        logger.debug(f"图片增强完成: {os.path.basename(output_path)}")
        return output_path

    except Exception as e:
        logger.warning(f"图片增强失败, 退回原始图片: {e}")
        return input_path


def enhance_text_only(input_path: str, output_path: Optional[str] = None) -> str:
    """专为OCR准备的增强：二值化 + 形态学闭操作连接断裂笔画。"""
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_text{ext}"

    try:
        img = cv2.imread(input_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return input_path

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        img = clahe.apply(img)

        _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        cv2.imwrite(output_path, binary, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        logger.debug(f"文字增强完成: {os.path.basename(output_path)}")
        return output_path

    except Exception as e:
        logger.warning(f"文字增强失败: {e}")
        return input_path
