# -*- coding: utf-8 -*-
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.rule_checker import RuleChecker


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

    def get_metadata_field(self, fn, field):
        return ""


def _make_rules_file(tmp_path, rules_list):
    rules_data = {"version": "1.0.0", "last_updated": "2026-05-18", "rules": rules_list}
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(rules_data, ensure_ascii=False), encoding="utf-8")
    return str(rules_path)


def _create_checker_with_rules_path(tmp_path, rules_path, loader):
    checker = RuleChecker(loader)
    checker._rules_path = rules_path
    checker._load_rules()
    return checker


_SAMPLE_RULES = [
    {
        "rule_id": "rule_001",
        "category": "\u5efa\u7b51",
        "description": "\u4f4f\u5b85\u5367\u5ba4\u51c0\u9ad8\u4e0d\u5e94\u4f4e\u4e8e2.4m",
        "keywords": ["\u5367\u5ba4", "\u51c0\u9ad8", "2.4"],
        "regex": "\u5367\u5ba4.*\u51c0\u9ad8.*(2\\.?\\d+)",
        "severity": "\u9ad8",
        "standard_code": "GB 55038-2025 \u7b2c4.1.2\u6761",
    },
    {
        "rule_id": "rule_002",
        "category": "\u7ed3\u6784",
        "description": "\u6df7\u51dd\u571f\u4fdd\u62a4\u5c42\u539a\u5ea6\u4e0d\u5e94\u5c0f\u4e8e15mm",
        "keywords": ["\u4fdd\u62a4\u5c42", "\u539a\u5ea6", "15mm"],
        "regex": "\u4fdd\u62a4\u5c42.*\u539a\u5ea6.*(1[4-9]\\d?)\\s*mm",
        "severity": "\u9ad8",
        "standard_code": "GB 50010-2010 \u7b2c8.2.1\u6761",
    },
]


def test_init_no_rules_file(tmp_path):
    loader = MockLoader()
    checker = _create_checker_with_rules_path(
        tmp_path, str(tmp_path / "nonexistent_rules.json"), loader
    )
    assert checker.mandatory_rules == []
    assert isinstance(checker.rules_config, dict)


def test_check_all_rules_empty(tmp_path):
    loader = MockLoader()
    rules_path = _make_rules_file(tmp_path, _SAMPLE_RULES)
    checker = _create_checker_with_rules_path(tmp_path, rules_path, loader)
    results = checker.check_all_rules()
    assert len(results) == 2
    for r in results:
        assert r["compliance_status"] == "\u4e0d\u9002\u7528"


def test_check_all_rules_normal(tmp_path):
    loader = MockLoader(
        files=["file_a"],
        readable_names={"file_a": "\u5efa\u7b51\u5e73\u9762\u56fe"},
        text_lines={"file_a": ["\u5367\u5ba4\u51c0\u9ad8\u4e0d\u5e94\u4f4e\u4e8e2.45m \u7b26\u5408\u8981\u6c42"]},
    )
    rules_path = _make_rules_file(tmp_path, _SAMPLE_RULES)
    checker = _create_checker_with_rules_path(tmp_path, rules_path, loader)
    results = checker.check_all_rules()
    assert len(results) == 2
    assert results[0]["rule_id"] == "rule_001"
    assert results[0]["compliance_status"] == "\u5408\u89c4"
    assert results[0]["matched_keywords"] == ["\u5367\u5ba4", "\u51c0\u9ad8", "2.4"]
    assert results[0]["file"] == "\u5efa\u7b51\u5e73\u9762\u56fe"


