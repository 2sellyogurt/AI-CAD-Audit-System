# -*- coding: utf-8 -*-
import json
import os
import tempfile
import pytest
from engine.experience_matcher import ExperienceMatcher


class TestExperienceMatcher:

    def test_init_creates_instance(self):
        matcher = ExperienceMatcher()
        assert isinstance(matcher._experiences, list)
        assert isinstance(matcher._cross_project_experiences, list)

    def test_init_sets_paths(self):
        matcher = ExperienceMatcher()
        assert os.path.isabs(matcher._project_root)
        assert matcher._experience_path.endswith("experience_context.json")

    def test_build_empty_result_structure(self):
        matcher = ExperienceMatcher()
        result = matcher._build_empty_result()
        assert "results" in result
        assert "summary" in result
        assert result["results"] == []
        assert result["summary"]["total_experiences"] == 0
        assert result["summary"]["matched_count"] == 0
        assert "check_results" in result["summary"]
        assert result["summary"]["check_results"]["passed"] == 0
        assert result["summary"]["check_results"]["warnings"] == 0
        assert result["summary"]["check_results"]["violations"] == 0
        assert result["summary"]["check_results"]["skipped"] == 0

    def test_evaluate_experience_with_keyword_match(self):
        matcher = ExperienceMatcher()
        exp = {
            "id": "exp_001",
            "description": "Test experience",
            "keywords": ["fire", "smoke"],
            "pattern": "",
            "status": "warnings",
            "rule_category": "fire_safety",
            "discipline": "architectural",
            "suggestion": "Check fire rating",
            "project_source": "test_project",
        }
        result = matcher._evaluate_experience(exp, ["fire door rating check"], "local")
        assert result["matched"] is True
        assert result["status"] == "warnings"
        assert "keyword:fire" in result["match_details"]
        assert result["source"] == "local"

    def test_evaluate_experience_with_pattern_match(self):
        matcher = ExperienceMatcher()
        exp = {
            "id": "exp_002",
            "description": "Pattern test",
            "keywords": [],
            "pattern": r"height\s*<\s*\d+",
            "status": "violations",
        }
        result = matcher._evaluate_experience(exp, ["height < 2400 found"], "local")
        assert result["matched"] is True
        assert "pattern:" in result["match_details"][0]

    def test_evaluate_experience_no_match(self):
        matcher = ExperienceMatcher()
        exp = {
            "id": "exp_003",
            "description": "No match",
            "keywords": ["nonexistent_keyword"],
            "pattern": "",
            "status": "passed",
        }
        result = matcher._evaluate_experience(exp, ["some unrelated text"], "local")
        assert result["matched"] is False
        assert result["match_details"] == []

    def test_evaluate_experience_none_report_texts_auto_active(self):
        matcher = ExperienceMatcher()
        exp = {
            "id": "exp_004",
            "description": "Auto active",
            "keywords": ["fire"],
            "pattern": "",
            "status": "warnings",
        }
        result = matcher._evaluate_experience(exp, None, "local")
        assert result["matched"] is True
        assert "auto_active" in result["match_details"]

    def test_evaluate_experience_empty_report_texts(self):
        matcher = ExperienceMatcher()
        exp = {
            "id": "exp_005",
            "description": "Empty texts",
            "keywords": ["fire"],
            "pattern": "",
            "status": "passed",
        }
        result = matcher._evaluate_experience(exp, [], "local")
        assert result["matched"] is False

    def test_evaluate_experience_invalid_status_defaults_skipped(self):
        matcher = ExperienceMatcher()
        exp = {
            "id": "exp_006",
            "description": "Invalid status",
            "keywords": ["fire"],
            "pattern": "",
            "status": "invalid_status",
        }
        result = matcher._evaluate_experience(exp, None, "local")
        assert result["status"] == "skipped"

    def test_evaluate_experience_non_dict_exp(self):
        matcher = ExperienceMatcher()
        result = matcher._evaluate_experience("not_a_dict", ["text"], "local")
        assert result["matched"] is False
        assert result["experience_id"] == ""

    def test_evaluate_experience_invalid_regex_pattern(self):
        matcher = ExperienceMatcher()
        exp = {
            "id": "exp_007",
            "description": "Bad regex",
            "keywords": [],
            "pattern": r"[invalid",
            "status": "passed",
        }
        result = matcher._evaluate_experience(exp, ["text"], "local")
        assert result["matched"] is False

    def test_evaluate_experience_cross_project_source(self):
        matcher = ExperienceMatcher()
        exp = {
            "id": "exp_008",
            "description": "Cross project",
            "keywords": ["fire"],
            "pattern": "",
            "status": "passed",
        }
        result = matcher._evaluate_experience(exp, ["fire test"], "cross_project")
        assert result["source"] == "cross_project"

    def test_run_checks_empty_experiences(self):
        matcher = ExperienceMatcher()
        matcher.clear_experiences()
        result = matcher.run_checks(["some text"])
        assert result["summary"]["total_experiences"] == 0
        assert result["summary"]["matched_count"] == 0

    def test_run_checks_with_local_experiences(self):
        matcher = ExperienceMatcher()
        matcher._experiences = [
            {
                "id": "exp_001",
                "description": "Test",
                "keywords": ["fire"],
                "pattern": "",
                "status": "warnings",
            }
        ]
        matcher._cross_project_experiences = []
        result = matcher.run_checks(["fire door check"])
        assert result["summary"]["total_experiences"] == 1
        assert result["summary"]["matched_count"] == 1
        assert result["summary"]["check_results"]["warnings"] == 1

    def test_run_checks_with_cross_project_experiences(self):
        matcher = ExperienceMatcher()
        matcher._experiences = []
        matcher._cross_project_experiences = [
            {
                "id": "cross_001",
                "description": "Cross test",
                "keywords": ["smoke"],
                "pattern": "",
                "status": "violations",
            }
        ]
        result = matcher.run_checks(["smoke detection issue"])
        assert result["summary"]["total_experiences"] == 1
        assert result["summary"]["matched_count"] == 1
        assert result["summary"]["check_results"]["violations"] == 1

    def test_run_checks_mixed_local_and_cross(self):
        matcher = ExperienceMatcher()
        matcher._experiences = [
            {
                "id": "local_001",
                "description": "Local",
                "keywords": ["fire"],
                "pattern": "",
                "status": "passed",
            }
        ]
        matcher._cross_project_experiences = [
            {
                "id": "cross_001",
                "description": "Cross",
                "keywords": ["smoke"],
                "pattern": "",
                "status": "warnings",
            }
        ]
        result = matcher.run_checks(["fire and smoke"])
        assert result["summary"]["total_experiences"] == 2
        assert result["summary"]["matched_count"] == 2

    def test_run_checks_none_texts(self):
        matcher = ExperienceMatcher()
        matcher._experiences = [
            {
                "id": "exp_001",
                "description": "Auto active",
                "keywords": ["fire"],
                "pattern": "",
                "status": "passed",
            }
        ]
        matcher._cross_project_experiences = []
        result = matcher.run_checks(None)
        assert result["summary"]["matched_count"] == 1

    def test_run_checks_non_dict_experiences_skipped(self):
        matcher = ExperienceMatcher()
        matcher._experiences = ["not_a_dict", 123, None]
        matcher._cross_project_experiences = []
        result = matcher.run_checks(["text"])
        assert result["summary"]["total_experiences"] == 0

    def test_update_experience_library_adds_new(self):
        matcher = ExperienceMatcher()
        matcher.clear_experiences()
        new_exps = [
            {"id": "new_001", "description": "New exp", "keywords": ["test"], "status": "passed"},
            {"id": "new_002", "description": "New exp 2", "keywords": ["test2"], "status": "warnings"},
        ]
        added = matcher.update_experience_library(new_exps)
        assert added == 2
        assert matcher.get_local_count() == 2

    def test_update_experience_library_deduplicates_by_id(self):
        matcher = ExperienceMatcher()
        matcher._experiences = [
            {"id": "existing_001", "description": "Existing", "keywords": [], "status": "passed"}
        ]
        new_exps = [
            {"id": "existing_001", "description": "Duplicate", "keywords": [], "status": "passed"},
            {"id": "new_001", "description": "New", "keywords": [], "status": "passed"},
        ]
        added = matcher.update_experience_library(new_exps)
        assert added == 1
        assert matcher.get_local_count() == 2

    def test_update_experience_library_non_list_input(self):
        matcher = ExperienceMatcher()
        matcher.clear_experiences()
        added = matcher.update_experience_library("not_a_list")
        assert added == 0

    def test_update_experience_library_non_dict_items_skipped(self):
        matcher = ExperienceMatcher()
        matcher.clear_experiences()
        added = matcher.update_experience_library(["not_a_dict", 123, None])
        assert added == 0

    def test_get_experience_count(self):
        matcher = ExperienceMatcher()
        matcher._experiences = [{"id": "1"}, {"id": "2"}]
        matcher._cross_project_experiences = [{"id": "3"}]
        assert matcher.get_experience_count() == 3

    def test_get_local_count(self):
        matcher = ExperienceMatcher()
        matcher._experiences = [{"id": "1"}, {"id": "2"}]
        assert matcher.get_local_count() == 2

    def test_get_cross_project_count(self):
        matcher = ExperienceMatcher()
        matcher._cross_project_experiences = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        assert matcher.get_cross_project_count() == 3

    def test_clear_experiences(self):
        matcher = ExperienceMatcher()
        matcher._experiences = [{"id": "1"}]
        matcher._cross_project_experiences = [{"id": "2"}]
        matcher.clear_experiences()
        assert matcher.get_experience_count() == 0

    def test_print_summary_none_input(self, capsys):
        matcher = ExperienceMatcher()
        matcher.print_summary(None)
        captured = capsys.readouterr()
        assert "无结果" in captured.out

    def test_print_summary_empty_dict(self, capsys):
        matcher = ExperienceMatcher()
        matcher.print_summary({})
        captured = capsys.readouterr()
        assert "无结果" in captured.out

    def test_print_summary_with_results(self, capsys):
        matcher = ExperienceMatcher()
        result = {
            "results": [
                {
                    "experience_id": "exp_001",
                    "description": "Fire check",
                    "matched": True,
                    "status": "warnings",
                    "source": "local",
                    "match_details": ["keyword:fire"],
                }
            ],
            "summary": {
                "total_experiences": 1,
                "matched_count": 1,
                "check_results": {
                    "passed": 0,
                    "warnings": 1,
                    "violations": 0,
                    "skipped": 0,
                },
            },
        }
        matcher.print_summary(result)
        captured = capsys.readouterr()
        assert "经验匹配摘要" in captured.out
        assert "exp_001" in captured.out
        assert "Fire check" in captured.out
