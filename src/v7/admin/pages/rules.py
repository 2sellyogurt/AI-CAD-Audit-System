# -*- coding: utf-8 -*-
"""规则与专业维护页面模块

导出:
  render_page() -> str       返回完整 HTML 内容（不含外层框架）
  handle_api(path, method, body, qs) -> (status, data, content_type) | None
      path:  请求路径 str（如 /admin/api/rules/list）
      method: HTTP 方法 str（GET/POST/PUT/DELETE）
      body:   已解析的 JSON body dict（无 body 时为 {}）
      qs:     parse_qs 解析后的查询参数字典
      返回 (status_code, data, content_type) 或 None（不匹配时）
"""

import json
import re
import yaml
import glob
import os
import logging

logger = logging.getLogger("v7.admin.pages.rules")

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ════════════════════════════════════════════════════════
# 从统一常量模块加载（避免多处硬编码不一致）
# ════════════════════════════════════════════════════════

from v7.constants import (
    DISCIPLINE_LABELS,
    DISCIPLINE_LIST,
    SEVERITY_META,
    ROUTE_LABELS,
)

SEVERITY_LABELS = {k: v["label"] for k, v in SEVERITY_META.items()}


# ════════════════════════════════════════════════════════
# API 处理
# ════════════════════════════════════════════════════════

def handle_api(path, method, body, qs):
    """处理 /admin/api/rules/* 请求，返回 (status, data, content_type) 或 None。"""
    prefix = "/admin/api/rules"
    if not path.startswith(prefix):
        return None

    sub = path[len(prefix):]

    # GET /admin/api/rules/list?discipline=building
    if method == "GET" and sub == "/list":
        return _api_list(body, qs)

    # POST /admin/api/rules/reload
    if method == "POST" and sub == "/reload":
        return _api_reload(body, qs)

    # POST /admin/api/rules/toggle
    if method == "POST" and sub == "/toggle":
        return _api_toggle(body, qs)

    # POST /admin/api/rules → 新建
    if method == "POST" and sub == "":
        return _api_create(body, qs)

    # GET /admin/api/rules/{id} → 单个详情
    m = re.match(r"^/([^/]+)$", sub)
    if m:
        rule_id = m.group(1)
        if method == "GET":
            return _api_detail(rule_id, body, qs)
        if method == "PUT":
            return _api_update(rule_id, body, qs)
        if method == "DELETE":
            return _api_delete(rule_id, body, qs)

    return None


