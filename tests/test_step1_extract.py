# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.step1_extract import (
    infer_discipline,
    infer_building,
    clean_text,
    extract_elevations,
)


class TestInferDiscipline:
    def test_architectural(self):
        assert infer_discipline("建筑平面图.dxf") == "建筑"
        assert infer_discipline("总平面图.dxf") == "建筑"
        assert infer_discipline("门窗大样.dxf") == "建筑"

    def test_structural(self):
        assert infer_discipline("结构梁配筋图.dxf") == "结构"
        assert infer_discipline("柱配筋图.dxf") == "结构"

    def test_hvac(self):
        assert infer_discipline("空调风管图.dxf") == "暖通"

    def test_plumbing(self):
        assert infer_discipline("消防喷淋图.dxf") == "给排水"

    def test_electrical(self):
        assert infer_discipline("电气照明图.dxf") == "电气"
        assert infer_discipline("配电系统图.dxf") == "电气"

    def test_fire(self):
        assert infer_discipline("消防报警图.dxf") == "消防"

    def test_unknown(self):
        assert infer_discipline("xxx.dxf") == "未知"
        assert infer_discipline("") == "未知"


class TestInferBuilding:
    def test_workshop(self):
        assert infer_building("1号车间建筑图.dxf") == "车间"

    def test_complex(self):
        assert infer_building("综合楼结构图.dxf") == "综合楼"

    def test_dormitory(self):
        assert infer_building("宿舍给排水图.dxf") == "宿舍"

    def test_basement(self):
        assert infer_building("地下室电气图.dxf") == "地下室"

    def test_unknown(self):
        assert infer_building("xxx.dxf") == "未分类"


class TestCleanText:
    def test_normal_text(self):
        assert clean_text("卧室净高2.4m") == "卧室净高2.4m"

    def test_empty_text(self):
        result = clean_text("")
        assert result == "" or result is None

    def test_whitespace(self):
        assert clean_text("  卧室净高  ") == "卧室净高"

    def test_mtext_format(self):
        result = clean_text("卧室{\\fArial|b1|i0|c134|p2;净高}2.4m")
        assert "净高" in result
        assert "2.4m" in result

    def test_pure_number(self):
        result = clean_text("12345")
        assert result == "" or result is None

    def test_pure_dot(self):
        result = clean_text("...")
        assert result == "" or result is None


class TestExtractElevations:
    def test_normal_elevation(self):
        texts = ["标高±0.000", "层高3.600m", "净高2.4m"]
        result = extract_elevations(texts)
        assert len(result) >= 2

    def test_empty_list(self):
        result = extract_elevations([])
        assert result == []

    def test_no_elevation(self):
        texts = ["卧室", "客厅", "厨房"]
        result = extract_elevations(texts)
        assert len(result) == 0
