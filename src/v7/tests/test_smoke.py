# -*- coding: utf-8 -*-
"""冒烟测试 —— 覆盖 TODO_FIXES.md P2-7 中6个零测试模块的核心纯逻辑路径。

运行: pytest v7/tests/test_smoke.py -v
"""
import pytest
import sys
import os

_proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proj not in sys.path:
    sys.path.insert(0, _proj)


# ============================================================
# 1. building_classification — 建筑分类匹配
# ============================================================

class TestBuildingClassification:
    def test_get_all_ancestors_exact_match(self):
        from config.building_classification import get_all_ancestors
        result = get_all_ancestors("中小学")
        assert "中小学" in result
        assert "学校" in result
        assert "公建" in result
        assert "民用" in result

    def test_get_all_ancestors_root_only(self):
        from config.building_classification import get_all_ancestors
        result = get_all_ancestors("民用")
        assert result == {"民用"}

    def test_get_all_descendants(self):
        from config.building_classification import get_all_descendants
        result = get_all_descendants("学校")
        assert "中小学" in result
        assert "大学" in result
        assert "学校" in result

    def test_match_building_type_exact(self):
        from config.building_classification import match_building_type
        assert match_building_type("中小学", ["中小学"]) is True

    def test_match_building_type_upward(self):
        from config.building_classification import match_building_type
        # "中小学" 的上级有 "学校"/"公建"
        assert match_building_type("中小学", ["学校"]) is True
        assert match_building_type("中小学", ["公建"]) is True

    def test_match_building_type_downward(self):
        from config.building_classification import match_building_type
        # "学校" 包含子级 "中小学"
        assert match_building_type("中小学", ["学校"]) is True

    def test_match_building_type_no_match(self):
        from config.building_classification import match_building_type
        assert match_building_type("住宅", ["学校", "医院"]) is False

    def test_match_building_type_empty(self):
        from config.building_classification import match_building_type
        # 空项目类型/空适用类型 → 默认通过
        assert match_building_type("", ["学校"]) is True
        assert match_building_type("住宅", []) is True


# ============================================================
# 2. rationality_engine — 合理性评估（纯数学）
# ============================================================

class TestRationalityEngine:
    def test_classify_rationality_r3(self):
        """score > 80 = R3 设计优秀"""
        from v7.rationality_engine import classify_rationality
        level, _ = classify_rationality(95)
        assert level == "R3"

    def test_classify_rationality_r2(self):
        """56-80 = R2 设计基本合理"""
        from v7.rationality_engine import classify_rationality
        level, _ = classify_rationality(75)
        assert level == "R2"

    def test_classify_rationality_r0(self):
        """<= 30 = R0 设计不可行"""
        from v7.rationality_engine import classify_rationality
        level, _ = classify_rationality(30)
        assert level == "R0"

    def test_classify_rationality_r1(self):
        """31-55 = R1 条文合格但非最优"""
        from v7.rationality_engine import classify_rationality
        level, _ = classify_rationality(42)
        assert level == "R1"

    def test_make_rationality(self):
        from v7.rationality_engine import make_rationality
        r = make_rationality("R1", 42, "疏散宽度略大于规范最低要求")
        assert r["level"] == "R1"
        assert r["score"] == 42
        assert "疏散宽度" in r["explanation"]

    def test_evaluate_evacuation_pass(self):
        from v7.rationality_engine import evaluate_evacuation
        r = evaluate_evacuation(occupants=500, doors_width=4.0,
                                building_type="多层", use_type="教学楼",
                                max_distance=20)
        assert r["level"] in ("R0", "R1", "R2", "R3")
        assert 0 <= r["score"] <= 100

    def test_evaluate_pipe_layout_basic(self):
        from v7.rationality_engine import evaluate_pipe_layout
        r = evaluate_pipe_layout({
            "horizontal_margin": 0.15, "vertical_margin": 0.30,
            "pipe_type1": "给水", "pipe_type2": "排水",
            "has_maintenance_space": True,
            "construction_order_ok": True, "valve_accessible": True,
        })
        assert r["level"] in ("R0", "R1", "R2", "R3")

    def test_annotate_all_rationality(self):
        from v7.rationality_engine import annotate_all_rationality
        findings = [{"id": "F-001", "severity": "B"}]
        result = annotate_all_rationality(findings)
        assert len(result) == 1
        assert "rationality" in result[0]


# ============================================================
# 3. cross_drawing — 正则提取逻辑
# ============================================================