def _row_to_dict(row):
    """将 sqlite3.Row 转为普通 dict。"""
    if row is None:
        return None
    d = dict(row)
    try:
        d["config_json"] = json.loads(d.get("config_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        d["config_json"] = {}
    d["enabled"] = bool(d.get("enabled", 1))
    return d


def _api_list(body, qs):
    from v7.db import get_db
    db = get_db()
    disc = qs.get("discipline", [None])[0]
    search = qs.get("search", [None])[0]

    if disc and disc != "all":
        rows = db.execute(
            "SELECT * FROM checkpoints WHERE discipline=? ORDER BY priority DESC, id",
            (disc,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM checkpoints ORDER BY discipline, priority DESC, id"
        ).fetchall()

    items = [_row_to_dict(r) for r in rows]

    if search:
        s = search.lower()
        items = [i for i in items
                 if s in (i.get("id") or "").lower()
                 or s in (i.get("name") or "").lower()]

    return 200, {"items": items, "total": len(items)}, "application/json"


def _api_detail(rule_id, body, qs):
    from v7.db import get_db
    db = get_db()
    row = db.execute("SELECT * FROM checkpoints WHERE id=?", (rule_id,)).fetchone()
    if not row:
        return 404, {"error": "检查点不存在"}, "application/json"
    return 200, _row_to_dict(row), "application/json"


def _api_create(body, qs):
    from v7.db import get_db
    db = get_db()
    cid = body.get("id", "").strip()
    if not cid:
        return 400, {"error": "检查点ID不能为空"}, "application/json"
    existing = db.execute("SELECT id FROM checkpoints WHERE id=?", (cid,)).fetchone()
    if existing:
        return 409, {"error": f"检查点 {cid} 已存在"}, "application/json"

    config = body.get("config_json", {})
    config_json_str = json.dumps(config, ensure_ascii=False) if isinstance(config, dict) else "{}"

    # ── 记录版本：新建检查点 ──
    new_val = json.dumps(body, ensure_ascii=False, default=str)
    db.execute(
        "INSERT INTO config_versions (target_type, target_id, old_value, new_value) VALUES (?, ?, ?, ?)",
        ("checkpoint", cid, "", new_val),
    )

    db.execute(
        """INSERT INTO checkpoints
           (id, name, discipline, check_type, route, severity, priority,
            standard_code, standard_clause, description, enabled, config_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            cid,
            body.get("name", ""),
            body.get("discipline", "building"),
            body.get("check_type", "free_review"),
            body.get("route", "text"),
            body.get("severity", "B"),
            int(body.get("priority", 0)),
            body.get("standard_code", ""),
            body.get("standard_clause", ""),
            body.get("description", ""),
            1 if body.get("enabled", True) else 0,
            config_json_str,
        ),
    )
    db.commit()
    return 201, {"ok": True, "id": cid}, "application/json"


def _api_update(rule_id, body, qs):
    from v7.db import get_db
    db = get_db()
    row = db.execute("SELECT * FROM checkpoints WHERE id=?", (rule_id,)).fetchone()
    if not row:
        return 404, {"error": "检查点不存在"}, "application/json"

    # ── 记录版本：更新前读取旧值 ──
    old_val = json.dumps(dict(row), ensure_ascii=False, default=str)
    new_val = json.dumps(body, ensure_ascii=False, default=str)
    db.execute(
        "INSERT INTO config_versions (target_type, target_id, old_value, new_value) VALUES (?, ?, ?, ?)",
        ("checkpoint", rule_id, old_val, new_val),
    )

    config = body.get("config_json", {})
    config_json_str = json.dumps(config, ensure_ascii=False) if isinstance(config, dict) else row["config_json"]

    db.execute(
        """UPDATE checkpoints SET
           name=?, discipline=?, check_type=?, route=?, severity=?, priority=?,
           standard_code=?, standard_clause=?, description=?, enabled=?, config_json=?,
           updated_at=datetime('now','localtime')
           WHERE id=?""",
        (
            body.get("name", row["name"]),
            body.get("discipline", row["discipline"]),
            body.get("check_type", row["check_type"]),
            body.get("route", row["route"]),
            body.get("severity", row["severity"]),
            int(body.get("priority", row["priority"])),
            body.get("standard_code", row["standard_code"] or ""),
            body.get("standard_clause", row["standard_clause"] or ""),
            body.get("description", row["description"] or ""),
            1 if body.get("enabled", True) else 0,
            config_json_str,
            rule_id,
        ),
    )
    db.commit()
    return 200, {"ok": True, "id": rule_id}, "application/json"


def _api_delete(rule_id, body, qs):
    from v7.db import get_db
    db = get_db()
    row = db.execute("SELECT * FROM checkpoints WHERE id=?", (rule_id,)).fetchone()
    if not row:
        return 404, {"error": "检查点不存在"}, "application/json"

    # ── 记录版本：删除前保存旧值 ──
    old_val = json.dumps(dict(row), ensure_ascii=False, default=str)
    db.execute(
        "INSERT INTO config_versions (target_type, target_id, old_value, new_value) VALUES (?, ?, ?, ?)",
        ("checkpoint", rule_id, old_val, ""),
    )

    db.execute("DELETE FROM checkpoints WHERE id=?", (rule_id,))
    db.commit()
    return 200, {"ok": True}, "application/json"


def _api_toggle(body, qs):
    from v7.db import get_db
    db = get_db()
    ids = body.get("ids", [])
    enabled = body.get("enabled", True)
    if not ids or not isinstance(ids, list):
        return 400, {"error": "请提供检查点ID列表"}, "application/json"

    val = 1 if enabled else 0
    for cid in ids:
        db.execute(
            "UPDATE checkpoints SET enabled=?, updated_at=datetime('now','localtime') WHERE id=?",
            (val, cid),
        )
    db.commit()
    return 200, {"ok": True, "count": len(ids)}, "application/json"


def _api_reload(body, qs):
    from v7.db import get_db
    from v7.db.migrate import migrate_checkpoints
    db = get_db()
    count = migrate_checkpoints(db)
    return 200, {"ok": True, "count": count}, "application/json"


# ════════════════════════════════════════════════════════
# HTML 页面
# ════════════════════════════════════════════════════════

_STYLE = r"""
<style>
*{box-sizing:border-box;margin:0;padding:0}
.rules-wrap{font:14px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;background:#f5f6fa;min-height:calc(100vh - 50px)}
.rules-topbar{display:flex;align-items:center;gap:16px;padding:16px 24px;background:#1a1a2e;color:#fff;position:sticky;top:0;z-index:100}
.rules-topbar .title{font-size:18px;font-weight:bold;color:#e94560;white-space:nowrap}
.rules-topbar .search-box{flex:1;max-width:420px;position:relative}
.rules-topbar .search-box input{width:100%;padding:8px 12px 8px 36px;border:1px solid #333;border-radius:6px;background:#16213e;color:#fff;font-size:13px;outline:none}
.rules-topbar .search-box input::placeholder{color:#888}
.rules-topbar .search-box .s-icon{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:#888;font-size:14px}
.rules-topbar .btn{padding:8px 16px;border:none;border-radius:6px;font-size:13px;cursor:pointer;white-space:nowrap;font-weight:500}
.rules-topbar .btn-reload{background:transparent;border:1px solid #e94560;color:#e94560}
.rules-topbar .btn-reload:hover{background:#e94560;color:#fff}
.rules-body{display:flex;height:calc(100vh - 110px)}
.rules-sidebar{width:200px;background:#16213e;color:#fff;overflow-y:auto;flex-shrink:0;padding:8px 0}
.rules-sidebar .s-header{padding:12px 16px;font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px}
.rules-sidebar .s-item{display:block;padding:10px 16px;font-size:13px;color:#ccc;cursor:pointer;text-decoration:none;border-left:3px solid transparent;transition:all .15s}
.rules-sidebar .s-item:hover{background:rgba(233,69,96,.1);color:#fff}
.rules-sidebar .s-item.active{background:rgba(233,69,96,.15);color:#e94560;border-left-color:#e94560;font-weight:600}
.rules-sidebar .s-item .badge{float:right;background:rgba(255,255,255,.1);padding:0 6px;border-radius:10px;font-size:11px;color:#aaa}
.rules-main{flex:1;overflow-y:auto;padding:20px 24px}
.rules-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap;min-width:0}
.rules-toolbar .btn{padding:6px 14px;border:none;border-radius:5px;font-size:12px;cursor:pointer;font-weight:500}
.rules-toolbar .btn-primary{background:#16213e;color:#fff}
.rules-toolbar .btn-primary:hover{background:#1a1a2e}
.rules-toolbar .btn-success{background:#27ae60;color:#fff}
.rules-toolbar .btn-success:hover{background:#219a52}
.rules-toolbar .btn-danger{background:#c0392b;color:#fff}
.rules-toolbar .btn-danger:hover{background:#a93226}
.rules-toolbar .btn-warning{background:#e67e22;color:#fff}
.rules-toolbar .select-all{cursor:pointer;font-size:13px;color:#555;display:flex;align-items:center;gap:4px}
table.rules-table{width:100%;border-collapse:collapse;font-size:13px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)}
table.rules-table th{background:#16213e;color:#fff;padding:10px 12px;text-align:left;font-weight:500;font-size:12px}
table.rules-table th.center{text-align:center}
table.rules-table td{padding:10px 12px;border-bottom:1px solid #eee;color:#1a1a2e}
table.rules-table tr:hover{background:#f8f9ff}
table.rules-table tr.selected{background:#eaf0ff}
table.rules-table td.center{text-align:center}
.sev-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;min-width:28px;text-align:center}
.sev-A{background:#e94560;color:#fff}
.sev-B{background:#e67e22;color:#fff}
.sev-C{background:#3498db;color:#fff}
.sev-D{background:#95a5a6;color:#fff}
.route-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;background:#ecf0f1;color:#555}
.toggle-sw{position:relative;display:inline-block;width:40px;height:22px}
.toggle-sw input{display:none}
.toggle-sw .slider{position:absolute;top:0;left:0;right:0;bottom:0;background:#ccc;border-radius:22px;cursor:pointer;transition:.2s}
.toggle-sw .slider:before{position:absolute;content:'';height:16px;width:16px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.2s}
.toggle-sw input:checked+.slider{background:#27ae60}
.toggle-sw input:checked+.slider:before{transform:translateX(18px)}
.action-btn{padding:4px 10px;border:none;border-radius:4px;font-size:11px;cursor:pointer;margin:0 2px}
.action-btn.edit{background:#e8f0fe;color:#1a73e8}
.action-btn.edit:hover{background:#d2e3fc}
.action-btn.del{background:#fce8e6;color:#c0392b}
.action-btn.del:hover{background:#f5c6cb}
.empty-state{text-align:center;padding:60px 20px;color:#aaa}
.empty-state .icon{font-size:48px;margin-bottom:12px}
/* Modal */
.modal-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.45);z-index:200;align-items:center;justify-content:center}
.modal-overlay.show{display:flex}
.modal-box{background:#fff;border-radius:12px;width:680px;max-width:95vw;max-height:85vh;overflow-y:auto;box-shadow:0 8px 30px rgba(0,0,0,.2)}
.modal-box.wide{width:800px}
.modal-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid #eee;position:sticky;top:0;background:#fff;z-index:1;border-radius:12px 12px 0 0}
.modal-header h3{font-size:16px;color:#16213e}
.modal-header .close-btn{background:none;border:none;font-size:20px;color:#888;cursor:pointer;padding:4px 8px}
.modal-header .close-btn:hover{color:#333}
.modal-body{padding:20px}
.modal-footer{padding:12px 20px;border-top:1px solid #eee;display:flex;gap:10px;justify-content:flex-end}
.modal-footer .btn{padding:8px 20px;border:none;border-radius:6px;font-size:13px;cursor:pointer}
.modal-footer .btn-cancel{background:#eee;color:#555}
.modal-footer .btn-save{background:#e94560;color:#fff}
.modal-footer .btn-save:hover{background:#d63852}
.form-row{display:flex;gap:16px;margin-bottom:14px}
.form-row .form-group{flex:1;margin-bottom:0}
.form-group{margin-bottom:14px}
.form-group label{display:block;font-size:12px;color:#666;margin-bottom:4px;font-weight:500}
.form-group input,.form-group select,.form-group textarea{width:100%;padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:13px;outline:none;font-family:inherit}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:#e94560}
.form-group textarea{font-family:Consolas,monospace;min-height:80px;resize:vertical}
.toast{position:fixed;top:20px;right:20px;padding:12px 20px;border-radius:8px;color:#fff;font-size:13px;z-index:999;opacity:0;transform:translateY(-10px);transition:.25s;pointer-events:none}
.toast.show{opacity:1;transform:translateY(0)}
.toast.ok{background:#27ae60}
.toast.err{background:#c0392b}
.info-bar{display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:13px;color:#555}
.info-bar strong{color:#16213e}
</style>
"""


def render_page():
    """返回规则与专业维护页面的 HTML 主体（不含外层框架）。"""
    disc_items_html = ""
    for disc in DISCIPLINE_LIST:
        label = DISCIPLINE_LABELS.get(disc, disc)
        disc_items_html += f'<a class="s-item" data-disc="{disc}" onclick="selectDisc(\'{disc}\')">{label} <span class="badge">—</span></a>\n'

    return _STYLE + rf"""
<div class="rules-wrap">
  <!-- 顶部栏 -->
  <div class="rules-topbar">
    <span class="title">📋 规则与专业维护</span>
    <div class="search-box">
      <span class="s-icon">🔍</span>
      <input type="text" id="searchInput" placeholder="搜索检查点 ID 或名称..." oninput="onSearch()">
    </div>
    <button class="btn btn-reload" onclick="reloadYaml()" title="从 YAML 文件重新加载检查点">🔄 刷新 YAML</button>
  </div>

  <div class="rules-body">
    <!-- 左侧专业列表 -->
    <div class="rules-sidebar">
      <div class="s-header" style="color:#888">专业分类</div>
      {disc_items_html}
    </div>

    <!-- 右侧主区域 -->
    <div class="rules-main">
      <!-- 工具栏 -->
      <div class="rules-toolbar">
        <button class="btn btn-primary" onclick="openCreateModal()">+ 新建检查点</button>
        <label class="select-all"><input type="checkbox" id="selectAll" onchange="toggleSelectAll()"> 全选</label>
        <button class="btn btn-success" onclick="batchToggle(true)">批量启用</button>
        <button class="btn btn-warning" onclick="batchToggle(false)">批量禁用</button>
        <button class="btn btn-danger" onclick="batchDelete()">批量删除</button>
      </div>

      <!-- 信息栏 -->
      <div class="info-bar">
        当前专业: <strong id="currentDisc">建筑</strong> &nbsp;|&nbsp; 共 <strong id="totalCount">0</strong> 条检查点
      </div>

      <!-- 表格 -->
      <div id="tableContainer">
        <div class="empty-state"><div class="icon">📭</div><p>加载中...</p></div>
      </div>
    </div>
  </div>
</div>

<!-- 编辑弹窗 -->
<div class="modal-overlay" id="editModal">
  <div class="modal-box">
    <div class="modal-header">
      <h3 id="modalTitle">编辑检查点</h3>
      <button class="close-btn" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="modalMode">
      <div class="form-row">
        <div class="form-group">
          <label>检查点 ID *</label>
          <input id="fid" placeholder="如 JZ-001" maxlength="50">
        </div>
        <div class="form-group">
          <label>名称 *</label>
          <input id="fname" placeholder="检查点名称">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>专业</label>
          <select id="fdiscipline">{''.join(f'<option value="{d}">{DISCIPLINE_LABELS[d]}</option>' for d in DISCIPLINE_LIST)}</select>
        </div>
        <div class="form-group">
          <label>严重度</label>
          <select id="fseverity"><option value="A">A-强制</option><option value="B" selected>B-重要</option><option value="C">C-一般</option><option value="D">D-提示</option></select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>审查路径</label>
          <select id="froute"><option value="text">文本</option><option value="visual">视觉</option><option value="dual">双路径</option></select>
        </div>
        <div class="form-group">
          <label>审查类型</label>
          <select id="fcheck_type">
            <option value="free_review">自由审查</option><option value="dimension_min">尺寸下限</option>
            <option value="dimension_max">尺寸上限</option><option value="existence">存在性</option>
            <option value="text_keyword">关键词</option><option value="compliance">强条</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>优先级</label>
          <input id="fpriority" type="number" value="0" min="0" max="999">
        </div>
        <div class="form-group">
          <label>标准代号</label>
          <input id="fstandard_code" placeholder="如 GB50016-2014(2018)">
        </div>
      </div>
      <div class="form-group">
        <label>标准条款</label>
        <input id="fstandard_clause" placeholder="如 5.5.30">
      </div>
      <div class="form-group">
        <label>描述</label>
        <textarea id="fdescription" rows="2" placeholder="检查点描述..."></textarea>
      </div>
      <div class="form-group">
        <label>启用状态</label>
        <select id="fenabled"><option value="1">启用</option><option value="0">禁用</option></select>
      </div>
      <div class="form-group">
        <label>YAML 配置预览</label>
        <textarea id="fconfig_yaml" rows="6" readonly style="background:#f8f9fa;font-size:12px;color:#555"></textarea>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-cancel" onclick="closeModal()">取消</button>
      <button class="btn btn-save" onclick="saveCheckpoint()">保存</button>
    </div>
  </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<script>
var currentDiscipline = 'building';
var allItems = [];
var selectedIds = new Set();
var searchTimer = null;

// ── 初始化 ──
(function init() {{
  loadAllDisciplineCounts();
  selectDisc('building');
}})();

// ── 加载所有专业计数 ──
function loadAllDisciplineCounts() {{
  var disciplines = ['building', 'structure', 'hvac', 'plumbing', 'electrical', 'fire', 'curtain_wall', 'decoration', 'landscape', 'foundation_pit'];
  disciplines.forEach(function(disc) {{
    fetch('/admin/api/rules/list?discipline=' + encodeURIComponent(disc))
      .then(function(r) {{ return r.json(); }})
      .then(function(data) {{
        var count = (data.items || []).length;
        updateSidebarBadge(disc, count);
      }})
      .catch(function() {{ updateSidebarBadge(disc, 0); }});
  }});
}}

// ── 专业切换 ──
function selectDisc(disc) {{
  currentDiscipline = disc;
  document.querySelectorAll('.s-item').forEach(function(el) {{
    el.classList.toggle('active', el.dataset.disc === disc);
  }});
  document.getElementById('currentDisc').textContent = disciplineLabel(disc);
  document.getElementById('searchInput').value = '';
  selectedIds.clear();
  document.getElementById('selectAll').checked = false;
  loadList(disc, '');
}}

// ── 加载列表 ──
function loadList(disc, search) {{
  var qs = 'discipline=' + encodeURIComponent(disc);
  if (search) qs += '&search=' + encodeURIComponent(search);
  fetch('/admin/api/rules/list?' + qs)
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      allItems = data.items || [];
      document.getElementById('totalCount').textContent = allItems.length;
      // 更新侧边栏计数
      updateSidebarBadge(disc, allItems.length);
      renderTable();
    }})
    .catch(function(e) {{
      console.error(e);
      toastMsg('加载失败: ' + e.message, 'err');
    }});
}}

// ── 渲染表格 ──
function renderTable() {{
  var container = document.getElementById('tableContainer');
  if (allItems.length === 0) {{
    container.innerHTML = '<div class="empty-state"><div class="icon">📭</div><p>暂无检查点数据</p></div>';
    return;
  }}
  var html = '<table class="rules-table"><thead><tr>';
  html += '<th class="center" style="width:36px"><input type="checkbox" id="selectAll" onchange="toggleSelectAll()"></th>';
  html += '<th>ID</th><th>名称</th><th class="center">严重度</th><th class="center">路径</th><th class="center">启用</th><th class="center">操作</th>';
  html += '</tr></thead><tbody>';
  for (var i = 0; i < allItems.length; i++) {{
    var item = allItems[i];
    var sevLabel = item.severity || 'B';
    var sevText = sevLabel === 'A' ? 'A-强制' : sevLabel === 'B' ? 'B-重要' : sevLabel === 'C' ? 'C-一般' : 'D-提示';
    var routeLabels = {{'text':'文本','visual':'视觉','dual':'双路径'}};
    var routeText = routeLabels[item.route] || item.route || '文本';
    var checked = selectedIds.has(item.id) ? 'checked' : '';
    var rowClass = selectedIds.has(item.id) ? 'selected' : '';
    html += '<tr class="' + rowClass + '">';
    html += '<td class="center"><input type="checkbox" ' + checked + ' onchange="toggleItem(\'' + esc(item.id) + '\', this.checked)"></td>';
    html += '<td><code>' + esc(item.id) + '</code></td>';
    html += '<td>' + esc(item.name || '') + '</td>';
    html += '<td class="center"><span class="sev-badge sev-' + sevLabel + '">' + sevText + '</span></td>';
    html += '<td class="center"><span class="route-badge">' + routeText + '</span></td>';
    html += '<td class="center"><label class="toggle-sw"><input type="checkbox" ' + (item.enabled ? 'checked' : '') + ' onchange="toggleOne(\'' + esc(item.id) + '\', this.checked)"><span class="slider"></span></label></td>';
    html += '<td class="center"><button class="action-btn edit" onclick="openEditModal(\'' + esc(item.id) + '\')">编辑</button><button class="action-btn del" onclick="deleteOne(\'' + esc(item.id) + '\')">删除</button></td>';
    html += '</tr>';
  }}
  html += '</tbody></table>';
  container.innerHTML = html;
}}

// ── 搜索 ──
function onSearch() {{
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function() {{
    var val = document.getElementById('searchInput').value.trim();
    loadList(currentDiscipline, val);
  }}, 300);
}}

// ── 选择 ──
function toggleSelectAll() {{
  var checked = document.getElementById('selectAll').checked;
  allItems.forEach(function(item) {{
    if (checked) selectedIds.add(item.id);
    else selectedIds.delete(item.id);
  }});
  renderTable();
}}
function toggleItem(id, checked) {{
  if (checked) selectedIds.add(id); else selectedIds.delete(id);
  document.getElementById('selectAll').checked = (selectedIds.size === allItems.length && allItems.length > 0);
  renderTable();
}}
function allSelectedIds() {{
  return Array.from(selectedIds);
}}

// ── 弹窗 ──
function openCreateModal() {{
  document.getElementById('modalTitle').textContent = '新建检查点';
  document.getElementById('modalMode').value = 'create';
  document.getElementById('fid').value = '';
  document.getElementById('fid').disabled = false;
  document.getElementById('fname').value = '';
  document.getElementById('fdiscipline').value = currentDiscipline;
  document.getElementById('fseverity').value = 'B';
  document.getElementById('froute').value = 'text';
  document.getElementById('fcheck_type').value = 'free_review';
  document.getElementById('fpriority').value = '0';
  document.getElementById('fstandard_code').value = '';
  document.getElementById('fstandard_clause').value = '';
  document.getElementById('fdescription').value = '';
  document.getElementById('fenabled').value = '1';
  document.getElementById('fconfig_yaml').value = '';
  document.getElementById('editModal').classList.add('show');
}}

function openEditModal(id) {{
  fetch('/admin/api/rules/' + encodeURIComponent(id))
    .then(function(r) {{ return r.json(); }})
    .then(function(item) {{
      document.getElementById('modalTitle').textContent = '编辑检查点: ' + id;
      document.getElementById('modalMode').value = 'edit';
      document.getElementById('fid').value = item.id || '';
      document.getElementById('fid').disabled = true;
      document.getElementById('fname').value = item.name || '';
      document.getElementById('fdiscipline').value = item.discipline || 'building';
      document.getElementById('fseverity').value = item.severity || 'B';
      document.getElementById('froute').value = item.route || 'text';
      document.getElementById('fcheck_type').value = item.check_type || 'free_review';
      document.getElementById('fpriority').value = item.priority || 0;
      document.getElementById('fstandard_code').value = item.standard_code || '';
      document.getElementById('fstandard_clause').value = item.standard_clause || '';
      document.getElementById('fdescription').value = item.description || '';
      document.getElementById('fenabled').value = item.enabled ? '1' : '0';
      // YAML 预览
      var cfg = item.config_json || {{}};
      try {{
        document.getElementById('fconfig_yaml').value = jsToYaml(cfg);
      }} catch(e) {{
        document.getElementById('fconfig_yaml').value = JSON.stringify(cfg, null, 2);
      }}
      document.getElementById('editModal').classList.add('show');
    }})
    .catch(function(e) {{
      toastMsg('加载失败: ' + e.message, 'err');
    }});
}}

function closeModal() {{
  document.getElementById('editModal').classList.remove('show');
}}

// ── 保存 ──
function saveCheckpoint() {{
  var mode = document.getElementById('modalMode').value;
  var id = document.getElementById('fid').value.trim();
  var name = document.getElementById('fname').value.trim();
  if (!id || !name) {{ toastMsg('ID 和名称不能为空', 'err'); return; }}

  var body = {{
    id: id, name: name,
    discipline: document.getElementById('fdiscipline').value,
    severity: document.getElementById('fseverity').value,
    route: document.getElementById('froute').value,
    check_type: document.getElementById('fcheck_type').value,
    priority: parseInt(document.getElementById('fpriority').value) || 0,
    standard_code: document.getElementById('fstandard_code').value.trim(),
    standard_clause: document.getElementById('fstandard_clause').value.trim(),
    description: document.getElementById('fdescription').value.trim(),
    enabled: document.getElementById('fenabled').value === '1',
    config_json: {{}},
  }};

  var url = '/admin/api/rules';
  var method = 'POST';
  if (mode === 'edit') {{
    url = '/admin/api/rules/' + encodeURIComponent(id);
    method = 'PUT';
  }}

  fetch(url, {{
    method: method,
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body),
  }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.error) {{ toastMsg(data.error, 'err'); return; }}
      toastMsg('保存成功', 'ok');
      closeModal();
      loadList(currentDiscipline, document.getElementById('searchInput').value.trim());
    }})
    .catch(function(e) {{ toastMsg('保存失败: ' + e.message, 'err'); }});
}}

// ── 单个删除 ──
function deleteOne(id) {{
  if (!confirm('确认删除检查点 ' + id + '？此操作不可撤销。')) return;
  fetch('/admin/api/rules/' + encodeURIComponent(id), {{ method: 'DELETE' }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.error) {{ toastMsg(data.error, 'err'); return; }}
      toastMsg('已删除 ' + id, 'ok');
      selectedIds.delete(id);
      loadList(currentDiscipline, document.getElementById('searchInput').value.trim());
    }})
    .catch(function(e) {{ toastMsg('删除失败: ' + e.message, 'err'); }});
}}

// ── 单个启用/禁用 ──
function toggleOne(id, enabled) {{
  fetch('/admin/api/rules/toggle', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ids: [id], enabled: enabled}}),
  }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.error) {{ toastMsg(data.error, 'err'); return; }}
      toastMsg(id + ' 已' + (enabled ? '启用' : '禁用'), 'ok');
    }})
    .catch(function(e) {{ toastMsg('操作失败: ' + e.message, 'err'); }});
}}

// ── 批量启用/禁用 ──
function batchToggle(enabled) {{
  var ids = allSelectedIds();
  if (ids.length === 0) {{ toastMsg('请先选择检查点', 'err'); return; }}
  fetch('/admin/api/rules/toggle', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ids: ids, enabled: enabled}}),
  }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.error) {{ toastMsg(data.error, 'err'); return; }}
      toastMsg('已批量' + (enabled ? '启用' : '禁用') + ' ' + ids.length + ' 个检查点', 'ok');
      selectedIds.clear();
      document.getElementById('selectAll').checked = false;
      loadList(currentDiscipline, document.getElementById('searchInput').value.trim());
    }})
    .catch(function(e) {{ toastMsg('操作失败: ' + e.message, 'err'); }});
}}

// ── 批量删除 ──
function batchDelete() {{
  var ids = allSelectedIds();
  if (ids.length === 0) {{ toastMsg('请先选择检查点', 'err'); return; }}
  if (!confirm('确认删除 ' + ids.length + ' 个检查点？此操作不可撤销。')) return;
  var count = 0;
  var total = ids.length;
  ids.forEach(function(id) {{
    fetch('/admin/api/rules/' + encodeURIComponent(id), {{ method: 'DELETE' }})
      .then(function(r) {{ return r.json(); }})
      .then(function() {{
        count++;
        if (count >= total) {{
          toastMsg('已删除 ' + total + ' 个检查点', 'ok');
          selectedIds.clear();
          document.getElementById('selectAll').checked = false;
          loadList(currentDiscipline, document.getElementById('searchInput').value.trim());
        }}
      }})
      .catch(function(e) {{ toastMsg('删除失败: ' + e.message, 'err'); }});
  }});
}}

// ── 刷新 YAML ──
function reloadYaml() {{
  if (!confirm('将从 YAML 定义文件重新加载所有检查点到数据库，确认继续？')) return;
  fetch('/admin/api/rules/reload', {{ method: 'POST' }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.error) {{ toastMsg(data.error, 'err'); return; }}
      toastMsg('已从 YAML 重新加载 ' + data.count + ' 个检查点', 'ok');
      loadList(currentDiscipline, document.getElementById('searchInput').value.trim());
    }})
    .catch(function(e) {{ toastMsg('重新加载失败: ' + e.message, 'err'); }});
}}

// ── 辅助 ──
function disciplineLabel(disc) {{
  var labels = {json.dumps(DISCIPLINE_LABELS, ensure_ascii=False)};
  return labels[disc] || disc;
}}
function esc(s) {{ return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }}
function toastMsg(msg, type) {{
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + (type || 'ok') + ' show';
  clearTimeout(t._timer);
  t._timer = setTimeout(function() {{ t.classList.remove('show'); }}, 2500);
}}
function jsToYaml(obj, indent) {{
  indent = indent || 0;
  var sp = new Array(indent + 1).join('  ');
  if (obj === null || obj === undefined) return 'null';
  if (typeof obj === 'string') return '"' + obj.replace(/\\/g,'\\\\').replace(/"/g,'\\"') + '"';
  if (typeof obj === 'number' || typeof obj === 'boolean') return String(obj);
  if (Array.isArray(obj)) {{
    if (obj.length === 0) return '[]';
    return obj.map(function(v) {{ return sp + '- ' + jsToYaml(v, indent + 1).replace(/^\\s*/, ''); }}).join('\\n');
  }}
  if (typeof obj === 'object') {{
    var keys = Object.keys(obj);
    if (keys.length === 0) return '{{}}';
    return keys.map(function(k) {{ return sp + k + ': ' + jsToYaml(obj[k], indent + 1).replace(/^\\s*/, ''); }}).join('\\n');
  }}
  return String(obj);
}}
function updateSidebarBadge(disc, count) {{
  var items = document.querySelectorAll('.s-item');
  for (var i = 0; i < items.length; i++) {{
    if (items[i].dataset.disc === disc) {{
      var badge = items[i].querySelector('.badge');
      if (badge) badge.textContent = count;
      break;
    }}
  }}
}}
</script>
"""
