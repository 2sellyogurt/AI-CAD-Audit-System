# -*- coding: utf-8 -*-
"""
规则提炼脚本 - 从反馈数据中半自动生成规则候选

功能：
1. 读取 feedback_history.json 中的用户反馈
2. 分析高频误报和遗漏模式
3. 生成规则候选建议（JSON格式）
4. 供人工审核后加入 rules.json

用法：
  python tools/rule_refiner.py --feedback-dir ./output --output ./config/rule_candidates.json
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List


def load_feedback_history(feedback_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(feedback_path):
        print(f"[错误] 反馈文件不存在: {feedback_path}")
        return []
    try:
        with open(feedback_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[错误] 加载反馈文件失败: {e}")
        return []


def analyze_false_positives(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    fp_counter: Counter = Counter()
    fp_details: Dict[str, List[str]] = defaultdict(list)

    for entry in history:
        if entry.get("type") != "user_feedback":
            continue
        if entry.get("feedback_type") != "false_positive":
            continue
        rule_id = entry.get("rule_id", "unknown")
        fp_counter[rule_id] += 1
        comment = entry.get("comment", "")
        if comment:
            fp_details[rule_id].append(comment)

    return {
        "top_false_positives": fp_counter.most_common(20),
        "details": dict(fp_details),
    }


def analyze_missed_issues(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    missed_counter: Counter = Counter()
    missed_details: Dict[str, List[str]] = defaultdict(list)

    for entry in history:
        if entry.get("type") != "user_feedback":
            continue
        if entry.get("feedback_type") != "missed":
            continue
        rule_id = entry.get("rule_id", "unknown")
        missed_counter[rule_id] += 1
        comment = entry.get("comment", "")
        if comment:
            missed_details[rule_id].append(comment)

    return {
        "top_missed": missed_counter.most_common(20),
        "details": dict(missed_details),
    }


def analyze_confirmed(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    confirmed_counter: Counter = Counter()

    for entry in history:
        if entry.get("type") != "user_feedback":
            continue
        if entry.get("feedback_type") != "confirmed":
            continue
        rule_id = entry.get("rule_id", "unknown")
        confirmed_counter[rule_id] += 1

    return {
        "top_confirmed": confirmed_counter.most_common(20),
    }


def generate_candidates(
    fp_analysis: Dict[str, Any],
    missed_analysis: Dict[str, Any],
    confirmed_analysis: Dict[str, Any],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    for rule_id, count in fp_analysis["top_false_positives"]:
        if count >= 3:
            details = fp_analysis["details"].get(rule_id, [])
            candidates.append({
                "type": "adjust_threshold",
                "rule_id": rule_id,
                "reason": f"该规则误报{count}次，建议调整阈值或条件",
                "feedback_count": count,
                "sample_comments": details[:5],
                "suggestion": "建议降低该规则的敏感度或增加过滤条件",
                "priority": "high" if count >= 5 else "medium",
            })

    for rule_id, count in missed_analysis["top_missed"]:
        if count >= 2:
            details = missed_analysis["details"].get(rule_id, [])
            candidates.append({
                "type": "add_rule",
                "rule_id": rule_id,
                "reason": f"该规则遗漏{count}次，建议新增补充规则",
                "feedback_count": count,
                "sample_comments": details[:5],
                "suggestion": "建议基于反馈样本新增补充检测规则",
                "priority": "high" if count >= 3 else "medium",
            })

    for rule_id, count in confirmed_analysis["top_confirmed"]:
        if count >= 10:
            candidates.append({
                "type": "increase_confidence",
                "rule_id": rule_id,
                "reason": f"该规则已确认{count}次，置信度高",
                "feedback_count": count,
                "suggestion": "建议提高该规则的置信度权重",
                "priority": "low",
            })

    candidates.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["priority"], 3))
    return candidates


def generate_report(candidates: List[Dict[str, Any]]) -> str:
    lines = [
        "# 规则提炼报告",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**候选规则数**: {len(candidates)}",
        "",
        "## 候选规则列表",
        "",
    ]

    for idx, candidate in enumerate(candidates, 1):
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(candidate["priority"], "⚪")
        lines.append(f"### {idx}. {priority_icon} [{candidate['priority'].upper()}] {candidate['rule_id']}")
        lines.append("")
        lines.append(f"- **类型**: {candidate['type']}")
        lines.append(f"- **原因**: {candidate['reason']}")
        lines.append(f"- **建议**: {candidate['suggestion']}")
        if candidate.get("sample_comments"):
            lines.append("- **反馈样本**:")
            for comment in candidate["sample_comments"]:
                lines.append(f"  - {comment}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="规则提炼脚本 - 从反馈数据中生成规则候选"
    )
    parser.add_argument(
        "--feedback-dir",
        default="./output",
        help="反馈数据目录（默认: ./output）",
    )
    parser.add_argument(
        "--output",
        default="./config/rule_candidates.json",
        help="输出文件路径（默认: ./config/rule_candidates.json）",
    )
    parser.add_argument(
        "--report",
        default="",
        help="报告输出路径（可选）",
    )
    args = parser.parse_args()

    feedback_path = os.path.join(args.feedback_dir, "feedback_history.json")
    print(f"[1/4] 加载反馈数据: {feedback_path}")
    history = load_feedback_history(feedback_path)
    if not history:
        print("[警告] 无反馈数据，退出")
        return 0

    print(f"[2/4] 分析反馈数据（共{len(history)}条记录）")
    fp_analysis = analyze_false_positives(history)
    missed_analysis = analyze_missed_issues(history)
    confirmed_analysis = analyze_confirmed(history)

    print(f"  - 误报规则: {len(fp_analysis['top_false_positives'])}个")
    print(f"  - 遗漏规则: {len(missed_analysis['top_missed'])}个")
    print(f"  - 确认规则: {len(confirmed_analysis['top_confirmed'])}个")

    print("[3/4] 生成规则候选")
    candidates = generate_candidates(fp_analysis, missed_analysis, confirmed_analysis)
    print(f"  - 生成候选: {len(candidates)}个")

    print(f"[4/4] 保存结果")
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    output_data = {
        "generated_at": datetime.now().isoformat(),
        "total_feedback_entries": len(history),
        "candidates": candidates,
        "analysis": {
            "false_positives": fp_analysis["top_false_positives"],
            "missed_issues": missed_analysis["top_missed"],
            "confirmed": confirmed_analysis["top_confirmed"],
        },
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"  - 候选规则已保存: {args.output}")

    if args.report:
        report = generate_report(candidates)
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  - 报告已保存: {args.report}")

    print("\n[完成] 规则提炼完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
