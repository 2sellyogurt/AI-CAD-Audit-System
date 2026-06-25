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

try:
    from flask import Blueprint, request, jsonify, current_app, send_file
except ImportError:
    # Flask 未安装时提供空实现，避免导入失败
    # 注意: 主服务器 server.py 基于 http.server，不依赖 Flask
    # 此文件仅作为备用 Flask Blueprint
    Blueprint = None
    request = None
    jsonify = None
    current_app = None
    send_file = None

if Blueprint is None:
    # 创建一个轻量级替代，使模块可导入但不具备实际功能
    class _DummyBlueprint:
        def __init__(self, name, **kw):
            self.name = name
        def route(self, rule, **kw):
            def decorator(fn): return fn
            return decorator
        def errorhandler(self, code):
            def decorator(fn): return fn
            return decorator
    api_bp = _DummyBlueprint("api")
else:
    api_bp = Blueprint("api", __name__)

# ── 审查数据缓存 ────────────────────────────────────────
_cache = {"issues": [], "stats": {}, "conflicts": [], "cross": [], "ready": False, "taskId": None}
_cache_lock = threading.Lock()

# ── 报告文件动态扫描 ─────────────────────────────────────
REPORT_FILES = {}  # 动态填充

def _scan_report_files():
    """扫描输出目录中的报告文件"""
    global REPORT_FILES
    REPORT_FILES = {}
    output_dir = os.environ.get("V7_OUTPUT_DIR", "")
    if not output_dir or not os.path.isdir(output_dir):
        return
    keywords_map = {
        "scene1": ["基础错漏", "设计审查"],
        "scene2": ["跨专业", "施工审查"],
        "scene3": ["强条合规", "竣工验收"],
    }
    for scene, keywords in keywords_map.items():
        for fn in os.listdir(output_dir):
            if fn.endswith(".docx") and any(k in fn for k in keywords):
                REPORT_FILES[scene] = os.path.join(output_dir, fn)
                break


# ── 后台审查管线 ────────────────────────────────────────

def _run_review():
    """后台执行审查管线（v7 Agent集群管线）。"""
    task_id = uuid.uuid4().hex[:8]
    with _cache_lock:
        _cache["taskId"] = task_id
        _cache["ready"] = False

    try:
        from v7.checkpoints import CheckpointEngine
        from v7.scheduler import AgentOrchestrator
        from v7.problem_pool import ProblemPool
        from v7.preprocessor import DrawingExtractor
        from v7.scanner import DrawingScanner
        from v7.rationality_engine import annotate_all_rationality

        engine = CheckpointEngine()
        print(f"[API] 加载 {engine.total_count} 个检查点")

        extractor = DrawingExtractor()
        dxf_files = extractor.find_dxf_files()
        max_drawings = int(os.environ.get("V7_MAX_DRAWINGS", "20"))
        drawings = [extractor.process_drawing(f) for f in dxf_files[:max_drawings]]
        merged_text = "\n".join(d.text_content for d in drawings if d.text_content)
        print(f"[API] 扫描 {len(drawings)} 份图纸")

        orch = AgentOrchestrator()
        orch.create_all_agents()

        pool = ProblemPool()
        scanner = DrawingScanner()
        if merged_text:
            scan = scanner.scan(merged_text)
            active = scan.relevant_disciplines if scan and scan.relevant_disciplines else list(orch.agents.keys())
        else:
            active = list(orch.agents.keys())

        for aid in active:
            agent = orch.agents.get(aid)
            if not agent:
                continue
            try:
                agent_report = agent.execute(drawings, problem_pool=pool)
                print(f"[API]   [{aid}] {agent_report.issues_found} issues")
            except Exception as e:
                print(f"[API]   [{aid}] 异常: {e}")

        all_issues = pool.to_list()
        all_issues = annotate_all_rationality(all_issues)

        by_severity = {"A": 0, "B": 0, "C": 0, "D": 0}
        by_rationality = {"R0": 0, "R1": 0, "R2": 0, "R3": 0}
        for f in all_issues:
            by_severity[f.get("severity", "C")] = by_severity.get(f.get("severity", "C"), 0) + 1
            r = f.get("rationality", {}).get("level", "R2")
            by_rationality[r] = by_rationality.get(r, 0) + 1

        with _cache_lock:
            _cache["issues"] = all_issues
            _cache["cross"] = []
            _cache["conflicts"] = []
            _cache["stats"] = {
                "disciplines": 20, "available": 18, "pending": 2,
                "totalIssues": len(all_issues),
                "bySeverity": by_severity,
                "byRationality": by_rationality,
                "highConfConflicts": 0,
                "totalConflicts": 0,
                "medConfConflicts": 0,
                "reviewTimeMin": max(1, len(all_issues) // 20),
                "pipeline": "v7",
            }
            _cache["ready"] = True
            _cache["taskId"] = task_id
        print(f"[API] v7审查完成: {len(all_issues)} 项问题")

    except Exception as e:
        print(f"[API] 审查异常: {e}")
        import traceback
        traceback.print_exc()
        with _cache_lock:
            _cache["ready"] = True
            _cache["issues"] = []
            _cache["conflicts"] = []
            _cache["stats"] = {"totalIssues": 0, "totalConflicts": 0,
                               "bySeverity": {}, "reviewTimeMin": 0, "pipeline": "v7"}


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
    _scan_report_files()
    if scene not in REPORT_FILES:
        return jsonify({"error": "invalid scene"}), 400
    fp = REPORT_FILES[scene]
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
