# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from report.report_generator_v50 import (
    _load_normative_db,
    _extract_issues_flat,
    _classify_risk,
    _build_compliance_report,
    _build_defect_report,
    _build_cross_report,
    generate_all_reports,
)


class TestLoadNormativeDb:
    def test_empty_path(self):
        result = _load_normative_db(None)
        assert result == {}

    def test_empty_string(self):
        result = _load_normative_db("")
        assert result == {}

    def test_nonexistent_file(self):
        result = _load_normative_db("/nonexistent/path.json")
        assert result == {}

    def test_valid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump({"test": "data"}, f)
            temp_path = f.name
        try:
            result = _load_normative_db(temp_path)
            assert result == {"test": "data"}
        finally:
            os.unlink(temp_path)

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write("invalid json")
            temp_path = f.name
        try:
            result = _load_normative_db(temp_path)
            assert result == {}
        finally:
            os.unlink(temp_path)


class TestExtractIssuesFlat:
    def test_empty_dict(self):
        result = _extract_issues_flat({}, "test")
        assert result == []

    def test_empty_list(self):
        result = _extract_issues_flat([], "test")
        assert result == []

    def test_simple_issue(self):
        data = [{"description": "净高不足", "severity": "high", "location": "卧室"}]
        result = _extract_issues_flat(data, "test")
        assert len(result) == 1
        assert result[0]["description"] == "净高不足"
        assert result[0]["source"] == "test"

    def test_nested_structure(self):
        data = {
            "issues": [
                {"description": "问题1", "severity": "high"},
                {"description": "问题2", "severity": "medium"},
            ]
        }
        result = _extract_issues_flat(data, "test")
        assert len(result) == 2

    def test_no_description(self):
        data = [{"severity": "high", "location": "卧室"}]
        result = _extract_issues_flat(data, "test")
        assert len(result) == 0


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
        assert _classify_risk("") == "低风险"
        assert _classify_risk(None) == "低风险"


class TestBuildComplianceReport:
    def test_empty_results(self):
        result = _build_compliance_report(
            rule_results={},
            rule_stats={},
            normative_codes=[],
            project_info={"name": "测试项目"},
        )
        assert "强条合规审查报告" in result
        assert "测试项目" in result

    def test_with_issues(self):
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
        rule_stats = {
            "total": 91,
            "compliant": 80,
            "need_verify": 5,
            "non_compliant": 6,
        }
        result = _build_compliance_report(
            rule_results=rule_results,
            rule_stats=rule_stats,
            normative_codes=["GB 55038-2025"],
            project_info={"name": "测试项目"},
        )
        assert "净高不足" in result
        assert "GB 55038-2025" in result


class TestBuildDefectReport:
    def test_empty_results(self):
        result = _build_defect_report(
            elevation_results={},
            collision_results={},
            axis_collision_results={},
            mep_results={},
            geometry_results={},
            project_info={"name": "测试项目"},
        )
        assert "基础错漏排查报告" in result
        assert "测试项目" in result


class TestBuildCrossReport:
    def test_empty_results(self):
        result = _build_cross_report(
            cross_results={},
            deep_cross_results=[],
            cross_stats={},
            project_info={"name": "测试项目"},
        )
        assert "跨专业一致性校验报告" in result
        assert "测试项目" in result


class TestGenerateAllReports:
    def test_empty_data(self):
        result = generate_all_reports(
            rule_results={},
            rule_stats={},
            elevation_results={},
            collision_results={},
            axis_collision_results={},
            mep_results={},
            cross_results={},
            deep_cross_results=[],
            cross_stats={},
            engineering_results={},
            project_info={"name": "测试项目"},
        )
        assert isinstance(result, dict)
        assert "强条合规审查报告" in result
        assert "基础错漏排查报告" in result
        assert "跨专业一致性校验报告" in result
