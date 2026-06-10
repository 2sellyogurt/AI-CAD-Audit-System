# -*- coding: utf-8 -*-
import math
import os
import sys
import tempfile
from unittest import mock
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.dxf_parser import DxfParser


def _make_vector(x, y, z=0):
    v = MagicMock()
    v.x = x
    v.y = y
    v.z = z
    v.__iter__ = MagicMock(return_value=iter([x, y, z]))
    v.__len__ = MagicMock(return_value=3)
    return v


def _make_entity(etype, **kwargs):
    entity = MagicMock()
    entity.dxftype.return_value = etype
    entity.dxf.layer = kwargs.get("layer", "0")

    if etype == "LINE":
        entity.dxf.start = _make_vector(*kwargs.get("start", (0, 0, 0)))
        entity.dxf.end = _make_vector(*kwargs.get("end", (1, 0, 0)))
    elif etype == "CIRCLE":
        entity.dxf.center = _make_vector(*kwargs.get("center", (0, 0, 0)))
        entity.dxf.radius = kwargs.get("radius", 1.0)
    elif etype == "ARC":
        entity.dxf.center = _make_vector(*kwargs.get("center", (0, 0, 0)))
        entity.dxf.radius = kwargs.get("radius", 1.0)
        entity.dxf.start_angle = kwargs.get("start_angle", 0)
        entity.dxf.end_angle = kwargs.get("end_angle", 90)
    elif etype == "LWPOLYLINE":
        points = kwargs.get("points", [(0, 0), (1, 0), (1, 1)])
        entity.get_points.return_value = points
        entity.closed = kwargs.get("closed", False)
    elif etype == "POLYLINE":
        vertices = []
        for px, py in kwargs.get("points", [(0, 0), (1, 0)]):
            v = MagicMock()
            v.dxf.location = _make_vector(px, py, 0)
            vertices.append(v)
        entity.vertices = vertices
        entity.is_closed = kwargs.get("is_closed", False)
    elif etype == "TEXT":
        entity.dxf.text = kwargs.get("text", "hello")
        entity.dxf.insert = _make_vector(*kwargs.get("position", (0, 0, 0)))
        entity.dxf.height = kwargs.get("height", 2.5)
        entity.dxf.rotation = kwargs.get("rotation", 0)
    elif etype == "MTEXT":
        entity.text = kwargs.get("text", "mtext content")
        entity.dxf.insert = _make_vector(*kwargs.get("position", (1, 2, 0)))
        entity.dxf.height = kwargs.get("height", 3.0)
        entity.dxf.rotation = kwargs.get("rotation", 45)
    elif etype == "INSERT":
        entity.dxf.name = kwargs.get("block_name", "BLOCK1")
        entity.dxf.insert = _make_vector(*kwargs.get("position", (5, 5, 0)))
        entity.dxf.xscale = kwargs.get("xscale", 1.0)
        entity.dxf.yscale = kwargs.get("yscale", 1.0)
        entity.dxf.rotation = kwargs.get("rotation", 0)
    elif etype == "POINT":
        entity.dxf.location = _make_vector(*kwargs.get("location", (3, 4, 0)))
    elif etype == "ELLIPSE":
        entity.dxf.center = _make_vector(*kwargs.get("center", (0, 0, 0)))
        entity.dxf.major_axis = kwargs.get("major_axis", (2, 0, 0))
        entity.dxf.ratio = kwargs.get("ratio", 0.5)
    elif etype == "SOLID":
        for i, vtx in enumerate(kwargs.get("vertices", [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])):
            setattr(entity.dxf, f"vtx{i}", _make_vector(*vtx))
    elif etype == "UNKNOWN":
        pass

    return entity


class TestDxfParserInit:
    def test_default_init(self):
        parser = DxfParser()
        assert parser._expand_blocks is True
        assert parser._max_entities == 500000

    def test_custom_init(self):
        parser = DxfParser(expand_blocks=False, max_entities=1000)
        assert parser._expand_blocks is False
        assert parser._max_entities == 1000


class TestDxfParserFallback:
    @patch("engine.dxf_parser.HAS_EZDXF", False)
    def test_parse_when_no_ezdxf(self):
        parser = DxfParser()
        result = parser.parse("any_file.dxf")
        assert result["entities"] == []
        assert result["texts"] == []
        assert result["layers"] == {}
        assert result["entity_count"] == 0
        assert result["layer_count"] == 0
        assert "error" in result

    def test_fallback_parse_directly(self):
        parser = DxfParser()
        result = parser._fallback_parse("nonexistent.dxf")
        assert result["entity_count"] == 0
        assert result["layer_count"] == 0
        assert result["error"] == "ezdxf not available, fallback to empty"

    @patch("engine.dxf_parser.ezdxf")
    def test_parse_readfile_exception_triggers_fallback(self, mock_ezdxf):
        mock_ezdxf.readfile.side_effect = Exception("corrupt file")
        parser = DxfParser()
        result = parser.parse("bad_file.dxf")
        assert result["entity_count"] == 0
        assert "error" in result


