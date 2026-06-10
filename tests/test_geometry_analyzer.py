# -*- coding: utf-8 -*-
import os
import sys
import math

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.geometry_analyzer import RiskLevel, Finding, GeometryAnalyzer


@pytest.fixture
def empty_analyzer():
    return GeometryAnalyzer([], [])


@pytest.fixture
def sample_components():
    return [
        {
            "type": "LINE",
            "layer": "Wall-1",
            "layer_info": {"layer_name": "Wall-1", "discipline": "建筑", "category": "墙"},
            "start_point": [0, 0, 0],
            "end_point": [100, 0, 0],
            "length": 100.0,
        },
        {
            "type": "CIRCLE",
            "layer": "Pipe-1",
            "layer_info": {"layer_name": "Pipe-1", "discipline": "给排水", "category": "管道"},
            "center": [200, 0, 0],
            "radius": 50.0,
        },
        {
            "type": "INSERT",
            "layer": "Column-1",
            "layer_info": {"layer_name": "Column-1", "discipline": "结构", "category": "柱"},
            "insert_point": [500, 500, 0],
            "block_name": "COLUMN",
        },
        {
            "type": "INSERT",
            "layer": "Column-2",
            "layer_info": {"layer_name": "Column-2", "discipline": "结构", "category": "柱"},
            "insert_point": [20000, 500, 0],
            "block_name": "COLUMN",
        },
    ]


@pytest.fixture
def sample_dimensions():
    return [
        {
            "type": "TEXT",
            "layer": "Dim-1",
            "position": [10, 20, 0],
            "text": "300x200",
            "height": 2.5,
            "category": "标注文字",
        },
        {
            "type": "DIMENSION",
            "layer": "Dim-2",
            "position": [50, 50, 0],
            "dim_value": 500.0,
            "category": "尺寸标注",
        },
    ]


@pytest.fixture
def analyzer(sample_components, sample_dimensions):
    return GeometryAnalyzer(sample_components, sample_dimensions)


class TestRiskLevel:
    def test_risk_level_valid(self):
        rl = RiskLevel("高")
        assert rl.value == "高"

    def test_risk_level_invalid(self):
        rl = RiskLevel("极高")
        assert rl.value == "信息"

    def test_risk_level_eq_same(self):
        rl1 = RiskLevel("中")
        rl2 = RiskLevel("中")
        assert rl1 == rl2

    def test_risk_level_eq_string(self):
        rl = RiskLevel("低")
        assert rl == "低"

    def test_risk_level_eq_different(self):
        rl1 = RiskLevel("高")
        rl2 = RiskLevel("低")
        assert rl1 != rl2

    def test_risk_level_eq_other_type(self):
        rl = RiskLevel("高")
        assert rl != 42

    def test_risk_level_hash(self):
        rl1 = RiskLevel("高")
        rl2 = RiskLevel("高")
        assert hash(rl1) == hash(rl2)

    def test_risk_level_repr(self):
        rl = RiskLevel("中")
        assert repr(rl) == "RiskLevel('中')"


class TestFinding:
    def test_finding_init(self):
        f = Finding(
            finding_id="F001",
            category="重叠",
            description="测试描述",
            risk_level=RiskLevel("高"),
        )
        assert f.finding_id == "F001"
        assert f.category == "重叠"
        assert f.confidence == 1.0

    def test_finding_confidence_clamp(self):
        f = Finding(
            finding_id="F002",
            category="测试",
            description="测试",
            risk_level=RiskLevel("中"),
            confidence=1.5,
        )
        assert f.confidence == 1.0

        f2 = Finding(
            finding_id="F003",
            category="测试",
            description="测试",
            risk_level=RiskLevel("中"),
            confidence=-0.5,
        )
        assert f2.confidence == 0.0

    def test_finding_to_dict(self):
        f = Finding(
            finding_id="F001",
            category="重叠",
            description="测试描述",
            risk_level=RiskLevel("高"),
            component_a="Wall-1",
            component_b="Wall-2",
            location="Layer-1",
            evidence="测试证据",
            suggestion="测试建议",
            confidence=0.8,
        )
        d = f.to_dict()
        assert d["finding_id"] == "F001"
        assert d["category"] == "重叠"
        assert d["risk_level"] == "高"
        assert d["confidence"] == 0.8


