# -*- coding: utf-8 -*-
"""
AI智能审图系统 v7.0 — API服务器
前后端桥接层：将Python审查引擎的输出转换为前端可消费的JSON
"""

import json, os, sys, time, threading, uuid
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from secure_config import get_mode, get_provider, get_all_providers, set_api_key as cfg_set_key, set_mode as cfg_set_mode

OUTPUT_DIR = os.path.join(HERE, "output_v7.0")

# ── 审查数据缓存 ────────────────────────────────────────
_cache = {"issues": [], "stats": {}, "conflicts": [], "ready": False, "taskId": None}
_cache_lock = threading.Lock()


def run_review_pipeline():
    """在后台线程中执行审查管线"""
    task_id = uuid.uuid4().hex[:8]
    with _cache_lock:
        _cache["taskId"] = task_id
        _cache["ready"] = False

    try:
        from llm_full_review import (
            detect_best_mode, review_all_real_llm,
            cross_discipline_analysis, load_spatial,
            DISCIPLINE_REVIEWER_MAP,
        )
        from rationality_engine import annotate_all_rationality

        # 自动检测最佳审查模式
        review_mode = detect_best_mode()

        if review_mode.value == "real":
            print(f"[server] 实时LLM审查模式...")
            all_findings, llm_stats = review_all_real_llm()
            print(f"[server] LLM统计: {llm_stats}")
        else:
            print(f"[server] 缓存审查模式...")
            all_findings = []
            for disc_name, reviewer in DISCIPLINE_REVIEWER_MAP.items():
                issues = reviewer()
                for i in issues:
                    i["discipline"] = disc_name
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
            total_disc = len(DISCIPLINE_REVIEWER_MAP)
            available_disc = len(DISCIPLINE_REVIEWER_MAP)  # v7所有专业均已覆盖
            pending_disc = 0
            _cache["stats"] = {
                "disciplines": total_disc,
                "available": available_disc,
                "pending": pending_disc,
                "totalIssues": len(all_with_cross),
                "bySeverity": by_severity,
                "byRationality": by_rationality,
                "highConfConflicts": high_conf,
                "totalConflicts": len(conflicts),
                "medConfConflicts": med_conf,
                "reviewTimeMin": max(1, len(all_with_cross) // 15),
            }
            _cache["ready"] = True
            _cache["taskId"] = task_id
        print(f"[server] 审查完成: {len(all_with_cross)}项问题, {len(conflicts)}个冲突")

    except Exception as e:
        print(f"[server] 审查管线异常: {e}")
        import traceback
        traceback.print_exc()
        with _cache_lock:
            _cache["ready"] = False


# ── HTTP请求处理 ────────────────────────────────────────

class APIHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # 静默日志

    def _cors(self):
        allowed_origins = ["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost", "http://127.0.0.1"]
        origin = self.headers.get("Origin", "")
        if origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", "http://localhost:8080")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, data):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _file(self, path, mime):
        if not os.path.exists(path):
            self.send_error(404)
            return
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", mime)
        self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        self.end_headers()
        with open(path, "rb") as f:
            self.wfile.write(f.read())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # ── 健康检查 ──
        if path == "/api/health":
            return self._json(200, {"status": "ok", "mode": get_mode(), "provider": get_provider(), "ready": _cache["ready"]})

        # ── 统计数据 ──
        if path == "/api/stats":
            if not _cache["ready"]:
                return self._json(503, {"error": "审查数据未就绪，请先调用 POST /api/review/start"})
            return self._json(200, _cache["stats"])

        # ── 问题列表（支持过滤） ──
        if path == "/api/issues":
            if not _cache["ready"]:
                return self._json(503, {"error": "审查数据未就绪"})

            issues = list(_cache["issues"])
            sev = qs.get("severity", [None])[0]
            rat = qs.get("rationality", [None])[0]
            disc = qs.get("discipline", [None])[0]
            search = qs.get("search", [None])[0]

            if sev and sev != "all":
                issues = [i for i in issues if i["severity"] == sev]
            if rat and rat != "all":
                issues = [i for i in issues if i.get("rationality", {}).get("level") == rat]
            if disc:
                issues = [i for i in issues if i.get("discipline", "") == disc]
            if search:
                s = search.lower()
                issues = [i for i in issues if s in i.get("title", "").lower() or s in i.get("id", "").lower()]

            return self._json(200, {"total": len(issues), "items": issues})

        # ── 单条问题详情 ──
        if path.startswith("/api/issues/"):
            issue_id = path.split("/")[-1]
            for i in _cache["issues"]:
                if i.get("id") == issue_id:
                    return self._json(200, i)
            return self._json(404, {"error": "not found"})

        # ── 冲突数据 ──
        if path == "/api/conflicts":
            if not _cache["ready"]:
                return self._json(503, {"error": "审查数据未就绪"})
            return self._json(200, {"total": len(_cache["conflicts"]), "items": _cache["conflicts"]})

        # ── 报告下载 ──
        if path == "/api/reports/scene1":
            fp = os.path.join(OUTPUT_DIR, "场景1_基础错漏排查报告(3).docx")
            return self._file(fp, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        if path == "/api/reports/scene2":
            fp = os.path.join(OUTPUT_DIR, "场景2_跨专业一致性校验报告(3).docx")
            return self._file(fp, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        if path == "/api/reports/scene3":
            fp = os.path.join(OUTPUT_DIR, "场景3_强条合规性审查报告(3).docx")
            return self._file(fp, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

        # ── 配置信息（不含密钥） ──
        if path == "/api/config":
            return self._json(200, get_all_providers())

        # ── Vite HMR (浏览器扩展兼容) ──
        if path == "/@vite/client" or path.startswith("/@vite/"):
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/javascript")
            self.end_headers()
            self.wfile.write(b"// vite client placeholder\n")
            return

        # ── 静态文件 ──
        if path == "/" or path == "":
            path = "/index.html"
        static = os.path.join(HERE, path.lstrip("/"))
        static = os.path.realpath(static)
        if not static.startswith(os.path.realpath(HERE)):
            self.send_error(403, "Access denied")
            return
        if os.path.isfile(static):
            mime_map = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png"}
            ext = os.path.splitext(static)[1]
            self._file(static, mime_map.get(ext, "application/octet-stream"))
        else:
            self.send_error(404)

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        max_content_length = 10 * 1024 * 1024  # 10MB
        if content_len > max_content_length:
            self.send_error(413, "Request entity too large")
            return
        body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # ── 启动审查 ──
        if path == "/api/review/start":
            if _cache.get("ready"):
                mode = get_mode()
                return self._json(200, {"taskId": _cache["taskId"], "status": "ready", "mode": mode, "message": "使用缓存审查数据"})

            with _cache_lock:
                _cache["ready"] = False
            t = threading.Thread(target=run_review_pipeline, daemon=True)
            t.start()
            time.sleep(0.5)
            return self._json(202, {"taskId": _cache.get("taskId", ""), "status": "started", "mode": get_mode()})

        # ── 审查进度 ──
        if path.startswith("/api/review/progress"):
            return self._json(200, {
                "ready": _cache["ready"],
                "taskId": _cache.get("taskId", ""),
                "issues": len(_cache.get("issues", [])),
                "conflicts": len(_cache.get("conflicts", [])),
            })

        # ── 配置API Key ──
        if path == "/api/config/key":
            provider = body.get("provider", "")
            api_key = body.get("api_key", "")
            if not provider or not api_key:
                return self._json(400, {"error": "provider和api_key必填"})
            cfg_set_key(provider, api_key)
            return self._json(200, {"ok": True, "message": f"{provider} 密钥已加密保存"})

        # ── 切换模式 ──
        if path == "/api/config/mode":
            mode = body.get("mode", "proxy")
            cfg_set_mode(mode)
            return self._json(200, {"ok": True, "mode": mode})

        self._json(404, {"error": "not found"})


def main():
    port = int(os.environ.get("V7_PORT", "2708"))
    bind_addr = os.environ.get("V7_BIND_ADDR", "127.0.0.1")  # 默认仅本地访问
    server = HTTPServer((bind_addr, port), APIHandler)
    print(f"\n{'='*50}")
    print(f"  AI智能审图系统 v7.0 API服务器")
    print(f"  端口: {port}")
    print(f"  模式: {get_mode()}")
    print(f"  前端: http://localhost:{port}/index.html")
    print(f"{'='*50}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
