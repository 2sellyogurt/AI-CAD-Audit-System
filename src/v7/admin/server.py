# -*- coding: utf-8 -*-
"""v7.0 管理后台 — 基于 http.server 的统一入口

启动: python -m v7.admin.server [--port 2708]
"""

import json, os, sys, time, threading, uuid, hashlib, secrets, logging, logging.handlers, traceback
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程HTTP服务器，解决审查期间前端无法访问的问题。"""
    daemon_threads = True
    allow_reuse_address = True

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
ROOT = os.path.dirname(PARENT)

# Ensure src is in sys.path for all imports
SRC_DIR = os.path.dirname(ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
# Also ensure PARENT (v7 dir parent) is in path for relative imports
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

PASSWORD_FILE = os.path.join(PARENT, ".admin_password")
OUTPUT_DIR = os.path.join(ROOT, "output_v7.0")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 端口配置
try:
    from v7.config_loader import get_config
    _cfg = get_config()
    PORT = _cfg.admin_port
except (ImportError, ValueError):
    PORT = int(os.environ.get("V7_ADMIN_PORT", os.environ.get("V7_PORT", "2708")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            os.path.join(OUTPUT_DIR, "admin.log"),
            maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("v7.admin")

# 共享的审查缓存（与旧 server.py 共用数据源）
_review_cache = {"issues": [], "stats": {}, "conflicts": [], "ready": False, "taskId": None, "agents": {}}
_cache_lock = threading.Lock()
_review_running = False  # 并发保护标志（任务2.2）


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
    """将审查结果持久化到 SQLite。"""
    try:
        from v7.db import get_db
        db = get_db()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        project_row = db.execute("SELECT id FROM projects LIMIT 1").fetchone()
        if not project_row:
            db.execute("INSERT INTO projects(name, dxf_dir, output_dir) VALUES (?, ?, ?)",
                       ("默认项目", "", ""))
            db.commit()
            project_row = db.execute("SELECT id FROM projects LIMIT 1").fetchone()
        project_id = project_row["id"]
        by_sev = stats.get("bySeverity", {})
        db.execute(
            """INSERT INTO reviews (project_id, mode, status, total_issues,
               severity_a, severity_b, severity_c, severity_d,
               total_conflicts, elapsed_ms, started_at, finished_at, result_json)
               VALUES (?, 'cached', 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, stats.get("totalIssues", 0),
             by_sev.get("A", 0), by_sev.get("B", 0),
             by_sev.get("C", 0), by_sev.get("D", 0),
             stats.get("totalConflicts", 0), int(elapsed_ms) if elapsed_ms else 0,
             now_str, now_str,
             json.dumps({"taskId": task_id, "pipeline": "v7"}, ensure_ascii=False)),
        )
        review_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
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
        return None


def _hash(pw):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000)
    return f"{salt}${h.hex()}"

def _verify(pw):
    if not os.path.exists(PASSWORD_FILE):
        return True
    with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
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

_login_attempts = {}
_login_lock = threading.Lock()

def _check_login_rate_limit(client_ip, max_attempts=5, window_seconds=300):
    now = time.time()
    with _login_lock:
        if client_ip in _login_attempts:
            _login_attempts[client_ip] = [
                ts for ts in _login_attempts[client_ip] if now - ts < window_seconds
            ]
        attempts = _login_attempts.get(client_ip, [])
        if len(attempts) >= max_attempts:
            oldest = min(attempts)
            remaining = int(window_seconds - (now - oldest)) + 1
            return False, max(1, remaining)
        if client_ip not in _login_attempts:
            _login_attempts[client_ip] = []
        _login_attempts[client_ip].append(now)
        return True, 0


_STYLE = """<link rel="stylesheet" href="/static/admin.css">
<style>
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
  if(!d.status && d.error){
    document.getElementById('review-status').innerHTML='<div class="alert alert-e">❌ '+d.error+'</div>';
    return;
  }
  document.getElementById('review-status').innerHTML='<div class="alert alert-s">✅ 审查已启动 (Task: '+d.taskId+')</div>';
  let poll=setInterval(async()=>{
    const p=await fetch('/admin/api/review/progress');
    const s=await p.json();
    let agentHtml = '';
    if(s.agents && Object.keys(s.agents).length > 0){
      agentHtml = '<div style="margin-top:8px;font-size:12px;color:#666">';
      for(const [aid, info] of Object.entries(s.agents)){
        const icon = info.status==='completed' ? '✅' : info.status==='error' ? '❌' : '⏳';
        agentHtml += '<span style="display:inline-block;margin:2px 6px 2px 0">'+icon+' '+aid+'</span>';
      }
      agentHtml += '</div>';
    }
    if(s.running){
      document.getElementById('review-status').innerHTML='<div class="alert alert-s">⏳ 审查进行中... '+s.completedAgents+'/'+s.totalAgents+' Agent完成，已发现'+s.issues+'个问题</div>'+agentHtml;
    }
    if(s.ready){clearInterval(poll);
      document.getElementById('review-status').innerHTML='<div class="alert alert-s">✅ 审查完成！'+s.issues+'个问题，'+s.conflicts+'个冲突</div>'+agentHtml}
  },3000)}
"""


