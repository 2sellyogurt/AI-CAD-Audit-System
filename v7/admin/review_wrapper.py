# -*- coding: utf-8 -*-
"""review_ui 集成桥接 — 将原独立 Flask 应用作为子路径 /review/ 挂载

保留 review_ui/app.py 的完整首页和 API 不变，
通过在 create_app 时注册其路由。
"""

import os
import json
import uuid
from datetime import datetime, timezone
from functools import wraps


def init_app(app):
    """将 review_ui 的页面和 API 路由注册到统一 Flask app。"""

    HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 全局状态（与 review_ui 原 app 一致）
    app.config.setdefault("REVIEW_POOL", None)
    app.config.setdefault("REVIEW_AUDIT_LOG", "")

    # ── 从 master_v7 加载问题池（兼容 --review-only 模式） ──

    def _load_problem_pool():
        from v7.problem_pool import ProblemPool
        pool = ProblemPool()
        review_data = os.environ.get("V7_REVIEW_DATA", "")
        if review_data and os.path.exists(review_data):
            with open(review_data, "r", encoding="utf-8") as f:
                data = json.load(f)
            from v7.problem_pool import UnifiedIssue
            for item in data.get("issues", []):
                try:
                    issue = UnifiedIssue(**{k: v for k, v in item.items()
                                            if k in UnifiedIssue.__dataclass_fields__})
                except Exception:
                    continue
                pool.add_issue(issue)
        return pool

    # ── index.html 静态页面 ──
    index_path = os.path.join(HERE, "index.html")

    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            _review_html = f.read()
    else:
        _review_html = "<h1>审查界面未部署</h1>"

    @app.route("/review/")
    def review_index():
        return _review_html

    # ── 复核 API ──

    @app.route("/review/api/issues", methods=["GET"])
    def review_api_issues():
        pool = app.config.get("REVIEW_POOL") or _load_problem_pool()
        from flask import request, jsonify
        items = [issue_to_dict(i) for i in (pool._issues if hasattr(pool, '_issues') else [])]
        sev = request.args.get("severity")
        disc = request.args.get("discipline")
        search = request.args.get("search", "")
        if sev:
            items = [i for i in items if i.get("severity") == sev]
        if disc:
            items = [i for i in items if i.get("professional", "") == disc]
        if search:
            s = search.lower()
            items = [i for i in items if s in json.dumps(i, ensure_ascii=False).lower()]
        return jsonify({"total": len(items), "items": items})

    @app.route("/review/api/issues/<issue_id>", methods=["GET"])
    def review_api_issue_detail(issue_id):
        pool = app.config.get("REVIEW_POOL") or _load_problem_pool()
        for i in (pool._issues if hasattr(pool, '_issues') else []):
            if getattr(i, "issue_id", "") == issue_id:
                return app.response_class(
                    json.dumps(issue_to_dict(i), ensure_ascii=False),
                    mimetype="application/json"
                )
        return app.response_class(json.dumps({"error": "not found"}), status=404,
                                   mimetype="application/json")

    @app.route("/review/api/confirm", methods=["POST"])
    def review_api_confirm():
        data = request_or_json()
        _audit_log(app, "admin", "confirm", data.get("id", ""))
        return app.response_class(json.dumps({"ok": True, "action": "confirmed"}),
                                   mimetype="application/json")

    @app.route("/review/api/reject", methods=["POST"])
    def review_api_reject():
        data = request_or_json()
        _audit_log(app, "admin", "reject", data.get("id", ""), reason=data.get("reason", ""))
        return app.response_class(json.dumps({"ok": True, "action": "rejected"}),
                                   mimetype="application/json")

    @app.route("/review/api/modify", methods=["POST"])
    def review_api_modify():
        data = request_or_json()
        _audit_log(app, "admin", "modify", data.get("id", ""),
                    before=data.get("before", ""), after=data.get("after", ""))
        return app.response_class(json.dumps({"ok": True, "action": "modified"}),
                                   mimetype="application/json")

    @app.route("/review/api/add", methods=["POST"])
    def review_api_add():
        data = request_or_json()
        _audit_log(app, "admin", "add", data.get("id", f"MANUAL-{uuid.uuid4().hex[:8]}"))
        return app.response_class(json.dumps({"ok": True, "added": True}),
                                   mimetype="application/json")

    # ── 报告页面 ──
    @app.route("/review/report")
    def review_report():
        report_path = os.path.join(app.config.get("OUTPUT_DIR", ""), "review_report.md")
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"<pre style='padding:20px;font-size:14px'>{content}</pre>"
        return "<h2>暂无审查报告</h2><p>请先执行一次完整审查。</p>"


def issue_to_dict(issue) -> dict:
    """将 UnifiedIssue 转为可 JSON 序列化的 dict。"""
    d = {
        "issue_id": getattr(issue, "issue_id", ""),
        "checkpoint_id": getattr(issue, "checkpoint_id", ""),
        "checkpoint_name": getattr(issue, "checkpoint_name", ""),
        "professional": getattr(issue, "professional", ""),
        "discipline": getattr(issue, "discipline", ""),
        "description": getattr(issue, "description", ""),
        "suggestion": getattr(issue, "suggestion", ""),
        "severity": getattr(issue, "severity", ""),
        "confidence": getattr(issue, "confidence", "high"),
        "drawing_name": getattr(issue, "drawing_name", ""),
        "location": getattr(issue, "location", ""),
        "cad_script": getattr(issue, "cad_script", ""),
        "route_used": getattr(issue, "route_used", "text"),
    }
    return d


def request_or_json():
    from flask import request
    try:
        return request.get_json(force=True, silent=True) or {}
    except Exception:
        return {}


def _audit_log(app, user, action, target, before="", after="", reason=""):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user,
        "user_role": "reviewer",
        "action": action,
        "target": target,
        "before": before,
        "after": after,
        "reason": reason,
    }
    log_dir = app.config.get("AUDIT_LOG_DIR") or os.path.join(
        app.config.get("OUTPUT_DIR", ""), "audit_logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