class TestCrossDrawing:
    def test_floor_pattern_match(self):
        from v7.cross_drawing.cross_context import FLOOR_PATTERN
        matches = FLOOR_PATTERN.findall("一层平面图 二层 地下1层 BF2")
        assert len(matches) >= 3

    def test_fire_rating_pattern_cn(self):
        from v7.cross_drawing.cross_context import FIRE_RATING_PATTERN
        m = FIRE_RATING_PATTERN.search("耐火等级：一级")
        assert m is not None
        assert "一级" in m.group()

    def test_dimension_pattern(self):
        from v7.cross_drawing.cross_context import GENERIC_DIM_PATTERN
        m = GENERIC_DIM_PATTERN.search("宽度 3600mm")
        assert m is not None

    def test_elevation_pattern(self):
        from v7.cross_drawing.cross_context import ELEVATION_PATTERN
        m = ELEVATION_PATTERN.search("标高: 3.60m")
        assert m is not None

    def test_is_spatial_drawing_yes(self):
        from v7.cross_drawing.cross_context import CrossDrawingContext
        assert CrossDrawingContext._is_spatial_drawing("一层平面图") is True

    def test_is_spatial_drawing_no(self):
        from v7.cross_drawing.cross_context import CrossDrawingContext
        assert CrossDrawingContext._is_spatial_drawing("设计说明") is False
        assert CrossDrawingContext._is_spatial_drawing("目录") is False

    def test_add_drawing_and_analyze(self):
        from v7.cross_drawing.cross_context import CrossDrawingContext
        ctx = CrossDrawingContext()
        ctx.add_drawing("一层平面图", "building",
                       "1-10轴 A-F轴 一层 标高: 3.60m 101 办公室 耐火等级：一级")
        ctx.add_drawing("二层平面图", "building",
                       "1-10轴 A-F轴 二层 标高: 7.20m 201 办公室 耐火等级：一级")
        issues = ctx.analyze()
        assert isinstance(issues, list)


# ============================================================
# 4. CheckpointEngine — YAML加载 + 路由 + 统计（不调LLM）
# ============================================================

class TestCheckpointEngine:
    @pytest.fixture
    def engine(self):
        from v7.checkpoints import CheckpointEngine
        return CheckpointEngine()

    def test_loads_all_checkpoints(self, engine):
        assert engine.total_count > 0

    def test_all_ordered_by_priority(self, engine):
        cps = engine.all_checkpoints
        for i in range(len(cps) - 1):
            if cps[i].discipline == cps[i + 1].discipline:
                assert cps[i].priority >= cps[i + 1].priority, \
                    f"{cps[i].id} priority {cps[i].priority} < {cps[i+1].id} {cps[i+1].priority}"

    def test_get_returns_checkpoint(self, engine):
        cp = engine.get("FIRE-001")
        assert cp is not None
        assert cp.id == "FIRE-001"

    def test_get_nonexistent_returns_none(self, engine):
        assert engine.get("NONEXIST-999") is None

    def test_list_by_discipline(self, engine):
        building = engine.list_by_discipline("building")
        fire = engine.list_by_discipline("fire")
        assert len(building) > 0
        assert len(fire) > 0

    def test_list_by_type(self, engine):
        text_presence = engine.list_by_type("text_presence")
        dimension_min = engine.list_by_type("dimension_min")
        assert isinstance(text_presence, list)
        assert isinstance(dimension_min, list)

    def test_resolve_route_a_dual(self, engine):
        from v7.checkpoints import Route
        cp = engine.get("FIRE-001")  # severity A
        assert engine.resolve_route(cp) == Route.DUAL

    def test_resolve_route_b_dual(self, engine):
        from v7.checkpoints import Route
        # B级也强制升级为dual
        for cp in engine.all_checkpoints:
            if cp.severity.value == "B":
                assert engine.resolve_route(cp) == Route.DUAL, \
                    f"{cp.id}: B级应强制dual"

    def test_resolve_route_c_keeps_route(self, engine):
        from v7.checkpoints import Route
        # C级保持原route
        for cp in engine.all_checkpoints:
            if cp.severity.value == "C" and cp.route.value == "text":
                assert engine.resolve_route(cp) == Route.TEXT, \
                    f"{cp.id}: C级text应保持text"
                break  # 只测一个

    def test_get_statistics(self):
        from v7.checkpoints import CheckResult, Severity
        results = [
            CheckResult(checkpoint_id="T01", checkpoint_name="测试1", severity=Severity.A,
                       verdict="不合规", confidence=0.95, route_used="dual"),
            CheckResult(checkpoint_id="T02", checkpoint_name="测试2", severity=Severity.B,
                       verdict="合规", confidence=0.98, route_used="text"),
        ]
        from v7.checkpoints import CheckpointEngine
        engine = CheckpointEngine()
        stats = engine.get_statistics(results)
        assert stats["total"] == 2
        assert stats["compliant"] == 1
        assert stats["non_compliant"] == 1

    def test_reload(self, engine):
        before = engine.total_count
        engine.reload()
        assert engine.total_count == before


