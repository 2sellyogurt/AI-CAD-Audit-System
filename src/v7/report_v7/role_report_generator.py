# -*- coding: utf-8 -*-
"""4角色报告生成器

为同一份审查问题生成4个不同视角的报告，分别面向：
  - supervisor: 建设单位/监理视角 —— 进度影响+整改优先级
  - designer: 设计院视角 —— 技术深度+规范依据
  - checker: 审图公司视角 —— 合规性+逐条结论
  - owner: 业主视角 —— 风险等级+总投资影响
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# 风险评分权重
_RISK_WEIGHT_A = 10
_RISK_WEIGHT_B = 3
_RISK_WEIGHT_C = 1
_RISK_THRESHOLD_HIGH = 30  # 高风险
_RISK_THRESHOLD_MED = 10   # 中风险

# 成本估算系数
_A_COST_MIN = 5    # A级问题最低成本（万元）
_A_COST_MAX = 20   # A级问题最高成本（万元）
_B_COST_MIN = 1    # B级问题最低成本（万元）
_B_COST_MAX = 5    # B级问题最高成本（万元）
_C_COST_MIN = 0.1  # C级问题最低成本（万元）
_C_COST_MAX = 1    # C级问题最高成本（万元）


def generate_role_report(
    issues: List[Dict[str, Any]], role: str = "supervisor",
    coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    if role == "supervisor":
        return _generate_supervisor_report(issues, coverage_stats)
    elif role == "designer":
        return _generate_designer_report(issues, coverage_stats)
    elif role == "owner":
        return _generate_owner_report(issues, coverage_stats)
    else:
        return _generate_checker_report(issues, coverage_stats)


def generate_all_role_reports(
    issues: List[Dict[str, Any]], project_name: str = "",
    coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, str]:
    return {
        "supervisor": generate_role_report(issues, "supervisor", coverage_stats),
        "designer": generate_role_report(issues, "designer", coverage_stats),
        "checker": generate_role_report(issues, "checker", coverage_stats),
        "owner": generate_role_report(issues, "owner", coverage_stats),
    }


def _classify_issues(issues: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_severity: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_discipline: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for issue in issues:
        sev = issue.get("severity", "C")
        disc = issue.get("professional", issue.get("discipline", "unknown"))
        by_severity[sev].append(issue)
        by_discipline[disc].append(issue)
    return {"by_severity": dict(by_severity), "by_discipline": dict(by_discipline)}

def _count_by_severity(issues: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    for issue in issues:
        sev = issue.get("severity", "C")
        if sev in counts:
            counts[sev] += 1
    return counts


def _generate_coverage_section(
    coverage_stats: Optional[Dict[str, Dict[str, Any]]],
) -> str:
    """生成各专业审查覆盖率章节 HTML/Markdown 表格"""
    if not coverage_stats:
        return ""

    lines = []
    lines.append("## 各专业审查覆盖率\n")
    lines.append("")
    lines.append("下表展示本次审查各专业的检查点覆盖情况，区分\"已执行\"和\"未执行\"状态：\n")
    lines.append("| 专业 | 总检查点 | 已执行 | 未执行 | 失败 | 发现问题 | 覆盖率 | 执行状态 |")
    lines.append("|------|---------|-------|-------|------|---------|-------|---------|")

    # 排序：先按覆盖率升序排（覆盖率低的在前，突出问题）
    sorted_discs = sorted(
        coverage_stats.items(),
        key=lambda x: (x[1]["coverage_pct"], x[1]["defined"]),
    )
    for disc, stats in sorted_discs:
        defined = stats["defined"]
        executed = stats["executed"]
        skipped = stats["skipped"]
        failed = stats["failed"]
        issues_found = stats["issues_found"]
        coverage_pct = stats["coverage_pct"]
        status_label = {
            "completed": "已完成",
            "skipped_no_drawings": "无图纸跳过",
            "failed": "执行失败",
            "pending": "未执行",
            "running": "执行中",
            "partial": "部分完成",
        }.get(stats["status"], stats["status"])

        not_executed = defined - executed
        lines.append(
            f"| {disc} | {defined} | {executed} | {not_executed} | {failed} | "
            f"{issues_found} | {coverage_pct}% | {status_label} |"
        )

    lines.append("")
    lines.append("> **说明**: 覆盖率 = 已执行检查点数 ÷ 总检查点数 × 100%。")
    lines.append("> \"无图纸跳过\"表示该专业在输入图纸中未匹配到相关图纸，未被实际审查。")
    lines.append("> 覆盖率低于100%的专业建议补充图纸后重新审查。\n")
    return "\n".join(lines)


def _generate_supervisor_report(
    issues: List[Dict[str, Any]],
    coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """建设单位/监理视角：进度影响+整改优先级"""
    classified = _classify_issues(issues)
    severity_counts = _count_by_severity(issues)
    total = len(issues)

    lines = []
    lines.append("# 施工图审查报告（建设单位/监理用）\n")
    lines.append(f"> 生成时间: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"> 适用对象: 建设单位项目负责人、监理工程师\n")
    lines.append("## 一、审查概况\n")
    lines.append(f"本次审查共发现 **{total}** 个问题：")
    lines.append(f"- A级（必须整改）: {severity_counts['A']}项")
    lines.append(f"- B级（建议整改）: {severity_counts['B']}项")
    lines.append(f"- C级（优化建议）: {severity_counts['C']}项")
    lines.append(f"- D级（信息提示）: {severity_counts['D']}项\n")

    lines.append("## 二、按专业分布\n")
    for disc, disc_issues in sorted(classified["by_discipline"].items()):
        disc_sev = _count_by_severity(disc_issues)
        lines.append(f"### {disc}专业（{len(disc_issues)}项）")
        lines.append(f"- A级: {disc_sev['A']} | B级: {disc_sev['B']} | C级: {disc_sev['C']} | D级: {disc_sev['D']}")
        lines.append("")

    lines.append("## 三、A级问题清单（必须整改，影响验收）\n")
    a_issues = classified["by_severity"].get("A", [])
    if not a_issues:
        lines.append("_无A级问题_\n")
    else:
        for i, issue in enumerate(a_issues, 1):
            lines.append(f"**{i}. {issue.get('checkpoint_name', '未命名')}**")
            lines.append(f"- 位置: {issue.get('location', '未标注')}")
            lines.append(f"- 问题: {issue.get('description', '')}")
            if issue.get("current_value") and issue.get("expected_value"):
                lines.append(f"- 当前值/标准值: {issue['current_value']} / {issue['expected_value']}")
            lines.append(f"- 规范依据: {issue.get('standard_code', '')} {issue.get('standard_clause', '')}")
            lines.append(f"- 整改建议: {issue.get('suggestion', '')}")
            lines.append(f"- 建议整改期限: {'开工前' if issue.get('severity')=='A' else '施工前'}")
            lines.append("")

    lines.append("## 四、整改优先级建议\n")
    lines.append("| 优先级 | 内容 | 建议完成时间 |")
    lines.append("|--------|------|------------|")
    lines.append(f"| 最高 | {severity_counts['A']}项A级问题（涉及安全/合规） | 图纸修改后重新送审 |")
    lines.append(f"| 高 | {severity_counts['B']}项B级问题（涉及功能/质量） | 施工图交底前完成 |")
    lines.append(f"| 中 | {severity_counts['C']}项C级问题（优化建议） | 施工前确认 |")
    lines.append(f"| 低 | {severity_counts['D']}项D级问题（信息补充） | 施工过程中完善 |")

    cov_section = _generate_coverage_section(coverage_stats)
    if cov_section:
        lines.append("")
        lines.append(cov_section)

    lines.append("\n---\n")
    lines.append("*本报告由AI辅助生成，最终责任由签字工程师承担。*")
    return "\n".join(lines)


def _generate_designer_report(
    issues: List[Dict[str, Any]],
    coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """设计院视角：技术深度+规范依据"""
    classified = _classify_issues(issues)
    severity_counts = _count_by_severity(issues)
    total = len(issues)

    lines = []
    lines.append("# 施工图审查回复单（设计院用）\n")
    lines.append(f"> 生成时间: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"> 适用对象: 各专业设计负责人\n")
    lines.append(f"## 审查问题汇总（共{total}项）\n")

    for disc, disc_issues in sorted(classified["by_discipline"].items()):
        lines.append(f"## {disc}专业（{len(disc_issues)}项）\n")
        sev_order = {"A": 0, "B": 1, "C": 2, "D": 3}
        disc_issues_sorted = sorted(disc_issues, key=lambda x: sev_order.get(x.get("severity", "C"), 9))
        for i, issue in enumerate(disc_issues_sorted, 1):
            sev = issue.get("severity", "C")
            sev_label = {"A": "【强条】", "B": "【一般】", "C": "【建议】", "D": "【提示】"}
            lines.append(f"### 问题{i} {sev_label.get(sev, '')} {issue.get('checkpoint_name', '未命名')}")
            lines.append(f"- **严重等级**: {sev}级")
            lines.append(f"- **图纸/位置**: {issue.get('drawing_name', '')} / {issue.get('location', '未标注')}")
            lines.append(f"- **问题描述**: {issue.get('description', '')}")
            if issue.get("current_value"):
                lines.append(f"- **设计值**: {issue['current_value']}")
            if issue.get("expected_value"):
                lines.append(f"- **规范要求**: {issue['expected_value']}")
            lines.append(f"- **规范依据**: {issue.get('standard_code', '')} 第{issue.get('standard_clause', '')}条")
            if issue.get("clause_text", issue.get("standard_code", "")):
                ct = issue.get("clause_text", "")
                if ct:
                    lines.append(f"- **条文内容**: {ct}")
            lines.append(f"- **整改要求**: {issue.get('suggestion', '')}")
            lines.append(f"- **回复栏**: （设计填写：修改/解释/驳回）")
            lines.append("")

    cov_section = _generate_coverage_section(coverage_stats)
    if cov_section:
        lines.append("")
        lines.append(cov_section)

    return "\n".join(lines)


def _generate_checker_report(
    issues: List[Dict[str, Any]],
    coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """审图公司视角：合规性+逐条结论"""
    severity_counts = _count_by_severity(issues)
    total = len(issues)
    classified = _classify_issues(issues)

    lines = []
    lines.append("# 施工图设计文件审查报告\n")
    lines.append(f"> 报告编号: AI-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    lines.append(f"> 审查结论: {'不合格' if severity_counts['A'] > 0 else '基本合格'}\n")

    lines.append("## 一、审查结论\n")
    if severity_counts["A"] > 0:
        lines.append(f"**不合格**——存在{severity_counts['A']}项A级（违反强制性条文）问题，必须修改后重新送审。\n")
    elif severity_counts["B"] > 0:
        lines.append(f"**基本合格**——存在{severity_counts['B']}项B级问题，建议修改后通过。\n")
    else:
        lines.append("**合格**——无违反强制性条文问题。\n")

    lines.append("## 二、违反强制性条文（A级）\n")
    a_issues = classified["by_severity"].get("A", [])
    if not a_issues:
        lines.append("_无_\n")
    else:
        for i, issue in enumerate(a_issues, 1):
            lines.append(f"**A-{i}** {issue.get('checkpoint_name', '未命名')}")
            lines.append(f"- 违反: {issue.get('standard_code', '')} 第{issue.get('standard_clause', '')}条")
            lines.append(f"- 位置: {issue.get('location', '未标注')}")
            lines.append(f"- 问题: {issue.get('description', '')}")
            lines.append(f"- 整改: {issue.get('suggestion', '')}")
            lines.append("")

    lines.append("## 三、一般性问题（B级）\n")
    b_issues = classified["by_severity"].get("B", [])
    if not b_issues:
        lines.append("_无_\n")
    else:
        for i, issue in enumerate(b_issues, 1):
            lines.append(f"**B-{i}** {issue.get('checkpoint_name', '未命名')}")
            lines.append(f"- 规范: {issue.get('standard_code', '')} 第{issue.get('standard_clause', '')}条")
            lines.append(f"- 位置: {issue.get('location', '未标注')}")
            lines.append(f"- 问题: {issue.get('description', '')}")
            lines.append(f"- 建议: {issue.get('suggestion', '')}")
            lines.append("")

    lines.append("## 四、优化建议（C/D级）\n")
    cd_issues = classified["by_severity"].get("C", []) + classified["by_severity"].get("D", [])
    if not cd_issues:
        lines.append("_无_\n")
    else:
        for i, issue in enumerate(cd_issues, 1):
            lines.append(f"**C-{i}** {issue.get('checkpoint_name', '未命名')}")
            lines.append(f"- 内容: {issue.get('description', '')}")
            lines.append(f"- 建议: {issue.get('suggestion', '')}")
            lines.append("")

    cov_section = _generate_coverage_section(coverage_stats)
    if cov_section:
        lines.append("")
        lines.append(cov_section)

    return "\n".join(lines)


def _generate_owner_report(
    issues: List[Dict[str, Any]],
    coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """业主视角：风险等级+总投资影响"""
    severity_counts = _count_by_severity(issues)
    total = len(issues)
    classified = _classify_issues(issues)

    risk_score = severity_counts["A"] * _RISK_WEIGHT_A + severity_counts["B"] * _RISK_WEIGHT_B + severity_counts["C"] * _RISK_WEIGHT_C
    if risk_score >= _RISK_THRESHOLD_HIGH:
    # 高——估算每10个A级问题可能增加工期1个月
        risk_level = "高"
        estimated_delay = max(severity_counts["A"] // 10, 1)
    elif risk_score >= _RISK_THRESHOLD_MED:
        risk_level = "中"
        estimated_delay = 0
    else:
        risk_level = "低"
        estimated_delay = 0

    lines = []
    lines.append("# 项目设计质量评估报告（业主用）\n")
    lines.append(f"> 生成时间: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"> 适用对象: 建设单位决策层\n")

    lines.append("## 一、质量评估结论\n")
    lines.append(f"- **总体风险等级**: {risk_level}")
    lines.append(f"- **审查问题总数**: {total}项")
    lines.append(f"- **强制性条文违反**: {severity_counts['A']}项")
    lines.append(f"- **质量风险评分**: {risk_score}分")
    if risk_level == "高":
        lines.append(f"- ⚠️ **风险提示**: 建议要求设计院全面整改后重新送审，预计可能影响工期{estimated_delay}个月")
    elif risk_level == "中":
        lines.append("- **提示**: 存在较多一般性问题，建议施工图交底前完成修改")
    else:
        lines.append("- **结论**: 设计质量良好，可进入下一阶段")
    lines.append("")

    lines.append("## 二、分专业质量评估\n")
    for disc, disc_issues in sorted(classified["by_discipline"].items()):
        disc_sev = _count_by_severity(disc_issues)
        disc_risk = disc_sev["A"] * 10 + disc_sev["B"] * 3 + disc_sev["C"] * 1
        lines.append(f"### {disc}专业")
        lines.append(f"- 问题数: {len(disc_issues)}项 (A级{disc_sev['A']}/B级{disc_sev['B']}/C级{disc_sev['C']})")
        lines.append(f"- 专业风险评分: {disc_risk}分")
        if disc_sev["A"] > 0:
            lines.append(f"- ⚠️ 该专业存在A级问题，需重点关注")
        lines.append("")

    lines.append("## 三、总投资影响评估\n")
    lines.append("| 严重等级 | 数量 | 单项预估增加成本 | 总影响 |")
    lines.append("|---------|------|----------------|--------|")
    lines.append(f"| A级（强条） | {severity_counts['A']}项 | {_A_COST_MIN}-{_A_COST_MAX}万元 | {severity_counts['A']*_A_COST_MIN}-{severity_counts['A']*_A_COST_MAX}万元 |")
    lines.append(f"| B级（一般） | {severity_counts['B']}项 | {_B_COST_MIN}-{_B_COST_MAX}万元 | {severity_counts['B']*_B_COST_MIN}-{severity_counts['B']*_B_COST_MAX}万元 |")
    lines.append(f"| C级（建议） | {severity_counts['C']}项 | {_C_COST_MIN}-{_C_COST_MAX}万元 | {severity_counts['C']*_C_COST_MIN}-{severity_counts['C']*_C_COST_MAX}万元 |")
    total_min = severity_counts["A"]*_A_COST_MIN + severity_counts["B"]*_B_COST_MIN + severity_counts["C"]*_C_COST_MIN
    total_max = severity_counts["A"]*_A_COST_MAX + severity_counts["B"]*_B_COST_MAX + severity_counts["C"]*_C_COST_MAX
    lines.append(f"\n**预估整改总成本**: {total_min:.1f} ~ {total_max:.1f}万元\n")

    lines.append("## 四、决策建议\n")
    if risk_level == "高":
        lines.append("1. **暂缓施工招标**，待设计院完成A级问题整改")
        lines.append("2. **组织第三方复核**，确认整改到位")
        lines.append(f"3. **预留工期**，预计影响{estimated_delay}个月")
    elif risk_level == "中":
        lines.append("1. **要求设计院提交书面回复**，逐条解释或修改")
        lines.append("2. **施工图交底时重点复核**B级问题")
    else:
        lines.append("1. **可按计划推进**施工招标")
        lines.append("2. **施工图交底时确认**C/D级问题")

    cov_section = _generate_coverage_section(coverage_stats)
    if cov_section:
        lines.append("")
        lines.append(cov_section)

    lines.append("\n---\n")
    lines.append("*本评估由AI辅助生成，仅供参考，最终决策以正式施工图审查意见为准。*")
    return "\n".join(lines)
