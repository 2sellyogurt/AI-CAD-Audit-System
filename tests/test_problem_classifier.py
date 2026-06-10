# -*- coding: utf-8 -*-
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.problem_classifier import ProblemClassifier, CATEGORY_RULES


class TestProblemClassifier:

    def test_init(self):
        pc = ProblemClassifier()
        assert isinstance(pc.categories, list)
        assert len(pc.categories) == 8

    def test_categories_list(self):
        pc = ProblemClassifier()
        expected = [
            "强制条文违反", "规范条款不符", "专项图纸不合规",
            "专业图纸缺项", "前后打架", "显性错误", "落地类问题", "隐患类问题",
        ]
        assert pc.categories == expected

    def test_classify_mandatory_by_is_mandatory(self):
        pc = ProblemClassifier()
        issue = {"description": "问题", "is_mandatory": True, "severity": "中"}
        assert pc.classify(issue) == "强制条文违反"

    def test_classify_mandatory_by_severity_high(self):
        pc = ProblemClassifier()
        issue = {"description": "问题", "severity": "高"}
        assert pc.classify(issue) == "强制条文违反"

    def test_classify_mandatory_by_severity_severe(self):
        pc = ProblemClassifier()
        issue = {"description": "问题", "severity": "严重"}
        assert pc.classify(issue) == "强制条文违反"

    def test_classify_by_category_field(self):
        pc = ProblemClassifier()
        issue = {"description": "问题", "category": "specialized", "severity": "中"}
        assert pc.classify(issue) == "专项图纸不合规"

    def test_classify_by_keyword_fire(self):
        pc = ProblemClassifier()
        issue = {"description": "消防通道宽度不足", "severity": "中"}
        assert pc.classify(issue) == "专项图纸不合规"

    def test_classify_by_keyword_obstacle(self):
        pc = ProblemClassifier()
        issue = {"description": "无障碍坡道缺失", "severity": "中"}
        assert pc.classify(issue) == "专项图纸不合规"

    def test_classify_by_keyword_conflict(self):
        pc = ProblemClassifier()
        issue = {"description": "图纸矛盾，标高不一致", "severity": "中"}
        assert pc.classify(issue) == "前后打架"

    def test_classify_by_keyword_error(self):
        pc = ProblemClassifier()
        issue = {"description": "标注错误", "severity": "中"}
        assert pc.classify(issue) == "显性错误"

    def test_classify_by_keyword_risk(self):
        pc = ProblemClassifier()
        issue = {"description": "存在安全隐患", "severity": "中"}
        assert pc.classify(issue) == "隐患类问题"

    def test_classify_by_keyword_missing(self):
        pc = ProblemClassifier()
        issue = {"description": "缺少给排水图纸", "severity": "中"}
        assert pc.classify(issue) == "专业图纸缺项"

    def test_classify_by_keyword_construction(self):
        pc = ProblemClassifier()
        issue = {"description": "施工可行性存疑", "severity": "中"}
        assert pc.classify(issue) == "落地类问题"

    def test_classify_by_keyword_normative(self):
        pc = ProblemClassifier()
        issue = {"description": "不符合规范要求", "severity": "中"}
        assert pc.classify(issue) == "规范条款不符"

    def test_classify_default(self):
        pc = ProblemClassifier()
        issue = {"description": "普通问题", "severity": "低"}
        assert pc.classify(issue) == "规范条款不符"

    def test_classify_non_dict(self):
        pc = ProblemClassifier()
        assert pc.classify("not_a_dict") == "规范条款不符"
        assert pc.classify(None) == "规范条款不符"

    def test_classify_batch(self):
        pc = ProblemClassifier()
        issues = [
            {"description": "强条违规", "is_mandatory": True, "severity": "高"},
            {"description": "消防通道不足", "severity": "中"},
            {"description": "标注错误", "severity": "低"},
        ]
        results = pc.classify_batch(issues)
        assert len(results) == 3
        assert results[0]["problem_category"] == "强制条文违反"
        assert results[1]["problem_category"] == "专项图纸不合规"
        assert results[2]["problem_category"] == "显性错误"

    def test_classify_batch_non_list(self):
        pc = ProblemClassifier()
        assert pc.classify_batch("not_a_list") == []
        assert pc.classify_batch(None) == []

    def test_classify_batch_non_dict_items_skipped(self):
        pc = ProblemClassifier()
        results = pc.classify_batch(["not_a_dict", 123])
        assert len(results) == 0

    def test_classify_batch_adds_severity(self):
        pc = ProblemClassifier()
        issues = [{"description": "问题", "is_mandatory": True}]
        results = pc.classify_batch(issues)
        assert results[0]["category_severity"] == "严重"
        assert results[0]["category_is_mandatory"] is True

    def test_get_statistics(self):
        pc = ProblemClassifier()
        classified = [
            {"problem_category": "强制条文违反", "category_severity": "严重"},
            {"problem_category": "强制条文违反", "category_severity": "严重"},
            {"problem_category": "显性错误", "category_severity": "一般"},
        ]
        stats = pc.get_statistics(classified)
        assert stats["total"] == 3
        assert stats["by_category"]["强制条文违反"] == 2
        assert stats["by_category"]["显性错误"] == 1
        assert stats["by_severity"]["严重"] == 2
        assert stats["by_severity"]["一般"] == 1

    def test_get_statistics_empty(self):
        pc = ProblemClassifier()
        stats = pc.get_statistics([])
        assert stats["total"] == 0
        assert stats["by_category"] == {}

    def test_get_statistics_non_list(self):
        pc = ProblemClassifier()
        stats = pc.get_statistics("not_a_list")
        assert stats["total"] == 0

    def test_category_rules_structure(self):
        assert isinstance(CATEGORY_RULES, dict)
        assert len(CATEGORY_RULES) == 8
        for name, info in CATEGORY_RULES.items():
            assert "description" in info
            assert "severity" in info
            assert "is_mandatory" in info
            assert "keywords" in info
            assert "check_type" in info
