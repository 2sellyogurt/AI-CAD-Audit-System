# -*- coding: utf-8 -*-
import os
import sys
import json
import subprocess
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.master import STEPS, parse_args, print_banner, print_step_plan, run_step, main


class TestSteps:
    def test_steps_count(self):
        assert len(STEPS) == 7

    def test_step_ids(self):
        ids = [s["id"] for s in STEPS]
        assert ids == [0, 1, 2, 3, 4, 5, 6]

    def test_step_names(self):
        names = [s["name"] for s in STEPS]
        assert "项目参数锚定" in names[0]
        assert "DXF图纸参数提取" in names[1]
        assert "强制条文合规性审查" in names[2]
        assert "基础错漏排查" in names[3]
        assert "跨专业一致性校验" in names[4]
        assert "工程落地分析" in names[5]
        assert "BIM三维重建" in names[6]

    def test_step_scripts(self):
        scripts = [s["script"] for s in STEPS]
        assert scripts == [
            "step0_anchor.py",
            "step1_extract.py",
            "step2_compliance.py",
            "step3_defect.py",
            "step4_cross_check.py",
            "step5_engineering.py",
            "step6_bim.py",
        ]

    def test_step_has_description(self):
        for step in STEPS:
            assert "description" in step
            assert len(step["description"]) > 0

    def test_step_has_output_hint(self):
        for step in STEPS:
            assert "output_hint" in step
            assert len(step["output_hint"]) > 0


class TestParseArgs:
    def test_default_args(self):
        sys.argv = ["master.py"]
        args = parse_args()
        assert args.dxf_dir is not None
        assert args.json_dir is not None
        assert args.output_dir is not None

    def test_custom_dirs(self):
        sys.argv = [
            "master.py",
            "--dxf-dir", "/tmp/dxf",
            "--json-dir", "/tmp/json",
            "--output-dir", "/tmp/output",
        ]
        args = parse_args()
        assert args.dxf_dir == "/tmp/dxf"
        assert args.json_dir == "/tmp/json"
        assert args.output_dir == "/tmp/output"

    def test_skip_step(self):
        sys.argv = ["master.py", "--skip-step", "1", "2"]
        args = parse_args()
        assert args.skip_step == [1, 2]

    def test_only_step(self):
        sys.argv = ["master.py", "--only-step", "2", "3"]
        args = parse_args()
        assert args.only_step == [2, 3]

    def test_stop_after(self):
        sys.argv = ["master.py", "--stop-after", "3"]
        args = parse_args()
        assert args.stop_after == 3

    def test_dry_run(self):
        sys.argv = ["master.py", "--dry-run"]
        args = parse_args()
        assert args.dry_run is True


class TestPrintBanner:
    def test_prints_banner(self, capsys):
        print_banner()
        captured = capsys.readouterr()
        assert "施工图智能审查" in captured.out
        assert "v6.0" in captured.out


class TestPrintStepPlan:
    def test_prints_plan(self, capsys):
        steps = [STEPS[0], STEPS[1]]
        print_step_plan(steps)
        captured = capsys.readouterr()
        assert "Step 0" in captured.out
        assert "Step 1" in captured.out
        assert "项目参数锚定" in captured.out


