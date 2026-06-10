# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.feedback_loop import FeedbackCollector, PatternLearner


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_step_results():
    return {
        "step2": {
            "issues": [
                {"rule_id": "GB50016-5.3.1", "severity": "严重", "description": "防火分区面积超标"},
                {"rule_id": "GB50016-5.5.17", "severity": "重要", "description": "安全出口数量不足"},
                {"rule_id": "GB50016-5.3.1", "severity": "严重", "description": "防火分区面积超标2"},
            ]
        },
        "step3": {
            "issues": [
                {"rule_id": "GB50096-5.6.3", "severity": "一般", "description": "卧室净高不足"},
            ]
        },
    }


@pytest.fixture
def sample_project_params():
    return {
        "building_type": "住宅",
        "fire_rating": "二类高层",
        "building_height": 35.0,
    }


class TestFeedbackCollector:
    def test_init_creates_empty_history(self, temp_dir):
        collector = FeedbackCollector(temp_dir)
        assert collector.history == []

    def test_collect_review_stats(self, temp_dir, sample_step_results):
        collector = FeedbackCollector(temp_dir)
        stats = collector.collect_review_stats(sample_step_results, project_id="test_001")

        assert stats["total_issues"] == 4
        assert stats["rule_hits"]["GB50016-5.3.1"] == 2
        assert stats["rule_hits"]["GB50016-5.5.17"] == 1
        assert stats["rule_hits"]["GB50096-5.6.3"] == 1
        assert stats["severity_distribution"]["严重"] == 2
        assert stats["severity_distribution"]["重要"] == 1
        assert stats["severity_distribution"]["一般"] == 1

    def test_collect_review_stats_persists(self, temp_dir, sample_step_results):
        collector = FeedbackCollector(temp_dir)
        collector.collect_review_stats(sample_step_results)

        collector2 = FeedbackCollector(temp_dir)
        assert len(collector2.history) == 1

    def test_collect_user_feedback(self, temp_dir):
        collector = FeedbackCollector(temp_dir)
        entry = collector.collect_user_feedback(
            issue_id="ISSUE-001",
            rule_id="GB50016-5.3.1",
            feedback_type="confirmed",
            comment="确实超标",
            project_id="test_001",
        )

        assert entry["feedback_type"] == "confirmed"
        assert entry["rule_id"] == "GB50016-5.3.1"
        assert len(collector.history) == 1

    def test_collect_user_feedback_invalid_type(self, temp_dir):
        collector = FeedbackCollector(temp_dir)
        with pytest.raises(ValueError, match="无效的反馈类型"):
            collector.collect_user_feedback(
                issue_id="ISSUE-001",
                rule_id="GB50016-5.3.1",
                feedback_type="invalid",
            )

    def test_get_rule_stats_no_feedback(self, temp_dir):
        collector = FeedbackCollector(temp_dir)
        stats = collector.get_rule_stats("GB50016-5.3.1")
        assert stats["total_hits"] == 0
        assert stats["confirmed"] == 0
        assert stats["confidence"] == 0.5

    def test_get_rule_stats_with_feedback(self, temp_dir, sample_step_results):
        collector = FeedbackCollector(temp_dir)
        collector.collect_review_stats(sample_step_results)
        collector.collect_user_feedback("I1", "GB50016-5.3.1", "confirmed")
        collector.collect_user_feedback("I2", "GB50016-5.3.1", "confirmed")
        collector.collect_user_feedback("I3", "GB50016-5.3.1", "false_positive")

        stats = collector.get_rule_stats("GB50016-5.3.1")
        assert stats["total_hits"] == 2
        assert stats["confirmed"] == 2
        assert stats["false_positive"] == 1
        assert stats["confidence"] == pytest.approx(0.667, abs=0.01)

    def test_generate_feedback_report(self, temp_dir, sample_step_results):
        collector = FeedbackCollector(temp_dir)
        collector.collect_review_stats(sample_step_results)
        collector.collect_user_feedback("I1", "GB50016-5.3.1", "confirmed")
        collector.collect_user_feedback("I2", "GB50016-5.3.1", "confirmed")
        collector.collect_user_feedback("I3", "GB50016-5.3.1", "confirmed")
        collector.collect_user_feedback("I4", "GB50016-5.3.1", "confirmed")

        report = collector.generate_feedback_report()
        assert report["total_rules_tracked"] == 3
        assert report["total_feedback_entries"] == 4
        assert report["total_review_sessions"] == 1
        assert "GB50016-5.3.1" in report["high_confidence_rules"]

    def test_generate_feedback_report_low_confidence(self, temp_dir, sample_step_results):
        collector = FeedbackCollector(temp_dir)
        collector.collect_review_stats(sample_step_results)
        collector.collect_user_feedback("I1", "GB50016-5.5.17", "false_positive")
        collector.collect_user_feedback("I2", "GB50016-5.5.17", "false_positive")
        collector.collect_user_feedback("I3", "GB50016-5.5.17", "false_positive")
        collector.collect_user_feedback("I4", "GB50016-5.5.17", "confirmed")

        report = collector.generate_feedback_report()
        assert "GB50016-5.5.17" in report["low_confidence_rules"]
        assert "GB50016-5.5.17" in report["needs_review_rules"]


