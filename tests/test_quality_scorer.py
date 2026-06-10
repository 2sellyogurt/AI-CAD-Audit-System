# -*- coding: utf-8 -*-
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.quality_scorer import QualityScorer, REQUIRED_FIELDS


class TestQualityScorer:

    def test_init(self):
        scorer = QualityScorer()
        assert scorer._weights["field_completeness"] == 25

    def test_score_empty_list(self):
        scorer = QualityScorer()
        result = scorer.score([])
        assert result["total_score"] == 0

    def test_score_non_list(self):
        scorer = QualityScorer()
        result = scorer.score("not_a_list")
        assert result["total_score"] == 0

    def test_score_perfect_issue(self):
        scorer = QualityScorer()
        issues = [{
            "file": "test.dxf",
            "evidence": "标高3.600",
            "line": "10",
            "rule_id": "R001",
            "original_text": "EL=3.600",
            "severity": "高",
            "compliance_status": "不合规",
            "description": "标高超限",
        }]
        result = scorer.score(issues)
        assert result["total_score"] > 90
        assert result["dimensions"]["field_completeness"] == 25
        assert result["details"]["anomaly_rate"] == 0

    def test_score_missing_file(self):
        scorer = QualityScorer()
        issues = [{
            "file": "未知文件",
            "evidence": "标高3.600",
            "line": "10",
            "rule_id": "R001",
            "severity": "高",
            "compliance_status": "不合规",
            "description": "标高超限",
        }]
        result = scorer.score(issues)
        assert result["dimensions"]["field_completeness"] < 25
        assert result["details"]["anomaly_rate"] > 0

    def test_score_missing_evidence(self):
        scorer = QualityScorer()
        issues = [{
            "file": "test.dxf",
            "evidence": "",
            "line": "10",
            "rule_id": "R001",
            "severity": "高",
            "compliance_status": "不合规",
            "description": "标高超限",
        }]
        result = scorer.score(issues)
        assert result["dimensions"]["field_completeness"] < 25
        assert result["details"]["anomaly_rate"] > 0

    def test_score_invalid_severity(self):
        scorer = QualityScorer()
        issues = [{
            "file": "test.dxf",
            "evidence": "标高3.600",
            "line": "10",
            "rule_id": "R001",
            "severity": "无效等级",
            "compliance_status": "不合规",
            "description": "标高超限",
        }]
        result = scorer.score(issues)
        assert result["dimensions"]["data_accuracy"] < 25

    def test_score_multiple_issues(self):
        scorer = QualityScorer()
        issues = [
            {
                "file": "test1.dxf",
                "evidence": "标高3.600",
                "line": "10",
                "rule_id": "R001",
                "original_text": "EL=3.600",
                "severity": "高",
                "compliance_status": "不合规",
                "description": "标高超限",
            },
            {
                "file": "test2.dxf",
                "evidence": "梁高500",
                "line": "20",
                "rule_id": "R002",
                "original_text": "梁250x500",
                "severity": "中",
                "compliance_status": "待核实",
                "description": "梁高不足",
            },
        ]
        result = scorer.score(issues)
        assert result["total_score"] > 80
        assert result["details"]["total_issues"] == 2

    def test_score_non_dict_items_skipped(self):
        scorer = QualityScorer()
        issues = ["not_a_dict", 123, None]
        result = scorer.score(issues)
        assert result["details"]["total_issues"] == 3
        assert result["details"]["anomaly_rate"] == 1.0

    def test_get_grade(self):
        scorer = QualityScorer()
        assert scorer.get_grade(95) == "A"
        assert scorer.get_grade(85) == "B"
        assert scorer.get_grade(75) == "C"
        assert scorer.get_grade(65) == "D"
        assert scorer.get_grade(50) == "F"

    def test_get_grade_boundary(self):
        scorer = QualityScorer()
        assert scorer.get_grade(90) == "A"
        assert scorer.get_grade(80) == "B"
        assert scorer.get_grade(70) == "C"
        assert scorer.get_grade(60) == "D"
        assert scorer.get_grade(59) == "F"

    def test_score_dimensions_sum(self):
        scorer = QualityScorer()
        issues = [{
            "file": "test.dxf",
            "evidence": "标高3.600",
            "line": "10",
            "rule_id": "R001",
            "original_text": "EL=3.600",
            "severity": "高",
            "compliance_status": "不合规",
            "description": "标高超限",
        }]
        result = scorer.score(issues)
        dim_sum = sum(result["dimensions"].values())
        assert abs(dim_sum - result["total_score"]) < 0.1

    def test_required_fields_list(self):
        assert "file" in REQUIRED_FIELDS
        assert "evidence" in REQUIRED_FIELDS
        assert "line" in REQUIRED_FIELDS
        assert "rule_id" in REQUIRED_FIELDS
