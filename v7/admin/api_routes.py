# -*- coding: utf-8 -*-
"""REST API Blueprint — 原 server.py 端点移植到 Flask

端点:
  GET  /api/health        — 健康检查
  GET  /api/stats         — 审查统计
  GET  /api/issues        — 问题列表（支持过滤）
  GET  /api/issues/<id>   — 单条问题详情
  GET  /api/conflicts     — 空间冲突数据
  GET  /api/reports/<scene> — 报告下载
  GET  /api/config         — 配置信息（不含密钥）
  POST /api/review/start   — 启动审查
  POST /api/review/progress — 审查进度
"""

import json, os, sys, time, threading, uuid
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app, send_file

api_bp = Blueprint("api", __name__)

# ── 审查数据缓存 ────────────────────────────────────────
_cache = {"issues": [], "stats": {}, "conflicts": [], "cross": [], "ready": False, "taskId": None}
_cache_lock = threading.Lock()


# ── 后台审查管线 ────────────────────────────────────────

def _run_review():
    """后台执行审查管线（线程安全）。"""
    global _cache
    task_id = uuid.uuid4().hex[:8]
    with _cache_lock:
        _cache["taskId"] = task_id
        _cache["ready"] = False

    try:
        from v7.llm_full_review import (
            detect_best_mode, review_all_real_llm,
            cross_discipline_analysis, load_spatial, DISCIPLINE_REVIEWER_MAP,
        )
        from v7.rationality_engine import annotate_all_rationality

        mode = detect_best_mode()

        if mode.value == "real":
            print(f"[API] 实时LLM审查...")
            all_findings, llm_stats = review_all_real_llm()
        else:
            print(f"[API] 缓存审查...")
            all_findings = []
            for disc, reviewer in DISCIPLINE_REVIEWER_MAP.items():
                issues = reviewer()
                for i in issues:
                    i["discipline"] = disc
                all_findings.extend(issues)

        cross = cross_discipline_analysis()
        all_with_cross = all_findings + cross
        all_with_cross = annotate_all_rationality(all_with_cross)

        spatial_raw = load_spatial()
        conflicts = []
        for c in spatial_raw:
            conflicts.append({
                "type": c.get("type", ""),
                "severity": c.get("severity", "D"),
                "confidence": c.get("confidence", "low"),
                "floor": c.get("floor", 0),
                "description": c.get("description", "")[:200],
                "involved": c.get("involved", ""),
            })

        by_severity = {"A": 0, "B": 0, "C": 0, "D": 0}
        by_rationality = {"R0": 0, "R1": 0, "R2": 0, "R3": 0}
        for f in all_with_cross:
            by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
            r = f.get("rationality", {}).get("level", "R2")
            by_rationality[r] = by_rationality.get(r, 0) + 1

        high_conf = sum(1 for c in conflicts if c["confidence"] == "high")
        med_conf = sum(1 for c in conflicts if c["confidence"] == "medium")

        with _cache_lock:
            _cache["issues"] = all_with_cross
            _cache["cross"] = cross
            _cache["conflicts"] = conflicts
            _cache["stats"] = {
                "disciplines": 18, "available": 15, "pending": 3,
                "totalIssues": len(all_with_cross),
                "bySeverity": by_severity,
                "byRationality": by_rationality,
                "highConfConflicts": high_conf,
                "totalConflicts": len(conflicts),
                "medConfConflicts": med_conf,
                "reviewTimeMin": 10,
            }
            _cache["ready"] = True
            _cache["taskId"] = task_id
        print(f"[API] 审查完成: {len(all_with_cross)} 项问题, {len(conflicts)} 个冲突")

    except Exception as e:
        print(f"[API] 审查异常: {e}")
        import traceback
        traceback.print_exc()
        with _cache_lock:
            _cache["ready"] = False


# ── 路由 ────────────────────────────────────────────────

@api_bp.route("/health")
def health():
    return jsonify({"status": "ok", "ready": _cache["ready"], "taskId": _cache.get("taskId")})


@api_bp.route("/stats")
def stats():
    if not _cache["ready"]:
        return jsonify({"error": "审查数据未就绪，请先 POST /api/review/start"}), 503
    return jsonify(_cache["stats"])


@api_bp.route("/issues")
def issues():
    if not _cache["ready"]:
        return jsonify({"error": "审查数据未就绪"}), 503

    items = list(_cache["issues"])
    sev = request.args.get("severity")
    rat = request.args.get("rationality")
    disc = request.args.get("discipline")
    search = request.args.get("search")

    if sev and sev != "all":
        items = [i for i in items if i["severity"] == sev]
    if rat and rat != "all":
        items = [i for i in items if i.get("rationality", {}).get("level") == rat]
    if disc:
        items = [i for i in items if i.get("discipline", "") == disc]
    if search:
        s = search.lower()
        items = [i for i in items if s in i.get("id", "").lower()
                 or s in i.get("finding", "").lower()]

    return jsonify({"total": len(items), "items": items})


@api_bp.route("/issues/<issue_id>")
def issue_detail(issue_id):
    for i in _cache.get("issues", []):
        if i.get("id") == issue_id:
            return jsonify(i)
    return jsonify({"error": "not found"}), 404


@api_bp.route("/conflicts")
def conflicts():
    if not _cache["ready"]:
        return jsonify({"error": "审查数据未就绪"}), 503
    return jsonify({"total": len(_cache["conflicts"]), "items": _cache["conflicts"]})


@api_bp.route("/reports/<scene>")
def report_download(scene):
    output_dir = current_app.config.get("OUTPUT_DIR", "")
    scene_map = {
        "scene1": "场景1_基础错漏排查报告(3).docx",
        "scene2": "场景2_跨专业一致性校验报告(3).docx",
        "scene3": "场景3_强条合规性审查报告(3).docx",
    }
    if scene not in scene_map:
        return jsonify({"error": "invalid scene"}), 400
    fp = os.path.join(output_dir, scene_map[scene])
    if not os.path.exists(fp):
        # fallback to .md
        md_fp = fp.replace(".docx", ".md")
        if os.path.exists(md_fp):
            return send_file(md_fp, mimetype="text/markdown")
        return jsonify({"error": "report not found"}), 404
    return send_file(fp, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@api_bp.route("/config")
def config():
    from v7.secure_config import get_all_providers
    return jsonify(get_all_providers())


@api_bp.route("/review/start", methods=["POST"])
def review_start():
    if _cache.get("ready"):
        return jsonify({
            "taskId": _cache["taskId"], "status": "ready",
            "message": "使用缓存审查数据"
        })

    with _cache_lock:
        _cache["ready"] = False
    t = threading.Thread(target=_run_review, daemon=True)
    t.start()
    return jsonify({
        "taskId": _cache.get("taskId", ""), "status": "started"
    }), 202


@api_bp.route("/review/progress")
def review_progress():
    return jsonify({
        "ready": _cache["ready"],
        "taskId": _cache.get("taskId", ""),
        "issues": len(_cache.get("issues", [])),
        "conflicts": len(_cache.get("conflicts", [])),
    })
