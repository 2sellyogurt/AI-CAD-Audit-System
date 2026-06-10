# -*- coding: utf-8 -*-
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.geometry_extractor import GeometryExtractor


class MockLayerMapper:
    def classify(self, layer: str):
        if "墙" in layer:
            return {"layer_name": layer, "discipline": "建筑", "category": "墙"}
        return {"layer_name": layer, "discipline": "未知", "category": "未分类"}


@pytest.fixture
def extractor():
    return GeometryExtractor()


@pytest.fixture
def extractor_with_mapper():
    return GeometryExtractor(layer_mapper=MockLayerMapper())


class TestGeometryExtractorInit:
    def test_init_default(self, extractor):
        assert extractor._layer_mapper is None

    def test_init_with_mapper(self, extractor_with_mapper):
        assert extractor_with_mapper._layer_mapper is not None
        assert isinstance(extractor_with_mapper._layer_mapper, MockLayerMapper)


class TestExtractFromDxf:
    def test_extract_from_nonexistent_file(self, extractor):
        result = extractor.extract_from_dxf("/nonexistent/file.dxf")
        assert result["component_count"] == 0
        assert result["dimension_count"] == 0
        assert result["components"] == []
        assert result["dimensions"] == []

    def test_extract_from_empty_file(self, extractor):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False, encoding='utf-8') as f:
            f.write("")
            temp_path = f.name
        try:
            result = extractor.extract_from_dxf(temp_path)
            assert result["component_count"] == 0
            assert result["dimension_count"] == 0
        finally:
            os.unlink(temp_path)

    def test_extract_from_valid_dxf(self, extractor):
        dxf_content = "0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n10\n0.0\n20\n0.0\n11\n100.0\n21\n100.0\n0\nENDSEC\n0\nEOF\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False, encoding='utf-8') as f:
            f.write(dxf_content)
            temp_path = f.name
        try:
            result = extractor.extract_from_dxf(temp_path)
            assert result["component_count"] == 1
            assert result["components"][0]["type"] == "LINE"
        finally:
            os.unlink(temp_path)

    def test_extract_from_dxf_with_dimension(self, extractor):
        dxf_content = "0\nSECTION\n2\nENTITIES\n0\nTEXT\n8\n0\n10\n10.0\n20\n20.0\n40\n2.5\n1\n300x200\n0\nENDSEC\n0\nEOF\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False, encoding='utf-8') as f:
            f.write(dxf_content)
            temp_path = f.name
        try:
            result = extractor.extract_from_dxf(temp_path)
            assert result["dimension_count"] == 1
            assert result["dimensions"][0]["type"] == "TEXT"
            assert result["dimensions"][0]["text"] == "300x200"
        finally:
            os.unlink(temp_path)


class TestParseDxfPairs:
    def test_parse_dxf_pairs(self, extractor):
        lines = ["0", "SECTION", "2", "ENTITIES", "0", "ENDSEC"]
        pairs = extractor._parse_dxf_pairs(lines)
        assert len(pairs) == 3
        assert pairs[0] == ("0", "SECTION")
        assert pairs[1] == ("2", "ENTITIES")
        assert pairs[2] == ("0", "ENDSEC")

    def test_parse_dxf_pairs_empty(self, extractor):
        pairs = extractor._parse_dxf_pairs([])
        assert len(pairs) == 0

    def test_parse_dxf_pairs_odd_lines(self, extractor):
        lines = ["0", "SECTION", "2"]
        pairs = extractor._parse_dxf_pairs(lines)
        assert len(pairs) == 1
        assert pairs[0] == ("0", "SECTION")

    def test_parse_dxf_pairs_single_line(self, extractor):
        lines = ["0"]
        pairs = extractor._parse_dxf_pairs(lines)
        assert len(pairs) == 0


class TestFindEntitiesSection:
    def test_find_entities_section(self, extractor):
        pairs = [("0", "SECTION"), ("2", "ENTITIES"), ("0", "LINE"), ("0", "ENDSEC")]
        result = extractor._find_entities_section(pairs)
        assert len(result) == 1
        assert result[0] == ("0", "LINE")

    def test_find_entities_section_empty(self, extractor):
        pairs = [("0", "SECTION"), ("2", "HEADER"), ("0", "ENDSEC")]
        result = extractor._find_entities_section(pairs)
        assert len(result) == 0

    def test_find_entities_section_no_endsec(self, extractor):
        pairs = [("0", "SECTION"), ("2", "ENTITIES"), ("0", "LINE")]
        result = extractor._find_entities_section(pairs)
        assert len(result) == 1

    def test_find_entities_section_case_insensitive(self, extractor):
        pairs = [("0", "SECTION"), ("2", "entities"), ("0", "CIRCLE"), ("0", "endsec")]
        result = extractor._find_entities_section(pairs)
        assert len(result) == 1
        assert result[0] == ("0", "CIRCLE")