def _load_page(module_name):
    import importlib
    mod = importlib.import_module(f"v7.admin.pages.{module_name}")
    return getattr(mod, "render_page"), getattr(mod, "handle_api")

_PAGE_MODULES = {
    "/admin/drawings":  ("drawings",   "📐 图纸管理",   "dwg"),
    "/admin/rules":     ("rules",      "📋 规则与专业维护", "rul"),
    "/admin/agents":    ("agents",     "🤖 Agent 配置", "agt"),
    "/admin/api-config":("api_config", "🔑 API 配置",   "api"),
    "/admin/results":   ("results",    "📊 审查结果",   "res"),
    "/admin/system":    ("system",     "⚙️ 系统维护",   "sys"),
}
_PAGE_MODULES_CACHE = {}


def _generate_reports(all_issues, conflicts):
    """审查完成后生成三场景报告 .docx 文件。"""
    import traceback as _tb
    try:
        from v7.report_generation.scene_reports import generate_all_scenes
        spatial = []
        for c in (conflicts or []):
            spatial.append({
                "type": c.get("type", ""),
                "severity": c.get("severity", "D"),
                "description": c.get("description", ""),
                "floor": c.get("floor", 0),
            })
        issues = []
        for i in (all_issues or []):
            issues.append({
                "id": i.get("id", i.get("issue_id", "")),
                "severity": i.get("severity", "C"),
                "discipline": i.get("discipline", ""),
                "description": i.get("finding", i.get("title", "")),
            })
        generate_all_scenes(OUTPUT_DIR, issues, spatial, "施工图审查项目")
        logger.info("三场景报告已生成")
    except Exception as e:
        logger.warning(f"报告生成失败: {e}")
        # 生成失败不影响审查主流程


def _run_review(drawing_ids=None, hard_timeout_sec=600):
    """后台审查线程。混沌工程韧性加固: 添加10分钟硬超时。"""
    global _review_running
    task_id = uuid.uuid4().hex[:8]
    start_time = time.time()
    timeout_reached = False
    with _cache_lock:
        _review_cache["taskId"] = task_id
        _review_cache["ready"] = False
        _review_cache["agents"] = {}
    try:
        from v7.checkpoints import CheckpointEngine
        from v7.scheduler import AgentOrchestrator
        from v7.problem_pool import ProblemPool
        from v7.scanner import DrawingScanner
        from v7.rationality_engine import annotate_all_rationality

        engine = CheckpointEngine()
        logger.info(f"加载 {engine.total_count} 个检查点")

        # 任务2.3: 优先使用数据库图纸
        if drawing_ids:
            try:
                from v7.db import get_db
                conn = get_db()
                # SQL注入防护：确保drawing_ids都是整数
                safe_ids = []
                for did in drawing_ids:
                    if isinstance(did, int):
                        safe_ids.append(did)
                    elif isinstance(did, str) and did.isdigit():
                        safe_ids.append(int(did))
                if not safe_ids:
                    logger.warning("drawing_ids中无有效ID，降级为目录扫描")
                    raise ValueError("无有效图纸ID")
                drawing_ids = safe_ids
                placeholders = ','.join('?' * len(drawing_ids))
                rows = conn.execute(
                    f"SELECT id, filename, file_path, discipline, text_content FROM drawings WHERE id IN ({placeholders})",
                    drawing_ids
                ).fetchall()
                drawings = []
                for row in rows:
                    d = type('Drawing', (), {
                        'id': row[0], 'filename': row[1], 'file_path': row[2],
                        'discipline': row[3], 'text_content': row[4] or ''
                    })()
                    drawings.append(d)
                merged_text = "\n".join(d.text_content for d in drawings if d.text_content)
                logger.info(f"使用指定图纸: {len(drawings)} 份 (IDs={drawing_ids})")
            except Exception as e:
                logger.warning(f"从数据库读取图纸失败: {e}，降级为目录扫描")
                drawings = []
                merged_text = ""
        else:
            # 降级：扫描目录
            try:
                from v7.preprocessor import DrawingExtractor
                extractor = DrawingExtractor()
                dxf_files = extractor.find_dxf_files()
                drawings = [extractor.process_drawing(f) for f in dxf_files[:20]]
            except ImportError as e:
                logger.error(f"图纸预处理依赖缺失: {e}")
                logger.error("请安装依赖: pip install ezdxf")
                drawings = []
                dxf_files = []
            merged_text = "\n".join(d.text_content for d in drawings if d.text_content)
            logger.info(f"扫描 {len(drawings)} 份图纸")

        orch = AgentOrchestrator()
        orch.create_all_agents()
        logger.info(f"创建 {len(orch.agents)} 个Agent")

        pool = ProblemPool()
        scanner = DrawingScanner()
        if merged_text:
            scan = scanner.scan(merged_text)
            active = scan.relevant_disciplines if scan and scan.relevant_disciplines else list(orch.agents.keys())
        else:
            active = list(orch.agents.keys())

        for aid in active:
            # 混沌工程韧性加固: 检查硬超时
            elapsed = time.time() - start_time
            if elapsed > hard_timeout_sec:
                logger.warning(f"审查超时 ({elapsed:.0f}s > {hard_timeout_sec}s)，停止剩余Agent")
                timeout_reached = True
                with _cache_lock:
                    for remaining_aid in active:
                        if remaining_aid not in _review_cache["agents"]:
                            _review_cache["agents"][remaining_aid] = {"status": "timeout", "issues": 0}
                break

            agent = orch.agents.get(aid)
            if not agent:
                continue
            with _cache_lock:
                _review_cache["agents"][aid] = {"status": "running", "issues": 0}
            try:
                agent_report = agent.execute(drawings, problem_pool=pool)
                with _cache_lock:
                    _review_cache["agents"][aid] = {"status": "completed", "issues": getattr(agent_report, 'issues_found', 0)}
                logger.info(f"  [{aid}] {agent_report.issues_found} issues found")
            except Exception as e:
                with _cache_lock:
                    _review_cache["agents"][aid] = {"status": "error", "error": str(e)}
                logger.warning(f"  [{aid}] 执行异常: {e}")

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
                    "timeout": timeout_reached,
                },
            )
        logger.info(f"v7审查完成: {len(all_issues)}项")

        elapsed_ms = int((time.time() - start_time) * 1000)
        _persist_review_to_db(task_id, all_issues, _review_cache["stats"], elapsed_ms)
        _generate_reports(all_issues, _review_cache.get("conflicts", []))

    except Exception as e:
        logger.error(f"审查异常: {e}")
        logger.error(traceback.format_exc())
        with _cache_lock:
            _review_cache["ready"] = True
            _review_cache["issues"] = []
            _review_cache["conflicts"] = []
            _review_cache["stats"] = {"totalIssues": 0, "totalConflicts": 0,
                                       "bySeverity": {}, "reviewTimeMin": 0, "pipeline": "v7"}
    finally:
        _review_running = False  # 任务2.2: 无论成功/失败都重置标志


