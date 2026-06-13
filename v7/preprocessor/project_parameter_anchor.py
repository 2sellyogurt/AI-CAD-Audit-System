# -*- coding: utf-8 -*-
"""项目参数锚定模块 - 从DXF图框自动提取关键建筑参数

核心功能：
1. 从图签/图框提取建筑高度、层数、耐火等级等参数
2. 基于立面图视觉特征进行参数推断与补充
3. 支持复杂图纸场景（多建筑图、多层结构）
4. 参数提取规则库 + 可信度评估 + 人工校对接口
"""

from __future__ import annotations

import os
import re
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import ezdxf

logger = logging.getLogger("v7.preprocessor.project_parameter_anchor")


@dataclass
class ExtractedParameter:
    """提取的参数信息"""
    name: str
    value: str
    source: str  # 'title_block', 'text_search', 'visual_inference', 'rule_inference'
    confidence: float  # 0.0-1.0
    evidence: List[str] = field(default_factory=list)
    location: Optional[Tuple[float, float]] = None
    requires_review: bool = False


@dataclass
class ProjectParameters:
    """项目参数集合"""
    project_name: str = ""
    building_height: Optional[float] = None  # 建筑高度(m)
    floor_count: Optional[int] = None  # 层数
    underground_floor_count: Optional[int] = None  # 地下层数
    fire_resistance: str = ""  # 耐火等级
    seismic_level: str = ""  # 抗震设防烈度
    building_type: str = ""  # 建筑类型
    structural_system: str = ""  # 结构体系
    area: Optional[float] = None  # 建筑面积(㎡)
    facade_area: Optional[float] = None  # 外墙面积(㎡)
    parameters: List[ExtractedParameter] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "building_height": self.building_height,
            "floor_count": self.floor_count,
            "underground_floor_count": self.underground_floor_count,
            "fire_resistance": self.fire_resistance,
            "seismic_level": self.seismic_level,
            "building_type": self.building_type,
            "structural_system": self.structural_system,
            "area": self.area,
            "facade_area": self.facade_area,
            "parameters": [
                {
                    "name": p.name,
                    "value": p.value,
                    "source": p.source,
                    "confidence": p.confidence,
                    "evidence": p.evidence,
                    "requires_review": p.requires_review,
                }
                for p in self.parameters
            ],
        }