class TestRunStep:
    @patch("src.master.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        step = {"id": 1, "name": "测试步骤", "script": "step1_extract.py"}
        result = run_step(step, "/tmp/dxf", "/tmp/json", "/tmp/output")
        assert result is True

    @patch("src.master.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        step = {"id": 1, "name": "测试步骤", "script": "step1_extract.py"}
        result = run_step(step, "/tmp/dxf", "/tmp/json", "/tmp/output")
        assert result is False

    @patch("src.master.subprocess.run")
    def test_exception(self, mock_run):
        mock_run.side_effect = Exception("测试异常")
        step = {"id": 1, "name": "测试步骤", "script": "step1_extract.py"}
        result = run_step(step, "/tmp/dxf", "/tmp/json", "/tmp/output")
        assert result is False

    @patch("src.master.os.path.exists")
    def test_script_not_exists(self, mock_exists):
        mock_exists.return_value = False
        step = {"id": 1, "name": "测试步骤", "script": "nonexistent.py"}
        result = run_step(step, "/tmp/dxf", "/tmp/json", "/tmp/output")
        assert result is False

    @patch("src.master.subprocess.run")
    def test_non_step1_uses_json_dir(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        step = {"id": 2, "name": "合规性审查", "script": "step2_compliance.py"}
        result = run_step(step, "/tmp/dxf", "/tmp/json", "/tmp/output")
        assert result is True
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--json-dir" in cmd
        assert "/tmp/json" in cmd
        assert "--output-dir" in cmd
        assert "/tmp/output" in cmd

    @patch("src.master.subprocess.run")
    def test_step1_uses_dxf_dir(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        step = {"id": 1, "name": "DXF提取", "script": "step1_extract.py"}
        result = run_step(step, "/tmp/dxf", "/tmp/json", "/tmp/output")
        assert result is True
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "--dxf-dir" in cmd
        assert "/tmp/dxf" in cmd

    @patch("src.master.subprocess.run")
    def test_timeout_exception(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
        step = {"id": 1, "name": "测试步骤", "script": "step1_extract.py"}
        result = run_step(step, "/tmp/dxf", "/tmp/json", "/tmp/output")
        assert result is False

    @patch("src.master.os.path.exists")
    @patch("src.master.subprocess.run")
    def test_keyboard_interrupt_propagates(self, mock_run, mock_exists):
        mock_exists.return_value = True
        mock_run.side_effect = KeyboardInterrupt()
        step = {"id": 1, "name": "测试步骤", "script": "step1_extract.py"}
        with pytest.raises(KeyboardInterrupt):
            run_step(step, "/tmp/dxf", "/tmp/json", "/tmp/output")


class TestMain:
    def _make_mock_args(self, **overrides):
        defaults = dict(
            dxf_dir="/tmp/dxf",
            json_dir="/tmp/json",
            output_dir="/tmp/output",
            skip_step=[],
            only_step=[],
            stop_after=None,
            dry_run=False,
            dag=False,
            parallel=False,
            max_workers=3,
            llm_provider="",
            llm_model="",
            llm_api_key="",
        )
        defaults.update(overrides)
        return MagicMock(**defaults)

    @patch("src.master.run_step")
    @patch("src.master.os.makedirs")
    @patch("src.master.parse_args")
    def test_main_all_success(self, mock_parse, mock_makedirs, mock_run_step, capsys):
        mock_parse.return_value = self._make_mock_args()
        mock_run_step.return_value = True
        result = main()
        assert result == 0
        assert mock_run_step.call_count == 7
        captured = capsys.readouterr()
        assert "全部步骤执行成功" in captured.out

    @patch("src.master.run_step")
    @patch("src.master.os.makedirs")
    @patch("src.master.parse_args")
    def test_main_partial_failure(self, mock_parse, mock_makedirs, mock_run_step, capsys):
        mock_parse.return_value = self._make_mock_args()
        mock_run_step.side_effect = [True, True, False, True, True, True, True]
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "部分步骤执行失败" in captured.out

    @patch("src.master.parse_args")
    def test_main_dry_run(self, mock_parse, capsys):
        mock_parse.return_value = self._make_mock_args(dry_run=True)
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out

    @patch("src.master.parse_args")
    def test_main_only_step_no_match(self, mock_parse):
        mock_parse.return_value = self._make_mock_args(only_step=[99])
        result = main()
        assert result == 1

    @patch("src.master.run_step")
    @patch("src.master.os.makedirs")
    @patch("src.master.parse_args")
    def test_main_skip_step(self, mock_parse, mock_makedirs, mock_run_step):
        mock_parse.return_value = self._make_mock_args(skip_step=[1, 2])
        mock_run_step.return_value = True
        result = main()
        assert result == 0
        assert mock_run_step.call_count == 5

    @patch("src.master.run_step")
    @patch("src.master.os.makedirs")
    @patch("src.master.parse_args")
    def test_main_stop_after(self, mock_parse, mock_makedirs, mock_run_step):
        mock_parse.return_value = self._make_mock_args(stop_after=3)
        mock_run_step.return_value = True
        result = main()
        assert result == 0
        assert mock_run_step.call_count == 4

    @patch("src.master.run_step")
    @patch("src.master.os.makedirs")
    @patch("src.master.parse_args")
    def test_main_only_step_specific(self, mock_parse, mock_makedirs, mock_run_step):
        mock_parse.return_value = self._make_mock_args(only_step=[2, 3])
        mock_run_step.return_value = True
        result = main()
        assert result == 0
        assert mock_run_step.call_count == 2
        called_steps = [call[0][0]["id"] for call in mock_run_step.call_args_list]
        assert called_steps == [2, 3]

    @patch("src.master.run_step")
    @patch("src.master.os.makedirs")
    @patch("src.master.parse_args")
    def test_main_failure_prints_icon(self, mock_parse, mock_makedirs, mock_run_step, capsys):
        mock_parse.return_value = self._make_mock_args(only_step=[1])
        mock_run_step.return_value = False
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "✗" in captured.out

    @patch("src.master.run_step")
    @patch("src.master.os.makedirs")
    @patch("src.master.parse_args")
    def test_main_success_prints_report_dir(self, mock_parse, mock_makedirs, mock_run_step, capsys):
        mock_parse.return_value = self._make_mock_args(only_step=[1])
        mock_run_step.return_value = True
        result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "报告输出目录" in captured.out

    @patch("src.master.run_step")
    @patch("src.master.os.makedirs")
    @patch("src.master.parse_args")
    def test_main_mixed_results_determines_failure(self, mock_parse, mock_makedirs, mock_run_step, capsys):
        mock_parse.return_value = self._make_mock_args(only_step=[1, 2, 3])
        mock_run_step.side_effect = [True, True, False]
        result = main()
        assert result == 1
        captured = capsys.readouterr()
        assert "部分步骤执行失败" in captured.out
