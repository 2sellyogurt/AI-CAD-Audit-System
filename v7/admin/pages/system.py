# -*- coding: utf-8 -*-
"""系统维护页面模块 — render_page() + handle_api()

API 前缀: /admin/api/system
"""

import os
import sys
import platform
import shutil
import json
import time
import glob as _glob
from datetime import datetime

# ── 路径常量 ────────────────────────────────────────────

HERE = os.path.dirname(os.path.abspath(__file__))
ADMIN_DIR = os.path.dirname(HERE)
V7_ROOT = os.path.dirname(ADMIN_DIR)

DB_PATH = os.path.join(V7_ROOT, "v7_data.db")
OUTPUT_DIR = os.path.join(V7_ROOT, "output_v7.0")
CACHE_DIR = os.path.join(V7_ROOT, ".dxf_cache")

API_PREFIX = "/admin/api/system"

# ── 日志来源映射 ────────────────────────────────────────

_LOG_SOURCES = {
    "server": {
        "paths": [
            os.path.join(OUTPUT_DIR, "server.log"),
            os.path.join(OUTPUT_DIR, "server_output.log"),
            os.path.join(V7_ROOT, "server.log"),
        ],
        "label": "server.py 输出",
    },
    "admin": {
        "paths": [
            os.path.join(OUTPUT_DIR, "admin.log"),
            os.path.join(OUTPUT_DIR, "admin_output.log"),
            os.path.join(V7_ROOT, "admin.log"),
        ],
        "label": "admin 输出",
    },
    "review": {
        "paths": [
            os.path.join(OUTPUT_DIR, "review.log"),
            os.path.join(OUTPUT_DIR, "review_report.md"),
            os.path.join(OUTPUT_DIR, "unified_pipeline_report.json"),
        ],
        "label": "审查日志",
    },
    "audit": {
        "paths": [
            os.path.join(OUTPUT_DIR, "audit.log"),
            os.path.join(OUTPUT_DIR, "pipeline_report.json"),
        ],
        "label": "审计日志",
    },
}


# ════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════

def _get_dir_size(path: str) -> int:
    """递归计算目录大小（字节），目录不存在返回 0。"""
    if not os.path.isdir(path):
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def _get_dir_file_count(path: str) -> int:
    """递归计算目录下文件数，目录不存在返回 0。"""
    if not os.path.isdir(path):
        return 0
    count = 0
    for _dirpath, _dirnames, filenames in os.walk(path):
        count += len(filenames)
    return count


