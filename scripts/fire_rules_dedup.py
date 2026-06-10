import json
import re
import shutil
import os

RULES_FILE = r"f:\AI智能审图系统_v6.0_项目开发\config\rules.json"
BACKUP_FILE = RULES_FILE + ".bak"

FIRE_CODE_PATTERNS = [
    "GB 50016", "GB 55037", "GB 50974", "GB 50116", "GB 50140", "GB 50045", "GB 50084"
]
FIRE_KEYWORDS_NAME = ["消防", "防火", "疏散", "消火栓", "灭火器", "排烟", "防烟"]

def is_fire_rule(rule):
    cr = rule.get("code_reference", "")
    for pat in FIRE_CODE_PATTERNS:
        if pat in cr:
            return True
    if rule.get("discipline", "") == "消防":
        return True
    name_desc = rule.get("name", "") + rule.get("description", "")
    for kw in FIRE_KEYWORDS_NAME:
        if kw in name_desc:
            return True
    return False

MERGE_GROUPS = [
    {
        "article": "GB 50016-2014 第5.3.1条",
        "description": "防火分区面积-高层1500m²",
        "keep": ("rule_093", "GB 50016-2014(2018版) 第5.3.1条"),
        "delete": [
            ("rule_043a", "GB 50016-2014 第5.3.1条"),
            ("rule_p006", "GB 50016-2014 第5.3.1条"),
        ],
        "reason": "GB 50016-2014(2018版)优先于GB 50016-2014，同一场景(高层防火分区1500m²)"
    },
    {
        "article": "GB 50016-2014 第5.3.1条",
        "description": "防火分区面积-多层2500m²",
        "keep": ("rule_092", "GB 50016-2014(2018版) 第5.3.1条"),
        "delete": [
            ("rule_044a", "GB 50016-2014 第5.3.1条"),
        ],
        "reason": "GB 50016-2014(2018版)优先于GB 50016-2014，同一场景(多层防火分区2500m²)"
    },
    {
        "article": "GB 50016-2014 第5.5.8条",
        "description": "安全出口数量不少于2个",
        "keep": ("rule_086", "GB 50016-2014(2018版) 第5.5.8条"),
        "delete": [
            ("rule_p002", "GB 50016-2014 第5.5.8条"),
        ],
        "reason": "GB 50016-2014(2018版)优先于GB 50016-2014，同一场景(安全出口≥2个)"
    },
    {
        "article": "GB 50016-2014 第5.5.17条",
        "description": "疏散距离40m(两个安全出口之间)",
        "keep": ("rule_095", "GB 50016-2014(2018版) 第5.5.17条"),
        "delete": [
            ("rule_047a", "GB 50016-2014 第5.5.17条"),
            ("rule_p030", "GB 50016-2014 第5.5.17条"),
        ],
        "reason": "GB 50016-2014(2018版)优先于GB 50016-2014，同一场景(疏散距离40m)"
    },
    {
        "article": "GB 50016-2014 第5.5.18条",
        "description": "疏散走道/楼梯净宽",
        "keep": ("rule_085", "GB 50016-2014(2018版) 第5.5.18条"),
        "delete": [
            ("rule_046a", "GB 50016-2014 第5.5.18条"),
            ("rule_p003", "GB 50016-2014 第5.5.18条"),
            ("rule_p008", "GB 50016-2014 第5.5.18条"),
        ],
        "reason": "GB 50016-2014(2018版)优先于GB 50016-2014，同一场景(疏散通道净宽)"
    },
    {
        "article": "GB 50016-2014 第6.5.1条",
        "description": "防火门自闭功能",
        "keep": ("rule_099", "GB 50016-2014(2018版) 第6.5.1条"),
        "delete": [
            ("rule_049a", "GB 50016-2014 第6.5.1条"),
        ],
        "reason": "GB 50016-2014(2018版)优先于GB 50016-2014，同一场景(防火门闭门器)"
    },
    {
        "article": "GB 50016-2014 第7.1.8条",
        "description": "消防车道宽度不小于4m",
        "keep": ("rule_076", "GB 50016-2014(2018版) 第7.1.8条"),
        "delete": [
            ("rule_p019", "GB 50016-2014 第7.1.8条"),
        ],
        "reason": "GB 50016-2014(2018版)优先于GB 50016-2014，同一场景(消防车道宽度4m)"
    },
    {
        "article": "GB 50016-2014 第7.3.1条",
        "description": "消防电梯设置要求",
        "keep": ("rule_101", "GB 50016-2014(2018版) 第7.3.1条"),
        "delete": [
            ("rule_p004", "GB 50016-2014 第7.3.1条"),
        ],
        "reason": "GB 50016-2014(2018版)优先于GB 50016-2014，同一场景(应设消防电梯)"
    },
    {
        "article": "GB 50016-2014 第7.3.5条",
        "description": "消防电梯前室面积不小于6m²",
        "keep": ("rule_102", "GB 50016-2014(2018版) 第7.3.5条"),
        "delete": [
            ("rule_p023", "GB 50016-2014 第7.3.5条"),
        ],
        "reason": "GB 50016-2014(2018版)优先于GB 50016-2014，同一场景(前室面积6m²)"
    },
    {
        "article": "GB 50116-2013 第6.3.1条",
        "description": "手动报警按钮距离不大于30m",
        "keep": ("rule_109", "GB 50116-2013 第6.3.1条"),
        "delete": [
            ("rule_097", "GB 50116-2013 第6.3.1条"),
        ],
        "reason": "消防规则优先(含更完整描述)，同一场景(手动报警按钮30m)"
    },
    {
        "article": "GB 50974-2014 第4.3.4条",
        "description": "消防水池有效容积",
        "keep": ("rule_090", "GB 50974-2014 第4.3.4条"),
        "delete": [
            ("rule_073", "GB 50974-2014 第4.3.4条"),
        ],
        "reason": "消防规则优先(含具体数值100m³)，同一场景(消防水池容积)"
    },
    {
        "article": "GB 50974-2014 第5.2.1条",
        "description": "消防水箱有效容积",
        "keep": ("rule_080", "GB 50974-2014 第5.2.1条"),
        "delete": [
            ("rule_074", "GB 50974-2014 第5.2.1条"),
        ],
        "reason": "消防规则优先(含具体数值12m³和适用建筑类型)，同一场景(消防水箱容积)"
    },
]

