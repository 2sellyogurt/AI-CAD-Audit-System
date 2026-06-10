# -*- coding: utf-8 -*-
"""v7.0 管理后台 — 基于 http.server 的统一入口

启动: python -m v7.admin.server [--port 2708]
"""

import json, os, sys, time, threading, uuid, hashlib, secrets, logging, traceback
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ROOT = os.path.dirname(PARENT)

PASSWORD_FILE = os.path.join(PARENT, ".admin_password")
OUTPUT_DIR = os.path.join(ROOT, "output_v7.0")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(OUTPUT_DIR, "admin.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("v7.admin")

# 共享的审查缓存（与旧 server.py 共用数据源）
_review_cache = {"issues": [], "stats": {}, "conflicts": [], "ready": False, "taskId": None}
_cache_lock = threading.Lock()

# ── 密码 ──

def _hash(pw):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000)
    return f"{salt}${h.hex()}"

def _verify(pw):
    if not os.path.exists(PASSWORD_FILE):
        return True
    with open(PASSWORD_FILE, "r") as f:
        stored = f.read().strip()
    if "$" not in stored:
        return pw == stored
    salt, h = stored.split("$", 1)
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000).hex() == h

def _session_token():
    if os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE) as f:
            return hashlib.sha256(f"v7_{f.read().strip()}".encode()).hexdigest()[:32]
    return "unset"

# ── HTML 组件 ──

_STYLE = """<link rel="stylesheet" href="/static/admin.css">
<style>
/* admin page-specific overrides */
#review-status .loading{color:var(--text-muted)}
</style>"""

_NAV = """<a href="#main-content" class="skip-nav">跳到主内容</a>
<div class="nav" role="navigation" aria-label="主导航">
<a href="/admin/dashboard" class="brand" aria-label="AI审图 v7.0 首页">⚡ AI审图 v7.0</a>
<a href="/admin/drawings" class="$active_dwg" aria-label="图纸管理">📐 图纸</a>
<a href="/admin/rules" class="$active_rul" aria-label="规则与专业维护">📋 规则</a>
<a href="/admin/agents" class="$active_agt" aria-label="Agent 配置">🤖 Agent</a>
<a href="/admin/api-config" class="$active_api" aria-label="API 密钥配置">🔑 API</a>
<a href="/admin/results" class="$active_res" aria-label="审查结果">📊 结果</a>
<a href="/admin/system" class="$active_sys" aria-label="系统维护">⚙️ 系统</a>
<span style="margin-left:auto;color:var(--text-muted);font-size:0.8rem" aria-label="个人版">个人版</span>
</div>"""


def _page(title, body, active="dash", script=""):
    nav = _NAV.replace("$active_dwg", "active" if active=="dwg" else "")\
              .replace("$active_rul", "active" if active=="rul" else "")\
              .replace("$active_agt", "active" if active=="agt" else "")\
              .replace("$active_api", "active" if active=="api" else "")\
              .replace("$active_res", "active" if active=="res" else "")\
              .replace("$active_sys", "active" if active=="sys" else "")
    return f"""<!DOCTYPE html><html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — AI审图 v7.0</title>{_STYLE}</head>
<body>{nav}<main id="main-content" role="main" aria-label="{title}"><div class="content"><h1>{title}</h1>{body}</div></main>
<script>{script}</script></body></html>"""


# ── 仪表盘内联内容 ──

_DASHBOARD_BODY = """<div class="stats">
<div class="stat"><div class="num" id="s-cp">—</div><div class="lbl">检查点</div></div>
<div class="stat"><div class="num" id="s-ag">—</div><div class="lbl">Agent</div></div>
<div class="stat"><div class="num" id="s-rv">—</div><div class="lbl">审查次数</div></div>
<div class="stat"><div class="num" id="s-is">—</div><div class="lbl">累计问题</div></div>
<div class="stat"><div class="num" id="s-dw">—</div><div class="lbl">图纸</div></div>
<div class="stat"><div class="num" id="s-pj">—</div><div class="lbl">项目</div></div>
</div>
<div class="card"><h3>快速操作</h3>
<a href="/admin/drawings" class="btn btn-primary mr-2">📐 图纸管理</a>
<a href="/admin/rules" class="btn btn-primary mr-2">📋 规则维护</a>
<a href="/admin/results" class="btn btn-primary mr-2">📊 审查结果</a>
<button class="btn btn-success mr-2" onclick="startReview()">▶ 启动审查</button>
<br><div id="review-status" class="mt-2"></div>
</div>"""