# 参数提取规则库
PARAMETER_RULES = {
    "building_height": {
        "patterns": [
            r'建筑\s*高度\s*[:：]\s*([\d.]+)\s*[米m]',
            r'总高\s*[:：]\s*([\d.]+)\s*[米m]',
            r'建筑高度\s*=\s*([\d.]+)',
            r'height\s*[:=]\s*([\d.]+)',
            r'H\s*=\s*([\d.]+)\s*m',
        ],
        "units": ["米", "m", "M"],
        "default_unit": "米",
        "confidence_weight": 1.0,
    },
    "floor_count": {
        "patterns": [
            r'地上\s*(\d+)\s*层',
            r'层数\s*[:：]\s*(\d+)',
            r'共\s*(\d+)\s*层',
            r'层数\s*=\s*(\d+)',
            r'FLOORS?\s*[:=]\s*(\d+)',
        ],
        "confidence_weight": 1.0,
    },
    "underground_floor_count": {
        "patterns": [
            r'地下\s*(\d+)\s*层',
            r'地下室\s*(\d+)',
            r'B(\d+)\s*F?',
            r'地下.*层',
        ],
        "confidence_weight": 0.9,
    },
    "fire_resistance": {
        "patterns": [
            r'耐火等级\s*[:：]\s*(一|二|三|四)\s*级',
            r'耐火\s*[:：]\s*(一|二|三|四)级',
            r'fire\s*resistance\s*[:：]\s*(I|II|III|IV)',
        ],
        "mappings": {
            "一": "一级", "二": "二级", "三": "三级", "四": "四级",
            "I": "一级", "II": "二级", "III": "三级", "IV": "四级",
        },
        "confidence_weight": 1.0,
    },
    "seismic_level": {
        "patterns": [
            r'抗震\s*[:：]\s*(\d+)\s*度',
            r'抗震设防\s*[:：]\s*(\d+)度',
            r'seismic\s*[:：]\s*(\d+)',
            r'设防烈度\s*[:：]\s*(\d+)度',
        ],
        "confidence_weight": 1.0,
    },
    "building_type": {
        "patterns": [
            r'建筑类型\s*[:：]\s*([^\n]+)',
            r'用途\s*[:：]\s*([^\n]+)',
            r'功能\s*[:：]\s*([^\n]+)',
            r'类型\s*[:：]\s*([^\n]+)',
        ],
        "keywords": {
            "住宅": "residential",
            "商业": "commercial",
            "办公": "office",
            "医院": "hospital",
            "学校": "school",
            "工业": "industrial",
            "综合体": "mixed_use",
        },
        "confidence_weight": 0.8,
    },
    "structural_system": {
        "patterns": [
            r'结构体系\s*[:：]\s*([^\n]+)',
            r'结构类型\s*[:：]\s*([^\n]+)',
            r'structure\s*[:：]\s*([^\n]+)',
        ],
        "keywords": {
            "框架": "frame",
            "剪力墙": "shear_wall",
            "框架-剪力墙": "frame_shear_wall",
            "钢结构": "steel",
            "钢筋混凝土": "rc",
            "砌体": "masonry",
        },
        "confidence_weight": 0.85,
    },
    "area": {
        "patterns": [
            r'建筑面积\s*[:：]\s*([\d.]+)\s*[㎡m2]',
            r'面积\s*[:：]\s*([\d.]+)\s*[㎡m2]',
            r'area\s*[:=]\s*([\d.]+)',
        ],
        "units": ["㎡", "m2", "m²"],
        "confidence_weight": 0.9,
    },
}


# 立面图分析规则（用于视觉推理）
FACADE_ANALYSIS_RULES = {
    "floor_height": {
        "typical_values": [2.8, 3.0, 3.2, 3.6, 4.0],  # 常见层高(m)
        "ground_floor_factor": 1.2,  # 首层通常比标准层高20%
    },
    "window_pattern": {
        "min_windows_per_floor": 1,
        "max_windows_per_floor": 10,
    },
    "vertical_lines": {
        "threshold": 100,  # 超过此长度视为结构柱或墙
    },
}


