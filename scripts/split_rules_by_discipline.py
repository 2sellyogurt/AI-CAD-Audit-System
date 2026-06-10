# -*- coding: utf-8 -*-
import json
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rules_path = os.path.join(project_root, "config", "rules.json")
output_dir = os.path.join(project_root, "config", "rules")

os.makedirs(output_dir, exist_ok=True)

with open(rules_path, "r", encoding="utf-8") as f:
    data = json.load(f)

mandatory_rules = data.get("mandatory_rules", [])

by_discipline = {}
for rule in mandatory_rules:
    discipline = rule.get("discipline", "未分类")
    if discipline not in by_discipline:
        by_discipline[discipline] = []
    by_discipline[discipline].append(rule)

index = {
    "version": "7.0.0",
    "description": "规则库索引，按专业拆分",
    "disciplines": {},
}

for discipline, rules in by_discipline.items():
    safe_name = discipline.replace("/", "_").replace(" ", "_")
    filename = f"{safe_name}.json"
    filepath = os.path.join(output_dir, filename)

    discipline_data = {
        "discipline": discipline,
        "rule_count": len(rules),
        "mandatory_rules": rules,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(discipline_data, f, ensure_ascii=False, indent=2)

    index["disciplines"][discipline] = {
        "file": filename,
        "rule_count": len(rules),
    }

index_path = os.path.join(output_dir, "_index.json")
with open(index_path, "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)

print(f"规则模块化完成:")
print(f"  总规则数: {len(mandatory_rules)}")
print(f"  专业数: {len(by_discipline)}")
print(f"  输出目录: {output_dir}")
for discipline, info in index["disciplines"].items():
    print(f"    {discipline}: {info['rule_count']} 条规则 -> {info['file']}")
