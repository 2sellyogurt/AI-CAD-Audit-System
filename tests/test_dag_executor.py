# -*- coding: utf-8 -*-
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.dag_executor import (
    DAGExecutionReport,
    DAGExecutor,
    StepNode,
    StepStatus,
)


SIMPLE_STEPS = [
    {"id": 0, "name": "A", "script": "a.py", "depends_on": []},
    {"id": 1, "name": "B", "script": "b.py", "depends_on": [0]},
    {"id": 2, "name": "C", "script": "c.py", "depends_on": [0]},
    {"id": 3, "name": "D", "script": "d.py", "depends_on": [1, 2]},
]

PIPELINE_STEPS = [
    {"id": 0, "name": "参数锚定", "script": "step0.py", "depends_on": [1]},
    {"id": 1, "name": "DXF提取", "script": "step1.py", "depends_on": []},
    {"id": 2, "name": "合规审查", "script": "step2.py", "depends_on": [0, 1]},
    {"id": 3, "name": "错漏排查", "script": "step3.py", "depends_on": [0, 1]},
    {"id": 4, "name": "跨专业校验", "script": "step4.py", "depends_on": [2, 3]},
    {"id": 5, "name": "报告生成", "script": "step5.py", "depends_on": [4]},
    {"id": 6, "name": "BIM重建", "script": "step6.py", "depends_on": [1]},
]

CYCLIC_STEPS = [
    {"id": 0, "name": "A", "script": "a.py", "depends_on": [2]},
    {"id": 1, "name": "B", "script": "b.py", "depends_on": [0]},
    {"id": 2, "name": "C", "script": "c.py", "depends_on": [1]},
]


class TestStepNode:
    def test_default_status(self):
        node = StepNode(step_id=0, name="test", script="t.py", description="", output_hint="")
        assert node.status == StepStatus.PENDING
        assert node.elapsed is None

    def test_elapsed_calculation(self):
        node = StepNode(step_id=0, name="test", script="t.py", description="", output_hint="")
        node.start_time = 100.0
        node.end_time = 105.5
        assert node.elapsed == 5.5


