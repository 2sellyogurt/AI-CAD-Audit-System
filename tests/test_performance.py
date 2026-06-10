# -*- coding: utf-8 -*-
"""
性能压测脚本 - 验证112张图纸全流程处理时间

目标：112张图纸全流程 ≤ 5分钟（300秒）
测试范围：Step 2-5（JSON数据处理阶段）
Step 1（DXF提取）已由预处理完成，不计入本次测试
"""

import os
import sys
import time
import json
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
TARGET_SECONDS = 300
FILE_COUNT_TARGET = 112


@pytest.fixture(scope="module")
def json_files():
    files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith("_unified.json")]
    return files


@pytest.fixture(scope="module")
def loader():
    from engine.json_loader import JsonLoader
    return JsonLoader(OUTPUT_DIR)


class TestPerformanceBenchmark:
    def test_file_count(self, json_files):
        assert len(json_files) >= FILE_COUNT_TARGET, \
            f"期望至少{FILE_COUNT_TARGET}个文件，实际{len(json_files)}个"

    def test_json_loader_performance(self, json_files):
        from engine.json_loader import JsonLoader
        start = time.perf_counter()
        loader = JsonLoader(OUTPUT_DIR)
        elapsed = time.perf_counter() - start
        assert len(loader.files) >= FILE_COUNT_TARGET
        assert elapsed < 30, f"JsonLoader加载耗时{elapsed:.2f}s，超过30s阈值"

    def test_dedup_engine_performance(self, loader):
        from engine.dedup_engine import DedupEngine
        start = time.perf_counter()
        engine = DedupEngine()
        for fn in loader.files:
            meta = loader.get_metadata_by_file(fn)
            lines = loader.get_text_lines_by_file(fn)
            readable = loader.get_readable_name(fn)
            engine.register(fn, readable, lines, meta)
        report = engine.compute_dedup_report()
        elapsed = time.perf_counter() - start
        assert report.total_before >= FILE_COUNT_TARGET
        assert elapsed < 60, f"去重引擎耗时{elapsed:.2f}s，超过60s阈值"

    def test_rule_checker_performance(self, loader):
        from engine.rule_checker import RuleChecker
        start = time.perf_counter()
        checker = RuleChecker(loader)
        results = checker.check_all_rules()
        elapsed = time.perf_counter() - start
        assert elapsed < 120, f"规则检查耗时{elapsed:.2f}s，超过120s阈值"

    def test_cross_discipline_performance(self, loader):
        from engine.cross_discipline import CrossDiscipline
        start = time.perf_counter()
        cross = CrossDiscipline(loader)
        result = cross.run_all_checks()
        elapsed = time.perf_counter() - start
        assert "cross_results" in result
        assert elapsed < 60, f"跨专业校验耗时{elapsed:.2f}s，超过60s阈值"

    def test_engineering_analysis_performance(self, loader):
        from engine.engineering_analysis import EngineeringAnalyzer
        start = time.perf_counter()
        analyzer = EngineeringAnalyzer(loader)
        report = analyzer.full_lifecycle_report()
        elapsed = time.perf_counter() - start
        assert "summary" in report
        assert elapsed < 60, f"工程分析耗时{elapsed:.2f}s，超过60s阈值"

    def test_collision_detect_performance(self, loader):
        from engine.collision_detect import CollisionDetect
        start = time.perf_counter()
        detect = CollisionDetect(loader)
        result = detect.run_all_checks([])
        elapsed = time.perf_counter() - start
        assert "summary" in result
        assert elapsed < 60, f"碰撞检测耗时{elapsed:.2f}s，超过60s阈值"

    def test_full_pipeline_performance(self, json_files):
        from engine.json_loader import JsonLoader
        from engine.dedup_engine import DedupEngine
        from engine.rule_checker import RuleChecker
        from engine.cross_discipline import CrossDiscipline
        from engine.engineering_analysis import EngineeringAnalyzer
        from engine.collision_detect import CollisionDetect

        total_start = time.perf_counter()

        t0 = time.perf_counter()
        loader = JsonLoader(OUTPUT_DIR)
        t_load = time.perf_counter() - t0

        t0 = time.perf_counter()
        engine = DedupEngine()
        for fn in loader.files:
            meta = loader.get_metadata_by_file(fn)
            lines = loader.get_text_lines_by_file(fn)
            readable = loader.get_readable_name(fn)
            engine.register(fn, readable, lines, meta)
        dedup_report = engine.compute_dedup_report()
        t_dedup = time.perf_counter() - t0

        t0 = time.perf_counter()
        checker = RuleChecker(loader)
        checker.check_all_rules()
        t_rule = time.perf_counter() - t0

        t0 = time.perf_counter()
        cross = CrossDiscipline(loader)
        cross_result = cross.run_all_checks()
        t_cross = time.perf_counter() - t0

        t0 = time.perf_counter()
        analyzer = EngineeringAnalyzer(loader)
        eng_report = analyzer.full_lifecycle_report()
        t_eng = time.perf_counter() - t0

        t0 = time.perf_counter()
        detect = CollisionDetect(loader)
        detect_result = detect.run_all_checks([])
        t_collision = time.perf_counter() - t0

        total_elapsed = time.perf_counter() - total_start

        print("\n" + "=" * 60)
        print("性能压测报告 - 112张图纸全流程")
        print("=" * 60)
        print(f"文件数量: {len(loader.files)}")
        print(f"去重后唯一: {len(dedup_report.unique_files)}")
        print("-" * 60)
        print(f"{'阶段':<25} {'耗时(秒)':<12} {'占比':<10}")
        print("-" * 60)
        stages = [
            ("JSON加载", t_load),
            ("图纸去重", t_dedup),
            ("规则检查(250条)", t_rule),
            ("跨专业校验", t_cross),
            ("工程分析", t_eng),
            ("碰撞检测", t_collision),
        ]
        for name, t in stages:
            pct = (t / total_elapsed * 100) if total_elapsed > 0 else 0
            print(f"{name:<25} {t:<12.2f} {pct:<10.1f}%")
        print("-" * 60)
        print(f"{'总计':<25} {total_elapsed:<12.2f} {'100%':<10}")
        print("=" * 60)
        status = "✅ 通过" if total_elapsed <= TARGET_SECONDS else "❌ 超时"
        print(f"目标: ≤{TARGET_SECONDS}秒 | 实际: {total_elapsed:.2f}秒 | {status}")
        print("=" * 60)

        assert total_elapsed <= TARGET_SECONDS, \
            f"全流程耗时{total_elapsed:.2f}s，超过{TARGET_SECONDS}s目标"
