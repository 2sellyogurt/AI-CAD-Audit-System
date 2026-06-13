# -*- coding: utf-8 -*-
"""多角色报告模板模块

基于同一问题清单生成4份角色定制报告：
  - 设计师: 关注具体修改建议、调整量、规范依据
  - 施工方: 关注施工顺序、安装可行性、工期影响
  - 监理: 关注规范符合性、严重度分级、整改验收标准
  - 业主: 关注总体风险、成本影响、关键问题摘要
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RoleReportConfig:
    """角色报告配置"""
    role_name: str
    role_title: str
    filter_severity: List[str] = field(default_factory=list)
    sort_by: str = "severity"
    include_fields: List[str] = field(default_factory=list)
    exclude_fields: List[str] = field(default_factory=list)
    custom_sections: List[str] = field(default_factory=list)
    max_issues: int = 0  # 0表示不限制


# =====================================================================
# 角色配置定义
# =====================================================================

_DESIGNER_CONFIG = RoleReportConfig(
    role_name="designer",
    role_title="设计师技术报告",
    filter_severity=["critical", "major", "minor"],
    sort_by="severity",
    include_fields=[
        "issue_id", "severity", "issue_type", "drawing_name",
        "component", "location", "description", "standard",
        "requirement", "current_value", "expected_value",
        "evidence", "suggestion",
    ],
    custom_sections=["技术细节", "修改量", "规范条文", "图纸定位"],
)

_CONSTRUCTOR_CONFIG = RoleReportConfig(
    role_name="constructor",
    role_title="施工方执行报告",
    filter_severity=["critical", "major"],
    sort_by="location",
    include_fields=[
        "issue_id", "severity", "issue_type", "drawing_name",
        "component", "location", "description", "suggestion",
    ],
    custom_sections=["施工顺序", "安装可行性", "工期影响", "材料准备"],
)

_SUPERVISOR_CONFIG = RoleReportConfig(
    role_name="supervisor",
    role_title="监理验收报告",
    filter_severity=["critical", "major", "minor"],
    sort_by="severity",
    include_fields=[
        "issue_id", "severity", "issue_type", "drawing_name",
        "component", "location", "description", "standard",
        "requirement", "suggestion",
    ],
    custom_sections=["规范符合性", "严重度分级", "整改期限", "验收标准"],
)

_OWNER_CONFIG = RoleReportConfig(
    role_name="owner",
    role_title="业主风险摘要",
    filter_severity=["critical", "major"],
    sort_by="severity",
    include_fields=[
        "issue_id", "severity", "issue_type", "component",
        "location", "description", "suggestion",
    ],
    max_issues=20,
    custom_sections=["总体风险", "成本影响", "关键问题", "进度影响"],
)

_ROLE_CONFIGS = {
    "designer": _DESIGNER_CONFIG,
    "constructor": _CONSTRUCTOR_CONFIG,
    "supervisor": _SUPERVISOR_CONFIG,
    "owner": _OWNER_CONFIG,
}


# =====================================================================
# 问题转换器
# =====================================================================

def _transform_for_designer(issue: Dict[str, Any]) -> Dict[str, Any]:
    """设计师视角：增加技术细节和修改量。"""
    result = dict(issue)
    suggestion = issue.get("suggestion", "")
    # 提取修改量（如"平移900mm"中的900mm）
    import re
    shift_match = re.search(r'(\d+(?:\.\d+)?)\s*mm', suggestion)
    if shift_match:
        result["adjustment_value"] = f"{shift_match.group(1)}mm"
    else:
        result["adjustment_value"] = "需现场确认"
    # 增加技术备注
    result["technical_note"] = f"【技术要点】{issue.get('standard', '无规范依据')}"
    return result


def _transform_for_constructor(issue: Dict[str, Any]) -> Dict[str, Any]:
    """施工方视角：增加施工顺序和可行性评估。"""
    result = dict(issue)
    severity = issue.get("severity", "")
    issue_type = issue.get("issue_type", "")
    # 施工可行性评估
    if "碰撞" in issue_type:
        result["constructability"] = "需调整安装顺序，可能影响工期"
        result["install_order"] = "优先安装上层管线，下层避让"
    elif "规范违规" in issue_type:
        result["constructability"] = "需设计变更后施工"
        result["install_order"] = "按变更后的图纸施工"
    else:
        result["constructability"] = "可按建议整改"
        result["install_order"] = "常规施工顺序"
    # 工期影响
    result["schedule_impact"] = {
        "critical": "高（需立即停工整改）",
        "major": "中（需计划内整改）",
        "minor": "低（可随施工同步调整）",
    }.get(severity, "未知")
    return result


def _transform_for_supervisor(issue: Dict[str, Any]) -> Dict[str, Any]:
    """监理视角：增加验收标准和整改期限。"""
    result = dict(issue)
    severity = issue.get("severity", "")
    # 整改期限
    result["deadline"] = {
        "critical": "24小时内整改",
        "major": "3日内整改",
        "minor": "7日内整改",
    }.get(severity, "按项目计划")
    # 验收标准
    result["acceptance_criteria"] = f"符合{issue.get('standard', '相关规范')}要求"
    # 监理意见模板
    result["supervisor_comment"] = (
        f"经核查，{issue.get('component', '该构件')}存在{issue.get('issue_type', '问题')}，"
        f"违反{issue.get('standard', '规范')}。要求按整改建议执行，"
        f"整改完成后报验。"
    )
    return result


def _transform_for_owner(issue: Dict[str, Any]) -> Dict[str, Any]:
    """业主视角：简化信息，突出风险和成本。"""
    result = dict(issue)
    severity = issue.get("severity", "")
    # 风险等级
    result["risk_level"] = {
        "critical": "高风险（影响安全/功能）",
        "major": "中风险（影响质量）",
        "minor": "低风险（可优化）",
    }.get(severity, "未知")
    # 成本影响估算
    result["cost_impact"] = {
        "critical": "可能产生重大返工费用",
        "major": "可能产生中等整改费用",
        "minor": "费用影响较小",
    }.get(severity, "待评估")
    # 简化描述
    result["brief_description"] = (
        f"{issue.get('component', '构件')}在{issue.get('location', '某位置')}"
        f"存在{issue.get('issue_type', '问题')}"
    )
    return result


_TRANSFORMERS = {
    "designer": _transform_for_designer,
    "constructor": _transform_for_constructor,
    "supervisor": _transform_for_supervisor,
    "owner": _transform_for_owner,
}


# =====================================================================
# 报告生成器
# =====================================================================

class RoleReportGenerator:
    """多角色报告生成器"""

    def __init__(self):
        self._configs = _ROLE_CONFIGS
        self._transformers = _TRANSFORMERS

    def get_supported_roles(self) -> List[str]:
        return list(self._configs.keys())

    def generate_report(self, role: str, issues: List[Dict[str, Any]],
                        project_info: str = "") -> Dict[str, Any]:
        """生成指定角色的报告。

        Args:
            role: 角色名称 (designer/constructor/supervisor/owner)
            issues: 问题列表
            project_info: 项目信息

        Returns:
            报告字典
        """
        config = self._configs.get(role)
        if not config:
            raise ValueError(f"不支持的角色: {role}，支持: {list(self._configs.keys())}")

        transformer = self._transformers.get(role, lambda x: x)

        # 筛选严重度
        filtered = [i for i in issues if i.get("severity", "") in config.filter_severity]

        # 转换问题
        transformed = [transformer(i) for i in filtered]

        # 限制数量
        if config.max_issues > 0 and len(transformed) > config.max_issues:
            transformed = transformed[:config.max_issues]
            truncated = True
        else:
            truncated = False

        # 排序
        if config.sort_by == "severity":
            severity_order = {"critical": 0, "major": 1, "minor": 2}
            transformed.sort(key=lambda x: severity_order.get(x.get("severity", ""), 3))
        elif config.sort_by == "location":
            transformed.sort(key=lambda x: x.get("location", ""))

        # 统计
        severity_counts = {}
        issue_type_counts = {}
        for i in transformed:
            sev = i.get("severity", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            itype = i.get("issue_type", "unknown")
            issue_type_counts[itype] = issue_type_counts.get(itype, 0) + 1

        return {
            "role": role,
            "role_title": config.role_title,
            "project_info": project_info,
            "total_issues": len(transformed),
            "severity_counts": severity_counts,
            "issue_type_counts": issue_type_counts,
            "truncated": truncated,
            "custom_sections": config.custom_sections,
            "issues": transformed,
        }

    def generate_markdown(self, role: str, issues: List[Dict[str, Any]],
                          project_info: str = "") -> str:
        """生成Markdown格式的角色报告。"""
        report = self.generate_report(role, issues, project_info)
        config = self._configs[role]
        lines = []

        # 标题
        lines.append(f"# {report['role_title']}")
        lines.append("")
        if project_info:
            lines.append(f"**项目**: {project_info}")
            lines.append("")

        # 概况
        lines.append("## 审查概况")
        lines.append(f"- 发现问题: {report['total_issues']}")
        if report.get("truncated"):
            lines.append("- ⚠️ 问题数量较多，仅展示前20条")
        lines.append("")

        # 严重度统计
        counts = report["severity_counts"]
        lines.append("## 问题严重度统计")
        lines.append(f"- 🔴 严重 (critical): {counts.get('critical', 0)}")
        lines.append(f"- 🟠 一般 (major): {counts.get('major', 0)}")
        lines.append(f"- 🟡 提示 (minor): {counts.get('minor', 0)}")
        lines.append("")

        # 角色定制章节
        if role == "designer":
            lines.append("## 技术修改清单")
            lines.append("以下问题需要设计调整，请按issue_id跟踪修改。")
            lines.append("")
        elif role == "constructor":
            lines.append("## 施工执行清单")
            lines.append("以下问题影响施工，请按优先级安排整改。")
            lines.append("")
        elif role == "supervisor":
            lines.append("## 监理整改清单")
            lines.append("以下问题需要监理跟踪验收。")
            lines.append("")
        elif role == "owner":
            lines.append("## 风险摘要")
            lines.append("以下问题可能影响项目质量和成本。")
            lines.append("")

        # 问题清单
        lines.append("## 问题清单")
        for i, issue in enumerate(report["issues"], 1):
            severity = issue.get("severity", "")
            icon = {"critical": "🔴", "major": "🟠", "minor": "🟡"}.get(severity, "⚪")
            lines.append(f"### {i}. {icon} [{issue.get('issue_type', '')}] {issue.get('component', '')}")
            lines.append("")

            # 根据角色展示不同字段
            if role == "designer":
                lines.append(f"**位置**: {issue.get('location', '')}")
                lines.append(f"**问题**: {issue.get('description', '')}")
                if issue.get("standard"):
                    lines.append(f"**规范依据**: {issue['standard']}")
                if issue.get("current_value") or issue.get("expected_value"):
                    lines.append(f"**当前值**: {issue.get('current_value', '无')}")
                    lines.append(f"**期望值**: {issue.get('expected_value', '无')}")
                if issue.get("adjustment_value"):
                    lines.append(f"**调整量**: {issue['adjustment_value']}")
                if issue.get("suggestion"):
                    lines.append(f"**整改建议**: {issue['suggestion']}")
                if issue.get("technical_note"):
                    lines.append(f"**技术备注**: {issue['technical_note']}")

            elif role == "constructor":
                lines.append(f"**位置**: {issue.get('location', '')}")
                lines.append(f"**问题**: {issue.get('description', '')}")
                if issue.get("constructability"):
                    lines.append(f"**施工可行性**: {issue['constructability']}")
                if issue.get("install_order"):
                    lines.append(f"**安装顺序**: {issue['install_order']}")
                if issue.get("schedule_impact"):
                    lines.append(f"**工期影响**: {issue['schedule_impact']}")
                if issue.get("suggestion"):
                    lines.append(f"**整改建议**: {issue['suggestion']}")

            elif role == "supervisor":
                lines.append(f"**位置**: {issue.get('location', '')}")
                lines.append(f"**问题**: {issue.get('description', '')}")
                if issue.get("standard"):
                    lines.append(f"**规范依据**: {issue['standard']}")
                if issue.get("deadline"):
                    lines.append(f"**整改期限**: {issue['deadline']}")
                if issue.get("acceptance_criteria"):
                    lines.append(f"**验收标准**: {issue['acceptance_criteria']}")
                if issue.get("supervisor_comment"):
                    lines.append(f"**监理意见**: {issue['supervisor_comment']}")

            elif role == "owner":
                lines.append(f"**位置**: {issue.get('location', '')}")
                if issue.get("brief_description"):
                    lines.append(f"**问题摘要**: {issue['brief_description']}")
                if issue.get("risk_level"):
                    lines.append(f"**风险等级**: {issue['risk_level']}")
                if issue.get("cost_impact"):
                    lines.append(f"**成本影响**: {issue['cost_impact']}")
                if issue.get("suggestion"):
                    lines.append(f"**建议措施**: {issue['suggestion']}")

            lines.append("")

        return "\n".join(lines)

    def generate_all_reports(self, issues: List[Dict[str, Any]],
                             project_info: str = "") -> Dict[str, Dict[str, Any]]:
        """生成所有角色的报告。"""
        return {
            role: self.generate_report(role, issues, project_info)
            for role in self.get_supported_roles()
        }
