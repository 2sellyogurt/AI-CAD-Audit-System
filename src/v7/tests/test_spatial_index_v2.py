# -*- coding: utf-8 -*-
"""五级空间索引单元测试"""

import sys
import os
# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from v7.spatial_reasoning import SpatialEntityV2, SpatialIndexV2


def test_spatial_entity_v2():
    """测试五级空间实体"""
    entity = SpatialEntityV2(
        entity_type="beam",
        discipline="structure",
        drawing_name="test_drawing",
        layer="S-BEAM",
        x_min=0, y_min=0, x_max=100, y_max=50,
        floor_level=3.0,
        building="1",
        component="beam"
    )
    assert entity.building == "1"
    assert entity.component == "beam"
    assert entity.floor_level == 3.0
    print("✓ SpatialEntityV2 基础测试通过")


def test_spatial_index_v2_build():
    """测试五级索引构建"""
    index = SpatialIndexV2()

    entities = [
        SpatialEntityV2(
            entity_type="beam", discipline="structure", drawing_name="struct_1f",
            layer="S-BEAM", x_min=0, y_min=0, x_max=100, y_max=50,
            floor_level=1.0, building="1", component="beam"
        ),
        SpatialEntityV2(
            entity_type="duct", discipline="hvac", drawing_name="hvac_1f",
            layer="M-DUCT", x_min=20, y_min=10, x_max=80, y_max=40,
            floor_level=1.0, building="1", component="duct"
        ),
        SpatialEntityV2(
            entity_type="beam", discipline="structure", drawing_name="struct_2f",
            layer="S-BEAM", x_min=0, y_min=0, x_max=100, y_max=50,
            floor_level=2.0, building="1", component="beam"
        ),
    ]

    index.build(entities)

    # 验证五级索引结构
    assert "1" in index._index  # building
    assert 1.0 in index._index["1"]  # floor
    assert 2.0 in index._index["1"]  # floor
    assert "structure" in index._index["1"][1.0]  # discipline
    assert "hvac" in index._index["1"][1.0]  # discipline
    assert "beam" in index._index["1"][1.0]["structure"]  # component
    assert "duct" in index._index["1"][1.0]["hvac"]  # component

    print("✓ SpatialIndexV2 构建测试通过")


def test_spatial_index_v2_query():
    """测试五级索引查询"""
    index = SpatialIndexV2()

    entities = [
        SpatialEntityV2(
            entity_type="beam", discipline="structure", drawing_name="struct_1f",
            layer="S-BEAM", x_min=0, y_min=0, x_max=100, y_max=50,
            floor_level=1.0, building="1", component="beam"
        ),
        SpatialEntityV2(
            entity_type="duct", discipline="hvac", drawing_name="hvac_1f",
            layer="M-DUCT", x_min=20, y_min=10, x_max=80, y_max=40,
            floor_level=1.0, building="1", component="duct"
        ),
        SpatialEntityV2(
            entity_type="pipe", discipline="plumbing", drawing_name="plumb_1f",
            layer="P-PIPE", x_min=30, y_min=20, x_max=70, y_max=30,
            floor_level=1.0, building="1", component="pipe"
        ),
    ]

    index.build(entities)

    # 测试按楼层查询
    floor_1_entities = index.query(floor=1.0)
    assert len(floor_1_entities) == 3

    # 测试按专业查询
    structure_entities = index.query(discipline="structure")
    assert len(structure_entities) == 1
    assert structure_entities[0].entity_type == "beam"

    # 测试按构件查询
    duct_entities = index.query(component="duct")
    assert len(duct_entities) == 1
    assert duct_entities[0].entity_type == "duct"

    # 测试组合查询
    hvac_1f = index.query(floor=1.0, discipline="hvac")
    assert len(hvac_1f) == 1
    assert hvac_1f[0].component == "duct"

    # 测试 bbox 查询
    bbox = (10, 5, 90, 45)
    bbox_entities = index.query(bbox=bbox)
    assert len(bbox_entities) == 3  # 所有实体都在 bbox 内

    print("✓ SpatialIndexV2 查询测试通过")


def test_backward_compatibility():
    """测试向后兼容性（旧的两级接口）"""
    index = SpatialIndexV2()

    entities = [
        SpatialEntityV2(
            entity_type="beam", discipline="structure", drawing_name="struct_1f",
            layer="S-BEAM", x_min=0, y_min=0, x_max=100, y_max=50,
            floor_level=1.0, building="1", component="beam"
        ),
        SpatialEntityV2(
            entity_type="duct", discipline="hvac", drawing_name="hvac_1f",
            layer="M-DUCT", x_min=20, y_min=10, x_max=80, y_max=40,
            floor_level=1.0, building="1", component="duct"
        ),
    ]

    index.build(entities)

    # 测试旧接口 get_entities
    struct_entities = index.get_entities(floor_id=1.0, discipline="structure")
    assert len(struct_entities) == 1

    # 测试旧接口 query_bbox_overlap
    overlaps = index.query_bbox_overlap(floor_id=1.0, disc_a="structure", disc_b="hvac")
    assert len(overlaps) > 0  # beam 和 duct 有重叠

    print("✓ 向后兼容性测试通过")


def test_vlm_semantic_extractor():
    """测试 VLM 语义提取器（仅测试正则 fallback）"""
    from v7.preprocessor.vlm_semantic_extractor import VLMSemanticExtractor

    extractor = VLMSemanticExtractor()

    # 测试正则提取（无图片）
    label = extractor.extract_all(
        image_path="",
        drawing_name="1号楼-3层-结构平面图.dxf",
        dxf_layers=["S-BEAM", "S-COLUMN", "S-WALL"]
    )

    assert label.building == "1"
    assert label.floor == 3
    assert label.source == "regex"
    assert "beam" in label.components
    assert "column" in label.components
    assert "wall" in label.components

    print("✓ VLM 语义提取器测试通过")


if __name__ == "__main__":
    print("开始五级空间索引单元测试...\n")

    test_spatial_entity_v2()
    test_spatial_index_v2_build()
    test_spatial_index_v2_query()
    test_backward_compatibility()
    test_vlm_semantic_extractor()

    print("\n✅ 所有测试通过！")
