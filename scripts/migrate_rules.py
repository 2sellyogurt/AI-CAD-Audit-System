# -*- coding: utf-8 -*-
import json
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rules_path = os.path.join(project_root, "config", "rules.json")

with open(rules_path, "r", encoding="utf-8") as f:
    old_data = json.load(f)

new_data = {
    "project_info": {
        "name": "未命名项目",
        "building_types": [],
        "not_applicable_rules": []
    },
    "risk_levels": {
        "description": "四级风险分级体系，统一所有模块的风险判定标准",
        "levels": {
            "严重": {
                "code": "CRITICAL",
                "color": "红色",
                "criteria": "强条违规、结构安全隐患、消防系统失效",
                "response": "必须立即整改，不得通过审查",
                "deduction_points": 30
            },
            "重要": {
                "code": "MAJOR",
                "color": "橙色",
                "criteria": "非强条违规、净高不足、管线碰撞、跨专业不一致",
                "response": "应整改，影响使用功能或施工质量",
                "deduction_points": 15
            },
            "一般": {
                "code": "MODERATE",
                "color": "黄色",
                "criteria": "标注不完整、间距偏小、优化建议",
                "response": "建议整改，不影响安全但影响品质",
                "deduction_points": 5
            },
            "提示": {
                "code": "INFO",
                "color": "蓝色",
                "criteria": "信息提示、参考建议、低置信度待核实项",
                "response": "供参考，人工复核即可",
                "deduction_points": 0
            }
        },
        "mapping_rules": {
            "non_compliant_mandatory": "严重",
            "non_compliant": "重要",
            "need_verify_mandatory": "重要",
            "need_verify": "一般",
            "compliant": "提示",
            "low_confidence": "提示"
        }
    },
    "mandatory_rules": []
}

severity_map = {"高": True, "中": False, "低": False}
evidence_map = {"高": 2, "中": 1, "低": 1}
check_type_map = {"建筑": "any", "结构": "any", "暖通": "any", "给排水": "any", "电气": "any", "消防": "any"}

for rule in old_data.get("rules", []):
    category = rule.get("category", "")
    severity = rule.get("severity", "中")
    new_rule = {
        "rule_id": rule["rule_id"],
        "name": rule["description"],
        "discipline": category,
        "keywords": rule.get("keywords", []),
        "check_type": check_type_map.get(category, "any"),
        "evidence_required": evidence_map.get(severity, 1),
        "description": rule["description"],
        "is_mandatory": severity_map.get(severity, False),
        "code_reference": rule.get("standard_code", ""),
        "code_version": rule.get("standard_code", "").split(" ")[0] if rule.get("standard_code") else "",
        "status": "现行"
    }
    if "regex" in rule:
        new_rule["regex"] = rule["regex"]
    new_data["mandatory_rules"].append(new_rule)

output_path = os.path.join(project_root, "config", "rules_v7.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(new_data, f, ensure_ascii=False, indent=2)

print(f"迁移完成: {len(new_data['mandatory_rules'])} 条规则")
print(f"输出文件: {output_path}")