_DASHBOARD_SCRIPT = """
fetch('/admin/api/stats').then(r=>r.json()).then(d=>{
  document.getElementById('s-cp').innerText=d.checkpoints;
  document.getElementById('s-ag').innerText=d.agents;
  document.getElementById('s-rv').innerText=d.reviews;
  document.getElementById('s-is').innerText=d.issues;
  document.getElementById('s-dw').innerText=d.drawings;
  document.getElementById('s-pj').innerText=d.projects});
async function startReview(){
  document.getElementById('review-status').innerHTML='<div class=loading>⏳ 启动审查...</div>';
  const r=await fetch('/admin/api/review/start',{method:'POST'});
  const d=await r.json();
  document.getElementById('review-status').innerHTML='<div class="alert alert-s">✅ 审查已启动 (Task: '+d.taskId+')</div>';
  let poll=setInterval(async()=>{
    const p=await fetch('/admin/api/review/progress');
    const s=await p.json();
    if(s.ready){clearInterval(poll);
      document.getElementById('review-status').innerHTML='<div class="alert alert-s">✅ 审查完成！'+s.issues+'个问题，'+s.conflicts+'个冲突</div>'}
  },3000)}
"""


# ── 后台审查管线 ──

def _load_page(module_name):
    """统一延迟加载页面模块，返回 (render_page, handle_api)。"""
    import importlib
    mod = importlib.import_module(f"v7.admin.pages.{module_name}")
    return getattr(mod, "render_page"), getattr(mod, "handle_api")

# 页面路由 → (模块名, 显示标题, 导航 active 标识)
_PAGE_MODULES = {
    "/admin/drawings":  ("drawings",   "📐 图纸管理",   "dwg"),
    "/admin/rules":     ("rules",      "📋 规则与专业维护", "rul"),
    "/admin/agents":    ("agents",     "🤖 Agent 配置", "agt"),
    "/admin/api-config":("api_config", "🔑 API 配置",   "api"),
    "/admin/results":   ("results",    "📊 审查结果",   "res"),
    "/admin/system":    ("system",     "⚙️ 系统维护",   "sys"),
}

# 页面模块缓存
_PAGE_MODULES_CACHE = {}


# ── 后台审查管线 ──

def _run_review():
    task_id = uuid.uuid4().hex[:8]
    with _cache_lock:
        _review_cache["taskId"] = task_id
        _review_cache["ready"] = False
    try:
        from v7.llm_full_review import (
            detect_best_mode, review_all_real_llm,
            cross_discipline_analysis, load_spatial, DISCIPLINE_REVIEWER_MAP,
        )
        from v7.rationality_engine import annotate_all_rationality
        mode = detect_best_mode()
        if mode.value == "real":
            logger.info("实时LLM审查...")
            all_findings, _ = review_all_real_llm()
        else:
            logger.info("缓存审查...")
            all_findings = []
            for disc, reviewer in DISCIPLINE_REVIEWER_MAP.items():
                for i in reviewer():
                    i["discipline"] = disc
                    all_findings.append(i)
        cross = cross_discipline_analysis()
        all_with_cross = all_findings + cross
        all_with_cross = annotate_all_rationality(all_with_cross)
        spatial_raw = load_spatial()
        conflicts = [{"type": c.get("type",""),"severity": c.get("severity","D"),
                      "confidence": c.get("confidence","low"),"floor": c.get("floor",0),
                      "description": c.get("description","")[:200]} for c in spatial_raw]
        by_sev = {"A":0,"B":0,"C":0,"D":0}
        for f in all_with_cross:
            by_sev[f["severity"]] = by_sev.get(f["severity"],0)+1
        with _cache_lock:
            _review_cache.update(issues=all_with_cross, conflicts=conflicts, ready=True,
                taskId=task_id, stats={"totalIssues":len(all_with_cross),
                    "totalConflicts":len(conflicts),"bySeverity":by_sev,
                    "highConfConflicts":sum(1 for c in conflicts if c["confidence"]=="high"),
                    "reviewTimeMin":10})
        logger.info(f"审查完成: {len(all_with_cross)}项")
    except Exception as e:
        logger.error(f"审查异常: {e}")
        logger.error(traceback.format_exc())


