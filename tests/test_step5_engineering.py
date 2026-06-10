# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.step5_engineering import (
    clean_filenames_in_results,
    _replace_uuid_in_text,
    _validate_evidence_chain,
    _collect_issues,
    _infer_floor_from_line,
    _load_step2_result,
    _load_step3_result,
    _load_step4_result,
    _compute_step2,
    _compute_step3,
    _compute_step4,
    parse_args,
)


class MockLoader:
    def __init__(self):
        self._readable_names = {
            "abc_建筑平面图_unified.json": "建筑平面图",
            "def_结构梁图_unified.json": "结构梁图",
        }
        self._text_lines = {}

    def get_readable_name(self, fn):
        return self._readable_names.get(fn, fn)

    @property
    def files(self):
        return list(self._readable_names.keys())

    def get_text_lines_by_file(self, fn):
        return self._text_lines.get(fn, [])


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

    def test_nested_dict_recursive(self):
        data = {
            "category": {
                "issue_item": {
                    "description": "嵌套问题",
                    "file": "建筑平面图",
                    "evidence": "证据文本",
                    "line": 5,
                    "rule_id": "r001",
                    "code_reference": "GB50016",
                }
            }
        }
        result = _validate_evidence_chain(data)
        assert result["category"]["issue_item"]["confidence_level"] == "L3-完整"

    def test_list_recursive(self):
        data = [
            {
                "description": "列表中的问题",
                "file": "建筑平面图",
                "evidence": "证据",
            }
        ]
        result = _validate_evidence_chain(data)
        assert result[0]["confidence_level"] == "L1-基础"

    def test_nested_list_in_dict(self):
        data = {
            "issues": [
                {
                    "description": "问题A",
                    "file": "未知文件",
                    "question": "是否存在?",
                }
            ]
        }
        result = _validate_evidence_chain(data)
        assert result["issues"][0]["confidence_level"] == "L0-无证据"

    def test_evidence_none_falls_to_l0(self):
        data = {
            "description": "问题",
            "file": "建筑平面图",
            "evidence": None,
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L0-无证据"

    def test_original_text_as_evidence(self):
        data = {
            "description": "问题",
            "file": "建筑平面图",
            "original_text": "原始文本证据",
            "line": 10,
            "rule_id": "r001",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L2-增强"

    def test_raw_text_as_evidence(self):
        data = {
            "description": "问题",
            "file": "建筑平面图",
            "raw_text": "原始文本",
            "line": 10,
            "rule_id": "r001",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L2-增强"

    def test_line_empty_string_is_no_line(self):
        data = {
            "description": "问题",
            "file": "建筑平面图",
            "evidence": "证据",
            "line": "",
            "rule_id": "r001",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L1-基础"

    def test_non_dict_non_list_returns_unchanged(self):
        data = "just a string"
        result = _validate_evidence_chain(data)
        assert result == "just a string"

    def test_issue_field_as_trigger(self):
        data = {
            "issue": "发现的问题",
            "file": "建筑平面图",
            "evidence": "证据",
            "line": 1,
            "rule_id": "r001",
            "code_reference": "GB50016",
        }
        result = _validate_evidence_chain(data)
        assert result["confidence_level"] == "L3-完整"

    def test_detail_field_as_trigger(self):
        data = {
            "detail": "详细信息",
            "file": "建筑平面图",
            "evidence": "证据",
        }
        result = _validate_evidence_chain(data)
        assert "confidence_level" in result

    def test_question_field_as_trigger(self):
        data = {
            "question": "这是什么问题?",
            "file": "建筑平面图",
            "evidence": "证据",
        }
        result = _validate_evidence_chain(data)
        assert "confidence_level" in result


class TestCollectIssues:
    def test_empty_results(self):
        result = _collect_issues({}, "测试来源")
        assert result == []

    def test_dict_with_list_values(self):
        results = {
            "issues": [
                {"description": "问题1", "severity": "high"},
                {"description": "问题2", "level": "medium"},
            ]
        }
        result = _collect_issues(results, "规则检查")
        assert len(result) == 2
        assert result[0]["source"] == "规则检查"
        assert result[0]["category"] == "issues"
        assert result[0]["severity"] == "high"
        assert result[1]["severity"] == "medium"

    def test_nested_dict_structure(self):
        results = {
            "category1": {
                "subcategory": [
                    {"description": "嵌套问题", "severity": "low"}
                ]
            }
        }
        result = _collect_issues(results, "碰撞检测")
        assert len(result) == 1
        assert result[0]["category"] == "category1.subcategory"

    def test_non_dict_item_in_list(self):
        results = {"issues": ["not_a_dict", 123]}
        result = _collect_issues(results, "测试")
        assert len(result) == 0

    def test_dict_with_dict_values_containing_lists(self):
        results = {
            "碰撞检测": {
                "梁柱碰撞": [
                    {"description": "梁柱碰撞1", "severity": "high"},
                    {"rule_id": "R002", "level": "medium"},
                ],
                "管线碰撞": [
                    {"issue": "管线交叉", "severity": "low"},
                ],
            }
        }
        result = _collect_issues(results, "碰撞检测")
        assert len(result) == 3
        assert result[0]["category"] == "碰撞检测.梁柱碰撞"
        assert result[0]["key"] == "梁柱碰撞1"
        assert result[1]["key"] == "R002"
        assert result[2]["category"] == "碰撞检测.管线碰撞"
        assert result[2]["key"] == "管线交叉"

    def test_dict_with_non_list_non_dict_values(self):
        results = {
            "summary": {"total": 10},
            "status": "ok",
            "count": 5,
        }
        result = _collect_issues(results, "测试")
        assert len(result) == 0

    def test_severity_fallback_to_level(self):
        results = {
            "issues": [
                {"description": "问题", "level": "warning"},
            ]
        }
        result = _collect_issues(results, "测试")
        assert result[0]["severity"] == "warning"

    def test_severity_default_unknown(self):
        results = {
            "issues": [
                {"description": "问题"},
            ]
        }
        result = _collect_issues(results, "测试")
        assert result[0]["severity"] == "unknown"

    def test_key_fallback_chain(self):
        results = {
            "issues": [
                {"rule_id": "R001", "severity": "high"},
                {"issue": "具体问题描述", "severity": "medium"},
                {"other_field": "value", "severity": "low"},
            ]
        }
        result = _collect_issues(results, "测试")
        assert result[0]["key"] == "R001"
        assert result[1]["key"] == "具体问题描述"
        assert result[2]["key"] == str({"other_field": "value", "severity": "low"})

    def test_non_dict_results(self):
        result = _collect_issues("not_a_dict", "测试")
        assert result == []

    def test_non_dict_results_list(self):
        result = _collect_issues([1, 2, 3], "测试")
        assert result == []


class TestInferFloorFromLine:
    def test_from_filename_chinese(self):
        loader = MockLoader()
        result = _infer_floor_from_line("三层平面图", None, loader)
        assert result == "3F"

    def test_from_filename_rf(self):
        loader = MockLoader()
        result = _infer_floor_from_line("屋顶层平面图", None, loader)
        assert result == "RF"

    def test_from_filename_basement(self):
        loader = MockLoader()
        result = _infer_floor_from_line("地下室平面图", None, loader)
        assert result == "B1"

    def test_unknown_file(self):
        loader = MockLoader()
        result = _infer_floor_from_line("未知文件", None, loader)
        assert result == ""

    def test_none_line(self):
        loader = MockLoader()
        result = _infer_floor_from_line("未知文件", None, loader)
        assert result == ""


class TestLoadStep2Result:
    def test_file_not_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _load_step2_result(tmpdir)
            assert result is None

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "rule_results": {"issues": []},
                "rule_stats": {"compliant": 5, "need_verify": 2, "non_compliant": 1},
                "normative_codes": ["GB50016"],
            }
            path = os.path.join(tmpdir, "step2_compliance_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            result = _load_step2_result(tmpdir)
            assert result is not None
            assert result[0] == {"issues": []}
            assert result[1]["compliant"] == 5
            assert result[2] == ["GB50016"]

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "step2_compliance_result.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("invalid json")
            result = _load_step2_result(tmpdir)
            assert result is None

    def test_valid_json_with_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "rule_results": {},
                "rule_stats": {
                    "compliant": 10,
                    "need_verify": 3,
                    "non_compliant": 2,
                    "not_applicable": 5,
                },
                "normative_codes": ["GB50016", "GB55038"],
            }
            path = os.path.join(tmpdir, "step2_compliance_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            result = _load_step2_result(tmpdir)
            assert result is not None
            assert result[1]["not_applicable"] == 5
            assert len(result[2]) == 2


class TestLoadStep3Result:
    def test_file_not_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _load_step3_result(tmpdir)
            assert result is None

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "elevation_results": {"summary": {"beam_count": 5}},
                "collision_results": {"summary": {"total_issues": 3}},
                "mep_results": {"summary": {"pipeline_count": 10}},
                "geometry_results": {"findings": [], "enabled": False},
            }
            path = os.path.join(tmpdir, "step3_defect_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            result = _load_step3_result(tmpdir)
            assert result is not None
            assert result["elevation_results"]["summary"]["beam_count"] == 5

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "step3_defect_result.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("invalid json")
            result = _load_step3_result(tmpdir)
            assert result is None

    def test_valid_json_with_geometry_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "elevation_results": {"summary": {"beam_count": 5, "slab_count": 3}},
                "collision_results": {"summary": {"total_issues": 3}},
                "mep_results": {"summary": {"pipeline_count": 10, "scheme_feasible": True}},
                "geometry_results": {
                    "findings": [{"id": "f1", "category": "空间不足"}],
                    "summary": {"total": 1},
                    "enabled": True,
                },
            }
            path = os.path.join(tmpdir, "step3_defect_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            result = _load_step3_result(tmpdir)
            assert result is not None
            assert result["geometry_results"]["enabled"] is True
            assert len(result["geometry_results"]["findings"]) == 1

    def test_valid_json_with_mep_infeasible(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "elevation_results": {"summary": {}},
                "collision_results": {"summary": {}},
                "mep_results": {"summary": {"pipeline_count": 20, "scheme_feasible": False}},
                "geometry_results": {"findings": [], "enabled": False},
            }
            path = os.path.join(tmpdir, "step3_defect_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            result = _load_step3_result(tmpdir)
            assert result is not None
            assert result["mep_results"]["summary"]["scheme_feasible"] is False


class TestLoadStep4Result:
    def test_file_not_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _load_step4_result(tmpdir)
            assert result is None

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "cross_results": {"issues": []},
                "deep_cross_results": [],
                "cross_stats": {"compliant": 8, "non_compliant": 2},
            }
            path = os.path.join(tmpdir, "step4_cross_check_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            result = _load_step4_result(tmpdir)
            assert result is not None
            assert result["cross_stats"]["compliant"] == 8

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "step4_cross_check_result.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("invalid json")
            result = _load_step4_result(tmpdir)
            assert result is None

    def test_valid_json_with_all_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "cross_results": {"issues": [{"id": 1}]},
                "deep_cross_results": [{"check_name": "标高比对", "status": "不一致"}],
                "cross_stats": {
                    "compliant": 10,
                    "need_verify": 3,
                    "non_compliant": 2,
                    "total": 15,
                },
            }
            path = os.path.join(tmpdir, "step4_cross_check_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            result = _load_step4_result(tmpdir)
            assert result is not None
            assert result["cross_stats"]["total"] == 15
            assert len(result["deep_cross_results"]) == 1


class TestComputeStep2:
    @patch("src.step5_engineering.RuleChecker")
    def test_compute_step2_success(self, mock_rule_checker_cls):
        mock_checker = MagicMock()
        mock_checker.check_all_rules.return_value = {"issues": []}
        mock_checker.get_statistics.return_value = {
            "compliant": 10,
            "need_verify": 2,
            "non_compliant": 1,
            "not_applicable": 3,
        }
        mock_rule_checker_cls.return_value = mock_checker

        mock_loader = MagicMock()

        with patch("os.path.exists", return_value=False):
            rule_results, rule_stats, normative_codes = _compute_step2(mock_loader)

        assert rule_results == {"issues": []}
        assert rule_stats["compliant"] == 10
        assert normative_codes == []
        mock_checker.check_all_rules.assert_called_once()
        mock_checker.get_statistics.assert_called_once()

    @patch("src.step5_engineering.RuleChecker")
    def test_compute_step2_with_normative_db(self, mock_rule_checker_cls):
        mock_checker = MagicMock()
        mock_checker.check_all_rules.return_value = {}
        mock_checker.get_statistics.return_value = {
            "compliant": 0,
            "need_verify": 0,
            "non_compliant": 0,
            "not_applicable": 0,
        }
        mock_rule_checker_cls.return_value = mock_checker

        mock_loader = MagicMock()

        norm_db_data = {
            "codes": [
                {"code_id": "GB50016-2014", "name": "建筑设计防火规范"},
                {"code_id": "GB55038-2025", "name": "住宅项目规范"},
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(norm_db_data, f)
            tmp_path = f.name

        try:
            with patch("os.path.exists", return_value=True), \
                 patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__ = lambda s: MagicMock(
                    read=lambda: json.dumps(norm_db_data)
                )
                mock_open.return_value.__exit__ = MagicMock(return_value=False)

                import io
                with patch("builtins.open", return_value=io.StringIO(json.dumps(norm_db_data))):
                    rule_results, rule_stats, normative_codes = _compute_step2(mock_loader)

            assert isinstance(normative_codes, list)
        finally:
            os.unlink(tmp_path)


class TestComputeStep3:
    @patch("src.step5_engineering.MepCoordinator")
    @patch("src.step5_engineering.AxisCollisionDetector")
    @patch("src.step5_engineering.CollisionDetect")
    @patch("src.step5_engineering.ElevationCalc")
    def test_compute_step3_basic(
        self, mock_elev_cls, mock_coll_cls, mock_axis_cls, mock_mep_cls
    ):
        mock_elev = MagicMock()
        mock_elev.run_all_checks.return_value = {
            "beam_dimensions": [],
            "summary": {"beam_count": 5, "slab_count": 3},
        }
        mock_elev_cls.return_value = mock_elev

        mock_coll = MagicMock()
        mock_coll.run_all_checks.return_value = {
            "summary": {"total_issues": 2},
        }
        mock_coll_cls.return_value = mock_coll

        mock_axis = MagicMock()
        mock_axis.run_all_checks.return_value = {"issues": []}
        mock_axis_cls.return_value = mock_axis

        mock_mep = MagicMock()
        mock_mep.run_all_checks.return_value = {
            "summary": {"pipeline_count": 8, "scheme_feasible": True},
        }
        mock_mep_cls.return_value = mock_mep

        mock_loader = MagicMock()
        mock_rules_config = {}

        with patch("src.step5_engineering.Path") as mock_path_cls:
            mock_path_instance = MagicMock()
            mock_path_instance.parent = MagicMock()
            mock_path_instance.parent.glob.return_value = []
            mock_path_cls.return_value = mock_path_instance

            result = _compute_step3(mock_loader, mock_rules_config)

        assert "elevation_results" in result
        assert "collision_results" in result
        assert "mep_results" in result
        assert "geometry_results" in result
        assert result["elevation_results"]["summary"]["beam_count"] == 5
        assert result["collision_results"]["summary"]["total_issues"] == 2
        assert result["mep_results"]["summary"]["pipeline_count"] == 8
        assert result["geometry_results"]["enabled"] is False
        assert "axis_collision" in result["collision_results"]


class TestComputeStep4:
    @patch("src.step5_engineering.CrossDiscipline")
    def test_compute_step4_success(self, mock_cross_cls):
        mock_cross = MagicMock()
        mock_cross.run_all_checks.return_value = {"issues": []}
        mock_cross.get_statistics.return_value = {
            "compliant": 8,
            "need_verify": 2,
            "non_compliant": 1,
        }
        mock_cross.deep_check.return_value = [
            {"check_name": "标高比对", "status": "一致"},
        ]
        mock_cross_cls.return_value = mock_cross

        mock_loader = MagicMock()
        mock_rules_config = {}

        result = _compute_step4(mock_loader, mock_rules_config)

        assert result["cross_results"] == {"issues": []}
        assert result["cross_stats"]["compliant"] == 8
        assert len(result["deep_cross_results"]) == 1
        mock_cross.run_all_checks.assert_called_once()
        mock_cross.get_statistics.assert_called_once()
        mock_cross.deep_check.assert_called_once()

    @patch("src.step5_engineering.CrossDiscipline")
    def test_compute_step4_with_deep_results(self, mock_cross_cls):
        mock_cross = MagicMock()
        mock_cross.run_all_checks.return_value = {
            "issues": [{"id": 1, "status": "不一致"}],
        }
        mock_cross.get_statistics.return_value = {
            "compliant": 5,
            "need_verify": 1,
            "non_compliant": 3,
        }
        mock_cross.deep_check.return_value = [
            {"check_name": "标高比对", "status": "不一致"},
            {"check_name": "轴线比对", "status": "一致"},
            {"check_name": "管径比对", "status": "待核实"},
            {"check_name": "设备定位", "status": "一致"},
            {"check_name": "预留洞口", "status": "不一致"},
            {"check_name": "荷载校核", "status": "一致"},
        ]
        mock_cross_cls.return_value = mock_cross

        mock_loader = MagicMock()
        mock_rules_config = {}

        result = _compute_step4(mock_loader, mock_rules_config)

        assert len(result["deep_cross_results"]) == 6
        assert result["cross_stats"]["non_compliant"] == 3


class TestParseArgs:
    def test_default_args(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["step5_engineering.py"])
        args = parse_args()
        assert args.json_dir == os.environ.get("PIPELINE_JSON_DIR", "./json_data")
        assert args.output_dir == os.environ.get("PIPELINE_OUTPUT_DIR", "./output")

    def test_custom_json_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["step5_engineering.py", "--json-dir", "/tmp/jsons"])
        args = parse_args()
        assert args.json_dir == "/tmp/jsons"

    def test_custom_output_dir(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["step5_engineering.py", "--output-dir", "/tmp/output"])
        args = parse_args()
        assert args.output_dir == "/tmp/output"

    def test_both_dirs(self, monkeypatch):
        monkeypatch.setattr(
            sys, "argv",
            ["step5_engineering.py", "--json-dir", "/data/jsons", "--output-dir", "/data/output"],
        )
        args = parse_args()
        assert args.json_dir == "/data/jsons"
        assert args.output_dir == "/data/output"
