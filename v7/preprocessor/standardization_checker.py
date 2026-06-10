# -*- coding: utf-8 -*-
"""标准化校验器

基于规则的标注完整性检查。
规则驱动，不需要AI——检查"应该标注的有没有标注"。

覆盖规则示例：
  - 所有门必须有宽度标注
  - 所有梁必须有截面尺寸标注
  - 所有柱必须有截面标注
  - 消火栓必须有型号和安装高度
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class AnnotationRule:
    id: str
    name: str
    discipline: str
    component_pattern: str
    required_properties: List[str] = field(default_factory=list)
    severity: str = "warning"
    description: str = ""


DEFAULT_RULES: List[AnnotationRule] = [
    # ===== 建筑专业 (STD-001~008) =====
    AnnotationRule(
        id="STD-001", name="门必须有宽度标注", discipline="building",
        component_pattern=r"(疏散门|户门|防火门|门\s*[M|m]\d+|FM\d+|M\d+)",
        required_properties=[r"\d{3,4}\s*mm", r"宽度\s*\d{3,4}", r"宽\s*\d{3,4}"],
        description="所有门标注必须包含宽度信息"
    ),
    AnnotationRule(
        id="STD-002", name="楼梯必须有梯段净宽标注", discipline="building",
        component_pattern=r"(楼梯|疏散楼梯|梯段)",
        required_properties=[r"净宽.*\d{3,4}", r"宽度.*\d{3,4}", r"梯段宽"],
        description="楼梯必须标注梯段净宽度"
    ),
    AnnotationRule(
        id="STD-003", name="窗必须有尺寸和窗台高度标注", discipline="building",
        component_pattern=r"(窗\s*[C|c]\d+|C\d+|LC\d+)",
        required_properties=[r"\d{3,4}\s*[xX×]\s*\d{3,4}", r"台高|窗台"],
        description="窗标注必须包含尺寸和窗台高度"
    ),
    AnnotationRule(
        id="STD-004", name="坡道必须有坡度标注", discipline="building",
        component_pattern=r"(坡道|无障碍坡道|残疾人坡道)",
        required_properties=[r"坡度", r"1/\d+", r"%"],
        description="坡道标注必须包含坡度"
    ),
    AnnotationRule(
        id="STD-005", name="房间必须有名称标注", discipline="building",
        component_pattern=r"",
        required_properties=[r"间|室|厅|房|库|站"],
        description="各功能房间必须有房间名称标注"
    ),

    # ===== 结构专业 (STD-006~012) =====
    AnnotationRule(
        id="STD-006", name="梁必须有截面标注", discipline="structure",
        component_pattern=r"(梁\s*[L|l]\d+|KL\d+|LL\d+|框架梁|次梁)",
        required_properties=[r"\d{3}\s*[xX×]\s*\d{3}", r"截面", r"b\s*[xX×]\s*h"],
        description="所有梁标注必须包含截面尺寸(宽×高)"
    ),
    AnnotationRule(
        id="STD-007", name="柱必须有截面标注", discipline="structure",
        component_pattern=r"(柱\s*[Z|z]\d+|KZ\d+|框架柱)",
        required_properties=[r"\d{3}\s*[xX×]\s*\d{3}", r"截面"],
        description="所有柱标注必须包含截面尺寸"
    ),
    AnnotationRule(
        id="STD-008", name="板必须有厚度标注", discipline="structure",
        component_pattern=r"(板|楼板|现浇板|预制板|屋面板)",
        required_properties=[r"\d{2,3}\s*mm", r"板厚", r"h\s*=\s*\d{2,3}", r"厚度"],
        description="板必须标注厚度"
    ),
    AnnotationRule(
        id="STD-009", name="基础必须有尺寸标注", discipline="structure",
        component_pattern=r"(基础|独立基础|筏板|条形基础|桩基)",
        required_properties=[r"\d{3}\s*[xX×]\s*\d{3}", r"尺寸", r"标高"],
        description="基础必须有平面尺寸和标高标注"
    ),
    AnnotationRule(
        id="STD-010", name="钢筋必须有直径和间距标注", discipline="structure",
        component_pattern=r"(钢筋|纵筋|箍筋|分布筋|负筋)",
        required_properties=[r"Φ\d+|φ\d+|C\d+|B\d+", r"@\d+", r"间距"],
        description="钢筋标注必须包含直径和间距"
    ),
    AnnotationRule(
        id="STD-011", name="抗震构造必须有措施标注", discipline="structure",
        component_pattern=r"(抗震|抗震缝|防震缝)",
        required_properties=[r"抗震等级|抗震构造|抗震措施"],
        description="抗震构造必须标注抗震等级和构造措施"
    ),
    AnnotationRule(
        id="STD-012", name="后浇带必须有位置和做法标注", discipline="structure",
        component_pattern=r"(后浇带|施工缝)",
        required_properties=[r"宽度", r"\d{3,4}\s*mm", r"做法"],
        description="后浇带必须标注宽度和做法"
    ),

    # ===== 给排水专业 (STD-013~018) =====
    AnnotationRule(
        id="STD-013", name="消火栓必须有型号标注", discipline="plumbing",
        component_pattern=r"(消火栓|SN\d+|SG\d+)",
        required_properties=[r"SN\d+", r"DN\d+", r"型号"],
        description="消火栓标注必须包含型号"
    ),
    AnnotationRule(
        id="STD-014", name="排水管必须有管径和坡度标注", discipline="plumbing",
        component_pattern=r"(排水管|污水管|雨水管|废水管)",
        required_properties=[r"DN\d+|De\d+|DN\d+", r"坡度|i=", r"\d+%"],
        description="排水管必须标注管径和坡度"
    ),
    AnnotationRule(
        id="STD-015", name="给水管必须有管径标注", discipline="plumbing",
        component_pattern=r"(给水管|给水|生活给水)",
        required_properties=[r"DN\d+|De\d+"],
        description="给水管必须标注管径"
    ),
    AnnotationRule(
        id="STD-016", name="喷淋头必须有间距标注", discipline="plumbing",
        component_pattern=r"(喷淋|喷头|洒水喷头)",
        required_properties=[r"间距", r"\d{3,4}\s*mm"],
        description="喷淋头必须标注布置间距"
    ),
    AnnotationRule(
        id="STD-017", name="消防水池必须有容积标注", discipline="plumbing",
        component_pattern=r"(消防水池|消防水箱|水池)",
        required_properties=[r"容积|有效容积|V=", r"\d+\s*m³|\d+\s*m3"],
        description="消防水池(箱)必须标注有效容积"
    ),
    AnnotationRule(
        id="STD-018", name="水泵必须有流量扬程标注", discipline="plumbing",
        component_pattern=r"(水泵|消防泵|给水泵|循环泵)",
        required_properties=[r"流量|Q=", r"扬程|H="],
        description="水泵必须有流量和扬程参数标注"
    ),

    # ===== 暖通专业 (STD-019~022) =====
    AnnotationRule(
        id="STD-019", name="风管必须有截面尺寸", discipline="hvac",
        component_pattern=r"(风管|排烟管|送风管|回风管)",
        required_properties=[r"\d{3,4}\s*[xX×]\s*\d{3,4}", r"截面"],
        description="风管标注必须包含截面尺寸"
    ),
    AnnotationRule(
        id="STD-020", name="风机必须有型号和风量标注", discipline="hvac",
        component_pattern=r"(风机|排烟风机|送风机|新风机组)",
        required_properties=[r"型号", r"\d+\s*m³/h|\d+\s*CMH"],
        description="风机必须标注型号和风量"
    ),
    AnnotationRule(
        id="STD-021", name="防烟分区必须有面积标注", discipline="hvac",
        component_pattern=r"(防烟分区|防烟)",
        required_properties=[r"面积|≤\d+", r"m²|㎡"],
        description="防烟分区必须标注分区面积"
    ),
    AnnotationRule(
        id="STD-022", name="风口必须有尺寸和风量标注", discipline="hvac",
        component_pattern=r"(风口|送风口|回风口|排烟口|排风口)",
        required_properties=[r"\d{3}\s*[xX×]\s*\d{3}", r"\d+\s*m³/h"],
        description="风口必须标注尺寸和风量"
    ),

    # ===== 电气专业 (STD-023~026) =====
    AnnotationRule(
        id="STD-023", name="配电箱必须有编号和容量", discipline="electrical",
        component_pattern=r"(配电箱|AP\d+|AL\d+|配电柜)",
        required_properties=[r"AP\d+|AL\d+", r"\d+\s*[kK][wW]"],
        description="配电箱标注必须包含编号和容量"
    ),
    AnnotationRule(
        id="STD-024", name="电缆桥架必须有尺寸标注", discipline="electrical",
        component_pattern=r"(桥架|电缆桥架|线槽)",
        required_properties=[r"\d{2,4}\s*[xX×]\s*\d{2,4}", r"尺寸", r"截面"],
        description="电缆桥架必须标注截面尺寸"
    ),
    AnnotationRule(
        id="STD-025", name="应急照明必须有照度标注", discipline="electrical",
        component_pattern=r"(应急照明|疏散照明|备用照明)",
        required_properties=[r"\d+\s*[lL][xX]", r"lx", r"照度"],
        description="应急照明必须有照度值标注"
    ),
    AnnotationRule(
        id="STD-026", name="防雷接地必须有做法标注", discipline="electrical",
        component_pattern=r"(防雷|接地|避雷|接闪)",
        required_properties=[r"接地电阻|≤\d+|Ω"],
        description="防雷接地必须有接地电阻要求和做法标注"
    ),

    # ===== 消防专业 (STD-027~030) =====
    AnnotationRule(
        id="STD-027", name="防火门必须有耐火等级标注", discipline="fire",
        component_pattern=r"(防火门|FM|甲级防火门|乙级防火门|丙级防火门)",
        required_properties=[r"甲级|乙级|丙级", r"耐火"],
        description="防火门必须标注耐火等级(甲/乙/丙级)"
    ),
    AnnotationRule(
        id="STD-028", name="防火分区必须有面积和编号标注", discipline="fire",
        component_pattern=r"(防火分区|防烟分区)",
        required_properties=[r"F[FH]\d+|防火分区\s*\d+", r"\d+.*m²|面积"],
        description="防火(烟)分区必须有编号和面积标注"
    ),
    AnnotationRule(
        id="STD-029", name="疏散指示标志必须有间距标注", discipline="fire",
        component_pattern=r"(疏散指示|安全出口标志|疏散标志)",
        required_properties=[r"间距|距离|≤"],
        description="疏散指示标志必须有安装间距标注"
    ),
    AnnotationRule(
        id="STD-030", name="灭火器必须有类型和位置标注", discipline="fire",
        component_pattern=r"(灭火器|灭火器箱|\bMF\b|\bMFA\b)",
        required_properties=[r"MF[A-Z]{0,2}\d+|磷酸铵盐|灭火器"],
        description="灭火器必须标注类型和设置位置"
    ),
]


@dataclass
class StandardizationResult:
    passed: bool = True
    total_checks: int = 0
    passed_checks: int = 0
    missing_annotations: List[Dict[str, Any]] = field(default_factory=list)
    contradictory_annotations: List[Dict[str, Any]] = field(default_factory=list)
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "missing_annotations": self.missing_annotations,
            "contradictory_annotations": self.contradictory_annotations,
            "detection_rate": round(self.passed_checks / max(self.total_checks, 1), 3),
            "details": self.details,
        }


class StandardizationChecker:

    def __init__(self, rules: Optional[List[AnnotationRule]] = None):
        self._rules = rules or DEFAULT_RULES
        self._rules_by_discipline: Dict[str, List[AnnotationRule]] = {}
        for rule in self._rules:
            self._rules_by_discipline.setdefault(rule.discipline, []).append(rule)

    def check(self, text: str, discipline: str = "") -> StandardizationResult:
        rules = self._get_rules(discipline)
        result = StandardizationResult(total_checks=len(rules))
        matched_rules = 0

        for rule in rules:
            components = re.findall(rule.component_pattern, text, re.IGNORECASE)
            if not components:
                result.passed_checks += 1
                continue

            matched_rules += 1
            all_components_ok = True
            for comp in components:
                missing = []
                for prop in rule.required_properties:
                    search_text = text
                    if not re.search(prop, search_text, re.IGNORECASE):
                        missing.append(prop)
                if missing:
                    all_components_ok = False
                    result.missing_annotations.append({
                        "rule_id": rule.id, "rule_name": rule.name,
                        "component": comp, "missing_properties": missing,
                        "discipline": rule.discipline, "severity": rule.severity,
                    })
            if all_components_ok and components:
                result.passed_checks += 1

        result.passed = result.passed_checks >= result.total_checks * 0.85
        return result

    def check_with_context(
        self, text: str, discipline: str = "", window_size: int = 200
    ) -> StandardizationResult:
        result = self.check(text, discipline)
        for item in result.missing_annotations:
            comp = item["component"]
            idx = text.find(comp)
            if idx >= 0:
                start = max(0, idx - window_size)
                end = min(len(text), idx + len(comp) + window_size)
                item["context"] = text[start:end].replace("\n", " ").strip()
        return result

    def _get_rules(self, discipline: str) -> List[AnnotationRule]:
        if discipline and discipline in self._rules_by_discipline:
            return self._rules_by_discipline[discipline]
        return self._rules

    def get_missing_rate(self, result: StandardizationResult) -> float:
        return 1.0 - (result.passed_checks / max(result.total_checks, 1))
