# -*- coding: utf-8 -*-
"""Agent集群调度器

并行调度7个Agent + 异常恢复 + 进度监控 + 结果汇总。
"""

from __future__ import annotations

import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from v7.agents.base_agent import BaseAgent, AgentReport
from v7.agents import AGENT_REGISTRY, BaseAgent, FreeReviewAgent

logger = logging.getLogger("v7.scheduler")


@dataclass
class ExecutionReceipt:
    """执行确认回执——记录每个Agent的调度与执行状态"""
    agent_id: str
    agent_name: str
    discipline: str = ""
    execution_status: str = "pending"  # pending | running | completed | skipped_no_drawings | failed | partial
    total_checkpoints_defined: int = 0
    total_checkpoints_executed: int = 0
    total_checkpoints_skipped: int = 0
    total_checkpoints_failed: int = 0
    issues_found: int = 0
    error_message: str = ""
    start_time: str = ""
    end_time: str = ""
    dispatch_method: str = "full"  # full | smart_scan | manual
    filter_result_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "discipline": self.discipline,
            "execution_status": self.execution_status,
            "total_checkpoints_defined": self.total_checkpoints_defined,
            "total_checkpoints_executed": self.total_checkpoints_executed,
            "total_checkpoints_skipped": self.total_checkpoints_skipped,
            "total_checkpoints_failed": self.total_checkpoints_failed,
            "issues_found": self.issues_found,
            "error_message": self.error_message,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "dispatch_method": self.dispatch_method,
            "filter_result_count": self.filter_result_count,
        }


@dataclass
class OrchestrationReport:
    agent_reports: Dict[str, AgentReport] = field(default_factory=dict)
    execution_receipts: Dict[str, ExecutionReceipt] = field(default_factory=dict)
    total_issues: int = 0
    total_checkpoints: int = 0
    total_time_ms: float = 0.0
    failed_agents: List[str] = field(default_factory=list)
    pool_stats: Dict[str, Any] = field(default_factory=dict)
    execution_order: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_reports": {k: v.to_dict() for k, v in self.agent_reports.items()},
            "execution_receipts": {k: v.to_dict() for k, v in self.execution_receipts.items()},
            "total_issues": self.total_issues,
            "total_checkpoints": self.total_checkpoints,
            "total_time_ms": self.total_time_ms,
            "failed_agents": self.failed_agents,
            "pool_stats": self.pool_stats,
        }

    def coverage_stats(self) -> Dict[str, Dict[str, Any]]:
        """按专业统计审查覆盖率"""
        stats: Dict[str, Dict[str, Any]] = {}
        for agent_id, receipt in self.execution_receipts.items():
            disc = receipt.discipline or agent_id
            total = receipt.total_checkpoints_defined
            executed = receipt.total_checkpoints_executed
            skipped = receipt.total_checkpoints_skipped
            failed = receipt.total_checkpoints_failed
            stats[disc] = {
                "defined": total,
                "executed": executed,
                "skipped": skipped,
                "failed": failed,
                "issues_found": receipt.issues_found,
                "coverage_pct": round(executed / max(total, 1) * 100, 1) if total > 0 else 0.0,
                "status": receipt.execution_status,
                "dispatch_method": receipt.dispatch_method,
            }
        return stats