_ALLOWED_ORIGINS = {
    "http://localhost", "https://localhost",
    "http://127.0.0.1", "https://127.0.0.1",
}

def _check_cors_origin(handler):
    origin = handler.headers.get("Origin", "")
    if not origin:
        return True, ""
    for allowed in _ALLOWED_ORIGINS:
        if origin.startswith(allowed):
            return True, origin
    return False, origin


class AdminHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        logger.debug(fmt % args if args else fmt)

    def _html(self, code, content):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _json(self, code, data, extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _file(self, path, mime):
        if not os.path.exists(path):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        import urllib.parse
        encoded = urllib.parse.quote(os.path.basename(path))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded}")
        self.end_headers()
        with open(path, "rb") as f:
            self.wfile.write(f.read())

    def _send_raw(self, code, data, content_type):
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
        self.send_header("Set-Cookie", f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict")

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length > 0 else {}

    def _check_auth(self):
        token = (self.headers.get("Cookie") or "").split("v7_admin_token=")
        if len(token) > 1:
            return token[1].split(";")[0] == _session_token()
        return False

    def _serve_static(self):
        path = self.path.split("?")[0]
        if path == "/" or path == "":
            return False
        if path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return True
        static_dir = os.path.join(HERE, "static")
        if path.startswith("/static/"):
            relative_path = path[8:]
            fp = os.path.join(static_dir, relative_path)
            real_fp = os.path.realpath(fp)
            real_static_dir = os.path.realpath(static_dir)
            if not real_fp.startswith(real_static_dir + os.sep) and real_fp != real_static_dir:
                self.send_response(403)
                self.end_headers()
                return True
            if os.path.isfile(real_fp):
                self.send_response(200)
                ext = os.path.splitext(real_fp)[1]
                mimes = {".css":"text/css",".js":"text/javascript",".json":"application/json",
                         ".png":"image/png",".svg":"image/svg+xml",".ico":"image/x-icon"}
                self.send_header("Content-Type", mimes.get(ext, "application/octet-stream"))
                self.end_headers()
                with open(real_fp,"rb") as f: self.wfile.write(f.read())
                return True
        return False

    # ── GET ──

    def do_GET(self):
        global _review_running
        allowed, origin = _check_cors_origin(self)
        if not allowed:
            self.send_response(403); self.end_headers(); return

        if self._serve_static():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path == "/admin/login":
            has_api_key = False
            try:
                from v7.db import get_db
                db = get_db()
                row = db.execute("SELECT purpose FROM llm_configs WHERE api_key != '' LIMIT 1").fetchone()
                if not row:
                    row = db.execute("SELECT provider FROM api_keys WHERE api_key != '' LIMIT 1").fetchone()
                has_api_key = row is not None
            except:
                pass
            api_hint = ""
            if not has_api_key:
                api_hint = """<div class="alert" style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:12px;margin-bottom:16px">
                  <strong>提示：</strong>尚未配置 LLM API 密钥，审查功能将无法使用。<br>
                  <span style="font-size:12px;color:#666">登录后请前往 <a href="/admin/api-config" style="color:#16213e">🔑 API 配置</a> 页面添加密钥（推荐智谱/DeepSeek）。</span>
                </div>"""
            return self._html(200, _page("登录", f"""<div class="card" style="max-width:400px;margin:60px auto" role="form" aria-label="管理员登录">
{api_hint}
<h3>🔐 管理后台</h3><div class="form-group"><label for="admin-password">密码</label>
<input type="password" id="admin-password" placeholder="输入管理密码" autofocus aria-required="true"></div>
<button class="btn btn-primary" onclick="login()" aria-label="登录管理后台">登录</button>
<p id="msg" style="margin-top:10px" class="text-sev-a" role="alert"></p></div>""", "login", """async function login(){const r=await fetch('/admin/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('admin-password').value})});const d=await r.json();if(d.ok){if(d.firstLogin){document.getElementById('msg').innerHTML='⚠ 首次登录成功，请前往 ⚙️系统维护 设置管理密码';setTimeout(function(){location.href='/admin/dashboard';},2000);}else{location.href='/admin/dashboard';}}else{document.getElementById('msg').innerHTML='⚠ '+d.error;}}"""))

        if path == "/admin/api/login":
            return self.do_POST()
        if path == "/admin/api/set-password":
            return self.do_POST()
        # 混沌工程韧性加固: 增强健康检查端点
        if path == "/api/health":
            health = {
                "status": "ok",
                "version": "7.0",
                "port": PORT,
                "ready": _review_cache.get("ready", False),
                "review_running": _review_running,
            }
            # 数据库连通性检查
            try:
                from v7.db import get_db
                conn = get_db()
                conn.execute("SELECT 1")
                health["db"] = "connected"
            except Exception as e:
                health["db"] = f"error: {str(e)[:100]}"
            # LLM API 连通性检查（快速探测）
            try:
                from v7.config_loader import get_llm_config
                text_cfg = get_llm_config("text")
                if text_cfg and text_cfg.get("api_key"):
                    health["llm_text"] = "configured"
                else:
                    health["llm_text"] = "not_configured"
                vision_cfg = get_llm_config("vision")
                if vision_cfg and vision_cfg.get("api_key"):
                    health["llm_vision"] = "configured"
                else:
                    health["llm_vision"] = "not_configured"
            except Exception as e:
                health["llm"] = f"error: {str(e)[:100]}"
            # 熔断器状态
            try:
                from v7.llm.base_adapter import LLMBaseAdapter
                health["circuit_breaker"] = "available"
            except Exception:
                health["circuit_breaker"] = "unavailable"
            # 缓存状态
            health["cache"] = {
                "issues_count": len(_review_cache.get("issues", [])),
                "conflicts_count": len(_review_cache.get("conflicts", [])),
                "agents_count": len(_review_cache.get("agents", {})),
            }
            return self._json(200, health)

        # ── SPA /api/* 公共端点 ──
        if path == "/api/stats":
            if not _review_cache.get("ready"):
                return self._json(503, {"error": "审查数据未就绪，请先调用 POST /api/review/start"})
            return self._json(200, _review_cache.get("stats", {}))

        if path == "/api/issues":
            if not _review_cache.get("ready"):
                return self._json(503, {"error": "审查数据未就绪"})
            issues = list(_review_cache.get("issues", []))
            sev = qs.get("severity", [None])[0]
            rat = qs.get("rationality", [None])[0]
            disc = qs.get("discipline", [None])[0]
            search = qs.get("search", [None])[0]
            if sev and sev != "all":
                issues = [i for i in issues if i.get("severity") == sev]
            if rat and rat != "all":
                issues = [i for i in issues if i.get("rationality", {}).get("level") == rat]
            if disc:
                issues = [i for i in issues if i.get("discipline", "") == disc]
            if search:
                s = search.lower()
                issues = [i for i in issues if s in i.get("title", "").lower() or s in i.get("id", "").lower()]
            return self._json(200, {"total": len(issues), "items": issues})

        if path.startswith("/api/issues/"):
            issue_id = path.split("/")[-1]
            for i in _review_cache.get("issues", []):
                if i.get("id") == issue_id:
                    return self._json(200, i)
            return self._json(404, {"error": "not found"})

        if path == "/api/conflicts":
            if not _review_cache.get("ready"):
                return self._json(503, {"error": "审查数据未就绪"})
            return self._json(200, {"total": len(_review_cache.get("conflicts", [])), "items": _review_cache.get("conflicts", [])})

        # 任务1.2: 图纸列表端点
        if path == "/api/drawings":
            try:
                from v7.db import get_db
                conn = get_db()
                rows = conn.execute(
                    "SELECT d.id, d.filename, d.discipline, d.file_size_kb, d.text_entities, d.status, d.uploaded_at, p.name "
                    "FROM drawings d LEFT JOIN projects p ON d.project_id = p.id "
                    "ORDER BY d.uploaded_at DESC LIMIT 100"
                ).fetchall()
                items = []
                for r in rows:
                    items.append({
                        "id": r[0], "filename": r[1], "discipline": r[2] or "未分类",
                        "file_size_kb": r[3] or 0, "text_entities": r[4] or 0,
                        "status": r[5] or "uploaded", "uploaded_at": r[6] or "",
                        "project_name": r[7] or "未命名项目"
                    })
                return self._json(200, {"ok": True, "drawings": items})
            except Exception as e:
                logger.error(f"图纸列表查询失败: {e}")
                return self._json(200, {"ok": True, "drawings": []})

        # 任务1.3: 图纸删除端点 (GET /api/drawings/delete/{id})
        if path.startswith("/api/drawings/delete/"):
            did = path.split("/")[-1]
            try:
                from v7.db import get_db
                conn = get_db()
                row = conn.execute("SELECT file_path FROM drawings WHERE id=?", (did,)).fetchone()
                if not row:
                    return self._json(404, {"ok": False, "error": "图纸不存在"})
                fp = row[0]
                if fp and os.path.isfile(fp):
                    os.remove(fp)
                conn.execute("DELETE FROM drawings WHERE id=?", (did,))
                conn.commit()
                logger.info(f"图纸已删除: id={did}")
                return self._json(200, {"ok": True, "message": "图纸已删除"})
            except Exception as e:
                logger.error(f"图纸删除失败: {e}")
                return self._json(500, {"ok": False, "error": str(e)})

        # 动态查找报告文件
        report_map = {
            "scene1": ["基础错漏", "设计审查"],
            "scene2": ["跨专业", "施工审查"],
            "scene3": ["强条合规", "竣工验收"],
        }
        for scene, keywords in report_map.items():
            if path == f"/api/reports/{scene}":
                best = None
                if os.path.isdir(OUTPUT_DIR):
                    for fn in os.listdir(OUTPUT_DIR):
                        if fn.endswith(".docx") and any(k in fn for k in keywords):
                            best = os.path.join(OUTPUT_DIR, fn)
                            break
                if best and os.path.isfile(best):
                    return self._file(best, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                return self._json(404, {"error": "报告文件未找到，请先执行审查"})

        if path == "/api/config":
            try:
                from v7.secure_config import get_all_providers
                return self._json(200, get_all_providers())
            except ImportError:
                return self._json(200, {"mode": "proxy", "provider": "", "configured_providers": []})

        # 任务1.4: API配置状态端点
        if path == "/api/config/api-status":
            try:
                from v7.db import get_db
                conn = get_db()
                # 优先读取新表 llm_configs
                text_row = conn.execute("SELECT provider, api_key, base_url, model FROM llm_configs WHERE purpose='text'").fetchone()
                vision_row = conn.execute("SELECT provider, api_key, base_url, model FROM llm_configs WHERE purpose='vision'").fetchone()
                if text_row and text_row[1]:
                    return self._json(200, {
                        "ok": True, "configured": True,
                        "text_provider": text_row[0], "text_api_key": text_row[1],
                        "text_base_url": text_row[2], "text_model": text_row[3],
                        "vision_provider": vision_row[0] if vision_row else "",
                        "vision_api_key": vision_row[1] if vision_row else "",
                        "vision_base_url": vision_row[2] if vision_row else "",
                        "vision_model": vision_row[3] if vision_row else "",
                    })
                # 兼容旧表
                row = conn.execute("SELECT provider, api_key, base_url, text_model, vision_model, is_default FROM api_keys WHERE is_default=1").fetchone()
                if row and row[1]:
                    return self._json(200, {
                        "ok": True, "configured": True,
                        "provider": row[0], "api_key": row[1],
                        "base_url": row[2], "text_model": row[3],
                        "vision_model": row[4], "is_default": bool(row[5])
                    })
                return self._json(200, {"ok": True, "configured": False})
            except Exception as e:
                logger.error(f"API状态查询失败: {e}")
                return self._json(200, {"ok": True, "configured": False})

        if path.startswith("/api/review/progress"):
            parts = [p for p in path.split("/") if p]
            task_id = parts[-1] if len(parts) >= 5 and parts[-1] else ""
            agents_progress = _review_cache.get("agents", {})
            total_agents = len(agents_progress)
            completed_agents = sum(1 for a in agents_progress.values() if a.get("status") == "completed")
            return self._json(200, {
                "ready": _review_cache.get("ready", False),
                "taskId": _review_cache.get("taskId", task_id),
                "issues": len(_review_cache.get("issues", [])),
                "conflicts": len(_review_cache.get("conflicts", [])),
                "running": _review_running,
                "totalAgents": total_agents,
                "completedAgents": completed_agents,
                "agents": agents_progress,
            })

        # ── 需要认证 ──
        if not self._check_auth():
            return self._redirect("/admin/login")

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
            if _review_running:
                return self._json(409, {"ok": False, "error": "审查正在进行中"})
            _review_running = True
            with _cache_lock:
                _review_cache["ready"] = False
            threading.Thread(target=_run_review, daemon=True).start()
            return self._json(202, {"status":"started","taskId":_review_cache.get("taskId","")})

        if path == "/admin/api/review/progress":
            agents_progress = _review_cache.get("agents", {})
            total_agents = len(agents_progress)
            completed_agents = sum(1 for a in agents_progress.values() if a.get("status") == "completed")
            return self._json(200, {
                "ready": _review_cache["ready"],
                "issues": len(_review_cache.get("issues", [])),
                "conflicts": len(_review_cache.get("conflicts", [])),
                "running": _review_running,
                "totalAgents": total_agents,
                "completedAgents": completed_agents,
                "agents": agents_progress,
            })

        if path == "/admin/api/issues":
            items = list(_review_cache.get("issues",[]))
            sev = qs.get("severity",[None])[0]
            if sev and sev!="all":
                items = [i for i in items if i.get("severity")==sev]
            return self._json(200, {"total":len(items),"items":items})

        # 优先匹配精确页面路由（避免/api-config被API前缀拦截）
        if path == "/admin/dashboard" or path == "/admin/" or path == "/admin":
            return self._html(200, _page("仪表盘", _DASHBOARD_BODY, "dash", _DASHBOARD_SCRIPT))

        for page_url, (mod_name, title, active) in _PAGE_MODULES.items():
            if path == page_url:
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                rp, _ = _PAGE_MODULES_CACHE[mod_name]
                body = rp()
                return self._html(200, _page(title, body, active))

        # API路由（在页面路由之后，避免页面URL被API前缀拦截）
        for page_path, (mod_name, _, _) in _PAGE_MODULES.items():
            api_prefix = page_path.replace("/admin/", "/admin/api/", 1)
            if path.startswith(api_prefix):
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                _, ha = _PAGE_MODULES_CACHE[mod_name]
                result = ha(path, "GET", {}, qs)
                if result is not None:
                    status, data, ct = result
                    return self._json(status, data) if ct.startswith("application/json") else self._send_raw(status, data, ct)

        if path == "/index.html" or path == "/review":
            spa_path = os.path.join(ROOT, "index.html")
            if os.path.isfile(spa_path):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                with open(spa_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "index.html not found")
                return

        if path.startswith("/admin"):
            return self._redirect("/admin/dashboard")

        self.send_error(404)

    # ── POST ──

    def do_POST(self):
        allowed, origin = _check_cors_origin(self)
        if not allowed:
            self.send_response(403); self.end_headers(); return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        body = self._read_body()

        if path == "/admin/api/login":
            client_ip = self.client_address[0]
            allowed, remaining = _check_login_rate_limit(client_ip)
            if not allowed:
                return self._json(429, {"ok": False, "error": f"登录尝试过于频繁，请在 {remaining} 秒后重试"})
            password = body.get("password", "")
            if _verify(password):
                token = _session_token()
                first_login = not os.path.exists(PASSWORD_FILE)
                logger.info(f"登录成功 (IP={client_ip}, first={first_login})")
                return self._json(200, {"ok": True, "firstLogin": first_login},
                    extra_headers={"Set-Cookie": f"v7_admin_token={token}; Path=/; Max-Age={86400*30}; HttpOnly; SameSite=Strict"})
            else:
                logger.warning(f"登录失败 (IP={client_ip})")
                return self._json(401, {"ok": False, "error": "密码错误"})

        if path == "/admin/api/set-password":
            password = body.get("password", "")
            if not password or len(password) < 6:
                return self._json(400, {"ok": False, "error": "密码长度不能少于6位"})
            try:
                hashed = _hash(password)
                with open(PASSWORD_FILE, "w", encoding="utf-8") as f:
                    f.write(hashed)
                token = _session_token()
                logger.info("管理密码已设置")
                return self._json(200, {"ok": True},
                    extra_headers={"Set-Cookie": f"v7_admin_token={token}; Path=/; Max-Age={86400*30}; HttpOnly; SameSite=Strict"})
            except Exception as e:
                logger.error(f"设置密码失败: {e}")
                return self._json(500, {"ok": False, "error": f"设置密码失败: {e}"})

        # 任务1.1: 图纸上传端点
        if path == "/api/drawings/upload":
            import cgi
            try:
                content_type = self.headers.get("Content-Type", "")
                if "multipart/form-data" not in content_type:
                    return self._json(400, {"ok": False, "error": "不支持的文件格式，需要 multipart/form-data"})
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        "REQUEST_METHOD": "POST",
                        "CONTENT_TYPE": content_type,
                    }
                )
                file_item = form["file"]
                if not file_item or not file_item.filename:
                    return self._json(400, {"ok": False, "error": "未选择文件"})
                filename = os.path.basename(file_item.filename)
                ext = os.path.splitext(filename)[1].lower()
                if ext not in (".dxf", ".dwg"):
                    return self._json(400, {"ok": False, "error": f"不支持的文件格式: {ext}"})
                upload_dir = os.path.join(PARENT, "data", "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                save_path = os.path.join(upload_dir, filename)
                with open(save_path, "wb") as f:
                    f.write(file_item.file.read())
                file_size_kb = os.path.getsize(save_path) // 1024
                # 从文件名推断专业
                fn = filename.lower()
                if any(k in fn for k in ["结施", "结构", "基础", "配筋", "s-", "str"]):
                    discipline = "结构"
                elif any(k in fn for k in ["建施", "建筑", "总图", "平面", "b-", "bld"]):
                    discipline = "建筑"
                elif any(k in fn for k in ["暖施", "暖通", "空调", "通风", "h-", "hvac"]):
                    discipline = "暖通"
                elif any(k in fn for k in ["水施", "给排水", "给水", "排水", "p-", "plumb"]):
                    discipline = "给排水"
                elif any(k in fn for k in ["电施", "电气", "配电", "照明", "e-", "elec"]):
                    discipline = "电气"
                else:
                    discipline = "未分类"
                # 提取文本实体数
                text_entities = 0
                text_content = ""
                if ext == ".dxf":
                    try:
                        import ezdxf
                        doc = ezdxf.readfile(save_path)
                        msp = doc.modelspace()
                        texts = [e for e in msp if e.dxftype() in ("TEXT", "MTEXT")]
                        text_entities = len(texts)
                        text_content = "\n".join(e.dxf.get("text", str(e)) for e in texts[:500])
                    except Exception as e:
                        logger.warning(f"DXF文本提取失败: {e}")
                # 写入数据库
                try:
                    from v7.db import get_db
                    conn = get_db()
                    cur = conn.execute(
                        "INSERT INTO drawings (project_id, filename, file_path, discipline, text_content, file_size_kb, text_entities, status, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (1, filename, save_path, discipline, text_content, file_size_kb, text_entities, "uploaded", datetime.now().isoformat())
                    )
                    conn.commit()
                    did = cur.lastrowid
                except Exception as db_err:
                    # 数据库写入失败，删除已上传的文件（事务回滚）
                    logger.error(f"数据库写入失败，回滚文件: {db_err}")
                    try:
                        os.remove(save_path)
                    except OSError:
                        pass
                    return self._json(500, {"ok": False, "error": f"数据库写入失败: {str(db_err)}"})
                logger.info(f"图纸上传成功: {filename} (id={did}, {discipline}, {text_entities} entities)")
                return self._json(200, {
                    "ok": True,
                    "uploaded": [{"id": did, "filename": filename, "file_size_kb": file_size_kb, "text_entities": text_entities}],
                    "message": "上传成功"
                })
            except Exception as e:
                logger.error(f"图纸上传失败: {e}")
                logger.error(traceback.format_exc())
                return self._json(500, {"ok": False, "error": str(e)})

        # 任务2.1+2.2+P1-009: 修复 review/start（读取body + 并发保护 + 认证）
        if path == "/api/review/start":
            if not self._check_auth():
                return self._json(401, {"ok": False, "error": "请先登录"})
            if _review_running:
                return self._json(409, {"ok": False, "error": "审查正在进行中"})
            drawing_ids = body.get("drawing_ids", [])
            if not drawing_ids:
                # 无指定图纸时仍允许启动（使用目录扫描降级）
                pass
            _review_running = True
            with _cache_lock:
                _review_cache["ready"] = False
            threading.Thread(target=_run_review, args=(drawing_ids if drawing_ids else None,), daemon=True).start()
            return self._json(202, {"ok": True, "taskId": _review_cache.get("taskId", ""), "status": "started", "message": "审查任务已启动"})

        # 任务1.5: API配置保存端点
        if path == "/api/config/api-save":
            provider = body.get("provider", "")
            api_key = body.get("api_key", "")
            base_url = body.get("base_url", "")
            text_model = body.get("text_model", "")
            vision_model = body.get("vision_model", "")
            if not api_key:
                return self._json(400, {"ok": False, "error": "API密钥不能为空"})
            try:
                from v7.db import get_db
                conn = get_db()
                # 同时保存到新表 llm_configs（按用途分离）
                from v7.crypto_utils import encrypt_text
                now = datetime.now().isoformat()
                encrypted_key = encrypt_text(api_key) if api_key else ""
                # 文本模型
                conn.execute(
                    """INSERT INTO llm_configs (purpose, provider, api_key, base_url, model, updated_at)
                       VALUES ('text', ?, ?, ?, ?, ?)
                       ON CONFLICT(purpose) DO UPDATE SET
                       provider=excluded.provider, api_key=excluded.api_key,
                       base_url=excluded.base_url, model=excluded.model,
                       updated_at=excluded.updated_at""",
                    (provider, encrypted_key, base_url, text_model, now)
                )
                # 视觉模型（如果vision_model有值且与text不同provider，需要单独处理；这里简化：同provider共享key）
                if vision_model:
                    conn.execute(
                        """INSERT INTO llm_configs (purpose, provider, api_key, base_url, model, updated_at)
                           VALUES ('vision', ?, ?, ?, ?, ?)
                           ON CONFLICT(purpose) DO UPDATE SET
                           provider=excluded.provider, api_key=excluded.api_key,
                           base_url=excluded.base_url, model=excluded.model,
                           updated_at=excluded.updated_at""",
                        (provider, encrypted_key, base_url, vision_model, now)
                    )
                # 兼容旧表
                conn.execute("UPDATE api_keys SET is_default=0 WHERE is_default=1")
                conn.execute(
                    "INSERT OR REPLACE INTO api_keys (provider, api_key, base_url, text_model, vision_model, is_default) VALUES (?,?,?,?,?,?)",
                    (provider, api_key, base_url, text_model, vision_model, 1)
                )
                conn.commit()
                logger.info(f"API配置已保存: provider={provider}, text_model={text_model}, vision_model={vision_model}")
                return self._json(200, {"ok": True, "message": "API配置已保存"})
            except Exception as e:
                logger.error(f"API配置保存失败: {e}")
                return self._json(500, {"ok": False, "error": str(e)})

        # 任务1.6: API联通测试端点
        if path == "/api/config/api-test":
            provider = body.get("provider", "")
            api_key = body.get("api_key", "")
            base_url = body.get("base_url", "").rstrip("/")
            if not api_key or not base_url:
                return self._json(400, {"ok": False, "error": "API Key 和 Base URL 不能为空"})
            # 模型名映射
            model_map = {"zhipu": "glm-4-flash", "deepseek": "deepseek-chat", "qwen": "qwen-turbo", "openai": "gpt-3.5-turbo"}
            model = model_map.get(provider, "glm-4-flash")
            def _test_api():
                import http.client
                try:
                    parsed = urlparse(base_url)
                    host = parsed.hostname
                    port = parsed.port or (443 if parsed.scheme == "https" else 80)
                    conn_api = http.client.HTTPSConnection(host, port, timeout=15)
                    payload = json.dumps({
                        "model": model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 5
                    }).encode("utf-8")
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + api_key,
                        "Content-Length": str(len(payload))
                    }
                    conn_api.request("POST", parsed.path or "/v4/chat/completions", body=payload, headers=headers)
                    resp = conn_api.getresponse()
                    resp_body = resp.read().decode("utf-8")
                    conn_api.close()
                    if resp.status == 200:
                        return {"ok": True, "message": "连接成功", "response": resp_body[:500]}
                    else:
                        return {"ok": False, "error": f"连接失败: HTTP {resp.status} - {resp_body[:200]}"}
                except Exception as e:
                    return {"ok": False, "error": f"连接失败: {str(e)}"}
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_test_api)
                try:
                    result = future.result(timeout=20)
                    return self._json(200, result)
                except concurrent.futures.TimeoutError:
                    return self._json(504, {"ok": False, "error": "连接超时（20秒）"})

        if not self._check_auth():
            return self._json(401, {"ok": False, "error": "未登录"})

        if path == "/admin/api/review/start":
            with _cache_lock:
                _review_cache["ready"] = False
            # 从数据库获取所有就绪图纸ID
            try:
                from v7.db import get_db
                db = get_db()
                rows = db.execute("SELECT id FROM drawings WHERE status = 'ready'").fetchall()
                drawing_ids = [row["id"] for row in rows]
                logger.info(f"启动审查，使用 {len(drawing_ids)} 张就绪图纸")
            except Exception as e:
                logger.warning(f"读取就绪图纸失败: {e}")
                drawing_ids = None
            threading.Thread(target=_run_review, args=(drawing_ids,), daemon=True).start()
            return self._json(202, {"status": "started", "taskId": _review_cache.get("taskId", "")})

        for page_path, (mod_name, _, _) in _PAGE_MODULES.items():
            api_prefix = page_path.replace("/admin/", "/admin/api/", 1)
            if path.startswith(api_prefix):
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                _, ha = _PAGE_MODULES_CACHE[mod_name]
                result = ha(path, "POST", body, qs)
                if result is not None:
                    status, data, ct = result
                    return self._json(status, data) if ct.startswith("application/json") else self._send_raw(status, data, ct)

        self._json(404, {"ok": False, "error": "unknown POST endpoint"})

    # ── PUT ──

    def do_PUT(self):
        allowed, origin = _check_cors_origin(self)
        if not allowed:
            self.send_response(403); self.end_headers(); return

        if not self._check_auth():
            return self._json(401, {"ok": False, "error": "未登录"})

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        body = self._read_body()

        for page_path, (mod_name, _, _) in _PAGE_MODULES.items():
            api_prefix = page_path.replace("/admin/", "/admin/api/", 1)
            if path.startswith(api_prefix):
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                _, ha = _PAGE_MODULES_CACHE[mod_name]
                result = ha(path, "PUT", body, qs)
                if result is not None:
                    status, data, ct = result
                    return self._json(status, data) if ct.startswith("application/json") else self._send_raw(status, data, ct)

        self._json(404, {"ok": False, "error": "unknown PUT endpoint"})

    # ── DELETE ──

    def do_DELETE(self):
        allowed, origin = _check_cors_origin(self)
        if not allowed:
            self.send_response(403); self.end_headers(); return

        if not self._check_auth():
            return self._json(401, {"ok": False, "error": "未登录"})

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        body = self._read_body()

        for page_path, (mod_name, _, _) in _PAGE_MODULES.items():
            api_prefix = page_path.replace("/admin/", "/admin/api/", 1)
            if path.startswith(api_prefix):
                if mod_name not in _PAGE_MODULES_CACHE:
                    _PAGE_MODULES_CACHE[mod_name] = _load_page(mod_name)
                _, ha = _PAGE_MODULES_CACHE[mod_name]
                result = ha(path, "DELETE", body, qs)
                if result is not None:
                    status, data, ct = result
                    return self._json(status, data) if ct.startswith("application/json") else self._send_raw(status, data, ct)

        self._json(404, {"ok": False, "error": "unknown DELETE endpoint"})


def main():
    try:
        from v7.db import init_db, get_db
        init_db()
        # 自动迁移：如果agent_configs为空，执行数据迁移
        try:
            db = get_db()
            agent_count = db.execute("SELECT COUNT(*) FROM agent_configs").fetchone()[0]
            if agent_count == 0:
                logger.info("agent_configs 表为空，自动执行数据迁移...")
                from v7.db.migrate import auto_migrate
                result = auto_migrate(force=False)
                if result.get("errors"):
                    logger.warning(f"自动迁移出错: {result['errors']}")
                else:
                    logger.info(f"自动迁移完成: agents={result.get('agents', 0)}, checkpoints={result.get('checkpoints', 0)}")
        except Exception as e:
            logger.warning(f"自动迁移检查失败: {e}")
        _restore_cache_from_db()
    except Exception as e:
        logger.warning(f"数据库初始化/缓存恢复异常: {e}")

    server = ThreadedHTTPServer(("0.0.0.0", PORT), AdminHandler)
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