class TestPatternLearner:
    def test_init_creates_empty_patterns(self, temp_dir):
        learner = PatternLearner(temp_dir)
        assert learner.patterns["common_issues"] == {}
        assert learner.patterns["version"] == 1

    def test_learn_from_session(self, temp_dir, sample_step_results, sample_project_params):
        learner = PatternLearner(temp_dir)
        learner.learn_from_session(sample_step_results, sample_project_params)

        assert "GB50016-5.3.1" in learner.patterns["common_issues"]
        assert learner.patterns["common_issues"]["GB50016-5.3.1"]["count"] == 2
        assert "住宅_二类高层" in learner.patterns["building_type_patterns"]

    def test_learn_persists(self, temp_dir, sample_step_results, sample_project_params):
        learner = PatternLearner(temp_dir)
        learner.learn_from_session(sample_step_results, sample_project_params)

        learner2 = PatternLearner(temp_dir)
        assert "GB50016-5.3.1" in learner2.patterns["common_issues"]

    def test_get_common_issues(self, temp_dir, sample_step_results, sample_project_params):
        learner = PatternLearner(temp_dir)
        learner.learn_from_session(sample_step_results, sample_project_params)

        issues = learner.get_common_issues(top_n=2)
        assert len(issues) == 2
        assert issues[0]["count"] >= issues[1]["count"]

    def test_get_common_issues_by_building_type(self, temp_dir, sample_step_results, sample_project_params):
        learner = PatternLearner(temp_dir)
        learner.learn_from_session(sample_step_results, sample_project_params)

        issues = learner.get_common_issues(building_type="住宅", top_n=10)
        for issue in issues:
            assert issue["count"] > 0

    def test_get_building_type_risks(self, temp_dir, sample_step_results, sample_project_params):
        learner = PatternLearner(temp_dir)
        learner.learn_from_session(sample_step_results, sample_project_params)

        risks = learner.get_building_type_risks("住宅", "二类高层")
        assert len(risks) > 0
        assert "GB50016-5.3.1" in risks

    def test_generate_pattern_report(self, temp_dir, sample_step_results, sample_project_params):
        learner = PatternLearner(temp_dir)
        learner.learn_from_session(sample_step_results, sample_project_params)

        report = learner.generate_pattern_report()
        assert report["total_rules_learned"] == 3
        assert len(report["top_10_issues"]) > 0
        assert "住宅_二类高层" in report["building_type_profiles"]

    def test_multiple_sessions_accumulate(self, temp_dir, sample_step_results, sample_project_params):
        learner = PatternLearner(temp_dir)
        learner.learn_from_session(sample_step_results, sample_project_params)
        learner.learn_from_session(sample_step_results, sample_project_params)

        assert learner.patterns["common_issues"]["GB50016-5.3.1"]["count"] == 4
        assert learner.patterns["version"] == 3
