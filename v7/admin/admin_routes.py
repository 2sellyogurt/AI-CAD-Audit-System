# -*- coding: utf-8 -*-
"""管理后台 Blueprint — 个人版密码锁 + 页面骨架 + 导航

页面:
  /admin/            首页仪表盘
  /admin/drawings    图纸管理
  /admin/rules       规则+专业维护
  /admin/agents      Agent 配置
  /admin/api-config  API 密钥 + 费用统计
  /admin/results     审查结果管理
  /admin/system      系统维护
"""

import os
import hashlib
import secrets

from flask import Blueprint, request, jsonify, redirect, make_response, current_app

admin_bp = Blueprint("admin", __name__, template_folder=None)

PASSWORD_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              ".admin_password")


# ── 密码管理 ────────────────────────────────────────────

def _hash(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000)
    return f"{salt}${h.hex()}"


def _verify(password: str) -> bool:
    if not os.path.exists(PASSWORD_FILE):
        return True  # 首次使用无密码
    with open(PASSWORD_FILE, "r") as f:
        stored = f.read().strip()
    if "$" not in stored:
        return password == stored
    salt, h = stored.split("$", 1)
    computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000)
    return computed.hex() == h


def is_authenticated():
    return request.cookies.get("v7_admin_token") == _get_token()


def _get_token() -> str:
    if os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE) as f:
            stored = f.read().strip()
        return hashlib.sha256(f"v7_session_{stored}".encode()).hexdigest()[:32]
    return "unset"


# ── 鉴权中间件 ──────────────────────────────────────────

@admin_bp.before_request
def check_auth():
    path = request.path
    if path in ("/admin/login", "/admin/api/login", "/admin/api/set-password"):
        return None
    if not is_authenticated():
        if request.path.startswith("/admin/api/"):
            return jsonify({"error": "unauthorized", "need_login": True}), 401
        return redirect("/admin/login")


# ── 登录 API ────────────────────────────────────────────

@admin_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if _verify(password):
        resp = jsonify({"ok": True})
        resp.set_cookie("v7_admin_token", _get_token(), max_age=86400*30, httponly=True)
        return resp
    return jsonify({"ok": False, "error": "密码错误"}), 401


@admin_bp.route("/api/set-password", methods=["POST"])
def api_set_password():
    data = request.get_json(silent=True) or {}
    new_pw = data.get("password", "")
    if len(new_pw) < 4:
        return jsonify({"ok": False, "error": "密码至少4位"}), 400
    with open(PASSWORD_FILE, "w") as f:
        f.write(_hash(new_pw))
    os.chmod(PASSWORD_FILE, 0o600)
    return jsonify({"ok": True})


# ── 页面路由（骨架） ─────────────────────────────────────

_NAV = """
<nav style="background:#1a1a2e;color:#fff;padding:10px 20px;display:flex;gap:20px;font-size:14px">
  <a href="/admin/" style="color:#e94560;text-decoration:none;font-weight:bold">🔍 AI审图 v7.0</a>
  <a href="/admin/drawings" style="color:#eee;text-decoration:none">📐 图纸管理</a>
  <a href="/admin/rules" style="color:#eee;text-decoration:none">📋 规则维护</a>
  <a href="/admin/agents" style="color:#eee;text-decoration:none">🤖 Agent</a>
  <a href="/admin/api-config" style="color:#eee;text-decoration:none">🔑 API</a>
  <a href="/admin/results" style="color:#eee;text-decoration:none">📊 审查结果</a>
  <a href="/admin/system" style="color:#eee;text-decoration:none">⚙️ 系统</a>
  <span style="margin-left:auto;color:#888">个人版</span>
</nav>
"""

_STYLE = """
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;background:#f5f6fa;color:#333}
.content{max-width:1200px;margin:0 auto;padding:24px}
h1{font-size:22px;margin-bottom:16px}
h2{font-size:18px;margin:24px 0 12px}
.card{background:#fff;border-radius:8px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card h3{font-size:15px;margin-bottom:8px}
.form-group{margin-bottom:12px}
label{display:block;font-size:13px;color:#555;margin-bottom:4px}
input,select,textarea{width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:4px;font-size:14px}
textarea{font-family:monospace;min-height:120px}
button,.btn{padding:8px 20px;border:none;border-radius:4px;font-size:14px;cursor:pointer}
.btn-primary{background:#16213e;color:#fff}
.btn-success{background:#27ae60;color:#fff}
.btn-danger{background:#c0392b;color:#fff}
.btn-warning{background:#e67e22;color:#fff}
.alert{padding:12px 16px;border-radius:4px;margin:12px 0}
.alert-success{background:#d4edda;color:#155724}
.alert-error{background:#f8d7da;color:#721c24}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 12px;border-bottom:1px solid #eee;text-align:left}
th{background:#f8f9fa;font-weight:600}
.loading{text-align:center;padding:40px;color:#888}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}
.stat-card{background:#fff;border-radius:8px;padding:20px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.stat-card .num{font-size:28px;font-weight:bold;color:#16213e}
.stat-card .label{font-size:12px;color:#888;margin-top:4px}
</style>
"""


