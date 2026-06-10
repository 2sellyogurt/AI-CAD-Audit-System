# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.step6_persistence import (
    collect_all_issues,
    generate_snapshot,
    compare_snapshots,
)


class TestCollectAllIssues:

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            issues = collect_all_issues(tmpdir)
            assert issues == []

    def test_with_step2_data_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            step2_data = {
                "rule_results": [
                    {"rule_id": "R001", "description": "问题1", "severity": "高", "category": "建筑"},
                    {"rule_id": "R002", "description": "问题2", "severity": "中", "category": "结构"},
                ]
            }
            path = os.path.join(tmpdir, "step2_compliance_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(step2_data, f)

            issues = collect_all_issues(tmpdir)
            assert len(issues) == 2
            assert issues[0]["source"] == "step2_compliance"

    def test_with_step2_data_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            step2_data = {
                "rule_results": {
                    "建筑": [
                        {"rule_id": "R001", "description": "问题1", "severity": "高"},
                    ]
                }
            }
            path = os.path.join(tmpdir, "step2_compliance_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(step2_data, f)

            issues = collect_all_issues(tmpdir)
            assert len(issues) == 1
            assert issues[0]["source"] == "step2_compliance"
            assert issues[0]["category"] == "建筑"

    def test_with_step3_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            step3_data = {
                "collision_results": {
                    "tray_issues": [
                        {"rule_id": "C001", "description": "桥架碰撞", "severity": "中"},
                    ],
                    "pipe_spacing_issues": [
                        {"rule_id": "C002", "description": "管线间距不足", "severity": "低"},
                    ],
                }
            }
            path = os.path.join(tmpdir, "step3_defect_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(step3_data, f)

            issues = collect_all_issues(tmpdir)
            assert len(issues) == 2
            assert issues[0]["source"] == "step3_defect"
            assert issues[0]["category"] == "tray_issues"

    def test_with_step4_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            step4_data = {
                "cross_results": {
                    "cross_results": [
                        {"check_name": "轴线一致性", "status": "不一致", "severity": "高"},
                    ],
                    "deep_cross_results": [
                        {"check_name": "梁高vs净高", "status": "一致"},
                    ],
                }
            }
            path = os.path.join(tmpdir, "step4_cross_check_result.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(step4_data, f)

            issues = collect_all_issues(tmpdir)
            assert len(issues) == 2
            assert issues[0]["source"] == "step4_cross_check"
            assert issues[0]["category"] == "basic"
            assert issues[1]["category"] == "deep"

    def test_with_all_steps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            step2 = {"rule_results": [{"rule_id": "R001", "category": "建筑"}]}
            step3 = {"collision_results": {"tray_issues": [{"rule_id": "C001"}]}}
            step4 = {"cross_results": {"cross_results": [{"check_name": "X001"}], "deep_cross_results": []}}

            with open(os.path.join(tmpdir, "step2_compliance_result.json"), "w", encoding="utf-8") as f:
                json.dump(step2, f)
            with open(os.path.join(tmpdir, "step3_defect_result.json"), "w", encoding="utf-8") as f:
                json.dump(step3, f)
            with open(os.path.join(tmpdir, "step4_cross_check_result.json"), "w", encoding="utf-8") as f:
                json.dump(step4, f)

            issues = collect_all_issues(tmpdir)
            assert len(issues) == 3

    def test_invalid_json_handled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "step2_compliance_result.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("invalid json")

            issues = collect_all_issues(tmpdir)
            assert issues == []


class TestGenerateSnapshot:

    def test_generates_snapshot_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            issues = [
                {"rule_id": "R001", "severity": "高", "source": "step2_compliance"},
                {"rule_id": "R002", "severity": "中", "source": "step3_defect"},
            ]
            path = generate_snapshot(issues, tmpdir)
            assert os.path.exists(path)

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["total_issues"] == 2
            assert "timestamp" in data
            assert data["by_source"]["step2_compliance"] == 1
            assert data["by_severity"]["高"] == 1

    def test_empty_issues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_snapshot([], tmpdir)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["total_issues"] == 0


class TestCompareSnapshots:

    def test_no_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current_path = os.path.join(tmpdir, "current.json")
            with open(current_path, "w", encoding="utf-8") as f:
                json.dump({"issues": []}, f)

            result = compare_snapshots(current_path, os.path.join(tmpdir, "nonexistent.json"))
            assert result["has_previous"] is False
            assert result["lost_issues"] == []

    def test_lost_issues_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current = {
                "timestamp": "2026-05-20 10:00:00",
                "issues": [
                    {"rule_id": "R001", "file": "a.dxf", "line": "10"},
                ]
            }
            previous = {
                "timestamp": "2026-05-19 10:00:00",
                "issues": [
                    {"rule_id": "R001", "file": "a.dxf", "line": "10"},
                    {"rule_id": "R002", "file": "b.dxf", "line": "20"},
                ]
            }

            current_path = os.path.join(tmpdir, "current.json")
            previous_path = os.path.join(tmpdir, "previous.json")
            with open(current_path, "w", encoding="utf-8") as f:
                json.dump(current, f)
            with open(previous_path, "w", encoding="utf-8") as f:
                json.dump(previous, f)

            result = compare_snapshots(current_path, previous_path)
            assert result["has_previous"] is True
            assert result["lost_count"] == 1
            assert result["new_count"] == 0
            assert result["unchanged_count"] == 1

    def test_new_issues_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current = {
                "timestamp": "2026-05-20 10:00:00",
                "issues": [
                    {"rule_id": "R001", "file": "a.dxf", "line": "10"},
                    {"rule_id": "R003", "file": "c.dxf", "line": "30"},
                ]
            }
            previous = {
                "timestamp": "2026-05-19 10:00:00",
                "issues": [
                    {"rule_id": "R001", "file": "a.dxf", "line": "10"},
                ]
            }

            current_path = os.path.join(tmpdir, "current.json")
            previous_path = os.path.join(tmpdir, "previous.json")
            with open(current_path, "w", encoding="utf-8") as f:
                json.dump(current, f)
            with open(previous_path, "w", encoding="utf-8") as f:
                json.dump(previous, f)

            result = compare_snapshots(current_path, previous_path)
            assert result["has_previous"] is True
            assert result["lost_count"] == 0
            assert result["new_count"] == 1
            assert result["unchanged_count"] == 1

    def test_invalid_previous_handled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current_path = os.path.join(tmpdir, "current.json")
            previous_path = os.path.join(tmpdir, "previous.json")
            with open(current_path, "w", encoding="utf-8") as f:
                json.dump({"issues": []}, f)
            with open(previous_path, "w", encoding="utf-8") as f:
                f.write("invalid")

            result = compare_snapshots(current_path, previous_path)
            assert result["has_previous"] is False