# ============================================================
# 5. discipline_agents — 图纸过滤 //AGENT注册
# ============================================================

class TestAgentFiltering:
    def test_content_keywords_exist(self):
        from v7.agents.discipline_agents import CONTENT_DISCIPLINE_KEYWORDS
        assert "building" in CONTENT_DISCIPLINE_KEYWORDS
        assert len(CONTENT_DISCIPLINE_KEYWORDS["building"]) > 0
        assert "structure" in CONTENT_DISCIPLINE_KEYWORDS

    def test_agent_registry_all_instantiable(self):
        from v7.agents import AGENT_REGISTRY
        for aid, cls in AGENT_REGISTRY.items():
            agent = cls()
            assert agent.config.agent_id, f"{aid}: missing agent_id"
            prompt = agent.build_system_prompt()
            assert prompt, f"{aid}: empty system prompt"

    def test_filter_with_content_fallback(self):
        from v7.agents.discipline_agents import _filter_with_content_fallback
        from v7.agents.discipline_agents import CONTENT_DISCIPLINE_KEYWORDS

        class FakeDrawing:
            def __init__(self, discipline, text):
                self.discipline = discipline
                self.text_content = text
                self.filename = "test.dxf"

        drawings = [
            FakeDrawing("building", "一层平面图 楼梯 电梯 防火门"),
            FakeDrawing("hvac", "风管 送风 排烟"),
            FakeDrawing("unknown", "some general notes"),
        ]
        result = _filter_with_content_fallback(
            drawings, ["building"], CONTENT_DISCIPLINE_KEYWORDS["building"], "test")
        assert len(result) >= 1
        matched_ids = {d.discipline for d in result}
        assert "building" in matched_ids

    def test_free_review_no_filter(self):
        from v7.agents.discipline_agents import FreeReviewAgent

        class FakeDrawing:
            def __init__(self, discipline):
                self.discipline = discipline

        drawings = [FakeDrawing("building"), FakeDrawing("hvac")]
        agent = FreeReviewAgent()
        result = agent.filter_drawings(drawings)
        assert len(result) == 2


# ============================================================
# 6. ProblemPool — 问题添加/统计/导出（不调LLM）
# ============================================================

class TestProblemPool:
    def test_add_and_get(self):
        from v7.problem_pool import ProblemPool, UnifiedIssue
        pool = ProblemPool()
        issue = UnifiedIssue(
            issue_id="TEST-001", discipline="building",
            severity="B", description="测试问题", suggestion="修复测试")
        pool.add_issue(issue)
        assert pool.get("TEST-001") is not None
        assert pool.issue_count == 1

    def test_count_by_severity(self):
        from v7.problem_pool import ProblemPool, UnifiedIssue
        pool = ProblemPool()
        for i in range(3):
            pool.add_issue(UnifiedIssue(
                issue_id=f"T-{i}", discipline="fire",
                severity="A", description="x", suggestion="y"))
        pool.add_issue(UnifiedIssue(
            issue_id="T-3", discipline="fire",
            severity="C", description="x", suggestion="y"))
        counts = pool.count_by_severity()
        assert counts.get("A") == 3
        assert counts.get("C") == 1

    def test_get_by_discipline(self):
        from v7.problem_pool import ProblemPool, UnifiedIssue
        pool = ProblemPool()
        pool.add_issue(UnifiedIssue(
            issue_id="D1", discipline="plumbing",
            severity="B", description="d", suggestion="f"))
        pipes = pool.get_by_discipline("plumbing")
        assert len(pipes) == 1

    def test_record_compliance(self):
        from v7.problem_pool import ProblemPool
        pool = ProblemPool()
        pool.record_compliance(
            "CHK-001", "测试合规", "B", "建筑Agent", 0.98, "一层平面", "text")
        compliant = pool.get_compliant_results()
        assert len(compliant) == 1
        assert compliant[0]["checkpoint_id"] == "CHK-001"

    def test_stats(self):
        from v7.problem_pool import ProblemPool, UnifiedIssue
        pool = ProblemPool()
        pool.add_issue(UnifiedIssue(
            issue_id="S-1", discipline="plumbing",
            severity="A", description="d", suggestion="f"))
        s = pool.stats()
        assert s["total_issues"] == 1
        assert "by_severity" in s