class TestGeometryAnalyzerInit:
    def test_init_default(self, empty_analyzer):
        assert empty_analyzer._components == []
        assert empty_analyzer._dimensions == []
        assert empty_analyzer._findings == []

    def test_init_with_data(self, analyzer):
        assert len(analyzer._components) == 4
        assert len(analyzer._dimensions) == 2

    def test_init_invalid_data(self):
        analyzer = GeometryAnalyzer(None, None)
        assert analyzer._components == []
        assert analyzer._dimensions == []


class TestGetComponentBounds:
    def test_line_bounds(self, analyzer):
        comp = {"type": "LINE", "start_point": [10, 20, 0], "end_point": [100, 200, 0]}
        result = analyzer._get_component_bounds(comp)
        assert result == (10, 20, 100, 200)

    def test_circle_bounds(self, analyzer):
        comp = {"type": "CIRCLE", "center": [50, 50, 0], "radius": 25}
        result = analyzer._get_component_bounds(comp)
        assert result == (25, 25, 75, 75)

    def test_lwpolyline_bounds(self, analyzer):
        comp = {"type": "LWPOLYLINE", "vertices": [[0, 0, 0], [100, 0, 0], [100, 100, 0]]}
        result = analyzer._get_component_bounds(comp)
        assert result == (0, 0, 100, 100)

    def test_insert_bounds(self, analyzer):
        comp = {"type": "INSERT", "insert_point": [100, 200, 0]}
        result = analyzer._get_component_bounds(comp)
        assert result == (100, 200, 100, 200)

    def test_point_bounds(self, analyzer):
        comp = {"type": "POINT", "point": [50, 75, 0]}
        result = analyzer._get_component_bounds(comp)
        assert result == (50, 75, 50, 75)

    def test_unknown_bounds(self, analyzer):
        comp = {"type": "UNKNOWN"}
        result = analyzer._get_component_bounds(comp)
        assert result is None

    def test_empty_polyline_bounds(self, analyzer):
        comp = {"type": "LWPOLYLINE", "vertices": []}
        result = analyzer._get_component_bounds(comp)
        assert result is None


class TestBoundsIntersect:
    def test_bounds_intersect_true(self, analyzer):
        b1 = (0, 0, 100, 100)
        b2 = (50, 50, 150, 150)
        assert analyzer._bounds_intersect(b1, b2) is True

    def test_bounds_intersect_false(self, analyzer):
        b1 = (0, 0, 100, 100)
        b2 = (200, 200, 300, 300)
        assert analyzer._bounds_intersect(b1, b2) is False

    def test_bounds_intersect_edge_touching(self, analyzer):
        b1 = (0, 0, 100, 100)
        b2 = (100, 0, 200, 100)
        assert analyzer._bounds_intersect(b1, b2) is True

    def test_bounds_intersect_touching(self, analyzer):
        b1 = (0, 0, 100, 100)
        b2 = (99, 99, 200, 200)
        assert analyzer._bounds_intersect(b1, b2) is True

    def test_bounds_not_intersect_separated(self, analyzer):
        b1 = (0, 0, 100, 100)
        b2 = (101, 101, 200, 200)
        assert analyzer._bounds_intersect(b1, b2) is False


class TestBoundsMinDistance:
    def test_bounds_min_distance_overlapping(self, analyzer):
        b1 = (0, 0, 100, 100)
        b2 = (50, 50, 150, 150)
        assert analyzer._bounds_min_distance(b1, b2) == pytest.approx(0.0)

    def test_bounds_min_distance_separated(self, analyzer):
        b1 = (0, 0, 100, 0)
        b2 = (200, 0, 300, 0)
        assert analyzer._bounds_min_distance(b1, b2) == pytest.approx(100.0)

    def test_bounds_min_distance_diagonal(self, analyzer):
        b1 = (0, 0, 100, 100)
        b2 = (200, 200, 300, 300)
        expected = math.sqrt(100**2 + 100**2)
        assert analyzer._bounds_min_distance(b1, b2) == pytest.approx(expected)


