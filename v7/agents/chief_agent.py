# -*- coding: utf-8 -*-
"""总工Agent

汇总所有专业Agent的审查结果 → 去重 → 分类排序 → 专业润色 → 生成4角色报告。
"""

from __future__ import annotations

import json
import re
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("v7.chief_agent")


@dataclass
class DedupResult:
    original_count: int = 0
    merged_count: int = 0
    final_count: int = 0
    merged_groups: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ChiefReport:
    issues_by_discipline: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    issues_by_severity: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    dedup_result: DedupResult = field(default_factory=DedupResult)
    summary: str = ""
    contradiction_log: List[Dict[str, Any]] = field(default_factory=list)
    markdown_report: str = ""
    role_reports: Dict[str, str] = field(default_factory=dict)
    polished: bool = False
    coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None


class ChiefAgent:

    def __init__(self, problem_pool=None):
        self._pool = problem_pool
        self._merge_distance: float = 10.0

    def deduplicate(self, issues: List[Any]) -> DedupResult:
        """按位置+检查点去重合并。"""
        result = DedupResult(original_count=len(issues))
        merged_flags = [False] * len(issues)
        groups = []

        for i in range(len(issues)):
            if merged_flags[i]:
                continue
            group = [issues[i]]
            for j in range(i + 1, len(issues)):
                if merged_flags[j]:
                    continue
                if self._is_duplicate(issues[i], issues[j]):
                    group.append(issues[j])
                    merged_flags[j] = True
            groups.append(group)

        result.merged_count = sum(len(g) - 1 for g in groups if len(g) > 1)
        result.final_count = len(groups)

        for g in groups:
            if len(g) > 1:
                result.merged_groups.append({
                    "primary": self._issue_id(g[0]),
                    "merged_from": [self._issue_id(m) for m in g[1:]],
                })

        logger.info(f"去重: {result.original_count}→{result.final_count} (合并{result.merged_count}个)")
        return result

    def _is_duplicate(self, a, b) -> bool:
        aid = getattr(a, "checkpoint_id", "") or ""
        bid = getattr(b, "checkpoint_id", "") or ""
        if aid != bid:
            return False

        ax = getattr(a, "cad_coords", {}) or getattr(a, "coords", {}) or {}
        bx = getattr(b, "cad_coords", {}) or getattr(b, "coords", {}) or {}
        if ax and bx:
            dist = ((ax.get("x", 0) - bx.get("x", 0)) ** 2 +
                    (ax.get("y", 0) - bx.get("y", 0)) ** 2) ** 0.5
            return dist < self._merge_distance
        return False

    def classify_and_sort(self, issues: List[Any]) -> Dict[str, List[Any]]:
        by_discipline: Dict[str, List[Any]] = defaultdict(list)
        for issue in issues:
            disc = self._get_discipline(issue)
            by_discipline[disc].append(issue)

        sev_order = {"A": 0, "B": 1, "C": 2, "D": 3}
        for disc in by_discipline:
            by_discipline[disc].sort(
                key=lambda i: sev_order.get(self._get_severity(i), 9)
            )
        return by_discipline

    _TEXT_ABSENCE_PATTERNS = [
        re.compile(r'文本中未(出现|发现|找到|提及|涉及|包含)'),
        re.compile(r'未(标注|注明|标示|标识|说明|体现)'),
        re.compile(r'没有.*(标注|注明|说明)'),
        re.compile(r'无.*(标注|说明|标识)'),
        re.compile(r'图纸.*(未|没有|无).*(标注|说明|出现)'),
        re.compile(r'(全文|图纸文本).*(未|没有).*(出现|发现)'),
        re.compile(r'(未找到|不存在|缺失).*(标注|信息|说明)'),
    ]

    # 严重度降级映射：当发现为文本缺失类问题时，降低严重度一级
    _SEVERITY_DOWNGRADE = {"A": "B", "B": "C", "C": "D", "D": "D"}

    @classmethod
    def _is_text_absence_finding(cls, description: str) -> bool:
        if not description:
            return False
        for pat in cls._TEXT_ABSENCE_PATTERNS:
            if pat.search(description):
                return True
        return False

    @classmethod
    def _mark_visual_required(cls, issue_dict: Dict[str, Any]) -> Dict[str, Any]:
        desc = issue_dict.get("description", "")
        ev = issue_dict.get("evidence", "")
        combined = f"{desc} {ev}"
        if not cls._is_text_absence_finding(combined):
            return issue_dict

        old_sev = issue_dict.get("severity", "C")
        new_sev = cls._SEVERITY_DOWNGRADE.get(old_sev, old_sev)
        issue_dict["severity"] = new_sev
        issue_dict["visual_required"] = True
        issue_dict["description"] = f"【需视觉复核】{desc}"
        sug = issue_dict.get("suggestion", "")
        if sug:
            issue_dict["suggestion"] = f"{sug} (文本路径未检出，建议通过CAD截图视觉复核确认)"
        return issue_dict

    def polish(self, issues_by_discipline: Dict[str, List[Any]]) -> Dict[str, List[Dict[str, Any]]]:
        polished = {}
        for disc, issues in issues_by_discipline.items():
            polished[disc] = []
            for issue in issues:
                d = self._to_dict(issue)
                d = self._mark_visual_required(d)
                if d.get("description"):
                    d["description"] = self._polish_description(d["description"])
                if d.get("suggestion"):
                    d["suggestion"] = self._polish_suggestion(d["suggestion"])
                polished[disc].append(d)
        return polished

    def generate_report_markdown(
        self, polished: Dict[str, List[Dict[str, Any]]],
        project_name: str = "", stats: Optional[Dict[str, Any]] = None,
        coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        lines = []
        lines.append(f"# {project_name or '施工图'} AI辅助审查报告")
        lines.append(f"\n> 生成时间: {__import__('datetime').datetime.now().isoformat()}\n")

        if stats:
            lines.append("## 审查概览\n")
            lines.append(f"- 问题总数: {stats.get('total_issues', 0)}")
            sev = stats.get("by_severity", {})
            lines.append(f"- 严重(A): {sev.get('A', 0)} | 重要(B): {sev.get('B', 0)} | 一般(C): {sev.get('C', 0)} | 提示(D): {sev.get('D', 0)}")
            lines.append(f"- 双路径验证: {stats.get('dual_verified', 0)}项 ({stats.get('dual_verified_pct', 0)}%)")
            lines.append("")

        # 【覆盖率章节】各专业审查覆盖率
        if coverage_stats:
            lines.append("## 各专业审查覆盖率\n")
            lines.append("下表展示本次审查各专业的检查点覆盖情况，区分\"已执行\"和\"未执行\"状态：\n")
            lines.append("| 专业 | 总检查点 | 已执行 | 未执行 | 失败 | 发现问题 | 覆盖率 | 执行状态 |")
            lines.append("|------|---------|-------|-------|------|---------|-------|---------|")
            sorted_discs = sorted(
                coverage_stats.items(),
                key=lambda x: (x[1]["coverage_pct"], x[1]["defined"]),
            )
            for disc, cs in sorted_discs:
                defined = cs["defined"]
                executed = cs["executed"]
                not_executed = defined - executed
                failed = cs["failed"]
                issues_found = cs["issues_found"]
                coverage_pct = cs["coverage_pct"]
                status_label = {
                    "completed": "已完成",
                    "skipped_no_drawings": "无图纸跳过",
                    "failed": "执行失败",
                    "pending": "未执行",
                    "running": "执行中",
                    "partial": "部分完成",
                }.get(cs["status"], cs["status"])
                lines.append(
                    f"| {disc} | {defined} | {executed} | {not_executed} | {failed} | "
                    f"{issues_found} | {coverage_pct}% | {status_label} |"
                )
            lines.append("")
            lines.append("> **说明**: 覆盖率 = 已执行检查点数 ÷ 总检查点数 × 100%。")
            lines.append("> \"无图纸跳过\"表示该专业在输入图纸中未匹配到相关图纸，未被实际审查。")
            lines.append("> 覆盖率低于100%的专业建议补充图纸后重新审查。\n")

        sev_headers = {"A": "严重问题", "B": "重要问题", "C": "一般问题", "D": "提示信息"}
        for sev in ("A", "B", "C", "D"):
            sev_issues = []
            for disc, issues in polished.items():
                for issue in issues:
                    if issue.get("severity") == sev:
                        sev_issues.append((disc, issue))
            if not sev_issues:
                continue
            lines.append(f"## {sev_headers[sev]} ({len(sev_issues)}项)\n")
            for disc, issue in sev_issues:
                lines.append(self._format_issue_markdown(disc, issue))
            lines.append("")

        lines.append("---\n")
        lines.append("*本报告由AI辅助生成，已经人工复核确认。最终责任由签字工程师承担。*")
        return "\n".join(lines)

    def _format_issue_markdown(self, discipline: str, issue: Dict[str, Any]) -> str:
        sev = issue.get("severity", "C")
        cpid = issue.get("checkpoint_id", "")
        name = issue.get("checkpoint_name", issue.get("issue_id", "未命名"))
        header_name = f"{cpid} {name}" if cpid else name
        loc = issue.get("location", "")
        desc = issue.get("description", "")
        standard = issue.get("standard_code", "") + " " + issue.get("standard_clause", "")
        cur = issue.get("current_value", "")
        exp = issue.get("expected_value", "")
        sug = issue.get("suggestion", "")
        conf = issue.get("confidence", "")

        lines = [f"### [{sev}] [{discipline}] {header_name}"]
        if loc:
            lines.append(f"- **位置**: {loc}")
        lines.append(f"- **描述**: {desc}")
        lines.append(f"- **规范依据**: {standard}")
        if cur and exp:
            lines.append(f"- **当前值/期望值**: {cur} / {exp}")
        if sug:
            lines.append(f"- **整改建议**: {sug}")
        lines.append(f"- **置信度**: {conf}")
        lines.append("")
        return "\n".join(lines)

    def generate_role_reports(
        self, issues: List[Dict[str, Any]], role: str = "supervisor",
        coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> str:
        try:
            from v7.report_v7.role_report_generator import generate_role_report
            return generate_role_report(issues, role, coverage_stats)
        except ImportError:
            return self.generate_report_markdown(
                {"all": issues}, "", {"total_issues": len(issues)}, coverage_stats
            )

    def execute(self, problem_pool=None, project_name: str = "",
                coverage_stats: Optional[Dict[str, Dict[str, Any]]] = None) -> ChiefReport:
        if problem_pool:
            self._pool = problem_pool

        report = ChiefReport()
        report.coverage_stats = coverage_stats
        if not self._pool:
            logger.warning("总工Agent: 未关联问题池")
            return report

        issues = self._pool.get_all()
        if not issues:
            report.summary = "无审查问题"
            return report

        report.dedup_result = self.deduplicate(issues)

        by_disc = self.classify_and_sort(issues)
        polished = self.polish(by_disc)
        report.issues_by_discipline = polished

        stats = self._pool.stats()
        report.markdown_report = self.generate_report_markdown(
            polished, project_name, stats, coverage_stats
        )
        report.summary = (
            f"审查完成: {stats['total_issues']}个问题, "
            f"A级{stats['by_severity'].get('A',0)}, "
            f"双路径验证{stats['dual_verified_pct']}%"
        )

        all_dicts = [self._to_dict(i) for i in self._pool.get_all()]
        try:
            from v7.report_v7.role_report_generator import generate_all_role_reports
            report.role_reports = generate_all_role_reports(all_dicts, project_name, coverage_stats)
        except ImportError:
            report.role_reports = {}

        report.polished = True

        return report

    @staticmethod
    def _issue_id(issue) -> str:
        return getattr(issue, "issue_id", "") or ""

    @staticmethod
    def _get_discipline(issue) -> str:
        d = getattr(issue, "discipline", "") or ""
        if not d:
            d = getattr(issue, "professional", "") or ""
        return d or "unknown"

    @staticmethod
    def _get_severity(issue) -> str:
        return getattr(issue, "severity", "D") or "D"

    @staticmethod
    def _to_dict(issue) -> Dict[str, Any]:
        if hasattr(issue, "to_dict") and callable(issue.to_dict):
            return issue.to_dict()
        if isinstance(issue, dict):
            return issue
        return {}

    @staticmethod
    def _clean_json_artifacts(text: str) -> str:
        if not text:
            return text
        if text.strip().startswith("{") and text.strip().endswith("}"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    meaningful = []
                    for k in ("description", "evidence", "suggestion"):
                        v = data.get(k, "")
                        if v and isinstance(v, str) and len(v) > 2:
                            meaningful.append(v)
                    if meaningful:
                        return "；".join(meaningful)
            except Exception:
                pass

        cleaned = re.sub(r'^\s*\{[^{}]*"verdict"\s*:\s*"[^"]*"[^{}]*\}\s*$', '', text, flags=re.DOTALL)
        cleaned = re.sub(r'```json\s*\{[^`]*\}\s*```', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'```\s*\{[^`]*\}\s*```', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'\{[^{}]*"evidence"\s*:\s*"[^"]*"[^{}]*\}', '', cleaned)
        cleaned = re.sub(r'\{[^{}]*"verdict"\s*:\s*"[^"]*"[^{}]*\}', '', cleaned)

        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        cleaned = cleaned.strip().rstrip(',').rstrip(';')
        return cleaned if cleaned else text

    @staticmethod
    def _polish_description(text: str) -> str:
        if not text:
            return text
        text = ChiefAgent._clean_json_artifacts(text)
        replacements = {
            "不够宽": "净宽度不满足规范要求",
            "太小": "尺寸不足",
            "门不够": "门的设置不满足",
            "没有标注": "缺失标注",
            "可能有问题": "存在不合规风险",
            "少了": "缺少",
        }
        for informal, formal in replacements.items():
            if informal in text:
                text = text.replace(informal, formal)
        return text

    @staticmethod
    def _polish_suggestion(text: str) -> str:
        if not text:
            return text
        text = ChiefAgent._clean_json_artifacts(text)
        if not text.startswith("建议") and not text.startswith("应"):
            text = "建议" + text
        if not text.endswith("。") and len(text) > 10:
            text += "。"
        return text