def test_get_statistics(tmp_path):
    loader = MockLoader(
        files=["f1", "f2", "f3"],
        readable_names={
            "f1": "\u6587\u4ef61",
            "f2": "\u6587\u4ef62",
            "f3": "\u6587\u4ef63",
        },
        text_lines={
            "f1": ["\u5367\u5ba4\u51c0\u9ad8\u4e0d\u5e94\u4f4e\u4e8e2.45m"],
            "f2": ["\u4fdd\u62a4\u5c42\u539a\u5ea6\u4e0d\u8db312mm"],
            "f3": ["\u8fd9\u662f\u4e00\u4e2a\u6d4b\u8bd5\u5173\u952e\u8bcd\u7684\u6587\u672c"],
        },
    )
    rules_list = [
        {
            "rule_id": "r1",
            "category": "\u5efa\u7b51",
            "description": "d1",
            "keywords": ["\u5367\u5ba4", "\u51c0\u9ad8"],
            "regex": "\u5367\u5ba4.*\u51c0\u9ad8.*(2\\.?\\d+)",
            "severity": "\u9ad8",
            "standard_code": "GB1",
        },
        {
            "rule_id": "r2",
            "category": "\u7ed3\u6784",
            "description": "d2",
            "keywords": ["\u4fdd\u62a4\u5c42", "\u539a\u5ea6"],
            "regex": "",
            "severity": "\u4e2d",
            "standard_code": "GB2",
        },
        {
            "rule_id": "r3",
            "category": "\u6696\u901a",
            "description": "d3",
            "keywords": ["\u6d4b\u8bd5\u5173\u952e\u8bcd"],
            "regex": "",
            "severity": "\u4f4e",
            "standard_code": "GB3",
        },
    ]
    rules_path = _make_rules_file(tmp_path, rules_list)
    checker = _create_checker_with_rules_path(tmp_path, rules_path, loader)
    results = checker.check_all_rules()
    stats = checker.get_statistics(results)
    assert stats["total"] == 3
    assert stats["compliant"] >= 1
    assert stats["non_compliant"] >= 1
    assert stats["need_verify"] >= 1
    assert stats["by_discipline"]["\u5efa\u7b51"]["total"] == 1
    assert stats["by_discipline"]["\u7ed3\u6784"]["total"] == 1
    assert stats["by_discipline"]["\u6696\u901a"]["total"] == 1


def test_search_by_keyword(tmp_path):
    loader = MockLoader()
    rules_path = _make_rules_file(tmp_path, _SAMPLE_RULES)
    checker = _create_checker_with_rules_path(tmp_path, rules_path, loader)
    results = checker.search_by_keyword("\u5367\u5ba4")
    assert len(results) == 1
    assert results[0]["rule_id"] == "rule_001"
    results2 = checker.search_by_keyword("\u4fdd\u62a4\u5c42")
    assert len(results2) == 1
    assert results2[0]["rule_id"] == "rule_002"
    results3 = checker.search_by_keyword("")
    assert results3 == []
    results4 = checker.search_by_keyword("nonexistent_xyz")
    assert results4 == []


def test_search_by_regex(tmp_path):
    loader = MockLoader()
    rules_path = _make_rules_file(tmp_path, _SAMPLE_RULES)
    checker = _create_checker_with_rules_path(tmp_path, rules_path, loader)
    results = checker.search_by_regex(r"\u51c0\u9ad8")
    assert len(results) == 1
    assert results[0]["rule_id"] == "rule_001"
    results2 = checker.search_by_regex(r"\u4fdd\u62a4\u5c42|\u539a\u5ea6")
    assert len(results2) >= 1
    results3 = checker.search_by_regex("")
    assert results3 == []
    results4 = checker.search_by_regex("no_match_xyz_999")
    assert results4 == []


def test_reload_rules(tmp_path):
    loader = MockLoader()
    rules_v1 = [
        {
            "rule_id": "r_v1",
            "category": "\u5efa\u7b51",
            "description": "v1 rule",
            "keywords": ["v1"],
            "regex": "",
            "severity": "\u9ad8",
            "standard_code": "GB-V1",
        }
    ]
    rules_v2 = [
        {
            "rule_id": "r_v2",
            "category": "\u7ed3\u6784",
            "description": "v2 rule",
            "keywords": ["v2"],
            "regex": "",
            "severity": "\u4e2d",
            "standard_code": "GB-V2",
        }
    ]
    rules_path = _make_rules_file(tmp_path, rules_v1)
    checker = _create_checker_with_rules_path(tmp_path, rules_path, loader)
    assert len(checker.mandatory_rules) == 1
    assert checker.mandatory_rules[0]["rule_id"] == "r_v1"
    _make_rules_file(tmp_path, rules_v2)
    checker.reload_rules()
    assert len(checker.mandatory_rules) == 1
    assert checker.mandatory_rules[0]["rule_id"] == "r_v2"


def test_invalid_regex(tmp_path):
    loader = MockLoader()
    rules_list = [
        {
            "rule_id": "r_bad",
            "category": "\u5efa\u7b51",
            "description": "bad regex rule",
            "keywords": ["test"],
            "regex": "[invalid(regex",
            "severity": "\u9ad8",
            "standard_code": "GB-TEST",
        }
    ]
    rules_path = _make_rules_file(tmp_path, rules_list)
    checker = _create_checker_with_rules_path(tmp_path, rules_path, loader)
    results = checker.search_by_regex("[invalid(regex")
    assert results == []