class AgentOrchestrator:

    def __init__(self, max_workers: int = 11):
        self._max_workers = min(max_workers, len(AGENT_REGISTRY))
        self._agents: Dict[str, BaseAgent] = {}
        self._progress: Dict[str, str] = {}
        self._progress_lock = threading.Lock()

    @property
    def agents(self) -> Dict[str, BaseAgent]:
        return self._agents

    def create_all_agents(self) -> None:
        for agent_id, agent_cls in AGENT_REGISTRY.items():
            self._agents[agent_id] = agent_cls()
        logger.info(f"创建{len(self._agents)}个Agent")

    def get_progress(self) -> Dict[str, str]:
        with self._progress_lock:
            return dict(self._progress)

    def execute_parallel(
        self,
        drawing_infos: List[Any],
        problem_pool=None,
        image_paths: Optional[Dict[str, List[str]]] = None,
    ) -> OrchestrationReport:
        if not self._agents:
            self.create_all_agents()

        report = OrchestrationReport()
        start_all = time.time()

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {}
            for agent_id, agent in self._agents.items():
                future = executor.submit(
                    self._execute_agent_safe,
                    agent_id, agent, drawing_infos, problem_pool, image_paths,
                )
                futures[future] = agent_id

            for future in as_completed(futures):
                agent_id = futures[future]
                try:
                    agent_report = future.result()
                    report.agent_reports[agent_id] = agent_report
                    report.execution_order.append(agent_id)
                    with self._progress_lock:
                        self._progress[agent_id] = "completed"
                    logger.info(f"[{agent_id}] 完成: {agent_report.issues_found}个问题")
                except Exception as e:
                    logger.error(f"[{agent_id}] 执行失败: {e}")
                    report.failed_agents.append(agent_id)
                    with self._progress_lock:
                        self._progress[agent_id] = f"failed: {e}"

        report.total_time_ms = (time.time() - start_all) * 1000
        report.total_issues = sum(
            r.issues_found for r in report.agent_reports.values()
        )
        report.total_checkpoints = sum(
            r.total_checkpoints for r in report.agent_reports.values()
        )
        if problem_pool:
            report.pool_stats = problem_pool.stats()

        logger.info(
            f"调度完成: {len(report.agent_reports)}个Agent成功, "
            f"{len(report.failed_agents)}个失败, "
            f"{report.total_issues}个问题, "
            f"{report.total_time_ms:.0f}ms"
        )
        return report

    def _execute_agent_safe(
        self, agent_id: str, agent: BaseAgent,
        drawing_infos, problem_pool, image_paths,
    ) -> AgentReport:
        with self._progress_lock:
            self._progress[agent_id] = "running"

        for attempt in range(3):
            try:
                return agent.execute(drawing_infos, problem_pool, image_paths)
            except Exception as e:
                logger.warning(f"[{agent_id}] 第{attempt+1}次尝试失败: {e}")
                if attempt == 2:
                    raise
                time.sleep(2)

        raise RuntimeError(f"[{agent_id}] 3次尝试全部失败")

    def execute_sequential(
        self, drawing_infos, problem_pool=None, image_paths=None,
    ) -> OrchestrationReport:
        if not self._agents:
            self.create_all_agents()

        report = OrchestrationReport()
        start_all = time.time()

        priority_order = ["fire", "building", "structure", "hvac", "plumbing", "electrical",
                         "curtain_wall", "decoration", "landscape", "foundation_pit", "free_review"]
        for agent_id in priority_order:
            if agent_id not in self._agents:
                continue
            agent = self._agents[agent_id]
            report.execution_order.append(agent_id)
            try:
                agent_report = agent.execute(drawing_infos, problem_pool, image_paths)
                report.agent_reports[agent_id] = agent_report
            except Exception as e:
                report.failed_agents.append(agent_id)

        report.total_time_ms = (time.time() - start_all) * 1000
        report.total_issues = sum(r.issues_found for r in report.agent_reports.values())
        report.total_checkpoints = sum(r.total_checkpoints for r in report.agent_reports.values())
        if problem_pool:
            report.pool_stats = problem_pool.stats()

        return report

    def execute_smart(
        self, drawing_infos, problem_pool=None, image_paths=None, scan_result=None,
        project_params=None,
    ) -> OrchestrationReport:
        """全专业调度（3a）+ 执行确认回执（3b）。

        - 默认全专业调度：无论 scan_result 如何，始终激活所有已注册的 Agent
        - scan_result 仅用于记录元数据（检测到的专业、风险等级）和严重度过滤
        - 每个 Agent 均生成 ExecutionReceipt 作为执行确认回执
        - project_params: 项目参数对象，注入到每个Agent的审查上下文中
        """
        if not self._agents:
            self.create_all_agents()

        # 注入项目参数到所有Agent
        if project_params is not None:
            for agent in self._agents.values():
                agent.set_project_params(project_params)

        report = OrchestrationReport()
        start_all = time.time()
        now_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start_all))

        disc_map = {
            "building": "building", "structure": "structure",
            "hvac": "hvac", "plumbing": "plumbing",
            "electrical": "electrical", "fire": "fire",
            "curtain_wall": "curtain_wall", "decoration": "decoration",
            "landscape": "landscape", "foundation_pit": "foundation_pit",
            "free_review": "free_review",
        }

        # 【3a】默认全专业调度：激活所有已注册 Agent
        active_ids = list(self._agents.keys())
        dispatch_method = "full"

        # scan_result 仅用于记录元数据和严重度过滤，不用于排除专业
        skip_severities = {}
        scan_relevant_disciplines = []
        scan_skipped_disciplines = []
        if scan_result is not None:
            dispatch_method = "smart_scan"
            scan_relevant_disciplines = list(scan_result.relevant_disciplines)
            scan_skipped_disciplines = list(scan_result.suggested_skip_disciplines)
            if scan_result.risk_level == "low":
                skip_severities = {"C": True, "D": True}
            elif scan_result.risk_level == "medium":
                skip_severities = {"D": True}
            logger.info(
                f"全专业调度(scan辅助模式): 激活全部{len(active_ids)}个Agent, "
                f"scan检测专业={scan_relevant_disciplines}, "
                f"scan建议跳过={scan_skipped_disciplines}, "
                f"risk={scan_result.risk_level}, skip_sev={list(skip_severities.keys())}"
            )
        else:
            logger.info(f"全专业调度(无scan结果): 激活全部{len(active_ids)}个Agent")

        for agent_id in active_ids:
            if agent_id not in self._agents:
                continue
            agent = self._agents[agent_id]
            report.execution_order.append(agent_id)

            # 【3b】创建执行确认回执
            receipt = ExecutionReceipt(
                agent_id=agent_id,
                agent_name=agent.config.name if hasattr(agent.config, 'name') else agent_id,
                discipline=agent.config.discipline if hasattr(agent.config, 'discipline') else "",
                execution_status="running",
                start_time=now_str,
                dispatch_method=dispatch_method,
            )

            try:
                filtered = agent.filter_drawings(drawing_infos)
                receipt.filter_result_count = len(filtered)

                if not filtered:
                    logger.info(f"[{agent_id}] 过滤后无匹配图纸")
                    receipt.execution_status = "skipped_no_drawings"
                    # 仍有回执——记录为"无图纸可审"
                    report.execution_receipts[agent_id] = receipt
                    # 补充一个空的 AgentReport 以便后续统计
                    report.agent_reports[agent_id] = AgentReport(
                        agent_id=agent_id,
                        agent_name=agent.config.name if hasattr(agent.config, 'name') else agent_id,
                    )
                    continue

                agent_report = agent.execute_with_filter(
                    filtered, problem_pool, image_paths,
                    skip_severities=skip_severities,
                )
                report.agent_reports[agent_id] = agent_report

                # 【3b】填充回执详情
                receipt.total_checkpoints_defined = agent_report.total_checkpoints
                receipt.total_checkpoints_executed = agent_report.executed
                receipt.total_checkpoints_skipped = (
                    agent_report.total_checkpoints - agent_report.executed
                    if agent_report.total_checkpoints > 0 else 0
                )
                receipt.total_checkpoints_failed = agent_report.errors
                receipt.issues_found = agent_report.issues_found
                receipt.execution_status = "completed"

            except Exception as e:
                logger.error(f"[{agent_id}] 执行失败: {e}")
                receipt.execution_status = "failed"
                receipt.error_message = str(e)
                report.failed_agents.append(agent_id)
                report.agent_reports[agent_id] = AgentReport(
                    agent_id=agent_id,
                    agent_name=agent.config.name if hasattr(agent.config, 'name') else agent_id,
                    error=str(e),
                )

            receipt.end_time = time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime(time.time())
            )
            report.execution_receipts[agent_id] = receipt

        report.total_time_ms = (time.time() - start_all) * 1000
        report.total_issues = sum(r.issues_found for r in report.agent_reports.values())
        report.total_checkpoints = sum(r.total_checkpoints for r in report.agent_reports.values())
        if problem_pool:
            report.pool_stats = problem_pool.stats()

        # 输出覆盖率统计摘要
        cov = report.coverage_stats()
        cov_summary = "; ".join(
            f"{d}: {s['coverage_pct']}%({s['executed']}/{s['defined']})"
            for d, s in cov.items()
        )
        logger.info(
            f"全专业调度完成: {len(report.agent_reports)}个Agent, "
            f"{report.total_issues}个问题, {report.total_time_ms:.0f}ms | "
            f"覆盖率: {cov_summary}"
        )
        return report
