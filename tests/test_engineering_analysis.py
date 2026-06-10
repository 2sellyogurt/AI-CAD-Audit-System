# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.engineering_analysis import EngineeringAnalyzer


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

    def get_file_count(self):
        return len(self._files)


class TestEngineeringAnalyzer:
    def test_init_empty(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        assert analyzer._combined_text == ""

    def test_init_with_data(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["高层建筑", "混凝土用量:1000m³"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        assert len(analyzer._all_texts) == 1

    def test_run_all_checks_empty(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer.run_all_checks()
        assert "engineering_summary" in result
        assert "project_complexity" in result["engineering_summary"]

    def test_run_all_checks_with_data(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={
                "test.json": [
                    "高层建筑",
                    "混凝土用量:1000m³",
                    "钢筋用量:500t",
                    "建筑面积:50000m²",
                    "消防通道宽度不足",
                ]
            },
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer.run_all_checks()
        assert "engineering_summary" in result
        summary = result["engineering_summary"]
        assert "project_complexity" in summary
        assert "risk_level" in summary
        assert "main_risks" in summary

    def test_get_statistics_empty(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer.get_statistics()
        assert "quantities" in result

    def test_get_statistics_with_data(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={
                "test.json": [
                    "混凝土用量:1000m³",
                    "钢筋用量:500t",
                    "建筑面积:50000m²",
                ]
            },
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer.get_statistics()
        assert "quantities" in result
        assert "concrete" in result["quantities"]
        assert result["quantities"]["concrete"]["hits"] == 1

    def test_multiple_files(self):
        loader = MockLoader(
            files=["file1.json", "file2.json"],
            readable_names={"file1.json": "建筑图", "file2.json": "结构图"},
            text_lines={
                "file1.json": ["高层建筑", "建筑面积:50000m²"],
                "file2.json": ["混凝土用量:1000m³", "钢筋用量:500t"],
            },
        )
        analyzer = EngineeringAnalyzer(loader)
        assert len(analyzer._all_texts) == 2
        result = analyzer.run_all_checks()
        assert "engineering_summary" in result

    def test_empty_lines(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": []},
        )
        analyzer = EngineeringAnalyzer(loader)
        assert len(analyzer._all_texts) == 0

    def test_full_lifecycle_report_empty(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer.full_lifecycle_report()
        assert "summary" in result
        assert "engineering_summary" in result
        assert "statistics" in result
        assert "issues" in result
        assert "constructability_score" in result["summary"]
        assert "overall_score" in result["summary"]

    def test_full_lifecycle_report_with_data(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={
                "test.json": [
                    "高层建筑", "超限高层", "建筑面积:100000m²",
                    "地下3层", "地上32层", "钢结构",
                    "造价:5000万元", "工期:730天",
                    "消防疏散", "管线碰撞", "抗震设计",
                ]
            },
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer.full_lifecycle_report()
        assert result["summary"]["overall_score"] >= 0
        assert isinstance(result["issues"], list)

    def test_estimate_cost_no_data(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._estimate_cost()
        assert result["estimate_quality"] == "insufficient"
        assert result["has_cost_info"] is False

    def test_estimate_cost_with_keywords(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["工程总造价5000万元", "综合单价3500元/m²"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._estimate_cost()
        assert result["has_cost_info"] is True

    def test_estimate_cost_with_quantities(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["工程总造价5000万元", "混凝土用量:1000m³"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._estimate_cost()
        assert result["estimate_quality"] in ("good", "partial")

    def test_identify_main_risks_empty(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._identify_main_risks()
        assert result == []

    def test_identify_main_risks_structure(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["结构承载力不足", "抗震等级提高", "沉降观测"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._identify_main_risks()
        assert len(result) >= 1
        structure_risks = [r for r in result if r["risk_id"] == "structural"]
        assert len(structure_risks) >= 1

    def test_identify_main_risks_fire(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["消防通道被占用", "火灾隐患", "疏散距离不足"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._identify_main_risks()
        fire_risks = [r for r in result if r["risk_id"] == "fire"]
        assert len(fire_risks) >= 1

    def test_identify_main_risks_multiple(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={
                "test.json": [
                    "结构承载", "抗震", "消防", "疏散", "排烟",
                    "渗漏", "防水", "碰撞", "管线综合", "工期", "进度",
                ]
            },
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._identify_main_risks()
        assert len(result) >= 3

    def test_generate_optimization_suggestions_bim(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["碰撞检测", "管线综合优化", "净高不足"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._generate_optimization_suggestions()
        bim_suggestions = [s for s in result if s.get("category") == "design"]
        assert len(bim_suggestions) >= 1

    def test_generate_optimization_suggestions_green(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["节能设计", "绿色建筑认证", "能耗分析"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._generate_optimization_suggestions()
        assert len(result) >= 1

    def test_generate_optimization_suggestions_empty(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._generate_optimization_suggestions()
        assert result == []

    def test_calc_constructability_score_simple(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        score = analyzer._calc_constructability_score({
            "project_complexity": {"level": "simple"},
            "timeline_feasibility": {"feasibility": "feasible"},
            "major_engineering_content": [],
        })
        assert 0 <= score <= 100

    def test_calc_constructability_score_complex(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        score = analyzer._calc_constructability_score({
            "project_complexity": {"level": "complex"},
            "timeline_feasibility": {"feasibility": "challenging"},
            "major_engineering_content": [{"discipline": "x"}] * 6,
        })
        assert 0 <= score <= 100

    def test_calc_cost_efficiency_score_good(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        score = analyzer._calc_cost_efficiency_score({
            "cost_estimate": {"estimate_quality": "good"},
            "main_risks": [],
            "optimization_suggestions": [{"category": "cost"}],
        })
        assert 0 <= score <= 100

    def test_calc_cost_efficiency_score_insufficient(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        score = analyzer._calc_cost_efficiency_score({
            "cost_estimate": {"estimate_quality": "insufficient"},
            "main_risks": [{"risk_id": "cost", "match_count": 5}],
            "optimization_suggestions": [],
        })
        assert 0 <= score <= 100

    def test_calc_maintenance_score_positive(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["检修口", "维护通道", "可更换设备", "运营成本"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        score = analyzer._calc_maintenance_score({})
        assert 0 <= score <= 100

    def test_calc_maintenance_score_negative(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["隐蔽工程", "不可达管线", "封闭空间"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        score = analyzer._calc_maintenance_score({})
        assert 0 <= score <= 100

    def test_collect_lifecycle_issues_complex(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        issues = analyzer._collect_lifecycle_issues({
            "project_complexity": {"level": "complex"},
            "risk_level": {"level": "high", "level_label": "高风险"},
            "timeline_feasibility": {"feasibility": "challenging", "feasibility_label": "有挑战"},
            "cost_estimate": {"estimate_quality": "insufficient"},
            "main_risks": [{"risk_id": "structural", "severity": "high", "risk_name": "结构", "matched_keywords": ["承载"]}],
        })
        assert len(issues) >= 3

    def test_collect_lifecycle_issues_empty(self):
        loader = MockLoader()
        analyzer = EngineeringAnalyzer(loader)
        issues = analyzer._collect_lifecycle_issues({})
        assert issues == []

    def test_assess_project_complexity_high(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={
                "test.json": [
                    "超限高层", "大跨度", "深基坑", "装配式", "复杂地质",
                ]
            },
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._assess_project_complexity()
        assert result["level"] in ("complex", "moderate")

    def test_assess_project_complexity_simple(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["普通住宅"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._assess_project_complexity()
        assert result["level"] == "simple"

    def test_assess_risk_level_high(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={
                "test.json": [
                    "结构", "承载", "倾覆", "失稳", "倒塌", "裂缝", "沉降", "抗震",
                    "消防", "火灾", "疏散", "排烟", "防火", "喷淋",
                    "渗漏", "防水", "漏水", "止水", "变形缝",
                ]
            },
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._assess_risk_level()
        assert result["level"] in ("high", "medium")

    def test_assess_risk_level_low(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["普通住宅", "标准层"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._assess_risk_level()
        assert result["level"] == "low"

    def test_assess_timeline_feasibility(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["工期:730天", "关键路径法", "进度计划"]},
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._assess_timeline_feasibility()
        assert "feasibility" in result

    def test_identify_major_engineering_content(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={
                "test.json": [
                    "基础桩基", "主体结构梁板柱", "装修幕墙",
                    "给水排水", "空调通风", "配电照明", "电梯扶梯",
                ]
            },
        )
        analyzer = EngineeringAnalyzer(loader)
        result = analyzer._identify_major_engineering_content()
        assert len(result) >= 5
