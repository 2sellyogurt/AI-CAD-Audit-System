# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from report.meeting_list import (
    _classify_risk,
    _classify_discipline,
    _extract_issues_from_dict,
    MeetingList,
)


class TestClassifyRisk:
    def test_high_risk(self):
        assert _classify_risk("high") == "高风险"
        assert _classify_risk("严重") == "高风险"
        assert _classify_risk("critical") == "高风险"
        assert _classify_risk("不合规") == "高风险"

    def test_medium_risk(self):
        assert _classify_risk("medium") == "中风险"
        assert _classify_risk("警告") == "中风险"
        assert _classify_risk("待核实") == "中风险"

    def test_low_risk(self):
        assert _classify_risk("low") == "低风险"
        assert _classify_risk("提示") == "低风险"
        assert _classify_risk("compliant") == "低风险"

    def test_unknown_risk(self):
        assert _classify_risk("") == "unknown"
        assert _classify_risk(None) == "unknown"


class TestClassifyDiscipline:
    def test_architectural(self):
        assert _classify_discipline("建筑", "防火分区") == "建筑"
        assert _classify_discipline("", "疏散通道") == "建筑"

    def test_structural(self):
        assert _classify_discipline("结构", "梁截面不足") == "结构"
        assert _classify_discipline("", "柱配筋") == "结构"

    def test_hvac(self):
        assert _classify_discipline("暖通", "风管尺寸") == "暖通"
        assert _classify_discipline("", "空调系统") == "暖通"

    def test_plumbing(self):
        assert _classify_discipline("给排水", "管道直径") == "给排水"
        assert _classify_discipline("", "喷淋系统") == "给排水"

    def test_electrical(self):
        assert _classify_discipline("电气", "配电箱") == "电气"
        assert _classify_discipline("", "照明系统") == "电气"

    def test_fire(self):
        assert _classify_discipline("消防", "报警系统") == "消防"
        assert _classify_discipline("", "灭火器") == "消防"


class TestExtractIssuesFromDict:
    def test_empty_dict(self):
        result = _extract_issues_from_dict({}, "test")
        assert result == []

    def test_empty_list(self):
        result = _extract_issues_from_dict([], "test")
        assert result == []

    def test_simple_issue(self):
        data = [{"description": "净高不足", "severity": "high", "location": "卧室"}]
        result = _extract_issues_from_dict(data, "test")
        assert len(result) == 1
        assert result[0]["description"] == "净高不足"
        assert result[0]["risk_level"] == "高风险"

    def test_nested_structure(self):
        data = {
            "issues": [
                {"description": "问题1", "severity": "high"},
                {"description": "问题2", "severity": "medium"},
            ]
        }
        result = _extract_issues_from_dict(data, "test")
        assert len(result) == 2

    def test_no_description(self):
        data = [{"severity": "high", "location": "卧室"}]
        result = _extract_issues_from_dict(data, "test")
        assert len(result) == 0


class TestMeetingList:
    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ml = MeetingList(tmpdir)
            assert ml._output_dir == os.path.abspath(tmpdir)
            assert ml.items == []

    def test_generate_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ml = MeetingList(tmpdir)
            result = ml.generate()
            assert isinstance(result, str)
            assert "会审问题清单" in result

    def test_generate_with_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ml = MeetingList(tmpdir)
            rule_results = {
                "issues": [
                    {
                        "description": "净高不足",
                        "severity": "high",
                        "location": "卧室",
                        "line": 10,
                        "code_reference": "GB 55038-2025",
                    }
                ]
            }
            result = ml.generate(
                project_info={"name": "测试项目"},
                rule_results=rule_results,
            )
            assert isinstance(result, str)
            assert "会审问题清单" in result