class TestGetDisciplineAndCategory:
    def test_get_discipline(self, analyzer):
        comp = {"layer_info": {"discipline": "建筑", "category": "墙"}}
        assert analyzer._get_discipline(comp) == "建筑"

    def test_get_discipline_missing(self, analyzer):
        comp = {}
        assert analyzer._get_discipline(comp) == "未知"

    def test_get_category(self, analyzer):
        comp = {"layer_info": {"category": "管道"}}
        assert analyzer._get_category(comp) == "管道"

    def test_get_category_missing(self, analyzer):
        comp = {}
        assert analyzer._get_category(comp) == "未分类"


class TestGetClearanceKey:
    def test_get_clearance_key_known(self, analyzer):
        comp_a = {"layer_info": {"category": "管道"}}
        comp_b = {"layer_info": {"category": "电缆"}}
        result = analyzer._get_clearance_key(comp_a, comp_b)
        assert result == "管道-电缆"

    def test_get_clearance_key_reverse(self, analyzer):
        comp_a = {"layer_info": {"category": "电缆"}}
        comp_b = {"layer_info": {"category": "管道"}}
        result = analyzer._get_clearance_key(comp_a, comp_b)
        assert result == "管道-电缆"

    def test_get_clearance_key_unknown(self, analyzer):
        comp_a = {"layer_info": {"category": "未知A"}}
        comp_b = {"layer_info": {"category": "未知B"}}
        result = analyzer._get_clearance_key(comp_a, comp_b)
        assert result == "默认"


class TestRunAllChecks:
    def test_run_all_checks_empty(self, empty_analyzer):
        findings = empty_analyzer.run_all_checks()
        assert findings == []

    def test_run_all_checks_with_data(self, analyzer):
        findings = analyzer.run_all_checks()
        assert isinstance(findings, list)

    def test_run_all_checks_returns_list(self, analyzer):
        findings = analyzer.run_all_checks()
        assert isinstance(findings, list)


class TestGetSummary:
    def test_get_summary_empty(self, empty_analyzer):
        summary = empty_analyzer.get_summary()
        assert summary["total_count"] == 0
        assert summary["by_risk"] == {}
        assert summary["by_category"] == {}

    def test_get_summary_with_findings(self, empty_analyzer):
        empty_analyzer._add_finding("重叠", "测试", RiskLevel("高"))
        empty_analyzer._add_finding("间距不足", "测试2", RiskLevel("中"))
        summary = empty_analyzer.get_summary()
        assert summary["total_count"] == 2
        assert summary["by_risk"]["高"] == 1
        assert summary["by_risk"]["中"] == 1

    def test_get_summary_category_count(self, empty_analyzer):
        empty_analyzer._add_finding("重叠", "测试1", RiskLevel("高"))
        empty_analyzer._add_finding("重叠", "测试2", RiskLevel("高"))
        summary = empty_analyzer.get_summary()
        assert summary["by_category"]["重叠"] == 2


class TestAddFinding:
    def test_add_finding(self, empty_analyzer):
        empty_analyzer._add_finding(
            category="重叠",
            description="测试构件重叠",
            risk_level=RiskLevel("高"),
            component_a="Wall-1",
            component_b="Wall-2",
        )
        assert len(empty_analyzer._findings) == 1
        finding = empty_analyzer._findings[0]
        assert finding.category == "重叠"
        assert finding.description == "测试构件重叠"
        assert finding.risk_level == RiskLevel("高")