class ProjectParameterAnchor:
    """项目参数锚定器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._rules = dict(PARAMETER_RULES)
        self._facade_rules = dict(FACADE_ANALYSIS_RULES)
        if config:
            self._rules.update(config.get("parameter_rules", {}))
        self._text_cache: Dict[str, str] = {}
    
    def _extract_all_text(self, dxf_path: str) -> List[Tuple[str, float, float]]:
        """提取DXF中所有文本实体及其坐标"""
        try:
            doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
            texts = []
            for e in msp.query('TEXT MTEXT'):
                try:
                    if e.dxftype() == "TEXT":
                        txt = e.dxf.text if hasattr(e.dxf, "text") else ""
                    else:
                        txt = e.plain_text() if hasattr(e, "plain_text") else ""
                    if txt and txt.strip():
                        insert = e.dxf.insert if hasattr(e.dxf, "insert") else (0, 0, 0)
                        texts.append((txt.strip(), insert[0], insert[1]))
                except Exception:
                    continue
            return texts
        except Exception as e:
            logger.error(f"读取DXF失败: {dxf_path}: {e}")
            return []
    
    def _extract_dimensions(self, dxf_path: str) -> List[Tuple[str, float, float]]:
        """提取尺寸标注"""
        try:
            doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
            dimensions = []
            for e in msp.query('DIMENSION'):
                try:
                    text = e.dxf.text if hasattr(e.dxf, "text") else ""
                    if text and text.strip():
                        insert = e.dxf.insert if hasattr(e.dxf, "insert") else (0, 0, 0)
                        dimensions.append((text.strip(), insert[0], insert[1]))
                except Exception:
                    continue
            return dimensions
        except Exception as e:
            logger.error(f"提取尺寸标注失败: {dxf_path}: {e}")
            return []
    
    def _extract_from_title_block(self, dxf_path: str) -> Dict[str, str]:
        """从图签提取参数"""
        from .title_block_extractor import TitleBlockExtractor
        extractor = TitleBlockExtractor()
        data = extractor.extract(dxf_path)
        
        result = {}
        if data.get("project_name"):
            result["project_name"] = data["project_name"]
        
        # 尝试从图签文本中提取建筑参数
        combined_text = "\n".join([
            data.get("drawing_name", ""),
            data.get("project_name", ""),
            data.get("sub_project", ""),
            data.get("drawing_type", ""),
        ])
        
        for param_name, rules in self._rules.items():
            for pattern in rules.get("patterns", []):
                match = re.search(pattern, combined_text)
                if match:
                    value = match.group(1).strip()
                    if param_name not in result:
                        result[param_name] = value
                        logger.debug(f"从图签提取 {param_name} = {value}")
        return result
    
    def _search_text_patterns(self, texts: List[Tuple[str, float, float]]) -> Dict[str, List[Tuple[str, float, float]]]:
        """在文本中搜索参数模式"""
        results = {}
        for param_name, rules in self._rules.items():
            matches = []
            for text, x, y in texts:
                for pattern in rules.get("patterns", []):
                    match = re.search(pattern, text)
                    if match:
                        matches.append((match.group(1).strip(), x, y))
            if matches:
                results[param_name] = matches
        return results
    
    def _infer_from_facade(self, dxf_path: str) -> Dict[str, Any]:
        """从立面图视觉特征推断参数"""
        try:
            doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
        except Exception as e:
            logger.error(f"读取DXF失败: {dxf_path}: {e}")
            return {}
        
        result = {}
        
        # 分析垂直线条（可能代表楼层分界线）
        vertical_lines = []
        for e in msp.query('LINE'):
            try:
                start = e.dxf.start
                end = e.dxf.end
                dx = abs(end[0] - start[0])
                dy = abs(end[1] - start[1])
                if dx < 10 and dy > self._facade_rules["vertical_lines"]["threshold"]:
                    vertical_lines.append((start[1], end[1]))
            except Exception:
                continue
        
        # 分析水平线（可能代表楼层高度）
        horizontal_segments = []
        for e in msp.query('LINE'):
            try:
                start = e.dxf.start
                end = e.dxf.end
                dx = abs(end[0] - start[0])
                dy = abs(end[1] - start[1])
                if dy < 10 and dx > 100:
                    horizontal_segments.append((start[1], end[1]))
            except Exception:
                continue
        
        # 推断层数：水平线数量 - 1（顶层和底层各一条）
        if horizontal_segments:
            unique_y = sorted(set([h[0] for h in horizontal_segments]))
            if len(unique_y) >= 2:
                inferred_floors = len(unique_y) - 1
                if inferred_floors >= 1:
                    result["floor_count_inferred"] = inferred_floors
                    logger.debug(f"从立面图推断层数: {inferred_floors}层")
        
        # 推断建筑高度
        if horizontal_segments:
            y_coords = [h[0] for h in horizontal_segments]
            if y_coords:
                min_y = min(y_coords)
                max_y = max(y_coords)
                height_units = max_y - min_y
                
                # 假设典型层高3.0米，估算实际高度
                typical_floor_height = 3.0
                if result.get("floor_count_inferred"):
                    estimated_height = result["floor_count_inferred"] * typical_floor_height
                    result["building_height_inferred"] = estimated_height
                    logger.debug(f"从立面图推断高度: {estimated_height}m")
        
        return result
    
    def _extract_from_elevations(self, elevation_paths: List[str]) -> Dict[str, Any]:
        """从立面图提取参数"""
        results = {}
        for path in elevation_paths:
            facade_data = self._infer_from_facade(path)
            results.update(facade_data)
        return results
    
    def _apply_rules(self, raw_params: Dict[str, Any]) -> List[ExtractedParameter]:
        """应用参数提取规则，生成带可信度的参数列表"""
        params = []
        
        for param_name, rules in self._rules.items():
            if param_name in raw_params:
                value = raw_params[param_name]
                
                # 应用映射规则
                if "mappings" in rules:
                    if value in rules["mappings"]:
                        value = rules["mappings"][value]
                
                # 计算可信度
                confidence = rules.get("confidence_weight", 0.8)
                
                # 检查是否需要人工复核
                requires_review = confidence < 0.9
                
                params.append(ExtractedParameter(
                    name=param_name,
                    value=str(value),
                    source="rule_based",
                    confidence=confidence,
                    requires_review=requires_review,
                ))
        
        return params
    
    def _validate_parameters(self, params: ProjectParameters) -> ProjectParameters:
        """验证参数的合理性"""
        # 验证建筑高度与层数的关系
        if params.building_height and params.floor_count:
            avg_floor_height = params.building_height / params.floor_count
            if avg_floor_height < 2.0 or avg_floor_height > 6.0:
                # 层高异常，标记需要复核
                for p in params.parameters:
                    if p.name in ["building_height", "floor_count"]:
                        p.requires_review = True
                        p.confidence = min(p.confidence, 0.7)
        
        # 验证耐火等级的合理性
        if params.fire_resistance:
            valid_grades = ["一级", "二级", "三级", "四级"]
            if params.fire_resistance not in valid_grades:
                for p in params.parameters:
                    if p.name == "fire_resistance":
                        p.requires_review = True
        
        # 验证抗震设防烈度
        if params.seismic_level:
            try:
                level = int(params.seismic_level)
                if level < 6 or level > 9:
                    for p in params.parameters:
                        if p.name == "seismic_level":
                            p.requires_review = True
            except ValueError:
                for p in params.parameters:
                    if p.name == "seismic_level":
                        p.requires_review = True
        
        return params
    
    def _merge_parameters(self, title_block_data: Dict, text_search_data: Dict, 
                         facade_data: Dict) -> ProjectParameters:
        """合并多种来源的参数"""
        params = ProjectParameters()
        
        # 优先使用图签数据
        if title_block_data.get("project_name"):
            params.project_name = title_block_data["project_name"]
        
        # 合并数值参数（图签优先，文本搜索补充，立面图推断兜底）
        param_mapping = {
            "building_height": float,
            "floor_count": int,
            "underground_floor_count": int,
            "area": float,
            "facade_area": float,
        }
        
        for param_name, converter in param_mapping.items():
            value = None
            source = ""
            
            # 优先图签
            if param_name in title_block_data:
                try:
                    value = converter(title_block_data[param_name])
                    source = "title_block"
                except ValueError:
                    pass
            
            # 其次文本搜索
            if value is None and param_name in text_search_data:
                for val, _, _ in text_search_data[param_name]:
                    try:
                        value = converter(val)
                        source = "text_search"
                        break
                    except ValueError:
                        continue
            
            # 最后立面图推断
            if value is None and f"{param_name}_inferred" in facade_data:
                value = facade_data[f"{param_name}_inferred"]
                source = "visual_inference"
            
            setattr(params, param_name, value)
            if value is not None:
                params.parameters.append(ExtractedParameter(
                    name=param_name,
                    value=str(value),
                    source=source,
                    confidence=0.9 if source == "title_block" else 0.75,
                ))
        
        # 处理分类参数
        for param_name in ["fire_resistance", "seismic_level", "building_type", "structural_system"]:
            value = None
            source = ""
            
            if param_name in title_block_data:
                value = title_block_data[param_name]
                source = "title_block"
            elif param_name in text_search_data:
                for val, _, _ in text_search_data[param_name]:
                    value = val
                    source = "text_search"
                    break
            
            setattr(params, param_name, value or "")
            if value:
                params.parameters.append(ExtractedParameter(
                    name=param_name,
                    value=value,
                    source=source,
                    confidence=0.9 if source == "title_block" else 0.8,
                ))
        
        return params
    
    def extract(self, dxf_path: str, elevation_paths: Optional[List[str]] = None) -> ProjectParameters:
        """从DXF文件提取项目参数"""
        logger.info(f"开始提取项目参数: {os.path.basename(dxf_path)}")
        
        # 1. 从图签提取
        title_block_data = self._extract_from_title_block(dxf_path)
        logger.debug(f"图签数据: {title_block_data}")
        
        # 2. 从文本搜索提取
        all_texts = self._extract_all_text(dxf_path)
        dimensions = self._extract_dimensions(dxf_path)
        all_texts.extend(dimensions)
        text_search_data = self._search_text_patterns(all_texts)
        logger.debug(f"文本搜索数据: {text_search_data}")
        
        # 3. 从立面图推断（如果提供）
        facade_data = {}
        if elevation_paths and elevation_paths[0]:
            facade_data = self._extract_from_elevations(elevation_paths)
            logger.debug(f"立面图推断数据: {facade_data}")
        
        # 4. 合并参数
        params = self._merge_parameters(title_block_data, text_search_data, facade_data)
        
        # 5. 验证参数合理性
        params = self._validate_parameters(params)
        
        logger.info(f"参数提取完成: 建筑高度={params.building_height}m, 层数={params.floor_count}层")
        return params
    
    def extract_batch(self, dxf_paths: List[str], 
                     elevation_paths: Optional[List[str]] = None) -> Dict[str, ProjectParameters]:
        """批量提取多个DXF文件的参数"""
        results = {}
        for dxf_path in dxf_paths:
            try:
                params = self.extract(dxf_path, elevation_paths)
                results[os.path.basename(dxf_path)] = params
            except Exception as e:
                logger.error(f"提取失败: {dxf_path}: {e}")
        return results
    
    def to_json(self, params: ProjectParameters, output_path: str) -> str:
        """输出参数为JSON"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(params.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"项目参数已保存: {output_path}")
        return output_path
    
    def get_review_list(self, params: ProjectParameters) -> List[ExtractedParameter]:
        """获取需要人工复核的参数列表"""
        return [p for p in params.parameters if p.requires_review]
    
    def update_parameter(self, params: ProjectParameters, param_name: str, 
                        new_value: str, reviewer: str = "") -> bool:
        """人工校对更新参数"""
        for p in params.parameters:
            if p.name == param_name:
                p.value = new_value
                p.confidence = 1.0
                p.requires_review = False
                if reviewer:
                    p.evidence.append(f"人工校对 by {reviewer}")
                setattr(params, param_name, new_value)
                return True
        return False


# 测试用例
def test_extraction():
    """测试参数提取功能"""
    logging.basicConfig(level=logging.DEBUG)
    anchor = ProjectParameterAnchor()
    
    # 测试模拟数据
    test_params = ProjectParameters(
        project_name="测试项目",
        building_height=50.0,
        floor_count=15,
        fire_resistance="一级",
        seismic_level="7",
        building_type="住宅",
    )
    
    print("测试参数验证...")
    validated = anchor._validate_parameters(test_params)
    print(f"验证结果: {validated.to_dict()}")
    
    print("\n测试需要复核的参数...")
    review_list = anchor.get_review_list(validated)
    print(f"需复核参数: {[p.name for p in review_list]}")
    
    print("\n测试人工校对...")
    result = anchor.update_parameter(validated, "building_height", "55.0", "test_user")
    print(f"更新结果: {result}")
    print(f"更新后高度: {validated.building_height}")


if __name__ == "__main__":
    test_extraction()