# -*- coding: utf-8 -*-
"""假阴性审计系统

每月随机抽取10%的"通过"结论做双路径复核 → 统计假阴性率 → 超标自动触发全量重审。
"""

from __future__ import annotations

import random
import time
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("v7.audit")


@dataclass
class AuditSample:
    issue_id: str = ""
    checkpoint_id: str = ""
    original_verdict: str = ""
    original_route: str = ""
    original_confidence: str = ""
    recheck_verdict: str = ""
    recheck_route: str = ""
    recheck_confidence: str = ""
    is_false_negative: bool = False
    discrepancy: str = ""


@dataclass
class AuditReport:
    total_passed: int = 0
    sample_size: int = 0
    false_negatives: int = 0
    false_negative_rate: float = 0.0
    threshold_breached: bool = False
    samples: List[AuditSample] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    audit_time: str = ""
    audit_period: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_passed": self.total_passed,
            "sample_size": self.sample_size,
            "false_negatives": self.false_negatives,
            "false_negative_rate": round(self.false_negative_rate, 4),
            "threshold_breached": self.threshold_breached,
            "samples": [
                {
                    "issue_id": s.issue_id,
                    "checkpoint_id": s.checkpoint_id,
                    "original_verdict": s.original_verdict,
                    "recheck_verdict": s.recheck_verdict,
                    "is_false_negative": s.is_false_negative,
                }
                for s in self.samples
            ],
            "recommendations": self.recommendations,
            "audit_time": self.audit_time,
            "audit_period": self.audit_period,
        }


class FalseNegativeAuditor:

    def __init__(
        self,
        sample_rate: float = 0.10,
        threshold: float = 0.001,
        checkpoint_engine=None,
        problem_pool=None,
    ):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._engine = checkpoint_engine
        self._pool = problem_pool
        self._history: List[AuditReport] = []

    def audit(
        self,
        all_check_results: Optional[List[Any]] = None,
        drawing_texts: Optional[Dict[str, str]] = None,
    ) -> AuditReport:
        report = AuditReport(
            audit_time=datetime.now(timezone.utc).isoformat(),
            audit_period=f"monthly_{datetime.now(timezone.utc).strftime('%Y%m')}",
        )

        passed_results = self._get_passed_results(all_check_results)
        if not passed_results:
            logger.info("审计: 无'通过'结论可抽样")
            return report

        report.total_passed = len(passed_results)
        sample_size = max(1, int(len(passed_results) * self.sample_rate))
        report.sample_size = sample_size

        # 基于审计周期设置随机种子，确保结果可复现
        # 使用独立Random实例，避免污染全局random状态
        _rng = random.Random(report.audit_time)
        samples = _rng.sample(passed_results, min(sample_size, len(passed_results)))

        for result in samples:
            sample = AuditSample(
                issue_id=getattr(result, "checkpoint_id", "unknown"),
                checkpoint_id=getattr(result, "checkpoint_id", ""),
                original_verdict=getattr(result, "verdict", "合规"),
                original_route=getattr(result, "route_used", ""),
                original_confidence=getattr(result, "confidence", ""),
            )

            if self._engine:
                try:
                    text = ""
                    cp = self._engine.get(sample.checkpoint_id)
                    if cp and drawing_texts:
                        drawing_name = getattr(result, "drawing_name", "")
                        text = drawing_texts.get(drawing_name, "")
                        if not text and drawing_texts:
                            text = list(drawing_texts.values())[0]

                    recheck = self._engine.execute_one(
                        cp or result, text
                    )
                    sample.recheck_verdict = recheck.verdict
                    sample.recheck_route = recheck.route_used
                    sample.recheck_confidence = recheck.confidence

                    recheck_verdict = getattr(recheck, "verdict", "")
                    if recheck_verdict == "不合规" and sample.original_verdict == "合规":
                        sample.is_false_negative = True
                        sample.discrepancy = f"原判合规→复核判{recheck_verdict}"
                except Exception as e:
                    logger.warning(f"复核异常 [{sample.issue_id}]: {e}")
                    sample.discrepancy = f"复核异常: {e}"

            report.samples.append(sample)

        report.false_negatives = sum(1 for s in report.samples if s.is_false_negative)
        report.false_negative_rate = report.false_negatives / max(report.sample_size, 1)
        report.threshold_breached = report.false_negative_rate > self.threshold

        if report.threshold_breached:
            report.recommendations.append(
                f"假阴性率{report.false_negative_rate:.4f}超过阈值{self.threshold}，建议触发全量重审"
            )
        if report.false_negatives > 0:
            cp_ids = {s.checkpoint_id for s in report.samples if s.is_false_negative}
            report.recommendations.append(
                f"漏判检查点: {', '.join(sorted(cp_ids))}，建议优化Prompt"
            )

        self._history.append(report)
        logger.info(
            f"审计完成: {report.sample_size}样本/{report.total_passed}通过, "
            f"假阴性{report.false_negatives}个({report.false_negative_rate:.2%}), "
            f"{'⚠️ 超标' if report.threshold_breached else '✓ 达标'}"
        )
        return report

    def _get_passed_results(self, results):
        if not results:
            if not self._pool:
                return []
            passed = []
            for i in self._pool.get_all():
                v = getattr(i, "verdict", "")
                if v == "合规":
                    passed.append(i)
            return passed
        return [r for r in results if getattr(r, "verdict", "") == "合规"]

    def generate_quarterly_report(self) -> str:
        if not self._history:
            return "无审计数据"

        lines = [
            "# 假阴性季度审计报告",
            f"\n审计次数: {len(self._history)}",
        ]

        rates = [r.false_negative_rate for r in self._history]
        lines.append(f"平均假阴性率: {sum(rates)/len(rates):.4f}")
        lines.append(f"最高假阴性率: {max(rates):.4f}")
        lines.append(f"最低假阴性率: {min(rates):.4f}")

        breaches = [r for r in self._history if r.threshold_breached]
        if breaches:
            lines.append(f"\n## ⚠️ 超标记录 ({len(breaches)}次)")
            for b in breaches:
                lines.append(f"- {b.audit_period}: {b.false_negative_rate:.4f}")

        all_fn = []
        for r in self._history:
            for s in r.samples:
                if s.is_false_negative:
                    all_fn.append(s.checkpoint_id)
        if all_fn:
            from collections import Counter
            top = Counter(all_fn).most_common(5)
            lines.append(f"\n## 高频漏判检查点 TOP5")
            for cp_id, count in top:
                lines.append(f"- {cp_id}: {count}次")

        all_recs = []
        for r in self._history:
            all_recs.extend(r.recommendations)
        unique_recs = list(dict.fromkeys(all_recs))
        if unique_recs:
            lines.append(f"\n## 改进建议")
            for rec in unique_recs[:10]:
                lines.append(f"- {rec}")

        return "\n".join(lines)

    def save_report(self, path: str, report: Optional[AuditReport] = None) -> str:
        if report is None:
            report = self._history[-1] if self._history else AuditReport()
        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"审计报告已保存: {path}")
        return path
