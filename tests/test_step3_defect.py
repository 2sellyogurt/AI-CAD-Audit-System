# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.step3_defect import (
    clean_filenames_in_results,
    _replace_uuid_in_text,
    _validate_evidence_chain,
    _infer_floor_from_line,
    parse_args,
)


class MockLoader:
    def __init__(self):
        self._readable_names = {
            "abc_建筑平面图_unified.json": "建筑平面图",
            "def_结构梁图_unified.json": "结构梁图",
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890_建筑平面图_unified.json": "建筑平面图",
            "b2c3d4e5-f6a7-8901-bcde-f12345678901_结构梁图_unified.json": "结构梁图",
        }
        self._text_lines = {
            "abc_建筑平面图_unified.json": [
                "一层平面图",
                "卧室净高2.4m",
                "层高2.8m",
            ],
        }

    def get_readable_name(self, fn):
        return self._readable_names.get(fn, fn)

    def get_text_lines_by_file(self, fn):
        return self._text_lines.get(fn, [])

    @property
    def files(self):
        return list(self._readable_names.keys())


class TestReplaceUuidInText:
    def setup_method(self):
        self.loader = MockLoader()

    def test_normal_uuid(self):
        text = "文件 abc_建筑平面图_unified.json 中存在问题"
        result = _replace_uuid_in_text(text, self.loader)
        assert "建筑平面图" in result

    def test_no_uuid(self):
        text = "普通文本内容"
        result = _replace_uuid_in_text(text, self.loader)
        assert result == text

    def test_empty_text(self):
        assert _replace_uuid_in_text("", self.loader) == ""
        assert _replace_uuid_in_text(None, self.loader) is None

    def test_non_string(self):
        assert _replace_uuid_in_text(123, self.loader) == 123


class TestCleanFilenamesInResults:
    def setup_method(self):
        self.loader = MockLoader()

    def test_dict_with_file(self):
        data = {"file": "abc_建筑平面图_unified.json", "description": "测试"}
        result = clean_filenames_in_results(data, self.loader)
        assert result["file"] == "建筑平面图"

    def test_dict_with_location(self):
        data = {"location": "abc_建筑平面图_unified.json", "description": "测试"}
        result = clean_filenames_in_results(data, self.loader)
        assert result["location"] == "建筑平面图"

    def test_list_data(self):
        data = [{"file": "abc_建筑平面图_unified.json"}]
        result = clean_filenames_in_results(data, self.loader)
        assert result[0]["file"] == "建筑平面图"

    def test_nested_dict(self):
        data = {
            "issues": [
                {"file": "abc_建筑平面图_unified.json", "description": "问题1"},
                {"file": "def_结构梁图_unified.json", "description": "问题2"},
            ]
        }
        result = clean_filenames_in_results(data, self.loader)
        assert result["issues"][0]["file"] == "建筑平面图"
        assert result["issues"][1]["file"] == "结构梁图"

    def test_empty_data(self):
        result = clean_filenames_in_results({}, self.loader)
        assert result == {}


