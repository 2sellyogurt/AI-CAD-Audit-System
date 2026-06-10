# -*- coding: utf-8 -*-
"""建筑分类体系配置

基于土木工程房建分类标准，定义多维度分类体系和层级关系。
用于规则库标注和规则匹配时的建筑类型过滤。
"""
from typing import Dict, List, Set

BUILDING_FUNCTION_HIERARCHY: Dict[str, List[str]] = {
    "民用": ["住宅", "公建"],
    "住宅": ["低层住宅", "多层住宅", "高层住宅", "超高层住宅", "公寓", "宿舍"],
    "公建": ["学校", "医院", "办公", "商业", "酒店", "体育", "文化", "交通", "宗教"],
    "学校": ["中小学", "大学", "幼儿园"],
    "医院": ["综合医院", "专科医院", "诊所"],
    "商业": ["商场", "超市", "商铺"],
    "工业": ["厂房", "仓库", "动力站"],
    "农业": ["温室", "畜禽舍", "粮库"],
}

STRUCTURE_SYSTEMS: List[str] = [
    "砌体", "框架", "剪力墙", "框剪", "筒体", "框架核心筒",
    "排架", "板柱", "钢结构", "木结构", "组合结构",
]

HEIGHT_CLASSES: List[str] = [
    "低层", "多层", "中高层", "高层", "超高层",
]

CONSTRUCTION_METHODS: List[str] = [
    "现浇", "预制装配式", "装配整体式",
]

def get_all_ancestors(bt: str) -> Set[str]:
    """获取建筑类型的所有上级类型（含自身）"""
    ancestors = {bt}
    for parent, children in BUILDING_FUNCTION_HIERARCHY.items():
        if bt in children:
            ancestors.add(parent)
            ancestors.update(get_all_ancestors(parent))
    return ancestors

def get_all_descendants(bt: str) -> Set[str]:
    """获取建筑类型的所有下级类型（含自身）"""
    descendants = {bt}
    children = BUILDING_FUNCTION_HIERARCHY.get(bt, [])
    for child in children:
        descendants.update(get_all_descendants(child))
    return descendants

def match_building_type(project_type: str, applicable_types: List[str]) -> bool:
    """层级匹配：项目类型与规则适用类型是否匹配

    匹配逻辑：
    - 空列表 = 通用规则，匹配所有项目
    - 项目类型在适用列表中 = 直接匹配
    - 项目的任一上级类型在适用列表中 = 向上匹配（如"中小学"项目匹配"学校"规则）
    - 适用类型的任一下级类型等于项目类型 = 向下匹配（如"学校"规则匹配"中小学"项目）
    """
    if not applicable_types:
        return True
    if not project_type:
        return True

    project_ancestors = get_all_ancestors(project_type)

    for at in applicable_types:
        if project_type == at:
            return True
        if at in project_ancestors:
            return True
        at_descendants = get_all_descendants(at)
        if project_type in at_descendants:
            return True

    return False
