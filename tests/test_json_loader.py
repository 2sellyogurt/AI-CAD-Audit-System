# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.json_loader import JsonLoader


def test_init_empty_dir(tmp_path):
    loader = JsonLoader(str(tmp_path))
    assert loader.files == []
    assert loader.get_file_count() == 0


def test_init_normal_json(tmp_path):
    content = {
        "raw_texts": ["卧室净高2.4m", "层高2.8m"],
        "elevations": ["0.000", "3.600"],
        "metadata": {
            "source_file": "建筑平面图.dwg",
            "discipline": "建筑",
            "building": "1号楼",
        },
    }
    file_path = tmp_path / "abc_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    assert len(loader.files) == 1
    assert loader.files[0] == "abc_unified.json"
    assert loader.get_file_count() == 1
    lines = loader.get_text_lines_by_file("abc_unified.json")
    assert "卧室净高2.4m" in lines
    assert "层高2.8m" in lines


def test_init_gbk_encoding(tmp_path):
    content = {
        "raw_texts": ["\u5ba4\u5185\u51c0\u9ad8", "\u5c42\u9ad82.8m"],
        "elevations": [],
        "metadata": {},
    }
    json_str = json.dumps(content, ensure_ascii=False)
    file_path = tmp_path / "gbk_file_unified.json"
    file_path.write_text(json_str, encoding="gbk")
    loader = JsonLoader(str(tmp_path))
    assert len(loader.files) == 1
    lines = loader.get_text_lines_by_file("gbk_file_unified.json")
    assert len(lines) == 2


def test_init_bom_json(tmp_path):
    content = {
        "raw_texts": ["BOM\u6d4b\u8bd5"],
        "elevations": [],
        "metadata": {},
    }
    json_str = json.dumps(content, ensure_ascii=False)
    file_path = tmp_path / "bom_file_unified.json"
    with open(str(file_path), "wb") as f:
        f.write(b"\xef\xbb\xbf")
        f.write(json_str.encode("utf-8"))
    loader = JsonLoader(str(tmp_path))
    assert len(loader.files) == 1
    lines = loader.get_text_lines_by_file("bom_file_unified.json")
    assert "BOM\u6d4b\u8bd5" in lines