def find_rule(rules, rule_id, code_ref=None):
    for r in rules:
        if r["rule_id"] == rule_id:
            if code_ref is None:
                return r
            if code_ref in r.get("code_reference", ""):
                return r
    return None

def find_rule_index(rules, rule_id, code_ref=None):
    for i, r in enumerate(rules):
        if r["rule_id"] == rule_id:
            if code_ref is None:
                return i
            if code_ref in r.get("code_reference", ""):
                return i
    return None

def main():
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    rules = data.get("mandatory_rules", [])

    fire_rules = [r for r in rules if is_fire_rule(r)]

    print(f"=== 消防规则去重合并分析 ===")
    print(f"总规则数: {len(rules)}")
    print(f"消防相关规则数: {len(fire_rules)}")
    print()

    delete_indices = set()
    report = []

    for i, group in enumerate(MERGE_GROUPS, 1):
        keep_id, keep_ref = group["keep"]
        keeper = find_rule(rules, keep_id, keep_ref)
        if not keeper:
            print(f"  ⚠️ 警告: 保留规则 {keep_id} (含 {keep_ref}) 不存在，跳过该组")
            continue

        entry = {
            "序号": i,
            "条文": group["article"],
            "场景说明": group["description"],
            "合并原因": group["reason"],
            "保留": {
                "rule_id": keeper["rule_id"],
                "name": keeper["name"],
                "discipline": keeper.get("discipline", ""),
                "code_reference": keeper["code_reference"],
                "applicable_building_types": keeper.get("applicable_building_types", [])
            },
            "删除": []
        }

        for del_id, del_ref in group["delete"]:
            idx = find_rule_index(rules, del_id, del_ref)
            if idx is not None:
                deleted = rules[idx]
                delete_indices.add(idx)
                entry["删除"].append({
                    "rule_id": deleted["rule_id"],
                    "name": deleted["name"],
                    "discipline": deleted.get("discipline", ""),
                    "code_reference": deleted["code_reference"]
                })
            else:
                print(f"  ⚠️ 警告: 删除规则 {del_id} (含 {del_ref}) 不存在")

        report.append(entry)

    print("=" * 80)
    print("合并报告")
    print("=" * 80)
    for entry in report:
        print(f"\n--- 第{entry['序号']}组: {entry['条文']} ---")
        print(f"  场景: {entry['场景说明']}")
        print(f"  原因: {entry['合并原因']}")
        print(f"  ✅ 保留: {entry['保留']['rule_id']} ({entry['保留']['name']}) [{entry['保留']['discipline']}]")
        print(f"     引用: {entry['保留']['code_reference']}")
        if entry['保留']['applicable_building_types']:
            print(f"     适用建筑类型: {entry['保留']['applicable_building_types']}")
        print(f"  ❌ 删除:")
        for d in entry['删除']:
            print(f"     - {d['rule_id']} ({d['name']}) [{d['discipline']}] {d['code_reference']}")

    print(f"\n{'=' * 80}")
    print(f"总计: 删除 {len(delete_indices)} 条重复规则")
    print(f"{'=' * 80}")

    if not os.path.exists(BACKUP_FILE):
        shutil.copy2(RULES_FILE, BACKUP_FILE)
        print(f"\n已备份原文件到: {BACKUP_FILE}")
    else:
        print(f"\n备份文件已存在，跳过备份: {BACKUP_FILE}")

    new_rules = [r for i, r in enumerate(rules) if i not in delete_indices]
    data["mandatory_rules"] = new_rules

    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n已更新 rules.json")
    print(f"  修改前规则数: {len(rules)}")
    print(f"  修改后规则数: {len(new_rules)}")
    print(f"  删除规则数: {len(rules) - len(new_rules)}")

    report_file = r"f:\AI智能审图系统_v6.0_项目开发\scripts\fire_rules_dedup_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "总规则数_修改前": len(rules),
                "总规则数_修改后": len(new_rules),
                "删除规则数": len(delete_indices),
                "消防规则总数": len(fire_rules),
                "合并组数": len(report)
            },
            "删除的规则": [
                {"rule_id": rules[i]["rule_id"], "name": rules[i]["name"], "code_reference": rules[i]["code_reference"]}
                for i in sorted(delete_indices)
            ],
            "合并详情": report
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细报告已保存到: {report_file}")

if __name__ == "__main__":
    main()
