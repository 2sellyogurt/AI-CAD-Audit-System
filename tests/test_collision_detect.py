# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.collision_detect import CollisionDetect


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


class TestCollisionDetect:
    def test_init_empty(self):
        loader = MockLoader()
        detect = CollisionDetect(loader)
        assert detect._all_texts == []

    def test_init_with_data(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["桥架与风管碰撞", "管线间距不足"]},
        )
        detect = CollisionDetect(loader)
        assert len(detect._all_texts) == 1

    def test_collect_texts(self):
        loader = MockLoader(
            files=["file1.json", "file2.json"],
            readable_names={"file1.json": "文件1", "file2.json": "文件2"},
            text_lines={
                "file1.json": ["桥架与风管碰撞"],
                "file2.json": ["管线间距不足"],
            },
        )
        detect = CollisionDetect(loader)
        assert len(detect._all_texts) == 2

    def test_empty_lines(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": []},
        )
        detect = CollisionDetect(loader)
        assert len(detect._all_texts) == 0

    def test_no_files(self):
        loader = MockLoader()
        detect = CollisionDetect(loader)
        assert len(detect._all_texts) == 0

    def test_multiple_files_with_content(self):
        loader = MockLoader(
            files=["file1.json", "file2.json", "file3.json"],
            readable_names={
                "file1.json": "建筑图",
                "file2.json": "结构图",
                "file3.json": "暖通图",
            },
            text_lines={
                "file1.json": ["桥架与风管碰撞", "管线间距不足"],
                "file2.json": ["次梁阻挡管线", "梁底空间不足"],
                "file3.json": ["风管与喷淋间距不足"],
            },
        )
        detect = CollisionDetect(loader)
        assert len(detect._all_texts) == 3

    def test_find_line_number_found(self):
        loader = MockLoader()
        detect = CollisionDetect(loader)
        lines = ["第一行", "桥架与风管碰撞位置", "第三行"]
        result = detect._find_line_number(lines, "桥架与风管碰撞位置")
        assert result == "2"

    def test_find_line_number_not_found(self):
        loader = MockLoader()
        detect = CollisionDetect(loader)
        lines = ["第一行", "第二行"]
        result = detect._find_line_number(lines, "不存在的内容")
        assert result == "0"

    def test_match_keywords_on_texts(self):
        loader = MockLoader(
            files=["mep.json"],
            readable_names={"mep.json": "暖通图"},
            text_lines={"mep.json": ["暖通风管DN200", "电缆桥架200x100", "碰撞检测"]},
        )
        detect = CollisionDetect(loader)
        results = detect._match_keywords_on_texts(["桥架", "风管"])
        assert len(results) >= 1
        assert "matched_keyword" in results[0]

    def test_match_keywords_no_match(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["普通文本内容"]},
        )
        detect = CollisionDetect(loader)
        results = detect._match_keywords_on_texts(["桥架", "风管"])
        assert len(results) == 0

    def test_run_all_checks_empty(self):
        loader = MockLoader()
        detect = CollisionDetect(loader)
        result = detect.run_all_checks([])
        assert "summary" in result
        assert result["summary"]["total_issues"] == 0

    def test_run_all_checks_with_beam_data(self):
        loader = MockLoader(
            files=["struct.json"],
            readable_names={"struct.json": "结构图"},
            text_lines={"struct.json": ["梁250x500", "柱600x600"]},
        )
        detect = CollisionDetect(loader)
        beam_dims = [{"beam_height": 500, "beam_width": 250, "file": "结构图", "line": "1"}]
        result = detect.run_all_checks(beam_dims)
        assert "summary" in result
        assert "beam_interference_issues" in result

    def test_run_all_checks_with_mep_data(self):
        loader = MockLoader(
            files=["mep.json", "elec.json"],
            readable_names={
                "mep.json": "暖通图",
                "elec.json": "电气图",
            },
            text_lines={
                "mep.json": ["暖通风管DN200", "空调系统", "风管截面500x300"],
                "elec.json": ["电缆桥架200x100", "配电箱"],
            },
        )
        detect = CollisionDetect(loader)
        result = detect.run_all_checks([])
        assert result["summary"]["total_issues"] >= 0

    def test_detect_tray_collisions_with_data(self):
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
        detect = CollisionDetect(loader)
        result = detect._detect_tray_collisions()
        assert isinstance(result, list)

    def test_detect_beam_interference_with_data(self):
        loader = MockLoader(
            files=["struct.json"],
            readable_names={"struct.json": "结构图"},
            text_lines={"struct.json": ["梁250x500", "预留洞200x200"]},
        )
        detect = CollisionDetect(loader)
        beam_dims = [{"beam_height": 500, "beam_width": 250, "file": "结构图", "line": "1"}]
        result = detect._detect_beam_interference(beam_dims)
        assert isinstance(result, list)

    def test_detect_beam_interference_empty(self):
        loader = MockLoader()
        detect = CollisionDetect(loader)
        result = detect._detect_beam_interference([])
        assert result == []

    def test_detect_pipe_spacing(self):
        loader = MockLoader(
            files=["mep.json"],
            readable_names={"mep.json": "暖通图"},
            text_lines={"mep.json": ["暖通风管DN200", "管线间距"]},
        )
        detect = CollisionDetect(loader)
        result = detect._detect_pipe_spacing_issues()
        assert isinstance(result, list)

    def test_detect_ceiling_space(self):
        loader = MockLoader(
            files=["mep.json"],
            readable_names={"mep.json": "暖通图"},
            text_lines={"mep.json": ["暖通风管DN200", "吊顶空间不足"]},
        )
        detect = CollisionDetect(loader)
        result = detect._detect_ceiling_space_issues()
        assert isinstance(result, list)

    def test_detect_column_pipe(self):
        loader = MockLoader(
            files=["struct.json"],
            readable_names={"struct.json": "结构图"},
            text_lines={"struct.json": ["柱600x600", "管线穿柱"]},
        )
        detect = CollisionDetect(loader)
        result = detect._detect_column_pipe_issues()
        assert isinstance(result, list)

    def test_detect_duct_sprinkler(self):
        loader = MockLoader(
            files=["mep.json"],
            readable_names={"mep.json": "暖通图"},
            text_lines={"mep.json": ["暖通风管DN200", "喷淋头"]},
        )
        detect = CollisionDetect(loader)
        result = detect._detect_duct_sprinkler_issues()
        assert isinstance(result, list)

    def test_detect_elec_fire_gas(self):
        loader = MockLoader(
            files=["elec.json"],
            readable_names={"elec.json": "电气图"},
            text_lines={"elec.json": ["电缆桥架200x100", "燃气管道"]},
        )
        detect = CollisionDetect(loader)
        result = detect._detect_elec_fire_gas_issues()
        assert isinstance(result, list)

    def test_detect_tray_detail(self):
        loader = MockLoader(
            files=["elec.json"],
            readable_names={"elec.json": "电气图"},
            text_lines={"elec.json": ["电缆桥架200x100", "桥架弯通"]},
        )
        detect = CollisionDetect(loader)
        result = detect._detect_tray_detail_issues()
        assert isinstance(result, list)

    def test_run_all_checks_exception_handling(self):
        class BrokenLoader:
            @property
            def files(self):
                raise RuntimeError("broken")
        detect = CollisionDetect(BrokenLoader())
        result = detect.run_all_checks([])
        assert result["summary"]["total_issues"] == 0
