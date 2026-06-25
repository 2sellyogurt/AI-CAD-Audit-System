# -*- coding: utf-8 -*-
"""VLM语义提取器 - 使用视觉LLM从图纸图片提取语义标签

功能：
1. 楼栋识别：从图纸标题栏/图名识别楼栋号
2. 楼层识别：从图纸识别楼层信息
3. 构件类型识别：识别图纸中的主要构件类型（梁/柱/墙/风管等）

核心策略：VLM做语义理解 + ezdxf做坐标计算
"""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("v7.preprocessor.vlm_semantic_extractor")


@dataclass
class SemanticLabel:
    """语义标签"""
    building: str = ""          # 楼栋号（如"1"、"A"）
    floor: Optional[int] = None  # 楼层（如3表示3层，-1表示B1）
    drawing_type: str = ""      # 图纸类型（平面图/立面图/剖面图）
    components: List[str] = field(default_factory=list)  # 构件类型列表
    confidence: float = 0.0     # 整体置信度
    source: str = "vlm"         # 来源（vlm/regex/fallback）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "building": self.building,
            "floor": self.floor,
            "drawing_type": self.drawing_type,
            "components": self.components,
            "confidence": self.confidence,
            "source": self.source,
        }


# 构件类型标准列表
COMPONENT_TYPES = [
    "beam",         # 梁
    "column",       # 柱
    "wall",         # 墙（剪力墙/承重墙）
    "slab",         # 板
    "duct",         # 风管
    "pipe",         # 水管
    "cable_tray",   # 电缆桥架
    "window",       # 窗
    "door",         # 门
    "stair",        # 楼梯
    "elevator",     # 电梯
    "foundation",   # 基础
]

# DXF层名到构件类型的映射（用于fallback和互补验证）
LAYER_TO_COMPONENT = {
    # 结构
    "S-BEAM": "beam", "S-COLUMN": "column", "S-WALL": "wall",
    "S-SLAB": "slab", "S-FOUND": "foundation",
    "S-BEAM-STRUCT": "beam", "S-COLUMN-STRUCT": "column",
    "WALL": "wall", "BEAM": "beam", "COLUMN": "column",
    # 建筑
    "A-WALL": "wall", "A-DOOR": "door", "A-WINDOW": "window",
    "A-STAIR": "stair", "A-ELEV": "elevator",
    "DOOR": "door", "WINDOW": "window",
    # 暖通
    "M-DUCT": "duct", "M-DUCT-SUPPLY": "duct", "M-DUCT-RETURN": "duct",
    "M-PIPE": "pipe", "M-PIPE-SUPPLY": "pipe", "M-PIPE-RETURN": "pipe",
    "DUCT": "duct", "HVAC-DUCT": "duct",
    # 给排水
    "P-PIPE": "pipe", "P-WATER": "pipe", "P-DRAIN": "pipe",
    "PLUMB-PIPE": "pipe", "FIRE-PIPE": "pipe",
    # 电气
    "E-CABLE": "cable_tray", "E-TRAY": "cable_tray",
    "ELEC-CABLE": "cable_tray", "CABLE": "cable_tray",
}

# 楼层名称映射
FLOOR_NAME_MAP = {
    "一层": 1, "二层": 2, "三层": 3, "四层": 4, "五层": 5,
    "六层": 6, "七层": 7, "八层": 8, "九层": 9, "十层": 10,
    "1F": 1, "2F": 2, "3F": 3, "4F": 4, "5F": 5,
    "6F": 6, "7F": 7, "8F": 8, "9F": 9, "10F": 10,
    "B1": -1, "B2": -2, "B3": -3, "B4": -4, "B5": -5,
    "地下1层": -1, "地下2层": -2, "地下3层": -3,
    "屋顶层": 99, "屋顶": 99, "机房层": 100,
}


