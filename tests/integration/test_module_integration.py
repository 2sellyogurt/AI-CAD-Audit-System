import json
import os
import sys
import tempfile

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def sample_json_dir():
    with tempfile.TemporaryDirectory() as tmp:
        sample_data = {
            "raw_texts": [
                "卧室净高2.4m",
                "层高2.8m",
                "板厚120mm",
                "梁250x500",
            ],
            "elevations": [
                {"value": 3.600, "text": "层高3.6m", "type": "层高"},
                {"value": -0.050, "text": "标高-0.05m", "type": "标高"},
            ],
            "metadata": {
                "source_file": "建筑-一层平面图.dxf",
                "discipline": "建筑",
                "building": "综合楼",
                "text_count": 4,
                "elevation_count": 2,
            },
        }
        filepath = os.path.join(tmp, "建筑-一层平面图_unified.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, ensure_ascii=False, indent=2)
        yield tmp


class TestJsonLoaderWithRuleChecker:
    def test_json_loader_with_rule_checker(self, sample_json_dir):
        from engine.json_loader import JsonLoader
        from engine.rule_checker import RuleChecker

        loader = JsonLoader(sample_json_dir)
        assert loader.get_file_count() == 1
        assert len(loader.files) == 1

        checker = RuleChecker(loader)
        config = checker.rules_config
        assert isinstance(config, dict)
        rules = checker.mandatory_rules
        assert isinstance(rules, list)
        if len(rules) > 0:
            assert "rule_id" in rules[0]


class TestJsonLoaderWithElevationCalc:
    def test_json_loader_with_elevation_calc(self, sample_json_dir):
        from engine.json_loader import JsonLoader
        from engine.elevation_calc import ElevationCalc

        loader = JsonLoader(sample_json_dir)
        assert loader.get_file_count() == 1

        calc = ElevationCalc(loader)
        results = calc.run_all_checks()
        assert isinstance(results, dict)
        assert "summary" in results


class TestInferFloor:
    def test_infer_floor_one_floor(self):
        from report.utils import infer_floor
        assert infer_floor("一层平面图") == "1F"

    def test_infer_floor_roof(self):
        from report.utils import infer_floor
        assert infer_floor("屋顶平面图") == "RF"

    def test_infer_floor_basement(self):
        from report.utils import infer_floor
        assert infer_floor("地下室平面图") == "B1"

    def test_infer_floor_basement_two(self):
        from report.utils import infer_floor
        assert infer_floor("地下二层平面图") == "B2"

    def test_infer_floor_empty(self):
        from report.utils import infer_floor
        assert infer_floor("") == ""

    def test_infer_floor_none(self):
        from report.utils import infer_floor
        assert infer_floor(None) == ""


class TestEngineAllImports:
    def test_json_loader(self):
        from engine.json_loader import JsonLoader
        assert JsonLoader is not None

    def test_rule_checker(self):
        from engine.rule_checker import RuleChecker
        assert RuleChecker is not None

    def test_elevation_calc(self):
        from engine.elevation_calc import ElevationCalc
        assert ElevationCalc is not None

    def test_collision_detect(self):
        from engine.collision_detect import CollisionDetect
        assert CollisionDetect is not None

    def test_axis_collision(self):
        from engine.axis_collision import AxisCollisionDetector
        assert AxisCollisionDetector is not None

    def test_mep_coordinator(self):
        from engine.mep_coordinator import MepCoordinator
        assert MepCoordinator is not None

    def test_cross_discipline(self):
        from engine.cross_discipline import CrossDiscipline
        assert CrossDiscipline is not None

    def test_engineering_analysis(self):
        from engine.engineering_analysis import EngineeringAnalyzer
        assert EngineeringAnalyzer is not None

    def test_experience_matcher(self):
        from engine.experience_matcher import ExperienceMatcher
        assert ExperienceMatcher is not None

    def test_layer_mapper(self):
        from engine.layer_mapper import LayerMapper
        assert LayerMapper is not None

    def test_geometry_extractor(self):
        from engine.geometry_extractor import GeometryExtractor
        assert GeometryExtractor is not None

    def test_geometry_analyzer(self):
        from engine.geometry_analyzer import GeometryAnalyzer
        assert GeometryAnalyzer is not None


class TestReportAllImports:
    def test_report_utils(self):
        from report.utils import infer_floor
        assert callable(infer_floor)

    def test_meeting_list(self):
        from report.meeting_list import MeetingList
        assert MeetingList is not None

    def test_report_generator(self):
        from report.report_generator_v50 import generate_all_reports
        assert callable(generate_all_reports)


class TestConfigFilesExist:
    def test_rules_json_exists(self):
        path = os.path.join(PROJECT_ROOT, "config", "rules.json")
        assert os.path.exists(path), f"Missing config file: {path}"

    def test_rules_json_valid(self):
        path = os.path.join(PROJECT_ROOT, "config", "rules.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert "mandatory_rules" in data or "rules" in data

    def test_project_config_exists(self):
        path = os.path.join(PROJECT_ROOT, "config", "project_config.json")
        assert os.path.exists(path), f"Missing config file: {path}"

    def test_project_config_valid(self):
        path = os.path.join(PROJECT_ROOT, "config", "project_config.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_normative_database_exists(self):
        path = os.path.join(PROJECT_ROOT, "config", "normative_database.json")
        assert os.path.exists(path), f"Missing config file: {path}"

    def test_normative_database_valid(self):
        path = os.path.join(PROJECT_ROOT, "config", "normative_database.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)


class TestFullDirectoryStructure:
    def test_src_dir_exists(self):
        assert os.path.isdir(os.path.join(PROJECT_ROOT, "src"))

    def test_engine_dir_exists(self):
        assert os.path.isdir(os.path.join(PROJECT_ROOT, "engine"))

    def test_report_dir_exists(self):
        assert os.path.isdir(os.path.join(PROJECT_ROOT, "report"))

    def test_config_dir_exists(self):
        assert os.path.isdir(os.path.join(PROJECT_ROOT, "config"))

    def test_docs_dir_exists(self):
        assert os.path.isdir(os.path.join(PROJECT_ROOT, "docs"))

    def test_all_step_files_exist(self):
        src = os.path.join(PROJECT_ROOT, "src")
        for fname in ["master.py", "step1_extract.py", "step2_compliance.py",
                       "step3_defect.py", "step4_cross_check.py", "step5_engineering.py"]:
            assert os.path.isfile(os.path.join(src, fname)), f"Missing: src/{fname}"

    def test_all_engine_files_exist(self):
        eng = os.path.join(PROJECT_ROOT, "engine")
        for fname in ["__init__.py", "json_loader.py", "rule_checker.py", "elevation_calc.py",
                       "collision_detect.py", "axis_collision.py", "mep_coordinator.py",
                       "cross_discipline.py", "engineering_analysis.py", "experience_matcher.py",
                       "layer_mapper.py", "geometry_extractor.py", "geometry_analyzer.py"]:
            assert os.path.isfile(os.path.join(eng, fname)), f"Missing: engine/{fname}"

    def test_all_report_files_exist(self):
        rep = os.path.join(PROJECT_ROOT, "report")
        for fname in ["utils.py", "meeting_list.py", "report_generator_v50.py"]:
            assert os.path.isfile(os.path.join(rep, fname)), f"Missing: report/{fname}"
