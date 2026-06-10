# -*- coding: utf-8 -*-
"""Agent基类

每个专业Agent = 独立LLM实例 + 专属角色Prompt + 专业图纸过滤 + 指定检查点集。
"""

from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("v7.agents")


@dataclass
class AgentConfig:
    agent_id: str
    name: str
    discipline: str
    persona: str = ""
    role_title: str = ""
    experience_years: int = 15
    standards: List[str] = field(default_factory=list)
    checkpoints: List[str] = field(default_factory=list)
    text_provider: str = ""
    vision_provider: str = ""
    max_concurrent: int = 3


@dataclass
class AgentReport:
    agent_id: str
    agent_name: str
    total_checkpoints: int = 0
    executed: int = 0
    issues_found: int = 0
    errors: int = 0
    total_time_ms: float = 0.0
    results: List[Any] = field(default_factory=list)
    self_assessment: str = ""
    cross_discipline_notes: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "total_checkpoints": self.total_checkpoints,
            "executed": self.executed,
            "issues_found": self.issues_found,
            "errors": self.errors,
            "total_time_ms": self.total_time_ms,
            "self_assessment": self.self_assessment,
            "cross_discipline_notes": self.cross_discipline_notes,
            "error": self.error,
        }


class BaseAgent(ABC):

    def __init__(self, config: AgentConfig):
        self.config = config
        self._engine = None
        self._llm = None
        self._report = AgentReport(
            agent_id=config.agent_id,
            agent_name=config.name,
        )

    @property
    def engine(self):
        if self._engine is None:
            from v7.checkpoints import CheckpointEngine
            self._engine = CheckpointEngine()
        return self._engine

    @property
    def report(self) -> AgentReport:
        return self._report

    @abstractmethod
    def build_system_prompt(self) -> str:
        """构建该Agent的专属系统Prompt（角色人设）。"""

    @abstractmethod
    def filter_drawings(self, drawing_infos: List[Any]) -> List[Any]:
        """过滤属于本专业的图纸。"""

    def get_checkpoints(self) -> List[Any]:
        """获取本Agent需要执行的检查点列表。"""
        cps = self.engine.list_by_discipline(self.config.discipline)
        if self.config.checkpoints:
            cps = [c for c in cps if c.id in self.config.checkpoints]
        self._report.total_checkpoints = len(cps)
        return cps

    def execute(
        self,
        drawing_infos: List[Any],
        problem_pool=None,
        image_paths: Optional[Dict[str, List[str]]] = None,
    ) -> AgentReport:
        """执行Agent审查全流程（使用filter_drawings自动过滤图纸）。"""
        drawings = self.filter_drawings(drawing_infos)
        if not drawings:
            logger.warning(f"{self.config.name}: 无匹配图纸")
            self._report = AgentReport(
                agent_id=self.config.agent_id,
                agent_name=self.config.name,
            )
            return self._report
        return self._execute_core(drawings, problem_pool, image_paths)

    def execute_with_filter(
        self,
        drawings: List[Any],
        problem_pool=None,
        image_paths: Optional[Dict[str, List[str]]] = None,
        skip_severities: Optional[Dict[str, bool]] = None,
    ) -> AgentReport:
        """执行Agent审查——使用已过滤的图纸列表+可选的检查点严重度过滤。"""
        if not drawings:
            self._report = AgentReport(
                agent_id=self.config.agent_id,
                agent_name=self.config.name,
            )
            return self._report
        return self._execute_core(drawings, problem_pool, image_paths, skip_severities)

    _TEXT_BATCH_CHARS = 90000

    @staticmethod
    def _build_drawing_batches(drawings, image_paths=None):
        batches = []
        current_chars = 0
        current_texts = []
        current_imgs = []
        for d in drawings:
            d_text = getattr(d, 'text_content', '') or ''
            d_name = getattr(d, 'readable_name', '')
            d_imgs = (image_paths or {}).get(d_name, [])
            chunk = f"【{d_name}】\n{d_text}"
            if current_chars + len(chunk) > BaseAgent._TEXT_BATCH_CHARS and current_texts:
                batches.append(("\n\n=====\n\n".join(current_texts), list(current_imgs)))
                current_texts = []
                current_imgs = []
                current_chars = 0
            current_texts.append(chunk)
            current_imgs.extend(d_imgs)
            current_chars += len(chunk)
        if current_texts:
            batches.append(("\n\n=====\n\n".join(current_texts), list(current_imgs)))
        return batches

    def _execute_core(
        self,
        drawings: List[Any],
        problem_pool=None,
        image_paths: Optional[Dict[str, List[str]]] = None,
        skip_severities: Optional[Dict[str, bool]] = None,
    ) -> AgentReport:
        """执行Agent审查全流程。"""
        start = time.time()
        self._report = AgentReport(
            agent_id=self.config.agent_id,
            agent_name=self.config.name,
        )

        if not drawings:
            logger.warning(f"{self.config.name}: 无匹配图纸")
            self._report.total_time_ms = (time.time() - start) * 1000
            return self._report

        checkpoints = self.get_checkpoints()
        if skip_severities:
            checkpoints = [c for c in checkpoints
                           if str(c.severity.value) not in skip_severities]
        self._report.total_checkpoints = len(checkpoints)

        batches = self._build_drawing_batches(drawings, image_paths)
        total_chars = sum(len(b[0]) for b in batches)
        logger.info(
            f"{self.config.name}: {len(drawings)}张→{len(batches)}批(共{total_chars}字), "
            f"{len(checkpoints)}个检查点"
            + (f" (过滤{skip_severities})" if skip_severities else "")
        )

        for cp in checkpoints:
            try:
                best_issue = None
                all_compliant = True
                for batch_idx, (batch_text, batch_imgs) in enumerate(batches):
                    result = self.engine.execute_one(
                        cp, batch_text, batch_imgs if batch_imgs else None
                    )
                    result.agent_name = self.config.agent_id
                    if batch_idx == 0:
                        self._report.results.append(result)
                    self._report.executed += 1

                    if result.verdict == "不合规":
                        all_compliant = False
                        if best_issue is None:
                            best_issue = result
                        elif (result.confidence == "high"
                              and best_issue.confidence != "high"):
                            best_issue = result
                    elif result.error:
                        self._report.errors += 1

                if best_issue and problem_pool:
                    self._report.issues_found += 1
                    problem_pool.add_from_checkpoint(
                        best_issue,
                        text_entity=getattr(drawings[0], "text_entities", [None])[0]
                        if hasattr(drawings[0], "text_entities") and drawings[0].text_entities
                        else None,
                        agent_name=self.config.name,
                    )
                elif all_compliant and batches and problem_pool:
                    problem_pool.record_compliance(
                        checkpoint_id=cp.id if hasattr(cp, 'id') else "",
                        checkpoint_name=cp.name if hasattr(cp, 'name') else "",
                        severity=cp.severity.value if hasattr(cp.severity, 'value') else "",
                        agent_name=self.config.name,
                        confidence="high",
                        drawing_name=getattr(drawings[0], "readable_name", "") if drawings else "",
                        route_used="text",
                    )

            except Exception as e:
                logger.error(f"{self.config.name}执行{cp.id}失败: {e}")
                self._report.errors += 1

        self._report.total_time_ms = (time.time() - start) * 1000
        self._report.self_assessment = self._generate_self_assessment()
        logger.info(
            f"{self.config.name}: {self._report.executed}次检查({len(batches)}批), "
            f"{self._report.issues_found}个问题, "
            f"{self._report.errors}个错误, "
            f"{self._report.total_time_ms:.0f}ms"
        )
        return self._report

    def _generate_self_assessment(self) -> str:
        if self._report.total_checkpoints == 0:
            return "无检查点可执行"
        exec_rate = self._report.executed / max(self._report.total_checkpoints, 1)
        if exec_rate >= 0.95 and self._report.errors == 0:
            return f"本专业审查完成，{self._report.issues_found}个问题待复核"
        elif self._report.errors > 0:
            return f"审查完成但{self._report.errors}个检查点异常，建议人工复核"
        return f"审查进度{exec_rate:.0%}，建议补充执行未覆盖检查点"
