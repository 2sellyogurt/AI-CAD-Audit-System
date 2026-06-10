# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.elevation_calc import ElevationCalc


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


class TestElevationCalc:
    def test_init_empty(self):
        loader = MockLoader()
        calc = ElevationCalc(loader)
        assert calc._all_texts == []

    def test_init_with_data(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["标高±0.000", "层高3.600m"]},
        )
        calc = ElevationCalc(loader)
        assert len(calc._all_texts) == 1

    def test_extract_elevations(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["标高±0.000", "层高3.600m", "净高2.4m"]},
        )
        calc = ElevationCalc(loader)
        result = calc._extract_elevations()
        assert len(result) >= 2

    def test_extract_beam_dimensions(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["KL1 250x500", "梁截面=300x600"]},
        )
        calc = ElevationCalc(loader)
        result = calc._extract_beam_dimensions()
        assert len(result) >= 1

    def test_extract_slab_thicknesses(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["板厚=120mm", "楼板厚度:150"]},
        )
        calc = ElevationCalc(loader)
        result = calc._extract_slab_thicknesses()
        assert len(result) >= 1

    def test_extract_elevations_empty(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["卧室", "客厅"]},
        )
        calc = ElevationCalc(loader)
        result = calc._extract_elevations()
        assert len(result) == 0

    def test_extract_beam_dimensions_empty(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["卧室", "客厅"]},
        )
        calc = ElevationCalc(loader)
        result = calc._extract_beam_dimensions()
        assert len(result) == 0

    def test_extract_slab_thicknesses_empty(self):
        loader = MockLoader(
            files=["test.json"],
            readable_names={"test.json": "测试文件"},
            text_lines={"test.json": ["卧室", "客厅"]},
        )
        calc = ElevationCalc(loader)
        result = calc._extract_slab_thicknesses()
        assert len(result) == 0

    def test_multiple_files(self):
        loader = MockLoader(
            files=["file1.json", "file2.json"],
            readable_names={"file1.json": "文件1", "file2.json": "文件2"},
            text_lines={
                "file1.json": ["标高±0.000"],
                "file2.json": ["层高3.600m"],
            },
        )
        calc = ElevationCalc(loader)
        assert len(calc._all_texts) == 2
        result = calc._extract_elevations()
        assert len(result) >= 2
