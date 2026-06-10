# -*- coding: utf-8 -*-
import json
import os
import sys
import time
from datetime import datetime
from collections import defaultdict

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

# DXF 目录：优先环境变量，其次命令行参数，最后本机默认路径
DXF_DIR = os.environ.get(
    "DXF_REVIEW_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "input")
)
SKIP_MB = 150
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output_v7.0")
PROJECT = "温州医科大学阿尔伯塔学院"


def run_spatial_pipeline():
    """空间冲突全量检测"""
    from v7.spatial_reasoning import SpatialAnalyzer, SpatialIndex, SpatialEntity, FloorLabel, ElevationTag
    from v7.conflict_diff import diff as conflict_diff_run
    from v7.conflict_state_manager import ConflictStateManager
    from v7.preprocessor.drawing_extractor import DrawingExtractor
    import glob, hashlib, pickle

    print("=" * 70, flush=True)
    print(f"  [空间冲突] 全量DXF检测", flush=True)
    print("=" * 70, flush=True)

    t0 = time.time()
    dxf_paths = sorted(glob.glob(os.path.join(DXF_DIR, "*.dxf")), key=os.path.getsize)
    skipped = [f for f in dxf_paths if os.path.getsize(f) / 1e6 > SKIP_MB]
    dxf_paths = [f for f in dxf_paths if os.path.getsize(f) / 1e6 <= SKIP_MB]

    analyzer = SpatialAnalyzer(DXF_DIR)
    cache_dir = analyzer._cache_dir
    ext = DrawingExtractor()
    HVAC_PREFIXES = {"h-", "h_", "nt-", "nt_", "暖通", "hvac", "air", "duct", "xr-a", "xr_"}
    STRUCT_PREFIXES = {"s-", "s_", "结施", "结构", "基础", "配筋", "桩基", "预制", "埋件", "g-", "g_"}
    PLUMB_PREFIXES = {"水施", "给排水", "给水", "排水", "消火栓", "喷淋", "ss-", "ss_", "p-", "p_"}
    ELEC_PREFIXES = {"电施", "电气", "配电", "照明", "防雷", "弱电", "变配电", "ds-", "ds_", "e-", "e_"}

    def classify_enhanced(name):
        name_lower = name.lower()
        if any(k in name_lower for k in HVAC_PREFIXES): return "hvac"
        if any(k in name_lower for k in STRUCT_PREFIXES): return "structure"
        if any(k in name_lower for k in PLUMB_PREFIXES): return "plumbing"
        if any(k in name_lower for k in ELEC_PREFIXES): return "electrical"
        disc = ext.classify(name)
        return "building" if disc == "unknown" else disc

    cache_hits = 0
    for idx, dxf_path in enumerate(dxf_paths, 1):
        name = os.path.basename(dxf_path)
        fingerprint = hashlib.md5(f"{os.path.getmtime(dxf_path)}:{os.path.getsize(dxf_path)}:{dxf_path}".encode()).hexdigest()[:16]
        cache_file = os.path.join(cache_dir, f"{fingerprint}.pkl")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "rb") as cf:
                    cache_data = pickle.load(cf)
                for e_data in cache_data.get("entities", []):
                    analyzer.entities.append(SpatialEntity(**e_data))
                for fl_data in cache_data.get("floor_labels", []):
                    analyzer.floor_labels.append(FloorLabel(**fl_data))
                for et_data in cache_data.get("elevation_tags", []):
                    analyzer.elevation_tags.append(ElevationTag(**et_data))
                cache_hits += 1
                continue
            except Exception:
                pass
        disc = classify_enhanced(name)
        before = len(analyzer.entities)
        before_fl = len(analyzer.floor_labels)
        before_et = len(analyzer.elevation_tags)
        analyzer.extract_from_dxf(dxf_path, disc)
        cache_data = {
            "entities": [{"entity_type": e.entity_type, "discipline": e.discipline, "drawing_name": e.drawing_name, "layer": e.layer,
                          "x_min": e.x_min, "y_min": e.y_min, "x_max": e.x_max, "y_max": e.y_max,
                          "floor_level": e.floor_level, "z_bottom": e.z_bottom, "z_top": e.z_top, "text_content": e.text_content}
                         for e in analyzer.entities[before:]],
            "floor_labels": [{"x": fl.x, "y": fl.y, "floor": fl.floor, "text": fl.text, "drawing_name": fl.drawing_name}
                             for fl in analyzer.floor_labels[before_fl:]],
            "elevation_tags": [{"x": et.x, "y": et.y, "elevation": et.elevation, "text": et.text, "drawing_name": et.drawing_name}
                               for et in analyzer.elevation_tags[before_et:]]
        }
        os.makedirs(cache_dir, exist_ok=True)
        try:
            with open(cache_file, "wb") as cf:
                pickle.dump(cache_data, cf, protocol=4)
        except Exception:
            pass

    t1 = time.time()
    print(f"  实体加载: {len(analyzer.entities)} 实体, 缓存命中:{cache_hits}/{len(dxf_paths)}, 耗时{t1-t0:.0f}s", flush=True)

    analyzer._assign_floor_levels()
    t2 = time.time()
    assigned = sum(1 for e in analyzer.entities if e.floor_level and e.floor_level != 0)
    print(f"  楼层分配: {assigned}/{len(analyzer.entities)} 实体, 耗时{t2-t1:.0f}s", flush=True)

    si = SpatialIndex()
    si.build(analyzer.entities)
    analyzer.spatial_index = si
    t3 = time.time()
    print(f"  空间索引: {len(si._entity_map)} 空间实体, 耗时{t3-t2:.0f}s", flush=True)

    conflicts = analyzer.find_cross_floor_conflicts()
    t4 = time.time()
    print(f"  冲突检测: {len(conflicts)} 冲突簇, 耗时{t4-t3:.0f}s", flush=True)

    severity_order = {"A": 0, "B": 1, "C": 2, "D": 3}
    conflicts.sort(key=lambda c: severity_order.get(c["severity"], 5))

    # 写入前去重：同类型+同描述+同楼层的重复冲突
    raw_count = len(conflicts)
    seen = set()
    deduped = []
    for c in conflicts:
        key = (c.get("type"), c.get("description", "")[:100], c.get("floor", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    if raw_count != len(deduped):
        print(f"  空间冲突去重: {raw_count} → {len(deduped)} (删除 {raw_count - len(deduped)} 条重复)", flush=True)

    cur_path = os.path.join(OUTPUT_DIR, "spatial_conflicts_v5.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(cur_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    prev_path = os.path.join(OUTPUT_DIR, "spatial_conflicts_v4.json")
    diff_path = os.path.join(OUTPUT_DIR, "spatial_conflicts_v5_diff.json")

    state_manager = ConflictStateManager(project_name="医科大学")
    if os.path.exists(prev_path):
        conflict_diff_run(cur_path, prev_path, diff_path, state_manager=state_manager)

    by_type = defaultdict(int)
    by_floor = defaultdict(int)
    for c in deduped:
        by_type[c["type"]] += 1
        by_floor[str(c.get("floor", "?"))] += 1

    t_total = time.time() - t0
    spatial_result = {
        "total_conflicts": len(deduped),
        "total_entities": len(analyzer.entities),
        "indexed_entities": len(si._entity_map),
        "by_type": dict(by_type),
        "by_floor": dict(by_floor),
        "timing": {
            "load": round(t1-t0, 1),
            "floor_assign": round(t2-t1, 1),
            "index_build": round(t3-t2, 1),
            "conflict_detect": round(t4-t3, 1),
            "total": round(t_total, 1),
        },
        "cache_hits": cache_hits,
        "dxf_processed": len(dxf_paths),
        "dxf_skipped": len(skipped),
        "state_summary": state_manager.summary(),
    }
    print(f"  [空间冲突] 完成: {len(conflicts)} 冲突, 总耗时{t_total:.0f}s", flush=True)
    return spatial_result


def run_llm_pipeline():
    """LLM审查路径"""
    print(f"\n{'=' * 70}", flush=True)
    print(f"  [LLM审查] 文本+视觉双路径审查", flush=True)
    print(f"{'=' * 70}", flush=True)

    has_api = bool(os.environ.get("ZHIPU_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"))
    if not has_api:
        print(f"  ⚠️ 未检测到LLM API Key (ZHIPU_API_KEY / DEEPSEEK_API_KEY)", flush=True)
        print(f"  → LLM审查路径跳过，报告将引用历史数据", flush=True)
        return {"status": "skipped", "reason": "no_api_key", "dry_run": True}

    # 实际LLM调用
    from v7.master_v7 import run_full
    import argparse
    args = argparse.Namespace(
        dxf_dir=DXF_DIR, output_dir=OUTPUT_DIR, port=8080,
        conflict_diff=None, conflict_prev=None, conflict_output=None,
        conflict_show_status=False, project="医科大学"
    )
    run_full(args)
    return {"status": "completed", "dry_run": False}


def run_dry_run_pipeline():
    """干跑模式——验证管线可用性"""
    print(f"\n{'=' * 70}", flush=True)
    print(f"  [管线校验] 模块可用性 + 数据流验证", flush=True)
    print(f"{'=' * 70}", flush=True)

    from v7.master_v7 import run_dry_run
    import argparse
    args = argparse.Namespace(dxf_dir=DXF_DIR, output_dir=OUTPUT_DIR)
    pool = run_dry_run(args)
    return {"modules_ok": len(pool._issues) > 0}


def main():
    print("=" * 70)
    print(f"  AI智能审图系统 v7.0 — 统一全量管线")
    print(f"  项目: {PROJECT}")
    print(f"  时间: {datetime.now().isoformat(timespec='seconds')}")
    print(f"  DXF目录: {DXF_DIR}")
    print(f"  输出目录: {OUTPUT_DIR}")
    print("=" * 70)

    t_total_start = time.time()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. 空间冲突检测
    spatial_result = run_spatial_pipeline()

    # 2. 管线校验
    dry_result = run_dry_run_pipeline()

    # 3. LLM审查 (有Key则真实运行，无Key则跳过)
    llm_result = run_llm_pipeline()

    # 4. UAI审查数据合并 + 报告生成
    print(f"\n{'=' * 70}")
    print(f"  [报告翻译] UAI审查数据 → 格式合规报告")
    print(f"{'=' * 70}")
    from v7.uai_review_data import UAI_FINDINGS, SEVERITY_ADJUST
    import glob as _glob
    v5_files = sorted(_glob.glob(os.path.join(OUTPUT_DIR, "reports", "清单_v5_*.json")))
    if v5_files:
        latest_v5 = v5_files[-1]
        from v7.report_translator import generate_final_report
        spatial_v5 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "v7", "spatial_conflicts_v5.json")
        report_paths = generate_final_report(latest_v5, spatial_v5,
                                             UAI_FINDINGS, SEVERITY_ADJUST, OUTPUT_DIR)
    else:
        report_paths = {"md": "N/A", "txt": "N/A"}

    t_total = time.time() - t_total_start

    # 5. JSON元数据
    report = {
        "report_title": f"{PROJECT} — AI智能审图统一全量报告",
        "run_time": datetime.now().isoformat(timespec="seconds"),
        "project": PROJECT,
        "dxf_dir": DXF_DIR,
        "total_time": round(t_total, 1),
        "spatial": spatial_result,
        "llm_review": llm_result,
        "pipeline_check": dry_result,
        "final_report_md": report_paths.get("md", "N/A"),
        "final_report_txt": report_paths.get("txt", "N/A"),
    }

    report_path = os.path.join(OUTPUT_DIR, "unified_pipeline_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 70}")
    print(f"  统一全量管线完成")
    print(f"  总耗时: {t_total:.1f}s")
    print(f"  空间冲突: {spatial_result['total_conflicts']} 个")
    print(f"  LLM审查: {llm_result['status']}")
    print(f"  JSON元数据: {report_path}")
    print(f"  最终报告: {report_paths.get('md', 'N/A')}")
    print(f"  最终报告TXT: {report_paths.get('txt', 'N/A')}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
