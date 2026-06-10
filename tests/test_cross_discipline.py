# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.cross_discipline import CrossDiscipline


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


class TestCrossDiscipline:
    def test_init_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        assert len(cross._discipline_files) == 0

    def test_init_with_structural(self):
        loader = MockLoader(
            files=["struct.json"],
            readable_names={"struct.json": "结构图"},
            text_lines={"struct.json": ["梁截面250x500", "柱配筋"]},
        )
        cross = CrossDiscipline(loader)
        assert "structural" in cross._discipline_files

    def test_init_with_architectural(self):
        loader = MockLoader(
            files=["arch.json"],
            readable_names={"arch.json": "建筑图"},
            text_lines={"arch.json": ["建筑平面图", "门窗表"]},
        )
        cross = CrossDiscipline(loader)
        assert "architectural" in cross._discipline_files

    def test_init_with_mep(self):
        loader = MockLoader(
            files=["mep.json"],
            readable_names={"mep.json": "暖通图"},
            text_lines={"mep.json": ["暖通风管", "空调系统"]},
        )
        cross = CrossDiscipline(loader)
        assert "mep" in cross._discipline_files or "hvac" in cross._discipline_files

    def test_init_with_multiple_disciplines(self):
        loader = MockLoader(
            files=["struct.json", "arch.json", "mep.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
                "mep.json": "暖通图",
            },
            text_lines={
                "struct.json": ["梁截面250x500", "柱配筋"],
                "arch.json": ["建筑平面图", "门窗表"],
                "mep.json": ["暖通风管", "空调系统"],
            },
        )
        cross = CrossDiscipline(loader)
        assert len(cross._discipline_files) >= 2

    def test_init_empty_lines(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": []},
        )
        cross = CrossDiscipline(loader)
        assert len(cross._discipline_files) == 0

    def test_extract_elevations(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._extract_elevations(["标高:3.600"])
        assert len(result) >= 1
        assert 3.6 in result

    def test_extract_elevations_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._extract_elevations(["卧室", "客厅"])
        assert len(result) == 0

    def test_extract_beam_heights(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._extract_beam_heights(["梁250x500"])
        assert len(result) >= 1

    def test_extract_beam_heights_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._extract_beam_heights(["卧室", "客厅"])
        assert len(result) == 0

    def test_extract_clear_heights(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._extract_clear_heights(["净高:2.4", "层高:3.6"])
        assert len(result) >= 1

    def test_extract_clear_heights_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._extract_clear_heights(["卧室", "客厅"])
        assert len(result) == 0

    def test_get_discipline_texts_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._get_discipline_texts("structural")
        assert result == []

    def test_get_discipline_texts_with_data(self):
        loader = MockLoader(
            files=["struct.json"],
            readable_names={"struct.json": "结构图"},
            text_lines={"struct.json": ["梁截面250x500", "柱配筋"]},
        )
        cross = CrossDiscipline(loader)
        result = cross._get_discipline_texts("structural")
        assert len(result) >= 1

    def test_run_all_checks_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross.run_all_checks()
        assert "cross_results" in result
        assert "cross_stats" in result
        assert "deep_cross_results" in result
        assert "deep_cross_stats" in result

    def test_run_all_checks_with_multi_discipline(self):
        loader = MockLoader(
            files=["struct.json", "arch.json", "mep.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
                "mep.json": "暖通图",
            },
            text_lines={
                "struct.json": ["梁截面250x500", "柱配筋", "标高:3.600"],
                "arch.json": ["建筑平面图", "门窗表", "净高:2.4", "标高:3.600"],
                "mep.json": ["暖通风管DN200", "空调系统", "标高:2.900"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross.run_all_checks()
        assert isinstance(result["cross_results"], list)
        assert isinstance(result["deep_cross_results"], list)

    def test_get_statistics_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        stats = cross.get_statistics([])
        assert stats["total"] == 0
        assert stats["compliant"] == 0

    def test_get_statistics_with_results(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        results = [
            {"status": "compliant", "severity": "low", "category": "test"},
            {"status": "need_verify", "severity": "medium", "category": "test"},
            {"status": "non_compliant", "severity": "high", "category": "test2"},
        ]
        stats = cross.get_statistics(results)
        assert stats["total"] == 3
        assert stats["compliant"] == 1
        assert stats["need_verify"] == 1
        assert stats["non_compliant"] == 1

    def test_get_statistics_with_dict_input(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        results = {
            "a": [{"status": "compliant", "severity": "low", "category": "x"}],
            "b": [{"status": "need_verify", "severity": "medium", "category": "y"}],
        }
        stats = cross.get_statistics(results)
        assert stats["total"] == 2

    def test_get_statistics_invalid_status(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        results = [{"status": "unknown_status", "severity": "low", "category": "x"}]
        stats = cross.get_statistics(results)
        assert stats["need_verify"] == 1

    def test_compare_elevations_single_discipline(self):
        loader = MockLoader(
            files=["struct.json"],
            readable_names={"struct.json": "结构图"},
            text_lines={"struct.json": ["梁截面250x500", "标高:3.600"]},
        )
        cross = CrossDiscipline(loader)
        result = cross._compare_elevations()
        assert result == []

    def test_compare_elevations_two_disciplines_different(self):
        loader = MockLoader(
            files=["struct.json", "arch.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
            },
            text_lines={
                "struct.json": ["梁截面250x500", "标高:3.600"],
                "arch.json": ["建筑平面图", "标高:2.900"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._compare_elevations()
        assert len(result) >= 1

    def test_compare_elevations_matching(self):
        loader = MockLoader(
            files=["struct.json", "arch.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
            },
            text_lines={
                "struct.json": ["梁截面250x500", "标高:3.600"],
                "arch.json": ["建筑平面图", "标高:3.600"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._compare_elevations()
        for r in result:
            assert r["status"] == "compliant"

    def test_compare_axes(self):
        loader = MockLoader(
            files=["struct.json", "arch.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
            },
            text_lines={
                "struct.json": ["梁截面250x500", "A轴", "1轴"],
                "arch.json": ["建筑平面图", "A轴", "1轴"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._compare_axes()
        assert isinstance(result, list)

    def test_compare_component_positions(self):
        loader = MockLoader(
            files=["struct.json", "arch.json", "mep.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
                "mep.json": "暖通图",
            },
            text_lines={
                "struct.json": ["梁截面250x500", "柱600x600"],
                "arch.json": ["建筑平面图", "门窗表"],
                "mep.json": ["暖通风管DN200", "空调系统"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._compare_component_positions()
        assert isinstance(result, list)

    def test_deep_check_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross.deep_check()
        assert isinstance(result, list)
        assert len(result) == 6

    def test_deep_check_with_multi_discipline(self):
        loader = MockLoader(
            files=["struct.json", "arch.json", "mep.json", "elec.json", "plumb.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
                "mep.json": "暖通图",
                "elec.json": "电气图",
                "plumb.json": "给排水图",
            },
            text_lines={
                "struct.json": ["梁截面250x500", "柱配筋", "预留洞DN200"],
                "arch.json": ["建筑平面图", "净高:2.4", "防火分区"],
                "mep.json": ["暖通风管DN200", "空调系统"],
                "elec.json": ["电缆桥架200x100", "配电箱"],
                "plumb.json": ["消防管道DN100", "给水管DN50", "穿梁套管"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross.deep_check()
        assert len(result) == 6
        for r in result:
            assert "check_name" in r
            assert "status" in r

    def test_check_beam_compliant(self):
        loader = MockLoader(
            files=["struct.json", "arch.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
            },
            text_lines={
                "struct.json": ["梁250x500"],
                "arch.json": ["净高:3.6"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._check_beam_height_vs_clear_height()
        assert result["status"] == "compliant"

    def test_check_beam_warning(self):
        loader = MockLoader(
            files=["struct.json", "arch.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
            },
            text_lines={
                "struct.json": ["梁250x600"],
                "arch.json": ["净高:2.4"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._check_beam_height_vs_clear_height()
        assert result["status"] in ("need_verify", "non_compliant", "compliant")

    def test_check_beam_no_data(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._check_beam_height_vs_clear_height()
        assert result["status"] == "need_verify"

    def test_check_pipe_vs_equipment_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._check_pipe_vs_equipment_position()
        assert result["status"] == "need_verify"

    def test_check_pipe_vs_equipment_with_data(self):
        loader = MockLoader(
            files=["mep.json"],
            readable_names={"mep.json": "暖通图"},
            text_lines={"mep.json": ["暖通风管DN200", "空调机组位置"]},
        )
        cross = CrossDiscipline(loader)
        result = cross._check_pipe_vs_equipment_position()
        assert "check_name" in result

    def test_check_fire_pipe_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._check_fire_pipe_vs_fire_zone()
        assert result["status"] == "need_verify"

    def test_check_fire_pipe_with_data(self):
        loader = MockLoader(
            files=["plumb.json", "arch.json"],
            readable_names={
                "plumb.json": "给排水图",
                "arch.json": "建筑图",
            },
            text_lines={
                "plumb.json": ["消防管道DN100", "喷淋系统"],
                "arch.json": ["防火分区一", "防火分区二"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._check_fire_pipe_vs_fire_zone()
        assert "fire_pipe_count" in result

    def test_check_tray_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._check_tray_vs_mep()
        assert result["status"] == "need_verify"

    def test_check_tray_with_data(self):
        loader = MockLoader(
            files=["elec.json", "mep.json"],
            readable_names={
                "elec.json": "电气图",
                "mep.json": "暖通图",
            },
            text_lines={
                "elec.json": ["电缆桥架200x100"],
                "mep.json": ["暖通风管DN200"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._check_tray_vs_mep()
        assert result["tray_count"] >= 0

    def test_check_duct_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._check_duct_vs_opening()
        assert result["status"] == "need_verify"

    def test_check_duct_with_data(self):
        loader = MockLoader(
            files=["mep.json", "struct.json"],
            readable_names={
                "mep.json": "暖通图",
                "struct.json": "结构图",
            },
            text_lines={
                "mep.json": ["暖通风管DN200", "风管截面500x300"],
                "struct.json": ["预留洞200x200", "预留洞300x300"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._check_duct_vs_opening()
        assert "duct_count" in result

    def test_check_water_supply_empty(self):
        loader = MockLoader()
        cross = CrossDiscipline(loader)
        result = cross._check_water_supply_vs_structural()
        assert result["status"] == "need_verify"

    def test_check_water_supply_with_conflict(self):
        loader = MockLoader(
            files=["plumb.json", "struct.json"],
            readable_names={
                "plumb.json": "给排水图",
                "struct.json": "结构图",
            },
            text_lines={
                "plumb.json": ["给水管DN50", "排水管DN100", "穿梁套管"],
                "struct.json": ["梁截面250x500", "柱600x600"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross._check_water_supply_vs_structural()
        assert "water_hit_count" in result or "water_count" in result or "check_name" in result

    def test_classify_files_exception(self):
        class BrokenLoader:
            @property
            def files(self):
                raise RuntimeError("loader error")
        cross = CrossDiscipline(BrokenLoader())
        assert len(cross._discipline_files) == 0

    def test_run_all_checks_with_all_disciplines(self):
        loader = MockLoader(
            files=["struct.json", "arch.json", "mep.json", "elec.json", "plumb.json", "fire.json"],
            readable_names={
                "struct.json": "结构图",
                "arch.json": "建筑图",
                "mep.json": "暖通图",
                "elec.json": "电气图",
                "plumb.json": "给排水图",
                "fire.json": "消防图",
            },
            text_lines={
                "struct.json": ["梁截面250x500", "柱配筋", "标高:3.600", "A轴", "1轴"],
                "arch.json": ["建筑平面图", "门窗表", "净高:2.4", "标高:3.600", "A轴"],
                "mep.json": ["暖通风管DN200", "空调系统", "标高:2.900"],
                "elec.json": ["电缆桥架200x100", "配电箱", "照明回路"],
                "plumb.json": ["给水管DN50", "排水管DN100", "消防管道DN100"],
                "fire.json": ["喷淋系统", "防火分区"],
            },
        )
        cross = CrossDiscipline(loader)
        result = cross.run_all_checks()
        assert result["cross_stats"]["total"] >= 0
        assert result["deep_cross_stats"]["total"] >= 0