def test_init_invalid_json(tmp_path):
    file_path = tmp_path / "broken_unified.json"
    file_path.write_text("{broken json content [[[", encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    assert len(loader.files) == 1
    lines = loader.get_text_lines_by_file("broken_unified.json")
    assert lines == []


def test_init_nonexistent_dir():
    loader = JsonLoader("/nonexistent/path/that/does/not/exist")
    assert loader.files == []
    assert loader.get_file_count() == 0


def test_get_readable_name(tmp_path):
    content = {"raw_texts": [], "elevations": [], "metadata": {}}
    json_str = json.dumps(content, ensure_ascii=False)
    file_path = tmp_path / "a1b2c3d4-e5f6-7890-abcd-ef1234567890_\u5efa\u7b51\u5e73\u9762\u56fe_unified.json"
    file_path.write_text(json_str, encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    fn = loader.files[0]
    readable = loader.get_readable_name(fn)
    assert readable == "\u5efa\u7b51\u5e73\u9762\u56fe"
    readable2 = loader.get_readable_name("unknown.json")
    assert readable2 == "unknown.json"
    readable3 = loader.get_readable_name("some_data_unified.json")
    assert readable3 == "some_data"


def test_get_text_lines_by_file(tmp_path):
    content = {
        "raw_texts": [
            "\u7b2c\u4e00\u884c\u6587\u672c",
            "\u7b2c\u4e8c\u884c\u6587\u672c",
            {"text": "\u5b57\u5178\u5f62\u5f0f\u6587\u672c"},
            {"content": "\u53e6\u4e00\u79cd\u5b57\u5178"},
            12345,
        ],
        "elevations": [],
        "metadata": {},
    }
    json_str = json.dumps(content, ensure_ascii=False)
    file_path = tmp_path / "text_lines_unified.json"
    file_path.write_text(json_str, encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    lines = loader.get_text_lines_by_file("text_lines_unified.json")
    assert len(lines) == 5
    assert "\u7b2c\u4e00\u884c\u6587\u672c" in lines
    assert "\u7b2c\u4e8c\u884c\u6587\u672c" in lines
    assert "\u5b57\u5178\u5f62\u5f0f\u6587\u672c" in lines
    assert "\u53e6\u4e00\u79cd\u5b57\u5178" in lines
    assert "12345" in lines


def test_get_file_count(tmp_path):
    content = {"raw_texts": [], "elevations": [], "metadata": {}}
    json_str = json.dumps(content, ensure_ascii=False)
    for i in range(5):
        file_path = tmp_path / f"file_{i}_unified.json"
        file_path.write_text(json_str, encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    assert loader.get_file_count() == 5
    assert len(loader.files) == 5


def test_raw_texts_non_list(tmp_path):
    content = {
        "raw_texts": "\u8fd9\u4e0d\u662f\u5217\u8868\u800c\u662f\u5b57\u7b26\u4e32",
        "elevations": [],
        "metadata": {},
    }
    json_str = json.dumps(content, ensure_ascii=False)
    file_path = tmp_path / "non_list_unified.json"
    file_path.write_text(json_str, encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    lines = loader.get_text_lines_by_file("non_list_unified.json")
    assert lines == []


def test_get_professional_data(tmp_path):
    content = {
        "raw_texts": ["测试"],
        "elevations": [],
        "metadata": {},
        "professional_data": {"discipline": "建筑", "building": "1号楼"},
    }
    file_path = tmp_path / "prof_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    pd = loader.get_professional_data("prof_unified.json")
    assert pd["discipline"] == "建筑"
    assert pd["building"] == "1号楼"


def test_get_professional_data_missing(tmp_path):
    content = {"raw_texts": ["测试"], "elevations": [], "metadata": {}}
    file_path = tmp_path / "no_prof_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    pd = loader.get_professional_data("no_prof_unified.json")
    assert pd == {}


def test_ensure_professional_data(tmp_path):
    content = {
        "raw_texts": ["测试"],
        "elevations": [],
        "metadata": {"discipline": "结构", "building": "2号楼", "source_file": "结构图.dwg"},
    }
    file_path = tmp_path / "ensure_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    loader.ensure_professional_data()
    pd = loader.get_professional_data("ensure_unified.json")
    assert pd.get("discipline") == "结构"
    assert pd.get("building") == "2号楼"


def test_ensure_professional_data_infer(tmp_path):
    content = {"raw_texts": ["测试"], "elevations": [], "metadata": {}}
    file_path = tmp_path / "暖通空调图_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    loader.ensure_professional_data()
    pd = loader.get_professional_data("暖通空调图_unified.json")
    assert pd.get("discipline") == "暖通"


def test_infer_discipline_arch(tmp_path):
    loader = JsonLoader(str(tmp_path))
    assert loader._infer_discipline("建筑平面图_unified.json") == "建筑"
    assert loader._infer_discipline("arch_plan_unified.json") == "建筑"


def test_infer_discipline_struct(tmp_path):
    loader = JsonLoader(str(tmp_path))
    assert loader._infer_discipline("结构梁配筋_unified.json") == "结构"
    assert loader._infer_discipline("struct_beam_unified.json") == "结构"


def test_infer_discipline_mep(tmp_path):
    loader = JsonLoader(str(tmp_path))
    assert loader._infer_discipline("暖通通风_unified.json") == "暖通"
    assert loader._infer_discipline("hvac_duct_unified.json") == "暖通"


def test_infer_discipline_plumb(tmp_path):
    loader = JsonLoader(str(tmp_path))
    assert loader._infer_discipline("给排水管道_unified.json") == "给排水"
    assert loader._infer_discipline("plumb_pipe_unified.json") == "给排水"


def test_infer_discipline_elec(tmp_path):
    loader = JsonLoader(str(tmp_path))
    assert loader._infer_discipline("电气照明_unified.json") == "电气"
    assert loader._infer_discipline("elec_light_unified.json") == "电气"


def test_infer_discipline_fire(tmp_path):
    loader = JsonLoader(str(tmp_path))
    assert loader._infer_discipline("消防喷淋_unified.json") == "消防"
    assert loader._infer_discipline("fire_sprinkler_unified.json") == "消防"


def test_infer_discipline_unknown(tmp_path):
    loader = JsonLoader(str(tmp_path))
    assert loader._infer_discipline("random_file_unified.json") == "未分类"


def test_get_metadata_by_file(tmp_path):
    content = {
        "raw_texts": ["测试"],
        "elevations": [],
        "metadata": {"discipline": "建筑", "building": "1号楼"},
    }
    file_path = tmp_path / "meta_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    meta = loader.get_metadata_by_file("meta_unified.json")
    assert meta["discipline"] == "建筑"
    assert meta["building"] == "1号楼"


def test_get_full_text_by_file(tmp_path):
    content = {
        "raw_texts": ["第一行", "第二行", "第三行"],
        "elevations": [],
        "metadata": {},
    }
    file_path = tmp_path / "fulltext_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    full = loader.get_full_text_by_file("fulltext_unified.json")
    assert "第一行" in full
    assert "第二行" in full
    assert "第三行" in full


def test_get_dedup_engine(tmp_path):
    content = {
        "raw_texts": ["测试内容"],
        "elevations": [],
        "metadata": {"discipline": "建筑"},
    }
    file_path = tmp_path / "dedup_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    engine = loader.get_dedup_engine()
    assert engine is not None
    engine2 = loader.get_dedup_engine()
    assert engine is engine2


def test_get_dedup_summary(tmp_path):
    content = {
        "raw_texts": ["测试内容"],
        "elevations": [],
        "metadata": {"discipline": "建筑"},
    }
    file_path = tmp_path / "summary_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    summary = loader.get_dedup_summary()
    assert "total_files" in summary


def test_get_unique_file_keys(tmp_path):
    content = {
        "raw_texts": ["测试内容"],
        "elevations": [],
        "metadata": {"discipline": "建筑"},
    }
    file_path = tmp_path / "unique_unified.json"
    file_path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    loader = JsonLoader(str(tmp_path))
    keys = loader.get_unique_file_keys()
    assert len(keys) >= 1


def test_compute_readable_name(tmp_path):
    loader = JsonLoader(str(tmp_path))
    assert loader._compute_readable_name("simple_unified.json") == "simple"
    assert loader._compute_readable_name("no_suffix.json") == "no_suffix.json"
    uuid_name = "a1b2c3d4-e5f6-7890-abcd-ef1234567890_建筑平面图_unified.json"
    assert loader._compute_readable_name(uuid_name) == "建筑平面图"