class VLMSemanticExtractor:
    """VLM语义提取器"""

    def __init__(self, max_retries: int = 2):
        self._max_retries = max_retries

    def extract_all(self, image_path: str, drawing_name: str = "",
                    dxf_layers: Optional[List[str]] = None) -> SemanticLabel:
        """综合提取语义标签（VLM + 正则fallback + 层名映射）

        Args:
            image_path: 图纸图片路径
            drawing_name: 图纸文件名（用于正则fallback）
            dxf_layers: DXF层名列表（用于层名映射）
        """
        label = SemanticLabel()

        # 1. 正则提取（快速、零成本）
        regex_label = self._extract_by_regex(drawing_name)
        if regex_label.building:
            label.building = regex_label.building
            label.source = "regex"
        if regex_label.floor is not None:
            label.floor = regex_label.floor
            label.source = "regex"
        if regex_label.drawing_type:
            label.drawing_type = regex_label.drawing_type

        # 2. 层名映射（互补验证）
        if dxf_layers:
            layer_components = self._classify_by_layers(dxf_layers)
            label.components.extend(layer_components)

        # 3. VLM提取（语义理解，补充正则无法覆盖的部分）
        if image_path and os.path.exists(image_path):
            vlm_label = self._extract_by_vlm(image_path)
            if vlm_label:
                # VLM结果补充正则未覆盖的字段
                if not label.building and vlm_label.building:
                    label.building = vlm_label.building
                    label.source = "vlm"
                if label.floor is None and vlm_label.floor is not None:
                    label.floor = vlm_label.floor
                    label.source = "vlm"
                if not label.drawing_type and vlm_label.drawing_type:
                    label.drawing_type = vlm_label.drawing_type
                # VLM构件识别与层名映射合并去重
                for comp in vlm_label.components:
                    if comp not in label.components:
                        label.components.append(comp)
                label.confidence = vlm_label.confidence

        # 去重
        label.components = list(dict.fromkeys(label.components))

        # 默认值（不再编造楼栋号，保留None表示未识别）
        if not label.building:
            logger.warning("未能识别楼栋号，building字段保持None")
        if not label.source:
            label.source = "fallback"

        return label

    def _extract_by_regex(self, drawing_name: str) -> SemanticLabel:
        """正则提取楼栋号和楼层"""
        label = SemanticLabel(source="regex")
        if not drawing_name:
            return label

        name = drawing_name.replace("\\", "/").split("/")[-1]  # 取文件名

        # 楼栋号匹配
        building_patterns = [
            r'(\d+)\s*[号楼栋#]',
            r'([一二三四五六七八九十]+)\s*[号楼栋]',
            r'([A-Z])\s*[号楼栋]',
            r'(\d+)\s*#\s*楼',
        ]
        for pattern in building_patterns:
            m = re.search(pattern, name)
            if m:
                label.building = m.group(1)
                break

        # 楼层匹配
        floor_patterns = [
            r'(\d+)\s*[Ff层]',
            r'第\s*(\d+)\s*[层楼]',
            r'B(\d+)\s*[Ff层]?',
            r'地下\s*(\d+)\s*[层楼]',
        ]
        for pattern in floor_patterns:
            m = re.search(pattern, name)
            if m:
                val = m.group(1)
                if pattern.startswith(r'B') or '地下' in pattern:
                    label.floor = -int(val)
                else:
                    label.floor = int(val)
                break

        # 中文楼层名
        for cn_name, floor_num in FLOOR_NAME_MAP.items():
            if cn_name in name:
                label.floor = floor_num
                break

        # 图纸类型匹配
        type_keywords = {
            "平面图": "plan", "平面": "plan",
            "立面图": "elevation", "立面": "elevation",
            "剖面图": "section", "剖面": "section",
            "详图": "detail", "大样": "detail",
            "总图": "site",
        }
        for kw, dtype in type_keywords.items():
            if kw in name:
                label.drawing_type = dtype
                break

        return label

    def _classify_by_layers(self, layers: List[str]) -> List[str]:
        """从DXF层名推断构件类型"""
        components = []
        for layer in layers:
            layer_upper = layer.upper().strip()
            # 精确匹配
            if layer_upper in LAYER_TO_COMPONENT:
                comp = LAYER_TO_COMPONENT[layer_upper]
                if comp not in components:
                    components.append(comp)
                continue
            # 前缀匹配
            for prefix, comp in LAYER_TO_COMPONENT.items():
                if layer_upper.startswith(prefix):
                    if comp not in components:
                        components.append(comp)
                    break
        return components

    def _extract_by_vlm(self, image_path: str) -> Optional[SemanticLabel]:
        """使用VLM提取语义标签"""
        try:
            from v7.llm import llm_call_json
        except ImportError:
            logger.warning("VLM模块不可用，跳过VLM提取")
            return None

        prompt = f"""请从这张建筑图纸中识别以下信息，以JSON格式输出：

{{
  "building": "楼栋号（如1、2、A、B，找不到填null）",
  "floor": 楼层数字（如3表示3层，-1表示B1，找不到填null）,
  "drawing_type": "图纸类型（plan/elevation/section/detail，找不到填null）",
  "components": ["构件类型列表，从以下选项选择：{', '.join(COMPONENT_TYPES)}"]
}}

要求：
1. 楼栋号从标题栏或图名中识别
2. 楼层从图名或标注中识别
3. 构件类型根据图纸内容判断
4. 仅输出JSON，不要其他文字"""

        system = "你是专业的建筑图纸分析助手，擅长识别图纸类型和构件。请严格按JSON格式输出。"

        for attempt in range(self._max_retries):
            try:
                result, provider = llm_call_json(
                    prompt=prompt,
                    system=system,
                    mode="vision",
                    image_paths=[image_path]
                )

                if result and "raw_text" not in result:
                    label = SemanticLabel(source="vlm")

                    # 楼栋号
                    building = result.get("building")
                    if building and str(building) != "null":
                        label.building = str(building)

                    # 楼层
                    floor = result.get("floor")
                    if floor is not None and str(floor) != "null":
                        try:
                            label.floor = int(float(floor))
                        except (ValueError, TypeError):
                            pass

                    # 图纸类型
                    dtype = result.get("drawing_type")
                    if dtype and str(dtype) != "null":
                        label.drawing_type = str(dtype)

                    # 构件类型
                    comps = result.get("components", [])
                    if isinstance(comps, list):
                        label.components = [c for c in comps if c in COMPONENT_TYPES]

                    # 动态置信度计算：基于提取到的字段数量和质量
                    extracted_fields = sum([
                        1 if label.building else 0,
                        1 if label.floor is not None else 0,
                        1 if label.drawing_type else 0,
                        1 if label.components else 0,
                    ])
                    # 基础置信度0.6，每多提取一个字段+0.1，最高0.95
                    label.confidence = min(0.6 + extracted_fields * 0.1, 0.95)

                    logger.info(f"VLM语义提取成功: building={label.building}, "
                               f"floor={label.floor}, components={label.components}, "
                               f"confidence={label.confidence:.2f}")
                    return label

            except Exception as e:
                logger.error(f"VLM语义提取失败 (attempt {attempt+1}): {e}")

        return None


# 便捷函数
def extract_semantic_label(image_path: str, drawing_name: str = "",
                           dxf_layers: Optional[List[str]] = None) -> SemanticLabel:
    """便捷函数：提取语义标签"""
    extractor = VLMSemanticExtractor()
    return extractor.extract_all(image_path, drawing_name, dxf_layers)