class TestParseEntities:
    def test_parse_entities(self, extractor):
        pairs = [("0", "LINE"), ("8", "0"), ("0", "CIRCLE"), ("8", "0")]
        result = extractor._parse_entities(pairs)
        assert len(result) == 2
        assert result[0]["type"] == "LINE"
        assert result[1]["type"] == "CIRCLE"

    def test_parse_entities_empty(self, extractor):
        result = extractor._parse_entities([])
        assert len(result) == 0

    def test_parse_entities_with_multiple_fields(self, extractor):
        pairs = [("0", "LINE"), ("8", "Wall"), ("10", "0.0"), ("20", "0.0")]
        result = extractor._parse_entities(pairs)
        assert len(result) == 1
        assert result[0]["type"] == "LINE"
        assert result[0]["8"] == "Wall"

    def test_parse_entities_unknown_type(self, extractor):
        pairs = [("0", "UNKNOWN"), ("8", "0")]
        result = extractor._parse_entities(pairs)
        assert len(result) == 0


class TestParseCoord:
    def test_parse_coord_normal(self, extractor):
        entity = {"10": "100.0", "11": "200.0", "12": "50.0"}
        result = extractor._parse_coord(entity, "1")
        assert result == (100.0, 200.0, 50.0)

    def test_parse_coord_missing(self, extractor):
        entity = {}
        result = extractor._parse_coord(entity, "1")
        assert result == (0.0, 0.0, 0.0)

    def test_parse_coord_invalid_values(self, extractor):
        entity = {"10": "abc", "11": None, "12": "50.0"}
        result = extractor._parse_coord(entity, "1")
        assert result == (0.0, 0.0, 50.0)

    def test_parse_coord_partial(self, extractor):
        entity = {"10": "100.0"}
        result = extractor._parse_coord(entity, "1")
        assert result == (100.0, 0.0, 0.0)


class TestClassifyLayer:
    def test_classify_layer_no_mapper(self, extractor):
        result = extractor._classify_layer("Wall-1")
        assert result["layer_name"] == "Wall-1"
        assert result["discipline"] == "未知"
        assert result["category"] == "未分类"

    def test_classify_layer_with_mapper(self, extractor_with_mapper):
        result = extractor_with_mapper._classify_layer("墙体-1")
        assert result["layer_name"] == "墙体-1"
        assert result["discipline"] == "建筑"
        assert result["category"] == "墙"

    def test_classify_layer_mapper_exception(self):
        class FailingMapper:
            def classify(self, layer):
                raise ValueError("test error")
        ext = GeometryExtractor(layer_mapper=FailingMapper())
        result = ext._classify_layer("test")
        assert result["layer_name"] == "test"
        assert result["discipline"] == "未知"


class TestDistance2D:
    def test_distance_2d_normal(self):
        result = GeometryExtractor._distance_2d((0, 0, 0), (3, 4, 0))
        assert result == pytest.approx(5.0)

    def test_distance_2d_same_point(self):
        result = GeometryExtractor._distance_2d((10, 20, 30), (10, 20, 30))
        assert result == pytest.approx(0.0)

    def test_distance_2d_negative(self):
        result = GeometryExtractor._distance_2d((-3, -4, 0), (0, 0, 0))
        assert result == pytest.approx(5.0)


class TestMakeComponents:
    def test_make_line_component(self, extractor):
        entity = {"type": "LINE", "8": "0", "10": "0.0", "11": "0.0", "12": "0.0", "20": "100.0", "21": "0.0", "22": "0.0"}
        result = extractor._make_line_component(entity, "0")
        assert result["type"] == "LINE"
        assert result["layer"] == "0"
        assert result["start_point"] == [0.0, 0.0, 0.0]
        assert result["end_point"] == [100.0, 0.0, 0.0]
        assert result["length"] == pytest.approx(100.0)

    def test_make_circle_component(self, extractor):
        entity = {"type": "CIRCLE", "8": "0", "10": "50.0", "11": "50.0", "12": "0.0", "40": "25.0"}
        result = extractor._make_circle_component(entity, "0")
        assert result["type"] == "CIRCLE"
        assert result["center"] == [50.0, 50.0, 0.0]
        assert result["radius"] == 25.0

    def test_make_arc_component(self, extractor):
        entity = {"type": "ARC", "8": "0", "10": "0.0", "11": "0.0", "12": "0.0", "40": "10.0", "50": "0.0", "51": "90.0"}
        result = extractor._make_arc_component(entity, "0")
        assert result["type"] == "ARC"
        assert result["radius"] == 10.0
        assert result["start_angle"] == 0.0
        assert result["end_angle"] == 90.0

    def test_make_lwpolyline_component(self, extractor):
        entity = {"type": "LWPOLYLINE", "8": "0", "90": "3", "10": "0.0", "20": "0.0", "30": "0.0", "40": "100.0", "50": "0.0", "60": "0.0", "70": "1"}
        result = extractor._make_lwpolyline_component(entity, "0")
        assert result["type"] == "LWPOLYLINE"
        assert result["vertex_count"] == 3
        assert result["closed"] is True

    def test_make_insert_component(self, extractor):
        entity = {"type": "INSERT", "8": "0", "2": "BLOCK1", "10": "100.0", "11": "200.0", "12": "0.0"}
        result = extractor._make_insert_component(entity, "0")
        assert result["type"] == "INSERT"
        assert result["block_name"] == "BLOCK1"
        assert result["insert_point"] == [100.0, 200.0, 0.0]

    def test_make_point_component(self, extractor):
        entity = {"type": "POINT", "8": "0", "10": "50.0", "11": "75.0", "12": "0.0"}
        result = extractor._make_point_component(entity, "0")
        assert result["type"] == "POINT"
        assert result["point"] == [50.0, 75.0, 0.0]

    def test_make_generic_component(self, extractor):
        entity = {"type": "ELLIPSE", "8": "0"}
        result = extractor._make_generic_component(entity, "0", "ELLIPSE")
        assert result["type"] == "ELLIPSE"
        assert result["layer"] == "0"


