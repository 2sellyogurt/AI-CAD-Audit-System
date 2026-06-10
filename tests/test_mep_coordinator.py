# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.mep_coordinator import MepCoordinator


class MockLoader:
    def __init__(self, files=None, readable_names=None, text_lines=None):
        self._files = files if files is not None else []
        self._readable_names = readable_names if readable_names is not None else {}
        self._text_lines = text_lines if text_lines is not None else {}

    @property
    def files(self):
        return list(self._files)

    def get_readable_name(self, fn):
        return self._readable_names.get(fn, fn)

    def get_text_lines_by_file(self, fn):
        return self._text_lines.get(fn, [])


class TestMepCoordinator:
    def test_init_empty(self):
        loader = MockLoader()
        coord = MepCoordinator(loader, rules_config=[])
        assert len(coord._all_texts) == 0

    def test_init_with_data(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["桥架在水管上方", "风管优先布置"]},
        )
        coord = MepCoordinator(loader, rules_config=[])
        assert len(coord._all_texts) == 1

    def test_init_with_rules(self):
        loader = MockLoader()
        rules = [{"rule_id": "rule_001", "name": "电上水下"}]
        coord = MepCoordinator(loader, rules_config=rules)
        assert len(coord._rules_config) == 1

    def test_run_all_checks_empty(self):
        loader = MockLoader()
        coord = MepCoordinator(loader, rules_config=[])
        result = coord.run_all_checks()
        assert "summary" in result
        assert result["summary"]["principle_compliant_count"] == 0
        assert result["summary"]["principle_total"] == 6

    def test_run_all_checks_with_data(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={
                "test.json": [
                    "桥架在水管上方",
                    "风管优先布置",
                    "有压管道避让重力管道",
                    "小管避让大管",
                    "检修空间预留",
                    "距墙距离不小于300mm",
                ]
            },
        )
        coord = MepCoordinator(loader, rules_config=[])
        result = coord.run_all_checks()
        assert "summary" in result
        summary = result["summary"]
        assert summary["principle_compliant_count"] == 6
        assert summary["principle_total"] == 6

    def test_run_all_checks_returns_dict(self):
        loader = MockLoader()
        coord = MepCoordinator(loader, rules_config=[])
        result = coord.run_all_checks()
        assert isinstance(result, dict)
        assert "principle_results" in result
        assert "summary" in result
        assert "maintenance_result" in result
        assert "optimizations" in result

    def test_multiple_files(self):
        loader = MockLoader(
            files=["file1.json", "file2.json"],
            readable_names={"file1.json": "暖通图", "file2.json": "给排水图"},
            text_lines={
                "file1.json": ["风管优先布置"],
                "file2.json": ["桥架在水管上方"],
            },
        )
        coord = MepCoordinator(loader, rules_config=[])
        assert len(coord._all_texts) == 2

    def test_empty_lines(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": []},
        )
        coord = MepCoordinator(loader, rules_config=[])
        assert len(coord._all_texts) == 0