class TestCheckComponentOverlap:
    def test_check_overlap_same_discipline(self, empty_analyzer):
        comps = [
            {
                "type": "LINE",
                "layer": "Wall-1",
                "layer_info": {"discipline": "建筑", "category": "墙"},
                "start_point": [0, 0, 0],
                "end_point": [100, 100, 0],
            },
            {
                "type": "LINE",
                "layer": "Wall-2",
                "layer_info": {"discipline": "建筑", "category": "墙"},
                "start_point": [50, 50, 0],
                "end_point": [150, 150, 0],
            },
        ]
        empty_analyzer._components = comps
        empty_analyzer._check_component_overlap()
        assert len(empty_analyzer._findings) == 1
        assert empty_analyzer._findings[0].category == "重叠"

    def test_check_overlap_different_discipline(self, empty_analyzer):
        comps = [
            {
                "type": "LINE",
                "layer": "Wall-1",
                "layer_info": {"discipline": "建筑", "category": "墙"},
                "start_point": [0, 0, 0],
                "end_point": [100, 100, 0],
            },
            {
                "type": "LINE",
                "layer": "Pipe-1",
                "layer_info": {"discipline": "给排水", "category": "管道"},
                "start_point": [50, 50, 0],
                "end_point": [150, 150, 0],
            },
        ]
        empty_analyzer._components = comps
        empty_analyzer._check_component_overlap()
        assert len(empty_analyzer._findings) == 0


class TestCheckClearance:
    def test_check_clearance_insufficient(self, empty_analyzer):
        comps = [
            {
                "type": "CIRCLE",
                "layer": "Pipe-1",
                "layer_info": {"discipline": "给排水", "category": "管道"},
                "center": [0, 0, 0],
                "radius": 10,
            },
            {
                "type": "CIRCLE",
                "layer": "Cable-1",
                "layer_info": {"discipline": "电气", "category": "电缆"},
                "center": [200, 0, 0],
                "radius": 10,
            },
        ]
        empty_analyzer._components = comps
        empty_analyzer._check_clearance()
        assert len(empty_analyzer._findings) == 1
        assert empty_analyzer._findings[0].category == "间距不足"

    def test_check_clearance_sufficient(self, empty_analyzer):
        comps = [
            {
                "type": "CIRCLE",
                "layer": "Pipe-1",
                "layer_info": {"discipline": "给排水", "category": "管道"},
                "center": [0, 0, 0],
                "radius": 10,
            },
            {
                "type": "CIRCLE",
                "layer": "Cable-1",
                "layer_info": {"discipline": "电气", "category": "电缆"},
                "center": [500, 0, 0],
                "radius": 10,
            },
        ]
        empty_analyzer._components = comps
        empty_analyzer._check_clearance()
        assert len(empty_analyzer._findings) == 0


class TestCheckDimensionRanges:
    def test_check_dimension_zero(self, empty_analyzer):
        empty_analyzer._dimensions = [
            {"dim_value": 0, "text": "0mm", "layer": "Dim-1"},
        ]
        empty_analyzer._check_dimension_ranges()
        assert len(empty_analyzer._findings) == 1
        assert empty_analyzer._findings[0].category == "标注异常"

    def test_check_dimension_negative(self, empty_analyzer):
        empty_analyzer._dimensions = [
            {"dim_value": -100, "text": "-100mm", "layer": "Dim-1"},
        ]
        empty_analyzer._check_dimension_ranges()
        assert len(empty_analyzer._findings) == 1

    def test_check_dimension_normal(self, empty_analyzer):
        empty_analyzer._dimensions = [
            {"dim_value": 500, "text": "500mm", "layer": "Dim-1"},
        ]
        empty_analyzer._check_dimension_ranges()
        assert len(empty_analyzer._findings) == 0