class TestValidateEvidenceChain:
    def test_l3_complete(self):
        data = {
            "description": "净高不足",
            "file": "建筑平面图",
            "evidence": "卧室净高2.2m",
            "line": 10,
            "rule_id": "rule_001",
            "code_reference": "GB 55038-2025",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L3-完整"
        assert result["low_confidence"] is False

    def test_l2_enhanced(self):
        data = {
            "description": "净高不足",
            "file": "建筑平面图",
            "evidence": "卧室净高2.2m",
            "line": 10,
            "rule_id": "rule_001",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L2-增强"
        assert result["low_confidence"] is False

    def test_l1_basic(self):
        data = {
            "description": "净高不足",
            "file": "建筑平面图",
            "evidence": "卧室净高2.2m",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L1-基础"
        assert result["low_confidence"] is True

    def test_l0_no_evidence(self):
        data = {
            "description": "净高不足",
            "file": "未知文件",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L0-无证据"
        assert result["low_confidence"] is True

    def test_non_issue(self):
        data = {"name": "测试数据"}
        result = _validate_evidence_chain(data)
        assert "confidence_level" not in result
        assert "low_confidence" not in result


class TestInferFloorFromLine:
    def setup_method(self):
        self.loader = MockLoader()

    def test_from_filename(self):
        result = _infer_floor_from_line("建筑平面图", 1, self.loader)
        assert isinstance(result, str)

    def test_from_content(self):
        result = _infer_floor_from_line("建筑平面图", 1, self.loader)
        assert isinstance(result, str)

    def test_empty_file(self):
        result = _infer_floor_from_line("", 1, self.loader)
        assert isinstance(result, str)

    def test_none_line(self):
        result = _infer_floor_from_line("建筑平面图", None, self.loader)
        assert isinstance(result, str)


class TestParseArgs:
    def test_default_args(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["step3_defect.py"])
        args = parse_args()
        assert args.json_dir is not None
        assert args.output_dir is not None

    def test_custom_json_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["step3_defect.py", "--json-dir", "/tmp/jsons"])
        args = parse_args()
        assert args.json_dir == "/tmp/jsons"

    def test_custom_output_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["step3_defect.py", "--output-dir", "/tmp/output"])
        args = parse_args()
        assert args.output_dir == "/tmp/output"

    def test_both_dirs(self, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            ["step3_defect.py", "--json-dir", "/a", "--output-dir", "/b"],
        )
        args = parse_args()
        assert args.json_dir == "/a"
        assert args.output_dir == "/b"

    def test_env_var_json_dir(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_JSON_DIR", "/env/json")
        monkeypatch.delenv("PIPELINE_OUTPUT_DIR", raising=False)
        monkeypatch.setattr(sys, "argv", ["step3_defect.py"])
        args = parse_args()
        assert args.json_dir == "/env/json"

    def test_env_var_output_dir(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_OUTPUT_DIR", "/env/output")
        monkeypatch.delenv("PIPELINE_JSON_DIR", raising=False)
        monkeypatch.setattr(sys, "argv", ["step3_defect.py"])
        args = parse_args()
        assert args.output_dir == "/env/output"

    def test_cli_overrides_env(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_JSON_DIR", "/env/json")
        monkeypatch.setattr(
            sys, "argv",
            ["step3_defect.py", "--json-dir", "/cli/json"],
        )
        args = parse_args()
        assert args.json_dir == "/cli/json"


class TestReplaceUuidInTextExtra:
    def setup_method(self):
        self.loader = MockLoader()

    def test_multiple_uuids(self):
        text = (
            "文件 abc_建筑平面图_unified.json 和 def_结构梁图_unified.json 存在碰撞"
        )
        result = _replace_uuid_in_text(text, self.loader)
        assert "建筑平面图" in result
        assert "结构梁图" in result

    def test_text_without_unified_suffix(self):
        text = "abc_建筑平面图.dxf"
        result = _replace_uuid_in_text(text, self.loader)
        assert result == text

    def test_loader_returns_original(self):
        loader = MockLoader()
        loader._readable_names = {}
        text = "文件 abc_建筑平面图_unified.json 中有问题"
        result = _replace_uuid_in_text(text, loader)
        assert "abc_建筑平面图_unified.json" in result


class TestCleanFilenamesInResultsExtra:
    def setup_method(self):
        self.loader = MockLoader()

    def test_duct_file_field(self):
        data = {"duct_file": "abc_建筑平面图_unified.json", "issue": "碰撞"}
        result = clean_filenames_in_results(data, self.loader)
        assert result["duct_file"] == "建筑平面图"

    def test_sprinkler_file_field(self):
        data = {"sprinkler_file": "def_结构梁图_unified.json"}
        result = clean_filenames_in_results(data, self.loader)
        assert result["sprinkler_file"] == "结构梁图"

    def test_description_with_uuid(self):
        data = {"description": "在 a1b2c3d4-e5f6-7890-abcd-ef1234567890_建筑平面图_unified.json 中发现管线碰撞"}
        result = clean_filenames_in_results(data, self.loader)
        assert "建筑平面图" in result["description"]
        assert "a1b2c3d4-e5f6-7890-abcd-ef1234567890_建筑平面图_unified.json" not in result["description"]

    def test_evidence_with_uuid(self):
        data = {"evidence": "参考 b2c3d4e5-f6a7-8901-bcde-f12345678901_结构梁图_unified.json 的梁截面数据"}
        result = clean_filenames_in_results(data, self.loader)
        assert "结构梁图" in result["evidence"]
        assert "b2c3d4e5-f6a7-8901-bcde-f12345678901_结构梁图_unified.json" not in result["evidence"]

    def test_pipe_info_with_uuid(self):
        data = {"pipe_info": "从 abc_建筑平面图_unified.json 提取"}
        result = clean_filenames_in_results(data, self.loader)
        assert "建筑平面图" in result["pipe_info"]

    def test_electrical_info_with_uuid(self):
        data = {"electrical_info": "参见 def_结构梁图_unified.json"}
        result = clean_filenames_in_results(data, self.loader)
        assert "结构梁图" in result["electrical_info"]

    def test_column_info_with_uuid(self):
        data = {"column_info": "柱位于 abc_建筑平面图_unified.json"}
        result = clean_filenames_in_results(data, self.loader)
        assert "建筑平面图" in result["column_info"]

    def test_pipe_type_with_uuid(self):
        data = {"pipe_type": "abc_建筑平面图_unified.json 中的管"}
        result = clean_filenames_in_results(data, self.loader)
        assert "建筑平面图" in result["pipe_type"]

    def test_tray_spec_with_uuid(self):
        data = {"tray_spec": "见 abc_建筑平面图_unified.json 桥架"}
        result = clean_filenames_in_results(data, self.loader)
        assert "建筑平面图" in result["tray_spec"]

    def test_sprinkler_text_with_uuid(self):
        data = {"sprinkler_text": "从 abc_建筑平面图_unified.json 喷淋"}
        result = clean_filenames_in_results(data, self.loader)
        assert "建筑平面图" in result["sprinkler_text"]

    def test_duct_text_with_uuid(self):
        data = {"duct_text": "abc_建筑平面图_unified.json 风管信息"}
        result = clean_filenames_in_results(data, self.loader)
        assert "建筑平面图" in result["duct_text"]

    def test_question_with_uuid(self):
        data = {"question": "abc_建筑平面图_unified.json 中的管线是否满足规范？"}
        result = clean_filenames_in_results(data, self.loader)
        assert "建筑平面图" in result["question"]

    def test_auto_floor_field_added(self):
        data = {"file": "建筑平面图", "line": 10, "description": "测试"}
        result = clean_filenames_in_results(data, self.loader)
        assert "floor" in result
        assert isinstance(result["floor"], str)

    def test_floor_not_overwritten(self):
        data = {"file": "建筑平面图", "line": 10, "floor": "2F"}
        result = clean_filenames_in_results(data, self.loader)
        assert result["floor"] == "2F"

    def test_list_with_string_items(self):
        data = ["a1b2c3d4-e5f6-7890-abcd-ef1234567890_建筑平面图_unified.json 引用", "普通文本"]
        result = clean_filenames_in_results(data, self.loader)
        assert "建筑平面图" in result[0]
        assert "a1b2c3d4-e5f6-7890-abcd-ef1234567890_建筑平面图_unified.json" not in result[0]
        assert result[1] == "普通文本"

    def test_list_with_non_string_non_dict(self):
        data = [123, None, True]
        result = clean_filenames_in_results(data, self.loader)
        assert result[0] == 123
        assert result[1] is None
        assert result[2] is True

    def test_deeply_nested(self):
        data = {
            "level1": {
                "level2": [
                    {"file": "abc_建筑平面图_unified.json", "evidence": "test"},
                ]
            }
        }
        result = clean_filenames_in_results(data, self.loader)
        assert result["level1"]["level2"][0]["file"] == "建筑平面图"

    def test_non_file_string_field_untouched(self):
        data = {"status": "合规", "name": "测试"}
        result = clean_filenames_in_results(data, self.loader)
        assert result["status"] == "合规"
        assert result["name"] == "测试"


class TestValidateEvidenceChainExtra:
    def test_question_key_marks_issue(self):
        data = {"question": "管线碰撞？", "file": "建筑平面图", "evidence": "x=100"}
        result = _validate_evidence_chain(data)
        assert "confidence_level" in result

    def test_detail_key_marks_issue(self):
        data = {"detail": "标高错误", "file": "建筑平面图", "raw_text": "3.2m"}
        result = _validate_evidence_chain(data)
        assert "confidence_level" in result
        assert result["confidence_level"] == "L1-基础"

    def test_issue_key_marks_issue(self):
        data = {"issue": "间距不足", "file": "建筑平面图"}
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L0-无证据"

    def test_raw_text_as_evidence(self):
        data = {
            "description": "管线冲突",
            "file": "结构梁图",
            "raw_text": "DN100管道穿梁",
            "line": 5,
            "rule_id": "rule_010",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L2-增强"

    def test_original_text_as_evidence(self):
        data = {
            "description": "管线冲突",
            "file": "结构梁图",
            "original_text": "管道与梁碰撞",
            "line": 3,
            "rule_id": "rule_010",
            "code_reference": "GB 50010-2010",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L3-完整"
        assert result["low_confidence"] is False

    def test_line_zero_is_valid(self):
        data = {
            "description": "标高问题",
            "file": "建筑平面图",
            "evidence": "3.2m",
            "line": 0,
            "rule_id": "rule_001",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L2-增强"
        assert result["low_confidence"] is False

    def test_file_empty_string(self):
        data = {
            "description": "标高问题",
            "file": "",
            "evidence": "3.2m",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L0-无证据"
        assert result["low_confidence"] is True

    def test_multiple_nested_issues(self):
        data = [
            {
                "description": "问题1",
                "file": "建筑平面图",
                "evidence": "e1",
                "line": 1,
                "rule_id": "r1",
                "code_reference": "GB1",
            },
            {
                "description": "问题2",
                "file": "未知文件",
            },
        ]
        result = _validate_evidence_chain(data)
        assert result[0]["confidence_level"] == "L3-完整"
        assert result[1]["confidence_level"] == "L0-无证据"

    def test_nested_data_in_list(self):
        data = {
            "issues": [
                {
                    "description": "净高不足",
                    "file": "建筑平面图",
                    "evidence": "卧室净高2.2m",
                    "line": 10,
                    "rule_id": "rule_001",
                    "code_reference": "GB 55038-2025",
                }
            ]
        }
        result = _validate_evidence_chain(data)
        assert result["issues"][0]["confidence_level"] == "L3-完整"

    def test_empty_list(self):
        result = _validate_evidence_chain([])
        assert result == []

    def test_non_dict_non_list(self):
        result = _validate_evidence_chain("plain text")
        assert result == "plain text"

    def test_deeply_nested(self):
        data = {
            "section": {
                "sub": [
                    {
                        "items": [
                            {
                                "detail": "深嵌套问题",
                                "file": "结构梁图",
                                "evidence": "梁截面不足",
                                "line": 20,
                                "rule_id": "rule_020",
                                "code_reference": "GB 50010",
                            }
                        ]
                    }
                ]
            }
        }
        result = _validate_evidence_chain(data)
        inner = result["section"]["sub"][0]["items"][0]
        assert inner["confidence_level"] == "L3-完整"


class TestInferFloorFromLineExtra:
    def setup_method(self):
        self.loader = MockLoader()

    def test_chinese_floor_from_filename(self):
        result = _infer_floor_from_line("三层平面图", None, self.loader)
        assert result == "3F"

    def test_roof_from_filename(self):
        result = _infer_floor_from_line("屋顶层平面图", None, self.loader)
        assert result == "RF"

    def test_basement_from_filename(self):
        result = _infer_floor_from_line("地下室平面图", None, self.loader)
        assert result == "B1"

    def test_first_floor_from_filename(self):
        result = _infer_floor_from_line("首层平面图", None, self.loader)
        assert result == "1F"

    def test_numeric_floor_from_filename(self):
        result = _infer_floor_from_line("3F平面图", None, self.loader)
        assert result == "3F"

    def test_unknown_returns_empty(self):
        result = _infer_floor_from_line("未知文件", None, self.loader)
        assert result == ""

    def test_empty_file_returns_empty(self):
        result = _infer_floor_from_line("", 1, self.loader)
        assert result == ""
