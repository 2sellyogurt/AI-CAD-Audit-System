# -*- coding: utf-8 -*-
"""
DAG执行引擎 - 将扁平化管线改造为有向无环图

核心能力：
1. 定义步骤间的依赖关系（DAG）
2. 自动计算拓扑排序
3. 支持并行执行无依赖关系的步骤
4. 失败传播：上游失败自动跳过下游
5. 执行报告：记录每个步骤的状态、耗时、依赖

设计原则：
- 保持向后兼容：原有线性执行模式不受影响
- 最小化修改：不改变各Step脚本的内部逻辑
- 安全第一：默认串行执行，并行需显式启用
"""

import os
import sys
import time
import subprocess
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepNode:
    step_id: int
    name: str
    script: str
    description: str
    output_hint: str
    depends_on: List[int] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error_message: Optional[str] = None

    @property
    def elapsed(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


@dataclass
class DAGExecutionReport:
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    total_elapsed: float = 0.0
    step_reports: Dict[int, StepNode] = field(default_factory=dict)
    execution_order: List[List[int]] = field(default_factory=list)
    parallel_enabled: bool = False

    @property
    def all_success(self) -> bool:
        return all(
            node.status in (StepStatus.SUCCESS, StepStatus.SKIPPED)
            for node in self.step_reports.values()
        )

    def summary(self) -> str:
        lines = []
        lines.append(f"总耗时: {self.total_elapsed:.1f}s")
        lines.append(f"并行模式: {'启用' if self.parallel_enabled else '禁用'}")
        lines.append(f"执行波次: {len(self.execution_order)}")
        lines.append("")
        for wave_idx, wave in enumerate(self.execution_order):
            lines.append(f"  波次 {wave_idx + 1}: {', '.join(f'Step{s}' for s in wave)}")
        lines.append("")
        for step_id in sorted(self.step_reports.keys()):
            node = self.step_reports[step_id]
            icon = {"success": "✓", "failed": "✗", "skipped": "⊘", "pending": "○"}.get(
                node.status.value, "?"
            )
            elapsed_str = f"{node.elapsed:.1f}s" if node.elapsed else "N/A"
            lines.append(f"  {icon} Step {node.step_id}: {node.name} [{elapsed_str}]")
            if node.error_message:
                lines.append(f"    错误: {node.error_message}")
        return "\n".join(lines)


class DAGExecutor:
    def __init__(self, steps_config: List[Dict[str, Any]]):
        self.nodes: Dict[int, StepNode] = {}
        self._build_graph(steps_config)

    def _build_graph(self, steps_config: List[Dict[str, Any]]):
        for cfg in steps_config:
            node = StepNode(
                step_id=cfg["id"],
                name=cfg["name"],
                script=cfg["script"],
                description=cfg.get("description", ""),
                output_hint=cfg.get("output_hint", ""),
                depends_on=cfg.get("depends_on", []),
            )
            self.nodes[node.step_id] = node

    def get_dependencies(self, step_id: int) -> List[int]:
        return list(self.nodes[step_id].depends_on)

    def get_dependents(self, step_id: int) -> List[int]:
        return [
            nid for nid, node in self.nodes.items()
            if step_id in node.depends_on
        ]

    def validate_dag(self) -> Tuple[bool, List[str]]:
        errors = []
        for step_id, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    errors.append(f"Step {step_id} 依赖不存在的 Step {dep}")

        if self._has_cycle():
            errors.append("DAG 中存在循环依赖")

        return len(errors) == 0, errors

    def _has_cycle(self) -> bool:
        visited = set()
        rec_stack = set()

        def dfs(node_id: int) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for dep in self.nodes[node_id].depends_on:
                if dep not in self.nodes:
                    continue
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in rec_stack:
                    return True
            rec_stack.discard(node_id)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if dfs(node_id):
                    return True
        return False

    def topological_sort(self) -> List[List[int]]:
        in_degree = {nid: len(node.depends_on) for nid, node in self.nodes.items()}
        waves = []
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])

        while queue:
            wave = list(queue)
            waves.append(sorted(wave))
            next_queue = deque()
            for nid in wave:
                for dependent in self.get_dependents(nid):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)
            queue = next_queue

        return waves

    def execute_sequential(
        self,
        run_step_fn: Callable,
        step_args: Dict[str, Any],
        skip_steps: Optional[Set[int]] = None,
        stop_after: Optional[int] = None,
    ) -> DAGExecutionReport:
        skip_steps = skip_steps or set()
        report = DAGExecutionReport(parallel_enabled=False)
        waves = self.topological_sort()
        report.execution_order = waves
        failed_upstream: Set[int] = set()

        for step_id in self.nodes:
            report.step_reports[step_id] = self.nodes[step_id]

        for wave in waves:
            for step_id in wave:
                if stop_after is not None and step_id > stop_after:
                    self.nodes[step_id].status = StepStatus.SKIPPED
                    continue

                if step_id in skip_steps:
                    self.nodes[step_id].status = StepStatus.SKIPPED
                    continue

                deps_blocked = any(
                    dep in failed_upstream
                    for dep in self.nodes[step_id].depends_on
                )
                if deps_blocked:
                    self.nodes[step_id].status = StepStatus.SKIPPED
                    self.nodes[step_id].error_message = "上游依赖失败，自动跳过"
                    failed_upstream.add(step_id)
                    continue

                self._execute_single(step_id, run_step_fn, step_args)
                if self.nodes[step_id].status == StepStatus.FAILED:
                    failed_upstream.add(step_id)

        report.end_time = datetime.now()
        report.total_elapsed = (report.end_time - report.start_time).total_seconds()
        return report

    def execute_parallel(
        self,
        run_step_fn: Callable,
        step_args: Dict[str, Any],
        max_workers: int = 3,
        skip_steps: Optional[Set[int]] = None,
        stop_after: Optional[int] = None,
    ) -> DAGExecutionReport:
        skip_steps = skip_steps or set()
        report = DAGExecutionReport(parallel_enabled=True)
        waves = self.topological_sort()
        report.execution_order = waves
        failed_upstream: Set[int] = set()

        for step_id in self.nodes:
            report.step_reports[step_id] = self.nodes[step_id]

        for wave in waves:
            runnable = []
            for step_id in wave:
                if stop_after is not None and step_id > stop_after:
                    self.nodes[step_id].status = StepStatus.SKIPPED
                    continue
                if step_id in skip_steps:
                    self.nodes[step_id].status = StepStatus.SKIPPED
                    continue
                deps_blocked = any(
                    dep in failed_upstream
                    for dep in self.nodes[step_id].depends_on
                )
                if deps_blocked:
                    self.nodes[step_id].status = StepStatus.SKIPPED
                    self.nodes[step_id].error_message = "上游依赖失败，自动跳过"
                    failed_upstream.add(step_id)
                    continue
                runnable.append(step_id)

            if len(runnable) <= 1:
                for step_id in runnable:
                    self._execute_single(step_id, run_step_fn, step_args)
                    if self.nodes[step_id].status == StepStatus.FAILED:
                        failed_upstream.add(step_id)
            else:
                with ThreadPoolExecutor(max_workers=min(max_workers, len(runnable))) as executor:
                    futures = {
                        executor.submit(self._execute_single, sid, run_step_fn, step_args): sid
                        for sid in runnable
                    }
                    for future in as_completed(futures):
                        sid = futures[future]
                        future.result()
                        if self.nodes[sid].status == StepStatus.FAILED:
                            failed_upstream.add(sid)

        report.end_time = datetime.now()
        report.total_elapsed = (report.end_time - report.start_time).total_seconds()
        return report

    def _execute_single(self, step_id: int, run_step_fn: Callable, step_args: Dict[str, Any]):
        node = self.nodes[step_id]
        node.status = StepStatus.RUNNING
        node.start_time = time.time()
        try:
            success = run_step_fn(
                {"id": node.step_id, "name": node.name, "script": node.script,
                 "description": node.description, "output_hint": node.output_hint},
                **step_args,
            )
            node.status = StepStatus.SUCCESS if success else StepStatus.FAILED
            if not success:
                node.error_message = "步骤执行失败"
        except Exception as e:
            node.status = StepStatus.FAILED
            node.error_message = str(e)
        finally:
            node.end_time = time.time()

    def execution_plan_str(self) -> str:
        waves = self.topological_sort()
        lines = ["DAG 执行计划:", ""]
        for wave_idx, wave in enumerate(waves):
            if len(wave) > 1:
                lines.append(f"  波次 {wave_idx + 1} (并行): {', '.join(f'Step{s}({self.nodes[s].name})' for s in wave)}")
            else:
                lines.append(f"  波次 {wave_idx + 1}: Step{wave[0]}({self.nodes[wave[0]].name})")
            deps_info = []
            for step_id in wave:
                deps = self.nodes[step_id].depends_on
                if deps:
                    deps_info.append(f"Step{step_id} ← {', '.join(f'Step{d}' for d in deps)}")
            if deps_info:
                for info in deps_info:
                    lines.append(f"         {info}")
        lines.append("")
        lines.append(f"  共 {len(waves)} 个波次，最大并行度: {max(len(w) for w in waves)}")
        return "\n".join(lines)