class TestCheckPipeDiameters:
    def test_check_pipe_diameter_large(self, empty_analyzer):
        empty_analyzer._dimensions = [
            {"text": "DN2500", "layer": "Pipe-1"},
        ]
        empty_analyzer._check_pipe_diameters()
        assert len(empty_analyzer._findings) == 1
        assert empty_analyzer._findings[0].category == "管径异常"

    def test_check_pipe_diameter_normal(self, empty_analyzer):
        empty_analyzer._dimensions = [
            {"text": "DN100", "layer": "Pipe-1"},
        ]
        empty_analyzer._check_pipe_diameters()
        assert len(empty_analyzer._findings) == 0

    def test_check_pipe_diameter_no_match(self, empty_analyzer):
        empty_analyzer._dimensions = [
            {"text": "普通文字", "layer": "Text-1"},
        ]
        empty_analyzer._check_pipe_diameters()
        assert len(empty_analyzer._findings) == 0


class TestCheckRoomSizes:
    def test_check_room_size_small(self, empty_analyzer):
        empty_analyzer._dimensions = [
            {"text": "卧室 2000x2500", "layer": "Room-1"},
        ]
        empty_analyzer._check_room_sizes()
        assert len(empty_analyzer._findings) == 1
        assert empty_analyzer._findings[0].category == "尺寸异常"

    def test_check_room_size_normal(self, empty_analyzer):
        empty_analyzer._dimensions = [
            {"text": "卧室 3500x3000", "layer": "Room-1"},
        ]
        empty_analyzer._check_room_sizes()
        assert len(empty_analyzer._findings) == 0


class TestCheckWallThickness:
    def test_check_wall_too_short(self, empty_analyzer):
        empty_analyzer._components = [
            {
                "type": "LINE",
                "layer": "Wall-1",
                "layer_info": {"category": "墙"},
                "length": 30.0,
            },
        ]
        empty_analyzer._check_wall_thickness()
        assert len(empty_analyzer._findings) == 1
        assert empty_analyzer._findings[0].category == "墙体异常"

    def test_check_wall_normal(self, empty_analyzer):
        empty_analyzer._components = [
            {
                "type": "LINE",
                "layer": "Wall-1",
                "layer_info": {"category": "墙"},
                "length": 1000.0,
            },
        ]
        empty_analyzer._check_wall_thickness()
        assert len(empty_analyzer._findings) == 0

    def test_check_wall_not_line(self, empty_analyzer):
        empty_analyzer._components = [
            {
                "type": "CIRCLE",
                "layer": "Wall-1",
                "layer_info": {"category": "墙"},
                "radius": 10.0,
            },
        ]
        empty_analyzer._check_wall_thickness()
        assert len(empty_analyzer._findings) == 0


class TestCheckColumnSpacing:
    def test_check_column_spacing_too_large(self, empty_analyzer):
        empty_analyzer._components = [
            {
                "type": "INSERT",
                "layer": "Col-1",
                "layer_info": {"category": "柱"},
                "insert_point": [0, 0, 0],
            },
            {
                "type": "INSERT",
                "layer": "Col-2",
                "layer_info": {"category": "柱"},
                "insert_point": [20000, 0, 0],
            },
        ]
        empty_analyzer._check_column_spacing()
        assert len(empty_analyzer._findings) == 1
        assert empty_analyzer._findings[0].category == "柱距异常"

    def test_check_column_spacing_normal(self, empty_analyzer):
        empty_analyzer._components = [
            {
                "type": "INSERT",
                "layer": "Col-1",
                "layer_info": {"category": "柱"},
                "insert_point": [0, 0, 0],
            },
            {
                "type": "INSERT",
                "layer": "Col-2",
                "layer_info": {"category": "柱"},
                "insert_point": [8000, 0, 0],
            },
        ]
        empty_analyzer._check_column_spacing()
        assert len(empty_analyzer._findings) == 0

    def test_check_column_spacing_single_column(self, empty_analyzer):
        empty_analyzer._components = [
            {
                "type": "INSERT",
                "layer": "Col-1",
                "layer_info": {"category": "柱"},
                "insert_point": [0, 0, 0],
            },
        ]
        empty_analyzer._check_column_spacing()
        assert len(empty_analyzer._findings) == 0