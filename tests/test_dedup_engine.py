# -*- coding: utf-8 -*-
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.dedup_engine import (
    DedupEngine, DrawingProfile, DuplicationReport,
    compute_text_hash,
)


class TestComputeTextHash:
    def test_same_texts_same_hash(self):
        texts = ["标高 3.600m", "轴线 A-1", "梁 300x600"]
        h1 = compute_text_hash(texts)
        h2 = compute_text_hash(texts)
        assert h1 == h2
        assert len(h1) == 16

    def test_different_texts_different_hash(self):
        h1 = compute_text_hash(["标高 3.600m"])
        h2 = compute_text_hash(["标高 5.400m"])
        assert h1 != h2

    def test_order_independent(self):
        texts = ["A", "B", "C"]
        h1 = compute_text_hash(texts)
        h2 = compute_text_hash(["C", "B", "A"])
        assert h1 == h2

    def test_empty_texts(self):
        h = compute_text_hash([])
        assert isinstance(h, str)
        assert len(h) == 16


class TestDrawingProfile:
    def test_basic_properties(self):
        p = DrawingProfile(
            "f1.json", "建筑-平面图",
            ["标高 ±0.000m", "标高 3.600m", "轴线 ①轴"],
            {"discipline": "建筑", "building": "教学楼", "source_file": "test.dxf"},
        )
        assert p.file_key == "f1.json"
        assert p.readable_name == "建筑-平面图"
        assert p.discipline == "建筑"
        assert p.building == "教学楼"

    def test_elevation_extraction(self):
        p = DrawingProfile(
            "f1.json", "test",
            ["标高 ±0.000m", "标高 3.600m", "标高 -0.450m"],
            {},
        )
        elevs = p.elevations
        assert len(elevs) == 3
        assert 0.0 in elevs
        assert 3.6 in elevs
        assert -0.45 in elevs

    def test_elevation_cached(self):
        p = DrawingProfile("f1.json", "test", ["标高 3.600m"], {})
        e1 = p.elevations
        e2 = p.elevations
        assert e1 is e2

    def test_axis_extraction(self):
        p = DrawingProfile(
            "f1.json", "test",
            ["①轴", "②轴", "③轴", "普通文本"],
            {},
        )
        axes = p.axes
        assert len(axes) >= 3

    def test_net_height_extraction(self):
        p = DrawingProfile(
            "f1.json", "test",
            ["净高:2800", "净高：3200mm", "层高:3600"],
            {},
        )
        nhs = p.net_heights
        assert len(nhs) >= 2

    def test_layer_height_extraction(self):
        p = DrawingProfile(
            "f1.json", "test",
            ["层高:3600", "层高：3.0"],
            {},
        )
        lhs = p.layer_heights
        assert len(lhs) >= 1

    def test_to_dict(self):
        p = DrawingProfile("f1.json", "test", ["标高 3.600m"], {"discipline": "建筑"})
        d = p.to_dict()
        assert "file_key" in d
        assert "text_hash" in d
        assert "discipline" in d
        assert d["discipline"] == "建筑"


class TestDedupEngine:
    def test_register_and_get(self):
        engine = DedupEngine()
        engine.register("f1.json", "图1", ["文本A"], {"discipline": "建筑"})
        engine.register("f2.json", "图2", ["文本B"], {"discipline": "结构"})

        assert len(engine.all_profiles) == 2
        p = engine.get_profile("f1.json")
        assert p is not None
        assert p.discipline == "建筑"

    def test_dedup_identical_files(self):
        engine = DedupEngine()
        engine.register("f1.json", "图1", ["相同文本", "标高3.6"], {})
        engine.register("f2.json", "图2", ["相同文本", "标高3.6"], {})
        engine.register("f3.json", "图3", ["不同文本"], {})

        report = engine.compute_dedup_report()
        assert report.total_before == 3
        assert report.total_after == 2
        assert report.dedup_ratio > 0

    def test_no_duplicates(self):
        engine = DedupEngine()
        engine.register("f1.json", "图1", ["文本A"], {})
        engine.register("f2.json", "图2", ["文本B"], {})

        report = engine.compute_dedup_report()
        assert report.total_before == 2
        assert report.total_after == 2
        assert report.dedup_ratio == 0.0

    def test_unique_profiles(self):
        engine = DedupEngine()
        engine.register("f1.json", "图1", ["相同"], {})
        engine.register("f2.json", "图2", ["相同"], {})
        engine.register("f3.json", "图3", ["不同"], {})

        unique = engine.get_unique_profiles()
        assert len(unique) == 2

    def test_discipline_groups(self):
        engine = DedupEngine()
        engine.register("f1.json", "图1", ["A"], {"discipline": "建筑"})
        engine.register("f2.json", "图2", ["B"], {"discipline": "建筑"})
        engine.register("f3.json", "图3", ["C"], {"discipline": "结构"})

        groups = engine.get_discipline_groups()
        assert len(groups["建筑"]) == 2
        assert len(groups["结构"]) == 1

    def test_building_groups(self):
        engine = DedupEngine()
        engine.register("f1.json", "图1", ["A"], {"building": "教学楼"})
        engine.register("f2.json", "图2", ["B"], {"building": "宿舍"})

        groups = engine.get_building_groups()
        assert "教学楼" in groups
        assert "宿舍" in groups

    def test_elevation_inconsistencies(self):
        engine = DedupEngine()
        engine.register("f1.json", "建筑-图1", ["标高 3.600m", "标高 7.200m"], {"discipline": "建筑", "building": "教学楼"})
        engine.register("f2.json", "建筑-图2", ["标高 3.600m"], {"discipline": "建筑", "building": "教学楼"})

        incs = engine.find_elevation_inconsistencies()
        found = [i for i in incs if i["elevation"] == 7.2]
        assert len(found) == 1
        assert "建筑-图2" in found[0]["absent_in"]

    def test_axis_inconsistencies(self):
        engine = DedupEngine()
        engine.register("f1.json", "结构-图1", ["①轴", "②轴", "③轴"], {"discipline": "结构", "building": "教学楼"})
        engine.register("f2.json", "建筑-图1", ["①轴", "②轴"], {"discipline": "建筑", "building": "教学楼"})

        incs = engine.find_axis_inconsistencies()
        assert len(incs) >= 1

    def test_empty_engine(self):
        engine = DedupEngine()
        assert len(engine.all_profiles) == 0
        report = engine.compute_dedup_report()
        assert report.total_before == 0

    def test_get_summary(self):
        engine = DedupEngine()
        engine.register("f1.json", "图1", ["A"], {"discipline": "建筑", "building": "教学楼"})
        summary = engine.get_summary()
        assert "total_files" in summary
        assert "unique_files" in summary
        assert "disciplines" in summary