class TestDAGExecutor:
    def test_build_graph(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        assert len(dag.nodes) == 4
        assert dag.nodes[0].depends_on == []
        assert dag.nodes[1].depends_on == [0]
        assert dag.nodes[3].depends_on == [1, 2]

    def test_get_dependencies(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        assert dag.get_dependencies(0) == []
        assert dag.get_dependencies(3) == [1, 2]

    def test_get_dependents(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        assert sorted(dag.get_dependents(0)) == [1, 2]
        assert dag.get_dependents(3) == []

    def test_validate_dag_valid(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        valid, errors = dag.validate_dag()
        assert valid is True
        assert errors == []

    def test_validate_dag_cyclic(self):
        dag = DAGExecutor(CYCLIC_STEPS)
        valid, errors = dag.validate_dag()
        assert valid is False
        assert any("循环" in e for e in errors)

    def test_validate_dag_missing_dependency(self):
        steps = [{"id": 0, "name": "A", "script": "a.py", "depends_on": [99]}]
        dag = DAGExecutor(steps)
        valid, errors = dag.validate_dag()
        assert valid is False
        assert any("99" in e for e in errors)

    def test_topological_sort_simple(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        waves = dag.topological_sort()
        assert len(waves) == 3
        assert waves[0] == [0]
        assert sorted(waves[1]) == [1, 2]
        assert waves[2] == [3]

    def test_topological_sort_pipeline(self):
        dag = DAGExecutor(PIPELINE_STEPS)
        waves = dag.topological_sort()
        assert len(waves) == 5
        assert waves[0] == [1]
        assert sorted(waves[1]) == [0, 6]
        assert sorted(waves[2]) == [2, 3]
        assert waves[3] == [4]
        assert waves[4] == [5]

    def test_execution_plan_str(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        plan = dag.execution_plan_str()
        assert "DAG 执行计划" in plan
        assert "波次" in plan
        assert "并行度" in plan


class TestDAGExecution:
    def _make_run_fn(self, results_map=None):
        if results_map is None:
            results_map = {}

        def run_fn(step, **kwargs):
            return results_map.get(step["id"], True)

        return run_fn

    def test_sequential_all_success(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        report = dag.execute_sequential(
            run_step_fn=self._make_run_fn(),
            step_args={},
        )
        assert report.all_success
        assert all(n.status == StepStatus.SUCCESS for n in report.step_reports.values())

    def test_sequential_failure_propagation(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        report = dag.execute_sequential(
            run_step_fn=self._make_run_fn({0: False}),
            step_args={},
        )
        assert not report.all_success
        assert report.step_reports[0].status == StepStatus.FAILED
        assert report.step_reports[1].status == StepStatus.SKIPPED
        assert report.step_reports[2].status == StepStatus.SKIPPED
        assert report.step_reports[3].status == StepStatus.SKIPPED

    def test_sequential_skip_steps(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        report = dag.execute_sequential(
            run_step_fn=self._make_run_fn(),
            step_args={},
            skip_steps={2},
        )
        assert report.step_reports[2].status == StepStatus.SKIPPED
        assert report.step_reports[0].status == StepStatus.SUCCESS
        assert report.step_reports[1].status == StepStatus.SUCCESS
        assert report.step_reports[3].status == StepStatus.SUCCESS

    def test_sequential_stop_after(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        report = dag.execute_sequential(
            run_step_fn=self._make_run_fn(),
            step_args={},
            stop_after=1,
        )
        assert report.step_reports[0].status == StepStatus.SUCCESS
        assert report.step_reports[1].status == StepStatus.SUCCESS
        assert report.step_reports[2].status == StepStatus.SKIPPED
        assert report.step_reports[3].status == StepStatus.SKIPPED

    def test_parallel_execution(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        report = dag.execute_parallel(
            run_step_fn=self._make_run_fn(),
            step_args={},
            max_workers=2,
        )
        assert report.all_success
        assert report.parallel_enabled
        assert len(report.execution_order) == 3

    def test_parallel_failure_propagation(self):
        dag = DAGExecutor(SIMPLE_STEPS)
        report = dag.execute_parallel(
            run_step_fn=self._make_run_fn({1: False}),
            step_args={},
            max_workers=2,
        )
        assert not report.all_success
        assert report.step_reports[1].status == StepStatus.FAILED
        assert report.step_reports[3].status == StepStatus.SKIPPED

    def test_pipeline_dag_execution(self):
        dag = DAGExecutor(PIPELINE_STEPS)
        report = dag.execute_sequential(
            run_step_fn=self._make_run_fn(),
            step_args={},
        )
        assert report.all_success
        assert len(report.execution_order) == 5

    def test_run_step_exception(self):
        def failing_fn(step, **kwargs):
            raise RuntimeError("测试异常")

        dag = DAGExecutor(SIMPLE_STEPS)
        report = dag.execute_sequential(
            run_step_fn=failing_fn,
            step_args={},
        )
        assert not report.all_success
        assert report.step_reports[0].status == StepStatus.FAILED
        assert "测试异常" in report.step_reports[0].error_message


class TestDAGExecutionReport:
    def test_all_success(self):
        report = DAGExecutionReport()
        report.step_reports[0] = StepNode(0, "A", "a.py", "", "", status=StepStatus.SUCCESS)
        report.step_reports[1] = StepNode(1, "B", "b.py", "", "", status=StepStatus.SKIPPED)
        assert report.all_success

    def test_has_failure(self):
        report = DAGExecutionReport()
        report.step_reports[0] = StepNode(0, "A", "a.py", "", "", status=StepStatus.SUCCESS)
        report.step_reports[1] = StepNode(1, "B", "b.py", "", "", status=StepStatus.FAILED)
        assert not report.all_success

    def test_summary(self):
        report = DAGExecutionReport()
        report.step_reports[0] = StepNode(0, "A", "a.py", "", "", status=StepStatus.SUCCESS)
        report.step_reports[0].start_time = 0
        report.step_reports[0].end_time = 1.5
        report.execution_order = [[0]]
        report.total_elapsed = 1.5
        summary = report.summary()
        assert "总耗时" in summary
        assert "Step 0" in summary
