# -*- coding: utf-8 -*-
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.issue_formatter import (
    IssueFormatter, IssueRecord, convert_legacy_issue,
)


class TestIssueRecord:
    def test_to_dict(self):
        r = IssueRecord(
            issue_id="TEST-001",
            source_step="step2_compliance",
            severity="高",
            category="强制条文合规",
            drawing_a="建筑-教学楼平面图",
            building="教学楼",
            floor="3F",
            regulation_code="GB 55038-2025 第4.1.2条",
            regulation_clause="住宅卧室室内净高不应低于2.4m",
            compliance_status="不合规",
        )
        d = r.to_dict()
        assert d["issue_id"] == "TEST-001"
        assert d["drawing"]["a"] == "建筑-教学楼平面图"
        assert d["location"]["building"] == "教学楼"
        assert d["location"]["floor"] == "3F"
        assert d["regulation"]["code"] == "GB 55038-2025 第4.1.2条"

    def test_to_markdown(self):
        r = IssueRecord(
            issue_id="TEST-001",
            severity="高",
            category="碰撞检测",
            drawing_a="结构-梁图",
            drawing_b="暖通-风管图",
            comparison_type="管线穿梁",
            building="教学楼",
            floor="2F",
            regulation_code="GB 50016-2014 第5.3.1条",
            compliance_status="存在冲突",
        )
        md = r.to_markdown()
        assert "图纸定位" in md
        assert "结构-梁图" in md
        assert "暖通-风管图" in md
        assert "空间定位" in md
        assert "教学楼" in md
        assert "规范依据" in md
        assert "GB 50016-2014" in md

    def test_single_drawing(self):
        r = IssueRecord(
            drawing_a="建筑-平面图",
            regulation_code="GB 55038-2025",
        )
        md = r.to_markdown()
        assert "来源图纸" in md
        assert "建筑-平面图" in md


class TestIssueFormatter:
    def test_add_issue(self):
        f = IssueFormatter()
        r = IssueRecord(severity="中", category="测试")
        f.add_issue(r)
        assert f.issue_count == 1
        assert f.issues[0].issue_id != ""

    def test_auto_id(self):
        f = IssueFormatter()
        r1 = IssueRecord()
        r2 = IssueRecord()
        f.add_issue(r1)
        f.add_issue(r2)
        assert r1.issue_id != r2.issue_id

    def test_create_rule_issue(self):
        f = IssueFormatter()
        r = f.create_rule_issue(
            rule_id="rule_001",
            rule_description="净高不应低于2.4m",
            standard_code="GB 55038-2025 第4.1.2条",
            drawing_name="建筑-平面图",
            building="教学楼",
            floor="3F",
            severity="高",
        )
        assert r.source_step == "step2_compliance"
        assert r.drawing_a == "建筑-平面图"
        assert r.building == "教学楼"
        assert r.regulation_code == "GB 55038-2025 第4.1.2条"

    def test_create_collision_issue(self):
        f = IssueFormatter()
        r = f.create_collision_issue(
            drawing_a="结构-梁图",
            drawing_b="暖通-风管图",
            building="教学楼",
            floor="2F",
            component_a="KL-1",
            component_b="风管-01",
            collision_type="管线穿梁",
            severity="严重",
        )
        assert r.source_step == "step3_defect"
        assert r.drawing_b == "暖通-风管图"
        assert "KL-1" in r.component

    def test_create_cross_check_issue(self):
        f = IssueFormatter()
        r = f.create_cross_check_issue(
            drawing_a="结构-图1",
            drawing_b="建筑-图1",
            check_name="轴线不一致",
            severity="高",
            regulation_code="GB 50001-2017 第2.1.2条",
        )
        assert r.source_step == "step4_cross_check"
        assert r.category == "跨专业不一致"

    def test_to_list(self):
        f = IssueFormatter()
        f.create_rule_issue(rule_id="r1", rule_description="测试", standard_code="GB", drawing_name="图1")
        f.create_collision_issue(drawing_a="图A", drawing_b="图B")
        lst = f.to_list()
        assert len(lst) == 2
        assert "drawing" in lst[0]
        assert "location" in lst[0]

    def test_to_markdown(self):
        f = IssueFormatter()
        f.create_rule_issue(
            rule_id="r1", rule_description="净高检查",
            standard_code="GB 55038-2025", drawing_name="图1",
            severity="高",
        )
        md = f.to_markdown()
        assert "三段式问题清单" in md
        assert "图纸定位" in md

    def test_to_markdown_empty(self):
        f = IssueFormatter()
        md = f.to_markdown()
        assert "无问题" in md

    def test_to_snapshot(self):
        f = IssueFormatter()
        f.create_rule_issue(rule_id="r1", rule_description="测试", standard_code="GB", drawing_name="图1")
        snap = f.to_snapshot()
        assert snap["total_issues"] == 1
        assert "by_severity" in snap
        assert "by_source" in snap


class TestConvertLegacyIssue:
    def test_basic_conversion(self):
        legacy = {
            "source": "规则检查",
            "category": "建筑",
            "key": "净高不应低于2.4m",
            "severity": "高",
            "file": "建筑-平面图",
            "building": "教学楼",
            "floor": "3F",
            "standard_code": "GB 55038-2025 第4.1.2条",
        }
        r = convert_legacy_issue(legacy, "step2_compliance")
        assert r.drawing_a == "建筑-平面图"
        assert r.building == "教学楼"
        assert r.floor == "3F"
        assert r.severity == "高"
        assert "GB 55038" in r.regulation_code

    def test_cross_check_conversion(self):
        legacy = {
            "check_name": "轴线一致性",
            "discipline_a": "structural",
            "discipline_b": "architectural",
            "status": "non_compliant",
            "severity": "high",
            "description": "轴线比对不一致",
        }
        r = convert_legacy_issue(legacy, "step4_cross_check")
        assert r.source_step == "step4_cross_check"
        assert r.category == "轴线一致性"