class TestMakeDimensions:
    def test_make_text_dimension(self, extractor):
        entity = {"type": "TEXT", "8": "Dim", "10": "10.0", "11": "0.0", "12": "0.0", "20": "20.0", "40": "2.5", "1": "300x200"}
        result = extractor._make_text_dimension(entity)
        assert result["type"] == "TEXT"
        assert result["text"] == "300x200"
        assert result["height"] == 2.5
        assert result["category"] == "标注文字"

    def test_make_text_dimension_invalid_height(self, extractor):
        entity = {"type": "TEXT", "8": "0", "10": "0.0", "11": "0.0", "12": "0.0", "20": "0.0", "40": "abc", "1": "test"}
        result = extractor._make_text_dimension(entity)
        assert result["height"] == 0.0

    def test_make_dimension_entity(self, extractor):
        entity = {"type": "DIMENSION", "8": "0", "10": "10.0", "11": "0.0", "12": "0.0", "20": "20.0", "42": "500.0"}
        result = extractor._make_dimension_entity(entity)
        assert result["type"] == "DIMENSION"
        assert result["dim_value"] == 500.0
        assert result["category"] == "尺寸标注"

    def test_make_dimension_entity_invalid_value(self, extractor):
        entity = {"type": "DIMENSION", "8": "0", "10": "0.0", "11": "0.0", "12": "0.0", "20": "0.0", "42": "abc"}
        result = extractor._make_dimension_entity(entity)
        assert result["dim_value"] == 0.0


class TestEntityToComponent:
    def test_entity_to_component_line(self, extractor):
        entity = {"type": "LINE", "8": "0", "10": "0.0", "11": "0.0", "12": "0.0", "20": "100.0", "21": "0.0", "22": "0.0"}
        result = extractor._entity_to_component(entity)
        assert result is not None
        assert result["type"] == "LINE"

    def test_entity_to_component_circle(self, extractor):
        entity = {"type": "CIRCLE", "8": "0", "10": "0.0", "11": "0.0", "12": "0.0", "20": "10.0", "40": "10.0"}
        result = extractor._entity_to_component(entity)
        assert result is not None
        assert result["type"] == "CIRCLE"

    def test_entity_to_component_unknown(self, extractor):
        entity = {"type": "UNKNOWN", "8": "0"}
        result = extractor._entity_to_component(entity)
        assert result is None

    def test_entity_to_component_no_type(self, extractor):
        entity = {"8": "0"}
        result = extractor._entity_to_component(entity)
        assert result is None


class TestEntityToDimension:
    def test_entity_to_dimension_text(self, extractor):
        entity = {"type": "TEXT", "8": "0", "10": "0.0", "11": "0.0", "12": "0.0", "20": "0.0", "1": "test"}
        result = extractor._entity_to_dimension(entity)
        assert result is not None
        assert result["type"] == "TEXT"

    def test_entity_to_dimension_mtext(self, extractor):
        entity = {"type": "MTEXT", "8": "0", "10": "0.0", "11": "0.0", "12": "0.0", "20": "0.0", "1": "test"}
        result = extractor._entity_to_dimension(entity)
        assert result is not None
        assert result["type"] == "MTEXT"

    def test_entity_to_dimension_dimension(self, extractor):
        entity = {"type": "DIMENSION", "8": "0", "10": "0.0", "11": "0.0", "12": "0.0", "20": "0.0", "42": "100.0"}
        result = extractor._entity_to_dimension(entity)
        assert result is not None
        assert result["type"] == "DIMENSION"

    def test_entity_to_dimension_unknown(self, extractor):
        entity = {"type": "LINE", "8": "0"}
        result = extractor._entity_to_dimension(entity)
        assert result is None

    def test_entity_to_dimension_no_type(self, extractor):
        entity = {"8": "0"}
        result = extractor._entity_to_dimension(entity)
        assert result is None