def _format_size(size_bytes: int) -> str:
    """格式化字节数为人类可读字符串。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _read_log(source: str, max_lines: int = 200) -> str:
    """读取日志内容，返回最近 N 行文本。"""
    source_info = _LOG_SOURCES.get(source)
    if not source_info:
        return ""

    log_path = None
    for p in source_info["paths"]:
        if os.path.isfile(p):
            log_path = p
            break

    if not log_path:
        return f"[{source_info['label']}] 暂无日志文件"

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        recent = lines[-max_lines:] if len(lines) > max_lines else lines
        return "".join(recent)
    except Exception as e:
        return f"读取日志失败: {e}"


# ════════════════════════════════════════════════════════
# API 处理
# ════════════════════════════════════════════════════════

def handle_api(path, method, body, qs):
    """处理 /admin/api/system/* 请求。

    Returns:
        None  — path 不匹配
        (status_code, data, content_type) — 匹配成功
    """
    if not path.startswith(API_PREFIX):
        return None

    # 规范化
    path = path.rstrip("/")
    method = method.upper()

    # ── GET /admin/api/system/status ──
    if path == API_PREFIX + "/status" and method == "GET":
        return _api_status()

    # ── GET /admin/api/system/caches ──
    if path == API_PREFIX + "/caches" and method == "GET":
        return _api_list_caches()

    # ── DELETE /admin/api/system/caches ──
    if path == API_PREFIX + "/caches" and method == "DELETE":
        return _api_clear_caches()

    # ── DELETE /admin/api/system/caches/expired ──
    if path == API_PREFIX + "/caches/expired" and method == "DELETE":
        return _api_clear_expired_caches()

    # ── DELETE /admin/api/system/caches/{filename} ──
    caches_prefix = API_PREFIX + "/caches/"
    if path.startswith(caches_prefix) and method == "DELETE":
        filename = path[len(caches_prefix):]
        return _api_delete_cache(filename)

    # ── GET /admin/api/system/logs ──
    if path == API_PREFIX + "/logs" and method == "GET":
        return _api_get_logs(qs)

    # ── POST /admin/api/system/reload-checkpoints ──
    if path == API_PREFIX + "/reload-checkpoints" and method == "POST":
        return _api_reload_checkpoints()

    # ── POST /admin/api/system/remigrate ──
    if path == API_PREFIX + "/remigrate" and method == "POST":
        return _api_remigrate()

    # ── POST /admin/api/system/backup-db ──
    if path == API_PREFIX + "/backup-db" and method == "POST":
        return _api_backup_db()

    # ── GET /admin/api/system/backups ──
    if path == API_PREFIX + "/backups" and method == "GET":
        return _api_list_backups()

    # ── POST /admin/api/system/restore-db ──
    if path == API_PREFIX + "/restore-db" and method == "POST":
        return _api_restore_db(body)

    # ── GET /admin/api/system/config-versions ──
    if path == API_PREFIX + "/config-versions" and method == "GET":
        return _api_config_versions()

    return None


def _json(status, data):
    return (status, data, "application/json; charset=utf-8")


def _api_status():
    """系统状态 API。"""
    db_size = os.path.getsize(DB_PATH) if os.path.isfile(DB_PATH) else 0
    output_size = _get_dir_size(OUTPUT_DIR)
    cache_size = _get_dir_size(CACHE_DIR)
    cache_files = _get_dir_file_count(CACHE_DIR)

    # 子进程数（当前进程及其子进程数 — 近似）
    import subprocess
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "(Get-WmiObject Win32_Process -Filter \"ParentProcessId=" + str(os.getpid()) + "\").Count"],
            capture_output=True, text=True, timeout=5
        )
        child_count = int(result.stdout.strip() or "0")
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"获取子进程数失败: {e}")
        child_count = 0

    from v7.db import get_db, SCHEMA_VERSION
    try:
        db = get_db()
        db_projects = db.execute("SELECT count(*) FROM projects").fetchone()[0]
        db_drawings = db.execute("SELECT count(*) FROM drawings").fetchone()[0]
        db_checkpoints = db.execute("SELECT count(*) FROM checkpoints").fetchone()[0]
        db_reviews = db.execute("SELECT count(*) FROM reviews").fetchone()[0]
        db_issues = db.execute("SELECT count(*) FROM review_issues").fetchone()[0]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"读取数据库统计失败: {e}")
        db_projects = 0
        db_drawings = 0
        db_checkpoints = 0
        db_reviews = 0
        db_issues = 0

    return _json(200, {
        "db": {
            "path": DB_PATH,
            "size": db_size,
            "size_formatted": _format_size(db_size),
            "schema_version": SCHEMA_VERSION,
            "projects": db_projects,
            "drawings": db_drawings,
            "checkpoints": db_checkpoints,
            "reviews": db_reviews,
            "issues": db_issues,
        },
        "directories": {
            "output_v7_0": {
                "path": OUTPUT_DIR,
                "size": output_size,
                "size_formatted": _format_size(output_size),
            },
            "dxf_cache": {
                "path": CACHE_DIR,
                "size": cache_size,
                "size_formatted": _format_size(cache_size),
                "file_count": cache_files,
            },
        },
        "system": {
            "python": sys.version,
            "platform": platform.platform(),
            "pid": os.getpid(),
            "child_processes": child_count,
        },
    })


def _api_list_caches():
    """缓存文件列表。"""
    if not os.path.isdir(CACHE_DIR):
        return _json(200, {"caches": [], "total": 0})

    items = []
    now = datetime.now()
    for fn in os.listdir(CACHE_DIR):
        fp = os.path.join(CACHE_DIR, fn)
        if os.path.isfile(fp):
            try:
                stat = os.stat(fp)
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime)
                days_old = (now - mtime).days
            except OSError:
                size = 0
                mtime = datetime.now()
                days_old = 0
            items.append({
                "filename": fn,
                "size": size,
                "size_formatted": _format_size(size),
                "modified": mtime.strftime("%Y-%m-%d %H:%M:%S"),
                "days_old": days_old,
                "expired": stat.st_mtime < time.time() - 30 * 86400,
            })

    items.sort(key=lambda x: x["modified"], reverse=True)
    return _json(200, {"caches": items, "total": len(items)})


def _api_clear_caches():
    """清空所有缓存文件。"""
    if not os.path.isdir(CACHE_DIR):
        return _json(200, {"ok": True, "deleted": 0})

    deleted = 0
    for fn in os.listdir(CACHE_DIR):
        fp = os.path.join(CACHE_DIR, fn)
        if os.path.isfile(fp):
            try:
                os.remove(fp)
                deleted += 1
            except OSError:
                pass

    return _json(200, {"ok": True, "deleted": deleted})


def _api_clear_expired_caches():
    """仅清空过期缓存文件（超过30天未修改）。"""
    if not os.path.isdir(CACHE_DIR):
        return _json(200, {"ok": True, "deleted": 0})

    threshold = time.time() - 30 * 86400
    deleted = 0
    for fn in os.listdir(CACHE_DIR):
        fp = os.path.join(CACHE_DIR, fn)
        if os.path.isfile(fp):
            try:
                if os.path.getmtime(fp) < threshold:
                    os.remove(fp)
                    deleted += 1
            except OSError:
                pass

    return _json(200, {"ok": True, "deleted": deleted})


def _api_delete_cache(filename):
    """删除单个缓存文件。"""
    # 安全检查：防止路径穿越
    safe_name = os.path.basename(filename)
    fp = os.path.join(CACHE_DIR, safe_name)
    if not os.path.isfile(fp):
        return _json(404, {"ok": False, "error": f"缓存文件不存在: {safe_name}"})
    try:
        os.remove(fp)
        return _json(200, {"ok": True, "filename": safe_name})
    except OSError as e:
        return _json(500, {"ok": False, "error": str(e)})


def _api_get_logs(qs):
    """获取日志内容。"""
    source = (qs.get("source") or ["server"])[0]
    try:
        lines = int((qs.get("lines") or ["200"])[0])
    except ValueError:
        lines = 200
    lines = max(1, min(lines, 2000))
    content = _read_log(source, lines)
    label = _LOG_SOURCES.get(source, {}).get("label", source)
    available = [{"key": k, "label": v["label"],
                  "has_file": any(os.path.isfile(p) for p in v["paths"])}
                 for k, v in _LOG_SOURCES.items()]
    return _json(200, {
        "source": source,
        "label": label,
        "lines": len(content.splitlines()) if content else 0,
        "content": content,
        "available_sources": available,
    })


def _api_reload_checkpoints():
    """从 YAML 重新加载检查点到数据库。"""
    try:
        from v7.db.migrate import migrate_checkpoints
        from v7.db import get_db
        db = get_db()
        count = migrate_checkpoints(db)
        return _json(200, {"ok": True, "count": count,
                           "message": f"已重新加载 {count} 条检查点"})
    except Exception as e:
        return _json(500, {"ok": False, "error": str(e)})


def _api_remigrate():
    """强制重新执行数据库迁移。"""
    try:
        from v7.db.migrate import auto_migrate
        result = auto_migrate(force=True)
        return _json(200, {"ok": True, "result": result,
                           "message": "数据库迁移完成"})
    except Exception as e:
        return _json(500, {"ok": False, "error": str(e)})


def _api_backup_db():
    """备份数据库文件（使用 SQLite 内置备份 API）。"""
    try:
        from v7.db.schema import backup_database
        backup_path = backup_database()
        backup_size = os.path.getsize(backup_path)
        return _json(200, {
            "ok": True,
            "backup_path": backup_path,
            "backup_name": os.path.basename(backup_path),
            "size": backup_size,
            "size_formatted": _format_size(backup_size),
        })
    except Exception as e:
        return _json(500, {"ok": False, "error": str(e)})


def _api_list_backups():
    """列出所有可用的数据库备份。"""
    try:
        from v7.db.schema import list_backups
        backups = list_backups()
        return _json(200, {"ok": True, "backups": backups, "total": len(backups)})
    except Exception as e:
        return _json(500, {"ok": False, "error": str(e)})


def _api_restore_db(request_body=None):
    """从备份恢复数据库。"""
    backup_path = (request_body or {}).get("backup_path", "")
    if not backup_path:
        return _json(400, {"ok": False, "error": "缺少 backup_path 参数"})
    try:
        from v7.db.schema import restore_database
        restore_database(backup_path)
        return _json(200, {"ok": True, "message": f"已从 {os.path.basename(backup_path)} 恢复数据库"})
    except FileNotFoundError as e:
        return _json(404, {"ok": False, "error": str(e)})
    except Exception as e:
        return _json(500, {"ok": False, "error": str(e)})


def _api_config_versions():
    """返回最近50条配置版本历史。"""
    from v7.db import get_db
    db = get_db()
    rows = db.execute(
        "SELECT * FROM config_versions ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    items = [dict(r) for r in rows]
    return _json(200, {"versions": items, "total": len(items)})


# ════════════════════════════════════════════════════════
# 页面渲染
# ════════════════════════════════════════════════════════

def render_page() -> str:
    """返回系统维护页面的完整 HTML 内容（不含外层框架/nav/html/head/body）。"""
    return _CSS + _HTML + _SCRIPT


# ── 内联 CSS ────────────────────────────────────────────

_CSS = """<style>
/* === 系统维护页面样式 === */
.sys-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
.sys-card-full{grid-column:1/-1}
.sys-card{background:#fff;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.06);overflow:hidden}
.sys-card-header{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:12px 18px;font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px}
.sys-card-header .icon{font-size:18px}
.sys-card-body{padding:16px 18px}
.sys-stat-row{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:4px}
.sys-stat-item{flex:1;min-width:140px;background:#f8f9fc;border-radius:8px;padding:12px 14px;border-left:3px solid #16213e}
.sys-stat-item .s-label{font-size:11px;color:#888;margin-bottom:2px;text-transform:uppercase;letter-spacing:.5px}
.sys-stat-item .s-value{font-size:16px;font-weight:700;color:#1a1a2e;word-break:break-all}
.sys-stat-item.warn{border-left-color:#e94560}
.sys-stat-item.ok{border-left-color:#27ae60}
.sys-stat-item.info{border-left-color:#2980b9}
.sys-btn{padding:7px 18px;border:none;border-radius:5px;font-size:13px;cursor:pointer;font-weight:500;transition:all .15s;display:inline-flex;align-items:center;gap:5px}
.sys-btn:hover{opacity:.88;transform:translateY(-1px)}
.sys-btn-primary{background:#16213e;color:#fff}
.sys-btn-danger{background:#e94560;color:#fff}
.sys-btn-warning{background:#e67e22;color:#fff}
.sys-btn-success{background:#27ae60;color:#fff}
.sys-btn-outline{background:transparent;color:#16213e;border:1px solid #16213e}
.sys-btn-sm{padding:4px 10px;font-size:11px}
.sys-table{width:100%;border-collapse:collapse;font-size:12px}
.sys-table th{background:#f0f2f5;color:#555;font-weight:600;padding:8px 10px;text-align:left;border-bottom:2px solid #ddd;white-space:nowrap}
.sys-table td{padding:7px 10px;border-bottom:1px solid #eee;vertical-align:middle}
.sys-table tr:hover{background:#f8f9fc}
.sys-table .expired td{background:#fff8e1}
.sys-table .expired:hover td{background:#fff3c4}
.sys-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}
.sys-badge-warn{background:#fff3cd;color:#856404}
.sys-badge-ok{background:#d4edda;color:#155724}
.sys-badge-danger{background:#f8d7da;color:#721c24}
.sys-log-viewer{background:#0d1117;color:#c9d1d9;font-family:'Cascadia Code',Consolas,'Courier New',monospace;font-size:12px;line-height:1.55;padding:14px;border-radius:6px;max-height:420px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}
.sys-log-viewer::-webkit-scrollbar{width:6px}
.sys-log-viewer::-webkit-scrollbar-track{background:#161b22}
.sys-log-viewer::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px}
.sys-toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.sys-select,.sys-input{padding:6px 10px;border:1px solid #ddd;border-radius:5px;font-size:13px;background:#fff}
.sys-select:focus,.sys-input:focus{outline:none;border-color:#16213e;box-shadow:0 0 0 2px rgba(22,33,62,.1)}
.sys-input{min-width:180px}
.sys-toast{position:fixed;top:20px;right:20px;z-index:9999;padding:12px 20px;border-radius:6px;font-size:13px;color:#fff;box-shadow:0 4px 12px rgba(0,0,0,.2);animation:sysSlideIn .25s ease;max-width:380px}
.sys-toast-success{background:#27ae60}
.sys-toast-error{background:#e94560}
.sys-toast-info{background:#16213e}
@keyframes sysSlideIn{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}
.sys-confirm-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998;align-items:center;justify-content:center}
.sys-confirm-overlay.show{display:flex}
.sys-confirm-box{background:#fff;border-radius:10px;padding:24px;max-width:420px;width:90%;box-shadow:0 8px 30px rgba(0,0,0,.2);text-align:center}
.sys-confirm-box h3{font-size:17px;margin-bottom:8px;color:#1a1a2e}
.sys-confirm-box p{font-size:13px;color:#666;margin-bottom:20px}
.sys-confirm-box .actions{display:flex;gap:10px;justify-content:center}
.sys-flex-row{display:flex;align-items:center;gap:8px}
.sys-toggle{position:relative;width:40px;height:22px;display:inline-block}
.sys-toggle input{opacity:0;width:0;height:0}
.sys-toggle .slider{position:absolute;cursor:pointer;inset:0;background:#ccc;border-radius:22px;transition:.2s}
.sys-toggle .slider:before{content:'';position:absolute;height:16px;width:16px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.2s}
.sys-toggle input:checked+.slider{background:#16213e}
.sys-toggle input:checked+.slider:before{transform:translateX(18px)}
.sys-version{display:inline-block;background:linear-gradient(135deg,#1a1a2e,#16213e);color:#e94560;padding:6px 14px;border-radius:6px;font-size:14px;font-weight:700;letter-spacing:.5px}
@media(max-width:900px){.sys-grid{grid-template-columns:1fr}}
</style>"""

# ── HTML 结构 ────────────────────────────────────────────

_HTML = """
<!-- 确认对话框 -->
<div id="sys-confirm" class="sys-confirm-overlay">
  <div class="sys-confirm-box">
    <h3 id="sys-confirm-title">确认操作</h3>
    <p id="sys-confirm-msg">确定要执行此操作吗？</p>
    <div class="actions">
      <button class="sys-btn sys-btn-outline" onclick="sysCloseConfirm()">取消</button>
      <button class="sys-btn sys-btn-danger" id="sys-confirm-btn" onclick="sysExecConfirm()">确认</button>
    </div>
  </div>
</div>

<!-- Toast -->
<div id="sys-toast-container"></div>

<div class="sys-grid">

  <!-- ═══ 卡片1: 系统状态仪表盘 ═══ -->
  <div class="sys-card sys-card-full">
    <div class="sys-card-header"><span class="icon">📊</span> 系统状态仪表盘</div>
    <div class="sys-card-body">
      <div class="sys-stat-row" id="sys-stats">
        <div class="sys-stat-item"><div class="s-label">数据库路径</div><div class="s-value" id="st-db-path">—</div></div>
        <div class="sys-stat-item"><div class="s-label">数据库大小</div><div class="s-value" id="st-db-size">—</div></div>
        <div class="sys-stat-item"><div class="s-label">output_v7.0 大小</div><div class="s-value" id="st-out-size">—</div></div>
        <div class="sys-stat-item"><div class="s-label">缓存大小 / 文件数</div><div class="s-value" id="st-cache-info">—</div></div>
        <div class="sys-stat-item"><div class="s-label">Python 版本</div><div class="s-value" id="st-py-ver">—</div></div>
        <div class="sys-stat-item"><div class="s-label">平台信息</div><div class="s-value" id="st-platform">—</div></div>
        <div class="sys-stat-item"><div class="s-label">子进程数</div><div class="s-value" id="st-child-proc">—</div></div>
        <div class="sys-stat-item info"><div class="s-label">DB Schema 版本</div><div class="s-value" id="st-schema-ver">—</div></div>
      </div>
      <button class="sys-btn sys-btn-primary" onclick="sysRefreshStatus()" style="margin-top:10px">🔄 刷新状态</button>
    </div>
  </div>

  <!-- ═══ 卡片2: 缓存管理 ═══ -->
  <div class="sys-card">
    <div class="sys-card-header"><span class="icon">🗂️</span> 缓存管理</div>
    <div class="sys-card-body">
      <div style="margin-bottom:10px;display:flex;gap:10px;flex-wrap:wrap">
        <button class="sys-btn sys-btn-primary" onclick="sysRefreshCaches()">🔄 刷新</button>
        <button class="sys-btn sys-btn-warning" onclick="sysClearExpiredCaches()">⏳ 清理过期缓存</button>
        <button class="sys-btn sys-btn-danger" onclick="sysClearAllCaches()">🗑️ 清空所有缓存</button>
      </div>
      <div style="max-height:360px;overflow-y:auto">
        <table class="sys-table">
          <thead><tr><th>文件名</th><th>大小</th><th>修改时间</th><th>状态</th><th>操作</th></tr></thead>
          <tbody id="sys-cache-tbody"><tr><td colspan="5" style="text-align:center;color:#888;padding:20px">加载中...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ═══ 卡片3: 日志查看器 ═══ -->
  <div class="sys-card">
    <div class="sys-card-header"><span class="icon">📜</span> 日志查看器</div>
    <div class="sys-card-body">
      <div class="sys-toolbar">
        <select class="sys-select" id="sys-log-source" onchange="sysRefreshLog()">
          <option value="server">server.py 输出</option>
          <option value="admin">admin 输出</option>
          <option value="review">审查日志</option>
          <option value="audit">审计日志</option>
        </select>
        <input class="sys-input" id="sys-log-filter" placeholder="搜索过滤..." oninput="sysApplyLogFilter()">
        <button class="sys-btn sys-btn-primary" onclick="sysRefreshLog()">🔄 刷新</button>
        <label class="sys-flex-row" style="cursor:pointer;font-size:12px;user-select:none">
          <span>自动刷新</span>
          <label class="sys-toggle"><input type="checkbox" id="sys-auto-refresh" onchange="sysToggleAutoRefresh(this.checked)"><span class="slider"></span></label>
        </label>
        <span style="font-size:11px;color:#888" id="sys-log-info">—</span>
      </div>
      <div class="sys-log-viewer" id="sys-log-viewer">点击刷新加载日志...</div>
    </div>
  </div>

  <!-- ═══ 卡片4: 系统操作 ═══ -->
  <div class="sys-card sys-card-full">
    <div class="sys-card-header"><span class="icon">🔧</span> 系统操作</div>
    <div class="sys-card-body">
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:18px">
        <button class="sys-btn sys-btn-success" onclick="sysReloadCheckpoints()">📥 重新加载检查点</button>
        <button class="sys-btn sys-btn-danger" onclick="sysRemigrate()">🔄 重新迁移数据库</button>
        <button class="sys-btn sys-btn-warning" onclick="sysBackupDb()">💾 数据库备份</button>
      </div>
      <div style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:#f8f9fc;border-radius:8px">
        <span class="sys-version" id="sys-version-display">AI审图 v7.0</span>
        <span style="font-size:12px;color:#888">DB Schema v<span id="sys-schema-ver-display">—</span></span>
      </div>
      <div id="sys-op-result" style="margin-top:12px"></div>
      <!-- 配置版本历史 -->
      <div style="margin-top:20px;border-top:1px solid #eee;padding-top:16px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
          <span style="font-size:14px;font-weight:600;color:#1a1a2e">配置版本历史</span>
          <button class="sys-btn sys-btn-sm sys-btn-primary" onclick="sysRefreshVersions()">刷新</button>
        </div>
        <div style="max-height:360px;overflow-y:auto">
          <table class="sys-table">
            <thead><tr><th>时间</th><th>类型</th><th>目标ID</th><th>操作摘要</th></tr></thead>
            <tbody id="sys-version-tbody"><tr><td colspan="4" style="text-align:center;color:#888;padding:20px">加载中...</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

</div>
"""

# ── JavaScript ───────────────────────────────────────────

_SCRIPT = """<script>
// === 系统维护页面逻辑 ===

const API_BASE = '/admin/api/system';
let _sysLogFull = '';
let _sysAutoRefreshTimer = null;
let _sysConfirmCallback = null;

// ── Toast ──
function sysToast(msg, type) {
  const c = document.getElementById('sys-toast-container');
  const el = document.createElement('div');
  el.className = 'sys-toast sys-toast-' + (type || 'info');
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(function(){ el.style.opacity='0'; el.style.transition='opacity .3s'; setTimeout(function(){ el.remove(); }, 300); }, 3000);
}

// ── 确认对话框 ──
function sysConfirm(title, msg, cb) {
  document.getElementById('sys-confirm-title').textContent = title;
  document.getElementById('sys-confirm-msg').textContent = msg;
  _sysConfirmCallback = cb;
  document.getElementById('sys-confirm').classList.add('show');
}
function sysCloseConfirm() {
  document.getElementById('sys-confirm').classList.remove('show');
  _sysConfirmCallback = null;
}
function sysExecConfirm() {
  document.getElementById('sys-confirm').classList.remove('show');
  if (_sysConfirmCallback) { var cb = _sysConfirmCallback; _sysConfirmCallback = null; cb(); }
}

// ── API 请求 ──
function sysApi(method, path, body) {
  var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) { opts.body = JSON.stringify(body); }
  return fetch(API_BASE + path, opts).then(function(r){ return r.json(); });
}

// ── 刷新系统状态 ──
function sysRefreshStatus() {
  sysApi('GET', '/status').then(function(d) {
    document.getElementById('st-db-path').textContent = d.db.path || '—';
    document.getElementById('st-db-size').textContent = d.db.size_formatted || '—';
    document.getElementById('st-out-size').textContent = d.directories.output_v7_0.size_formatted || '—';
    document.getElementById('st-cache-info').textContent = (d.directories.dxf_cache.size_formatted || '0 B') + ' / ' + (d.directories.dxf_cache.file_count || 0) + ' 个文件';
    document.getElementById('st-py-ver').textContent = (d.system.python || '').split('\\n')[0] || '—';
    document.getElementById('st-platform').textContent = d.system.platform || '—';
    document.getElementById('st-child-proc').textContent = d.system.child_processes || 0;
    document.getElementById('st-schema-ver').textContent = 'v' + (d.db.schema_version || '—');
    document.getElementById('sys-schema-ver-display').textContent = d.db.schema_version || '—';
  }).catch(function(e){ sysToast('获取系统状态失败: ' + e.message, 'error'); });
}

// ── 缓存管理 ──
function sysRefreshCaches() {
  sysApi('GET', '/caches').then(function(d) {
    var tbody = document.getElementById('sys-cache-tbody');
    if (!d.caches || d.caches.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#888;padding:20px">暂无缓存文件</td></tr>';
      return;
    }
    var html = '';
    for (var i = 0; i < d.caches.length; i++) {
      var c = d.caches[i];
      var rowClass = c.expired ? ' class="expired"' : '';
      var badge = c.expired ? '<span class="sys-badge sys-badge-warn">超30天</span>' : '<span class="sys-badge sys-badge-ok">正常</span>';
      html += '<tr' + rowClass + '>';
      html += '<td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + sysEscape(c.filename) + '">' + sysEscape(c.filename) + '</td>';
      html += '<td>' + c.size_formatted + '</td>';
      html += '<td>' + c.modified + '</td>';
      html += '<td>' + badge + '</td>';
      html += '<td><button class="sys-btn sys-btn-danger sys-btn-sm" onclick="sysDeleteCache(\\'' + sysEscapeQ(c.filename) + '\\')">删除</button></td>';
      html += '</tr>';
    }
    tbody.innerHTML = html;
  }).catch(function(e){ sysToast('获取缓存列表失败: ' + e.message, 'error'); });
}

function sysEscape(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function sysEscapeQ(s) { return (s || '').replace(/\\\\/g,'\\\\\\\\').replace(/'/g,"\\\\'"); }

function sysDeleteCache(fn) {
  sysApi('DELETE', '/caches/' + encodeURIComponent(fn)).then(function(d) {
    if (d.ok) { sysToast('已删除: ' + fn, 'success'); sysRefreshCaches(); }
    else { sysToast('删除失败: ' + (d.error || '未知错误'), 'error'); }
  }).catch(function(e){ sysToast('删除失败: ' + e.message, 'error'); });
}

function sysClearAllCaches() {
  sysConfirm('清空所有缓存', '确定要删除 .dxf_cache 目录下的所有缓存文件吗？此操作不可撤销。', function() {
    sysApi('DELETE', '/caches').then(function(d) {
      if (d.ok) { sysToast('已清空 ' + d.deleted + ' 个缓存文件', 'success'); sysRefreshCaches(); }
      else { sysToast('清空失败: ' + (d.error || '未知错误'), 'error'); }
    }).catch(function(e){ sysToast('清空失败: ' + e.message, 'error'); });
  });
}

function sysClearExpiredCaches() {
  sysConfirm('清理过期缓存', '确定要清理所有超过30天未修改的过期缓存文件吗？', function() {
    sysApi('DELETE', '/caches/expired').then(function(d) {
      if (d.ok) { sysToast('已清理 ' + d.deleted + ' 个过期缓存文件', 'success'); sysRefreshCaches(); }
      else { sysToast('清理失败: ' + (d.error || '未知错误'), 'error'); }
    }).catch(function(e){ sysToast('清理失败: ' + e.message, 'error'); });
  });
}

// ── 日志查看器 ──
function sysRefreshLog() {
  var src = document.getElementById('sys-log-source').value;
  sysApi('GET', '/logs?source=' + src + '&lines=200').then(function(d) {
    _sysLogFull = d.content || '';
    document.getElementById('sys-log-viewer').textContent = _sysLogFull || '(暂无日志)';
    document.getElementById('sys-log-info').textContent = (d.lines || 0) + ' 行 — ' + (d.label || src);
    sysApplyLogFilter();
  }).catch(function(e){ sysToast('获取日志失败: ' + e.message, 'error'); });
}

function sysApplyLogFilter() {
  var kw = document.getElementById('sys-log-filter').value;
  if (!kw) { document.getElementById('sys-log-viewer').textContent = _sysLogFull || '(暂无日志)'; return; }
  var lines = _sysLogFull.split('\\n');
  var filtered = [];
  var kwLower = kw.toLowerCase();
  for (var i = 0; i < lines.length; i++) {
    if (lines[i].toLowerCase().indexOf(kwLower) !== -1) { filtered.push(lines[i]); }
  }
  document.getElementById('sys-log-viewer').textContent = filtered.length > 0 ? filtered.join('\\n') : '(无匹配行)';
}

function sysToggleAutoRefresh(on) {
  if (_sysAutoRefreshTimer) { clearInterval(_sysAutoRefreshTimer); _sysAutoRefreshTimer = null; }
  if (on) { _sysAutoRefreshTimer = setInterval(sysRefreshLog, 10000); sysToast('已开启自动刷新 (10秒)', 'info'); }
  else { sysToast('已关闭自动刷新', 'info'); }
}

// ── 系统操作 ──
function sysRefreshVersions() {
  sysApi('GET', '/config-versions').then(function(d) {
    var tbody = document.getElementById('sys-version-tbody');
    if (!d.versions || d.versions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#888;padding:20px">暂无版本记录</td></tr>';
      return;
    }
    var typeLabels = {'checkpoint': '检查点', 'agent': 'Agent', 'api_key': 'API密钥'};
    var html = '';
    for (var i = 0; i < d.versions.length; i++) {
      var v = d.versions[i];
      var typeLabel = typeLabels[v.target_type] || v.target_type;
      var oldShort = (v.old_value || '').substring(0, 40);
      var newShort = (v.new_value || '').substring(0, 40);
      var actionIcon = '&#9998;';
      if (!v.old_value && v.new_value) { actionIcon = '&#10133;'; }
      else if (v.old_value && !v.new_value) { actionIcon = '&#128465;'; }
      html += '<tr>';
      html += '<td style="white-space:nowrap;font-size:11px">' + (v.created_at || '') + '</td>';
      html += '<td>' + typeLabel + '</td>';
      html += '<td><code>' + sysEscape(v.target_id || '') + '</code></td>';
      html += '<td title="旧: ' + sysEscape(oldShort) + '&#10;新: ' + sysEscape(newShort) + '" style="cursor:pointer;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + actionIcon + ' ' + sysEscape(v.field_name || (v.old_value && v.new_value ? '更新' : v.old_value ? '删除' : '新建')) + '</td>';
      html += '</tr>';
    }
    tbody.innerHTML = html;
  }).catch(function(e){ sysToast('获取版本历史失败: ' + e.message, 'error'); });
}

function sysReloadCheckpoints() {
  sysApi('POST', '/reload-checkpoints').then(function(d) {
    if (d.ok) { sysToast(d.message || '检查点已重新加载', 'success'); sysRefreshStatus(); }
    else { sysToast('加载失败: ' + (d.error || '未知错误'), 'error'); }
  }).catch(function(e){ sysToast('请求失败: ' + e.message, 'error'); });
}

function sysRemigrate() {
  sysConfirm('强制重新迁移数据库', '此操作将强制重新导入所有 YAML 配置、Agent 定义、API 密钥和系统设置到数据库中。已有数据可能被覆盖。确定继续？', function() {
    sysApi('POST', '/remigrate').then(function(d) {
      if (d.ok) { sysToast(d.message || '数据库迁移完成', 'success'); sysRefreshStatus(); }
      else { sysToast('迁移失败: ' + (d.error || '未知错误'), 'error'); }
    }).catch(function(e){ sysToast('请求失败: ' + e.message, 'error'); });
  });
}

function sysBackupDb() {
  sysApi('POST', '/backup-db').then(function(d) {
    if (d.ok) { sysToast('备份成功: ' + d.backup_name + ' (' + d.size_formatted + ')', 'success'); }
    else { sysToast('备份失败: ' + (d.error || '未知错误'), 'error'); }
  }).catch(function(e){ sysToast('请求失败: ' + e.message, 'error'); });
}

// ── 页面初始化 ──
(function() {
  sysRefreshStatus();
  sysRefreshCaches();
  sysRefreshLog();
  sysRefreshVersions();
})();
</script>"""