class TestEntityToRecord:
    def setup_method(self):
        self.parser = DxfParser()
        self.doc = MagicMock()

    def test_line_entity(self):
        entity = _make_entity("LINE", start=(0, 0, 0), end=(3, 4, 0))
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "LINE"
        assert record["start"] == (0, 0, 0)
        assert record["end"] == (3, 4, 0)
        assert abs(record["length"] - 5.0) < 1e-9

    def test_circle_entity(self):
        entity = _make_entity("CIRCLE", center=(1, 2, 0), radius=5.0)
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "CIRCLE"
        assert record["center"] == (1, 2, 0)
        assert record["radius"] == 5.0
        assert record["diameter"] == 10.0

    def test_arc_entity(self):
        entity = _make_entity("ARC", center=(0, 0, 0), radius=2.0, start_angle=30, end_angle=120)
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "ARC"
        assert record["radius"] == 2.0
        assert record["start_angle"] == 30
        assert record["end_angle"] == 120

    def test_lwpolyline_entity(self):
        entity = _make_entity("LWPOLYLINE", points=[(0, 0), (3, 0), (3, 4)], closed=True)
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "LWPOLYLINE"
        assert len(record["points"]) == 3
        assert record["closed"] is True
        assert record["bbox_2d"] == (0, 0, 3, 4)

    def test_lwpolyline_empty_points(self):
        entity = _make_entity("LWPOLYLINE", points=[], closed=False)
        entity.get_points.return_value = []
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["points"] == []
        assert "bbox_2d" not in record

    def test_polyline_entity(self):
        entity = _make_entity("POLYLINE", points=[(0, 0), (1, 0), (1, 1)], is_closed=True)
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "POLYLINE"
        assert len(record["points"]) == 3
        assert record["closed"] is True

    def test_text_entity(self):
        entity = _make_entity("TEXT", text="hello world", position=(10, 20, 0), height=5.0, rotation=90)
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "TEXT"
        assert record["text"] == "hello world"
        assert record["position"] == (10, 20, 0)
        assert record["height"] == 5.0
        assert record["rotation"] == 90

    def test_mtext_entity(self):
        entity = _make_entity("MTEXT", text="mtext content", position=(1, 2, 0), height=3.0, rotation=45)
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "MTEXT"
        assert record["text"] == "mtext content"
        assert record["position"] == (1, 2, 0)
        assert record["height"] == 3.0
        assert record["rotation"] == 45

    def test_insert_entity(self):
        entity = _make_entity("INSERT", block_name="MY_BLOCK", position=(5, 10, 0), xscale=2.0, yscale=3.0, rotation=30)
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "INSERT"
        assert record["block_name"] == "MY_BLOCK"
        assert record["position"] == (5, 10, 0)
        assert record["xscale"] == 2.0
        assert record["yscale"] == 3.0
        assert record["rotation"] == 30

    def test_point_entity(self):
        entity = _make_entity("POINT", location=(7, 8, 9))
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "POINT"
        assert record["location"] == (7, 8, 9)

    def test_ellipse_entity(self):
        entity = _make_entity("ELLIPSE", center=(1, 1, 0), major_axis=(4, 0, 0), ratio=0.25)
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "ELLIPSE"
        assert record["center"] == (1, 1, 0)
        assert record["ratio"] == 0.25

    def test_solid_entity(self):
        entity = _make_entity("SOLID", vertices=[(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert record["type"] == "SOLID"
        assert len(record["vertices"]) == 4
        assert record["vertices"][0] == (0, 0, 0)

    def test_solid_partial_vertices(self):
        entity = _make_entity("SOLID")
        del entity.dxf.vtx3
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is not None
        assert len(record["vertices"]) == 3

    def test_unknown_entity_returns_none(self):
        entity = MagicMock()
        entity.dxftype.return_value = "UNKNOWN_TYPE"
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is None

    def test_entity_dxftype_exception_returns_none(self):
        entity = MagicMock()
        entity.dxftype.side_effect = Exception("broken")
        record = self.parser._entity_to_record(entity, self.doc)
        assert record is None


class TestTransformRecord:
    def setup_method(self):
        self.parser = DxfParser()

    def test_transform_with_scale_only(self):
        record = {
            "type": "LINE",
            "start": (1.0, 2.0, 0),
            "end": (3.0, 4.0, 0),
        }
        self.parser._transform_record(record, dx=10, dy=20, dz=0, sx=2, sy=3, rot=0)
        assert record["start"] == (1 * 2 + 10, 2 * 3 + 20, 0)
        assert record["end"] == (3 * 2 + 10, 4 * 3 + 20, 0)

    def test_transform_with_rotation(self):
        record = {"type": "POINT", "location": (1.0, 0.0, 0)}
        angle = math.pi / 2
        self.parser._transform_record(record, dx=0, dy=0, dz=0, sx=1, sy=1, rot=angle)
        x, y, z = record["location"]
        assert abs(x - 0.0) < 1e-9
        assert abs(y - 1.0) < 1e-9

    def test_transform_points_list(self):
        record = {
            "type": "LWPOLYLINE",
            "points": [(1.0, 2.0), (3.0, 4.0)],
        }
        self.parser._transform_record(record, dx=0, dy=0, dz=0, sx=2, sy=2, rot=0)
        assert record["points"][0] == (2.0, 4.0, 0)
        assert record["points"][1] == (6.0, 8.0, 0)

    def test_transform_vertices(self):
        record = {
            "type": "SOLID",
            "vertices": [(1.0, 1.0, 0.0)],
        }
        self.parser._transform_record(record, dx=5, dy=5, dz=0, sx=1, sy=1, rot=0)
        assert record["vertices"][0] == (6.0, 6.0, 0.0)

    def test_transform_no_geometry_keys(self):
        record = {"type": "UNKNOWN"}
        self.parser._transform_record(record, dx=1, dy=1, dz=0, sx=1, sy=1, rot=0)
        assert record == {"type": "UNKNOWN"}

    def test_transform_2d_point_gets_z_default(self):
        record = {"center": (1.0, 2.0)}
        self.parser._transform_record(record, dx=0, dy=0, dz=5, sx=1, sy=1, rot=0)
        assert record["center"] == (1.0, 2.0, 5.0)


class TestExpandBlock:
    def setup_method(self):
        self.parser = DxfParser()

    def test_expand_block_not_in_doc(self):
        insert_entity = _make_entity("INSERT", block_name="MISSING")
        doc = MagicMock()
        doc.blocks.__contains__ = MagicMock(return_value=False)
        result = self.parser._expand_block(insert_entity, doc, 0)
        assert result == {"entities": [], "texts": [], "layers": {}}

    def test_expand_block_exception_returns_empty(self):
        insert_entity = MagicMock()
        insert_entity.dxf.name = "BLOCK1"
        insert_entity.dxf.insert = None
        doc = MagicMock()
        result = self.parser._expand_block(insert_entity, doc, 0)
        assert result["entities"] == []
        assert result["texts"] == []

    def test_expand_block_with_sub_entities(self):
        sub_line = _make_entity("LINE", start=(0, 0, 0), end=(1, 0, 0), layer="sub_layer")
        sub_text = _make_entity("TEXT", text="in block", position=(0, 0, 0), layer="text_layer")

        block = MagicMock()
        block.__iter__ = MagicMock(return_value=iter([sub_line, sub_text]))

        doc = MagicMock()
        doc.blocks.__contains__ = MagicMock(return_value=True)
        doc.blocks.__getitem__ = MagicMock(return_value=block)

        insert_entity = _make_entity("INSERT", block_name="BLOCK1", position=(10, 20, 0), xscale=1, yscale=1, rotation=0)
        result = self.parser._expand_block(insert_entity, doc, 0)
        assert len(result["entities"]) == 1
        assert len(result["texts"]) == 1
        assert "sub_layer" in result["layers"]
        assert "text_layer" in result["layers"]


class TestParseIntegration:
    def setup_method(self):
        self.parser = DxfParser()

    @patch("engine.dxf_parser.ezdxf")
    def test_parse_with_mixed_entities(self, mock_ezdxf):
        line = _make_entity("LINE", start=(0, 0, 0), end=(1, 0, 0), layer="walls")
        circle = _make_entity("CIRCLE", center=(0, 0, 0), radius=5, layer="symbols")
        text = _make_entity("TEXT", text="room1", position=(1, 1, 0), layer="text")
        mtext = _make_entity("MTEXT", text="desc", position=(2, 2, 0), layer="text")

        msp = MagicMock()
        msp.__iter__ = MagicMock(return_value=iter([line, circle, text, mtext]))

        doc = MagicMock()
        doc.modelspace.return_value = msp
        mock_ezdxf.readfile.return_value = doc

        result = self.parser.parse("test.dxf")
        assert result["entity_count"] == 4
        assert len(result["entities"]) == 2
        assert len(result["texts"]) == 2
        assert "walls" in result["layers"]
        assert "symbols" in result["layers"]
        assert "text" in result["layers"]
        assert result["layers"]["text"] == 2
        assert result["layer_count"] == 3

    @patch("engine.dxf_parser.ezdxf")
    def test_parse_with_max_entities_limit(self, mock_ezdxf):
        entities = [_make_entity("LINE", start=(0, 0, 0), end=(1, 0, 0)) for _ in range(10)]
        msp = MagicMock()
        msp.__iter__ = MagicMock(return_value=iter(entities))

        doc = MagicMock()
        doc.modelspace.return_value = msp
        mock_ezdxf.readfile.return_value = doc

        parser = DxfParser(max_entities=3)
        result = parser.parse("test.dxf")
        assert result["entity_count"] <= 3

    @patch("engine.dxf_parser.ezdxf")
    def test_parse_insert_without_expand(self, mock_ezdxf):
        insert = _make_entity("INSERT", block_name="B1", layer="blocks")
        msp = MagicMock()
        msp.__iter__ = MagicMock(return_value=iter([insert]))

        doc = MagicMock()
        doc.modelspace.return_value = msp
        mock_ezdxf.readfile.return_value = doc

        parser = DxfParser(expand_blocks=False)
        result = parser.parse("test.dxf")
        assert len(result["entities"]) == 1
        assert result["entities"][0]["block_name"] == "B1"

    @patch("engine.dxf_parser.ezdxf")
    def test_parse_insert_with_expand(self, mock_ezdxf):
        sub_line = _make_entity("LINE", start=(0, 0, 0), end=(1, 0, 0), layer="sub")

        block = MagicMock()
        block.__iter__ = MagicMock(return_value=iter([sub_line]))

        doc = MagicMock()
        doc.blocks.__contains__ = MagicMock(return_value=True)
        doc.blocks.__getitem__ = MagicMock(return_value=block)

        insert = _make_entity("INSERT", block_name="B1", layer="blocks", position=(0, 0, 0))
        msp = MagicMock()
        msp.__iter__ = MagicMock(return_value=iter([insert]))
        doc.modelspace.return_value = msp
        mock_ezdxf.readfile.return_value = doc

        parser = DxfParser(expand_blocks=True)
        result = parser.parse("test.dxf")
        assert any(e.get("layer") == "sub" for e in result["entities"])

    @patch("engine.dxf_parser.ezdxf")
    def test_parse_empty_modelspace(self, mock_ezdxf):
        msp = MagicMock()
        msp.__iter__ = MagicMock(return_value=iter([]))

        doc = MagicMock()
        doc.modelspace.return_value = msp
        mock_ezdxf.readfile.return_value = doc

        result = self.parser.parse("empty.dxf")
        assert result["entities"] == []
        assert result["texts"] == []
        assert result["entity_count"] == 0
        assert result["layer_count"] == 0

    @patch("engine.dxf_parser.ezdxf")
    def test_parse_unknown_entity_skipped(self, mock_ezdxf):
        unknown = MagicMock()
        unknown.dxftype.return_value = "DIMENSION"
        msp = MagicMock()
        msp.__iter__ = MagicMock(return_value=iter([unknown]))

        doc = MagicMock()
        doc.modelspace.return_value = msp
        mock_ezdxf.readfile.return_value = doc

        result = self.parser.parse("test.dxf")
        assert result["entity_count"] == 0


class TestRealDxfFile:
    def test_parse_real_dxf_with_ezdxf(self):
        try:
            import ezdxf
        except ImportError:
            pytest.skip("ezdxf not installed")

        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "walls"})
        msp.add_circle((5, 5), radius=3, dxfattribs={"layer": "symbols"})
        msp.add_text("Room A", dxfattribs={"layer": "text", "height": 2.5}).set_placement((5, 5))
        msp.add_mtext("Description", dxfattribs={"layer": "text"})
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={"layer": "outline"})
        msp.add_point((3, 3), dxfattribs={"layer": "points"})

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            temp_path = f.name

        try:
            doc.saveas(temp_path)
            parser = DxfParser()
            result = parser.parse(temp_path)

            assert result["entity_count"] >= 6
            assert "walls" in result["layers"]
            assert "symbols" in result["layers"]
            assert len(result["texts"]) >= 2
            assert any(e["type"] == "LINE" for e in result["entities"])
            assert any(e["type"] == "CIRCLE" for e in result["entities"])
            assert any(e["type"] == "LWPOLYLINE" for e in result["entities"])
            assert any(e["type"] == "POINT" for e in result["entities"])
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_parse_nonexistent_file_triggers_fallback(self):
        parser = DxfParser()
        result = parser.parse("Z:\\absolutely\\nonexistent\\path\\file.dxf")
        assert result["entity_count"] == 0
        assert "error" in result
