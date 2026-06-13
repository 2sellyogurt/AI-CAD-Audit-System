# -*- coding: utf-8 -*-
"""v7.0 管理后台 — 基于 http.server 的统一入口

启动: python -m v7.admin.server [--port 2708]
"""

import json, os, sys, time, threading, uuid, hashlib, secrets, logging, logging.handlers, traceback
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ROOT = os.path.dirname(PARENT)

PASSWORD_FILE = os.path.join(PARENT, ".admin_password")
OUTPUT_DIR = os.path.join(ROOT, "output_v7.0")
PORT = int(os.environ.get("V7_PORT", 2708))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            os.path.join(OUTPUT_DIR, "admin.log"),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("v7.admin")

# 共享的审查缓存（与旧 server.py 共用数据源）
_review_cache = {"issues": [], "stats": {}, "conflicts": [], "ready": False, "taskId": None}
_cache_lock = threading.Lock()


def _restore_cache_from_db():
    """启动时从 SQLite 恢复最近一次审查结果到内存缓存。"""
    try:
        from v7.db import get_db
        db = get_db()
        row = db.execute(
            "SELECT id, total_issues, severity_a, severity_b, severity_c, severity_d, "
            "total_conflicts, elapsed_ms, result_json, status, started_at, finished_at "
            "FROM reviews ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row or row["status"] not in ("completed", "done"):
            return
        review_id = row["id"]
        issues_rows = db.execute(
            "SELECT * FROM review_issues WHERE review_id = ? ORDER BY id", (review_id,)
        ).fetchall()
        all_issues = [dict(r) for r in issues_rows]
        by_sev = {"A": row["severity_a"], "B": row["severity_b"],
                  "C": row["severity_c"], "D": row["severity_d"]}
        with _cache_lock:
            _review_cache.update(
                issues=all_issues, conflicts=[], ready=True,
                taskId=f"r{review_id}",
                stats={
                    "totalIssues": row["total_issues"],
                    "totalConflicts": row["total_conflicts"],
                    "bySeverity": by_sev,
                    "highConfConflicts": 0,
                    "reviewTimeMin": max(1, row["total_issues"] // 20) if row["total_issues"] else 0,
                    "pipeline": "v7",
                },
            )
        logger.info(f"从数据库恢复审查结果: review_id={review_id}, {len(all_issues)}项问题")
    except Exception as e:
        logger.warning(f"恢复审查缓存失败: {e}")


def _persist_review_to_db(task_id, all_issues, stats, elapsed_ms=0):
    """将审查结果持久化到 SQLite 的 reviews + review_issues 表。"""
    try:
        from v7.db import get_db
        db = get_db()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 确保有默认项目
        project_row = db.execute("SELECT id FROM projects LIMIT 1").fetchone()
        if not project_row:
            db.execute("INSERT INTO projects(name, dxf_dir, output_dir) VALUES (?, ?, ?)",
                       ("默认项目", "", ""))
            db.commit()
            project_row = db.execute("SELECT id FROM projects LIMIT 1").fetchone()
        project_id = project_row["id"]

        by_sev = stats.get("bySeverity", {})
        import json as _json
        db.execute(
            """INSERT INTO reviews (project_id, mode, status, total_issues,
               severity_a, severity_b, severity_c, severity_d,
               total_conflicts, elapsed_ms, started_at, finished_at, result_json)
               VALUES (?, 'cached', 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, stats.get("totalIssues", 0),
             by_sev.get("A", 0), by_sev.get("B", 0),
             by_sev.get("C", 0), by_sev.get("D", 0),
             stats.get("totalConflicts", 0), elapsed_ms,
             now_str, now_str,
             _json.dumps({"taskId": task_id, "pipeline": "v7"}, ensure_ascii=False)),
        )
        review_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 写入问题明细
        for issue in all_issues:
            db.execute(
                """INSERT INTO review_issues
                   (review_id, issue_id, checkpoint_id, discipline, severity,
                    standard_code, finding, fix, drawing_name, location,
                    confidence, route_used, rationality, rationality_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (review_id,
                 issue.get("id", issue.get("issue_id", "")),
                 issue.get("checkpoint_id", ""),
                 issue.get("discipline", ""),
                 issue.get("severity", "C"),
                 issue.get("standard_code", ""),
                 issue.get("finding", issue.get("suggestion", "")),
                 issue.get("fix", ""),
                 issue.get("drawing_name", ""),
                 issue.get("location", ""),
                 issue.get("confidence", "high"),
                 issue.get("route_used", "text"),
                 issue.get("rationality", "R2"),
                 issue.get("rationality_score", 60)),
            )
        db.commit()
        logger.info(f"审查结果已持久化: review_id={review_id}, {len(all_issues)}项问题")
        return review_id
    except Exception as e:
        logger.error(f"持久化审查结果失败: {e}")
        logger.error(traceback.format_exc())
        return None

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
    """后台审查线程 — 使用 v7 Agent集群管线 (CheckpointEngine + AgentOrchestrator)"""
    task_id = uuid.uuid4().hex[:8]
    start_time = time.time()
    with _cache_lock:
        _review_cache["taskId"] = task_id
        _review_cache["ready"] = False
    try:
        from v7.checkpoints import CheckpointEngine
        from v7.scheduler import AgentOrchestrator
        from v7.problem_pool import ProblemPool
        from v7.preprocessor import DrawingExtractor
        from v7.scanner import DrawingScanner
        from v7.rationality_engine import annotate_all_rationality

        # 1. 加载检查点
        engine = CheckpointEngine()
        logger.info(f"加载 {engine.total_count} 个检查点")

        # 2. 扫描图纸
        extractor = DrawingExtractor()
        dxf_files = extractor.find_dxf_files()
        drawings = [extractor.process_drawing(f) for f in dxf_files[:20]]  # 限制20份
        merged_text = "\n".join(d.text_content for d in drawings if d.text_content)
        logger.info(f"扫描 {len(drawings)} 份图纸")

        # 3. 创建Agent集群
        orch = AgentOrchestrator()
        orch.create_all_agents()
        logger.info(f"创建 {len(orch.agents)} 个Agent")

        # 4. 执行审查
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
                logger.info(f"  [{aid}] {agent_report.issues_found} issues found")
            except Exception as e:
                logger.warning(f"  [{aid}] 执行异常: {e}")

        # 5. 汇总结果
        all_issues = pool.to_list()
        all_issues = annotate_all_rationality(all_issues)
        by_sev = {"A": 0, "B": 0, "C": 0, "D": 0}
        for f in all_issues:
            sev = f.get("severity", "C")
            by_sev[sev] = by_sev.get(sev, 0) + 1

        with _cache_lock:
            _review_cache.update(
                issues=all_issues, conflicts=[], ready=True,
                taskId=task_id,
                stats={
                    "totalIssues": len(all_issues),
                    "totalConflicts": 0,
                    "bySeverity": by_sev,
                    "highConfConflicts": 0,
                    "reviewTimeMin": max(1, len(all_issues) // 20),
                    "pipeline": "v7",
                },
            )
        logger.info(f"v7审查完成: {len(all_issues)}项")

        # 持久化审查结果到 SQLite
        elapsed_ms = int((time.time() - start_time) * 1000)
        _persist_review_to_db(task_id, all_issues, _review_cache["stats"], elapsed_ms)

    except Exception as e:
        logger.error(f"审查异常: {e}")
        logger.error(traceback.format_exc())
        with _cache_lock:
            _review_cache["ready"] = True
            _review_cache["issues"] = []
            _review_cache["conflicts"] = []
            _review_cache["stats"] = {"totalIssues": 0, "totalConflicts": 0,
                                       "bySeverity": {}, "reviewTimeMin": 0, "pipeline": "v7"}


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
            # 检测是否有API Key配置
            has_api_key = False
            try:
                from v7.db import get_db
                db = get_db()
                row = db.execute("SELECT provider FROM api_keys WHERE api_key != '' LIMIT 1").fetchone()
                has_api_key = row is not None
            except Exception:
                pass

            api_hint = ""
            if not has_api_key:
                api_hint = """
                <div class="alert" style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:12px;margin-bottom:16px">
                  <strong>提示：</strong>尚未配置 LLM API 密钥，审查功能将无法使用。<br>
                  <span style="font-size:12px;color:#666">登录后请前往 <a href="/admin/api-config" style="color:#16213e">🔑 API 配置</a> 页面添加密钥（推荐智谱/DeepSeek）。</span>
                </div>"""

            return self._html(200, _page("登录", f"""<div class="card" style="max-width:400px;margin:60px auto" role="form" aria-label="管理员登录">
{api_hint}
<h3>🔐 管理后台</h3><div class="form-group"><label for="admin-password">密码</label>
<input type="password" id="admin-password" placeholder="输入管理密码" autofocus aria-required="true"></div>
<button class="btn btn-primary" onclick="login()" aria-label="登录管理后台">登录</button>
<p id="msg" style="margin-top:10px" class="text-sev-a" role="alert"></p></div>""",
"""async function login(){const r=await fetch('/admin/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('admin-password').value})});const d=await r.json();if(d.ok){if(d.firstLogin){document.getElementById('msg').innerHTML='⚠ 首次登录成功，请前往 ⚙️系统维护 设置管理密码';setTimeout(function(){location.href='/admin/dashboard';},2000);}else{location.href='/admin/dashboard';}}else{document.getElementById('msg').innerHTML='⚠ '+d.error;}}"""))

        # ── 公共 API（无需认证） ──
        if path == "/admin/api/login":
            return self.do_POST()
        if path == "/admin/api/set-password":
            return self.do_POST()
        if path == "/api/health":
            return self._json(200, {"status": "ok", "version": "7.0", "port": PORT})

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
            # 首次无密码时：任意密码可登录，并提示设置密码
            is_first_login = not os.path.exists(PASSWORD_FILE)
            if _verify(pw):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._cookie("v7_admin_token", _session_token())
                self.end_headers()
                resp = {"ok": True}
                if is_first_login:
                    resp["firstLogin"] = True
                    resp["hint"] = "首次登录成功，建议立即设置管理密码"
                self.wfile.write(json.dumps(resp, ensure_ascii=False).encode())
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
    # 初始化数据库并恢复上次审查结果
    try:
        from v7.db import init_db
        init_db()
        _restore_cache_from_db()
    except Exception as e:
        logger.warning(f"数据库初始化/缓存恢复异常: {e}")

    server = HTTPServer(("0.0.0.0", PORT), AdminHandler)
    print(f"\n{'='*50}")
    print(f"  AI智能审图系统 v7.0 — 管理后台")
    print(f"  地址: http://localhost:{PORT}/admin/dashboard")
    print(f"  API:  http://localhost:{PORT}/admin/api/stats")
    print(f"{'='*50}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n关闭服务...")
        server.server_close()


if __name__ == "__main__":
    main()
