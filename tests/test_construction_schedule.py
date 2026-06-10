# -*- coding: utf-8 -*-
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.spatial_model import (
    BBox3D, Discipline, ElementCategory, SpatialElement, SpatialModel,
)
from engine.construction_schedule import (
    ConstructionScheduler, ScheduleResult, PhaseTask,
    PHASE_SEQUENCE, PHASE_DEPENDENCIES, _CATEGORY_PHASE_MAP,
)


def _make_element(elem_id, discipline, category, x=0, y=0, z=0, floor="1F"):
    bbox = BBox3D(x, y, z, x + 100, y + 100, z + 100)
    return SpatialElement(
        element_id=elem_id, discipline=discipline, category=category,
        bbox=bbox, floor=floor,
    )


def _build_sample_model():
    model = SpatialModel()
    model.add_element(_make_element("f1", Discipline.STRUCTURE, ElementCategory.FOUNDATION, z=0))
    model.add_element(_make_element("c1", Discipline.STRUCTURE, ElementCategory.COLUMN, z=0))
    model.add_element(_make_element("c2", Discipline.STRUCTURE, ElementCategory.COLUMN, z=3000))
    model.add_element(_make_element("b1", Discipline.STRUCTURE, ElementCategory.BEAM, z=3000))
    model.add_element(_make_element("s1", Discipline.STRUCTURE, ElementCategory.SLAB, z=3000))
    model.add_element(_make_element("w1", Discipline.ARCHITECTURE, ElementCategory.WALL, z=0))
    model.add_element(_make_element("d1", Discipline.ARCHITECTURE, ElementCategory.DOOR, z=0))
    model.add_element(_make_element("p1", Discipline.MEP, ElementCategory.PIPE, z=2500))
    model.add_element(_make_element("h1", Discipline.MEP, ElementCategory.DUCT, z=2800))
    return model


class TestConstructionScheduler:
    def test_basic_schedule(self):
        model = _build_sample_model()
        scheduler = ConstructionScheduler(teams=4)
        result = scheduler.generate_schedule(model)

        assert isinstance(result, ScheduleResult)
        assert result.total_duration_days > 0
        assert result.total_effort_days > 0
        assert len(result.tasks) > 0

    def test_schedule_has_all_phases(self):
        model = _build_sample_model()
        scheduler = ConstructionScheduler()
        result = scheduler.generate_schedule(model)

        phase_names = [t.phase_name for t in result.tasks]
        for expected in PHASE_SEQUENCE:
            assert expected in phase_names, f"缺少阶段: {expected}"

    def test_schedule_order_respects_dependencies(self):
        model = _build_sample_model()
        scheduler = ConstructionScheduler()
        result = scheduler.generate_schedule(model)

        task_map = {t.phase_name: t for t in result.tasks}
        for phase_name, deps in PHASE_DEPENDENCIES.items():
            task = task_map[phase_name]
            for dep_name in deps:
                dep_task = task_map[dep_name]
                assert task.start_day >= dep_task.end_day, (
                    f"{phase_name} 在第{task.start_day}天开始，但依赖 {dep_name} 在第{dep_task.end_day}天才结束"
                )

    def test_empty_model(self):
        model = SpatialModel()
        scheduler = ConstructionScheduler()
        result = scheduler.generate_schedule(model)

        assert isinstance(result, ScheduleResult)
        assert result.total_duration_days >= 0
        assert result.total_effort_days == 0

    def test_element_summary(self):
        model = _build_sample_model()
        scheduler = ConstructionScheduler()
        result = scheduler.generate_schedule(model)

        assert "column" in result.element_summary
        assert result.element_summary["column"] == 2
        assert result.element_summary["beam"] == 1
        assert result.element_summary["wall"] == 1

    def test_floor_schedule(self):
        model = _build_sample_model()
        scheduler = ConstructionScheduler()
        result = scheduler.generate_schedule(model)

        assert len(result.floor_schedule) > 0
        floor_1f = [f for f in result.floor_schedule if f["floor"] == "1F"]
        assert len(floor_1f) == 1
        assert floor_1f[0]["structure_count"] > 0

    def test_teams_affects_duration(self):
        model = _build_sample_model()
        sched_1 = ConstructionScheduler(teams=1)
        sched_10 = ConstructionScheduler(teams=10)
        r1 = sched_1.generate_schedule(model)
        r10 = sched_10.generate_schedule(model)

        assert r10.total_duration_days <= r1.total_duration_days

    def test_to_dict(self):
        model = _build_sample_model()
        scheduler = ConstructionScheduler()
        result = scheduler.generate_schedule(model)
        d = result.to_dict()

        assert "tasks" in d
        assert "total_duration_days" in d
        assert "total_effort_days" in d
        assert "element_summary" in d
        assert "floor_schedule" in d
        assert len(d["tasks"]) == len(result.tasks)

    def test_phase_task_to_dict(self):
        model = _build_sample_model()
        scheduler = ConstructionScheduler()
        result = scheduler.generate_schedule(model)

        for task in result.tasks:
            d = task.to_dict()
            assert "phase_name" in d
            assert "element_count" in d
            assert "duration_days" in d
            assert "start_day" in d
            assert "end_day" in d
            assert "dependencies" in d


class TestCategoryPhaseMap:
    def test_all_categories_mapped(self):
        for cat in ElementCategory:
            if cat == ElementCategory.UNKNOWN:
                continue
            assert cat in _CATEGORY_PHASE_MAP, f"{cat.value} 未映射到施工阶段"

    def test_structure_in_main_phase(self):
        assert _CATEGORY_PHASE_MAP[ElementCategory.COLUMN] == "结构工程"
        assert _CATEGORY_PHASE_MAP[ElementCategory.BEAM] == "结构工程"
        assert _CATEGORY_PHASE_MAP[ElementCategory.FOUNDATION] == "结构工程"

    def test_architecture_mapped(self):
        assert _CATEGORY_PHASE_MAP[ElementCategory.WALL] == "二构墙体砌筑"
        assert _CATEGORY_PHASE_MAP[ElementCategory.DOOR] == "二构墙体砌筑"

    def test_mep_mapped(self):
        assert _CATEGORY_PHASE_MAP[ElementCategory.PIPE] == "机电管线施工"
        assert _CATEGORY_PHASE_MAP[ElementCategory.DUCT] == "机电管线施工"