# ── 请求处理器 ──

class AdminHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _html(self, code, content):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_raw(self, code, data, content_type):
        """发送非 JSON 响应（如 CSV）。"""
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", "attachment; filename=review_issues.csv")
        self.end_headers()
        if isinstance(data, str):
            self.wfile.write(data.encode("utf-8"))
        else:
            self.wfile.write(data)

    def _redirect(self, path):
        self.send_response(302)
        self.send_header("Location", path)
        self.end_headers()

    def _cookie(self, name, value, max_age=86400*30):
        self.send_header("Set-Cookie", f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly")

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length > 0 else {}

    def _check_auth(self):
        token = (self.headers.get("Cookie") or "").split("v7_admin_token=")
        if len(token) > 1:
            return token[1].split(";")[0] == _session_token()
        return False

    def _serve_static(self):
        """静态文件服务"""
        path = self.path.split("?")[0]
        if path == "/" or path == "":
            path = "/admin/dashboard"
        if path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return
        static_dir = os.path.join(HERE, "static")
        if path.startswith("/static/"):
            fp = os.path.join(static_dir, path[8:])
            if os.path.isfile(fp):
                self.send_response(200)
                ext = os.path.splitext(fp)[1]
                mimes = {".css":"text/css",".js":"text/javascript",".json":"application/json",
                         ".png":"image/png",".svg":"image/svg+xml",".ico":"image/x-icon"}
                self.send_header("Content-Type", mimes.get(ext, "application/octet-stream"))
                self.end_headers()
                with open(fp,"rb") as f: self.wfile.write(f.read())
                return

    def do_GET(self):
        self._serve_static()
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # ── 无需认证 ──
        if path == "/admin/login":
            return self._html(200, _page("登录", """<div class="card" style="max-width:400px;margin:60px auto" role="form" aria-label="管理员登录">
<h3>🔐 管理后台</h3><div class="form-group"><label for="admin-password">密码</label>
<input type="password" id="admin-password" placeholder="输入管理密码" autofocus aria-required="true"></div>
<button class="btn btn-primary" onclick="login()" aria-label="登录管理后台">登录</button>
<p id="msg" style="margin-top:10px" class="text-sev-a" role="alert"></p></div>""",
"""async function login(){const r=await fetch('/admin/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('admin-password').value})});const d=await r.json();if(d.ok)location.href='/admin/dashboard';else document.getElementById('msg').innerHTML='⚠ '+d.error}"""))

        # ── 公共 API ──
        if path == "/admin/api/login":
            return self.do_POST()
        if path == "/admin/api/set-password":
            return self.do_POST()

        # ── 需要认证 ──
        if not self._check_auth():
            return self._redirect("/admin/login")

        # ── API 端点 ──
        if path == "/admin/api/stats":
            from v7.db import get_db
            db = get_db()
            return self._json(200, {
                "checkpoints": db.execute("SELECT count(*) FROM checkpoints").fetchone()[0],
                "agents": db.execute("SELECT count(*) FROM agent_configs").fetchone()[0],
                "reviews": db.execute("SELECT count(*) FROM reviews").fetchone()[0],
                "issues": db.execute("SELECT count(*) FROM review_issues").fetchone()[0],
                "drawings": db.execute("SELECT count(*) FROM drawings").fetchone()[0],
                "projects": db.execute("SELECT count(*) FROM projects").fetchone()[0],
            })

        if path == "/admin/api/review/start":
            with _cache_lock:
                _review_cache["ready"] = False
            threading.Thread(target=_run_review, daemon=True).start()
            return self._json(202, {"status":"started","taskId":_review_cache.get("taskId","")})

        if path == "/admin/api/review/progress":
            return self._json(200, {"ready":_review_cache["ready"],
                "issues":len(_review_cache.get("issues",[])),
                "conflicts":len(_review_cache.get("conflicts",[]))})

        if path == "/admin/api/issues":
            items = list(_review_cache.get("issues",[]))
            sev = qs.get("severity",[None])[0]
            if sev and sev!="all":
                items = [i for i in items if i.get("severity")==sev]
            return self._json(200, {"total":len(items),"items":items})

        # ── 委托页面模块 API ──
        for page_path, (mod_name, _, _) in _PAGE_MODULES.items():
            api_prefix = page_path if mod_name == "api_config" else page_path.replace("/admin/", "/admin/api/", 1)
            if path.startswith(api_prefix):
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                _, ha = _PAGE_MODULES_CACHE[mod_name]
                result = ha(path, "GET", {}, qs)
                if result is not None:
                    status, data, ct = result
                    return self._json(status, data) if ct == "application/json" else self._send_raw(status, data, ct)

        # ── 页面路由 ──
        if path == "/admin/dashboard" or path == "/admin/" or path == "/admin":
            return self._html(200, _page("仪表盘", _DASHBOARD_BODY, "dash", _DASHBOARD_SCRIPT))

        # 动态页面（从模块渲染）
        for page_url, (mod_name, title, active) in _PAGE_MODULES.items():
            if path == page_url:
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                rp, _ = _PAGE_MODULES_CACHE[mod_name]
                body = rp()
                return self._html(200, _page(title, body, active))

        if path.startswith("/admin"):
            return self._redirect("/admin/dashboard")

        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        body = self._read_body()

        if path == "/admin/api/login":
            pw = body.get("password", "")
            if _verify(pw):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._cookie("v7_admin_token", _session_token())
                self.end_headers()
                self.wfile.write(json.dumps({"ok":True}).encode())
            else:
                self._json(401, {"ok":False,"error":"密码错误"})
            return

        if path == "/admin/api/set-password":
            pw = body.get("password", "")
            if len(pw) < 4:
                return self._json(400, {"ok":False,"error":"密码至少4位"})
            with open(PASSWORD_FILE, "w") as f:
                f.write(_hash(pw))
            try: os.chmod(PASSWORD_FILE, 0o600)
            except OSError: pass
            return self._json(200, {"ok":True})

        if path == "/admin/api/review/start":
            with _cache_lock:
                _review_cache["ready"] = False
            threading.Thread(target=_run_review, daemon=True).start()
            return self._json(202, {"status":"started"})

        # 委托页面模块 API (POST)
        for page_path, (mod_name, _, _) in _PAGE_MODULES.items():
            api_prefix = page_path if mod_name == "api_config" else page_path.replace("/admin/", "/admin/api/", 1)
            if path.startswith(api_prefix):
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                _, ha = _PAGE_MODULES_CACHE[mod_name]
                result = ha(path, "POST", body, qs)
                if result is not None:
                    status, data, ct = result
                    return self._json(status, data) if ct == "application/json" else self._send_raw(status, data, ct)

        self._json(404, {"error":"not found"})

    def do_PUT(self):
        """PUT 请求委托给页面模块 API。"""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        body = self._read_body()

        for page_path, (mod_name, _, _) in _PAGE_MODULES.items():
            api_prefix = page_path if mod_name == "api_config" else page_path.replace("/admin/", "/admin/api/", 1)
            if path.startswith(api_prefix):
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                _, ha = _PAGE_MODULES_CACHE[mod_name]
                try:
                    result = ha(path, "PUT", body, qs)
                    if result is not None:
                        status, data, ct = result
                        return self._json(status, data) if ct == "application/json" else self._send_raw(status, data, ct)
                except Exception as e:
                    self._json(500, {"error": str(e)})
                    return

        self._json(404, {"error": "not found"})

    def do_DELETE(self):
        """DELETE 请求委托给页面模块 API。"""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        for page_path, (mod_name, _, _) in _PAGE_MODULES.items():
            api_prefix = page_path if mod_name == "api_config" else page_path.replace("/admin/", "/admin/api/", 1)
            if path.startswith(api_prefix):
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                _, ha = _PAGE_MODULES_CACHE[mod_name]
                try:
                    result = ha(path, "DELETE", {}, qs)
                    if result is not None:
                        status, data, ct = result
                        return self._json(status, data) if ct == "application/json" else self._send_raw(status, data, ct)
                except Exception as e:
                    self._json(500, {"error": str(e)})
                    return

        self._json(404, {"error": "not found"})


def main():
    port = int(os.environ.get("V7_PORT", 2708))
    server = HTTPServer(("0.0.0.0", port), AdminHandler)
    print(f"\n{'='*50}")
    print(f"  AI智能审图系统 v7.0 — 管理后台")
    print(f"  地址: http://localhost:{port}/admin/dashboard")
    print(f"  API:  http://localhost:{port}/admin/api/stats")
    print(f"{'='*50}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n关闭服务...")
        server.server_close()


if __name__ == "__main__":
    main()