def _render_page(title, body, extra_script=""):
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — AI审图 v7.0</title>
{_STYLE}
</head>
<body>
{_NAV}
<div class="content">
<h1>{title}</h1>
{body}
</div>
<script>
{extra_script}
</script>
</body>
</html>"""


# ── 登录页 ──────────────────────────────────────────────

@admin_bp.route("/login")
def login_page():
    return _render_page("登录", """
<div class="card" style="max-width:400px;margin:60px auto">
<h3>🔐 管理后台登录</h3>
<div class="form-group">
  <label>密码</label>
  <input type="password" id="pw" placeholder="输入管理密码" autofocus>
</div>
<button class="btn-primary" onclick="login()">登录</button>
<p id="msg" style="margin-top:12px;color:#c0392b"></p>
</div>
""", """
async function login(){
  const pw=document.getElementById('pw').value;
  const res=await fetch('/admin/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
  const data=await res.json();
  if(data.ok) location.href='/admin/';
  else document.getElementById('msg').innerHTML='⚠️ '+data.error;
}
""")

# ── 首页仪表盘 ──────────────────────────────────────────

@admin_bp.route("/")
def dashboard():
    if not is_authenticated():
        return redirect("/admin/login")
    return _render_page("仪表盘", """
<div class="stats-grid">
  <div class="stat-card"><div class="num" id="stat-projects">—</div><div class="label">项目数</div></div>
  <div class="stat-card"><div class="num" id="stat-drawings">—</div><div class="label">图纸数</div></div>
  <div class="stat-card"><div class="num" id="stat-checkpoints">—</div><div class="label">检查点</div></div>
  <div class="stat-card"><div class="num" id="stat-agents">—</div><div class="label">Agent</div></div>
  <div class="stat-card"><div class="num" id="stat-reviews">—</div><div class="label">审查次数</div></div>
  <div class="stat-card"><div class="num" id="stat-issues">—</div><div class="label">累计问题</div></div>
</div>
<div class="card"><h3>快速操作</h3>
  <a href="/admin/drawings" class="btn-primary" style="display:inline-block;margin:4px">📐 管理图纸</a>
  <a href="/admin/rules" class="btn-primary" style="display:inline-block;margin:4px">📋 维护规则</a>
  <a href="/admin/results" class="btn-primary" style="display:inline-block;margin:4px">📊 查看审查结果</a>
</div>
""", """
fetch('/api/health').then(r=>r.json()).then(d=>{
  document.getElementById('stat-projects').innerText=d.status||'✓';
});
fetch('/admin/api/stats').then(r=>r.json()).then(d=>{
  document.getElementById('stat-checkpoints').innerText=d.checkpoints||'—';
  document.getElementById('stat-agents').innerText=d.agents||'—';
  document.getElementById('stat-reviews').innerText=d.reviews||'—';
  document.getElementById('stat-issues').innerText=d.issues||'—';
  document.getElementById('stat-drawings').innerText=d.drawings||'—';
});
""")

# ── 管理 API ────────────────────────────────────────────

@admin_bp.route("/api/stats")
def admin_stats():
    from v7.db import get_db
    db = get_db()
    return jsonify({
        "checkpoints": db.execute("SELECT count(*) FROM checkpoints").fetchone()[0],
        "agents": db.execute("SELECT count(*) FROM agent_configs").fetchone()[0],
        "reviews": db.execute("SELECT count(*) FROM reviews").fetchone()[0],
        "issues": db.execute("SELECT count(*) FROM review_issues").fetchone()[0],
        "drawings": db.execute("SELECT count(*) FROM drawings").fetchone()[0],
        "projects": db.execute("SELECT count(*) FROM projects").fetchone()[0],
    })


# ════════════════════════════════════════════════════════
# 占位页面（任务 ③~⑧ 逐页实现时替换）
# ════════════════════════════════════════════════════════

PLACEHOLDER = """<div class="card"><p style="color:#888;text-align:center;padding:40px">🚧 此页面将在下一阶段实现</p></div>"""


@admin_bp.route("/drawings")
def drawings_page():
    return _render_page("📐 图纸管理", PLACEHOLDER)


@admin_bp.route("/rules")
def rules_page():
    return _render_page("📋 规则与专业维护", PLACEHOLDER)


@admin_bp.route("/agents")
def agents_page():
    return _render_page("🤖 Agent 配置", PLACEHOLDER)


@admin_bp.route("/api-config")
def api_config_page():
    return _render_page("🔑 API 配置", PLACEHOLDER)


@admin_bp.route("/results")
def results_page():
    return _render_page("📊 审查结果", PLACEHOLDER)


@admin_bp.route("/system")
def system_page():
    return _render_page("⚙️ 系统维护", PLACEHOLDER)
