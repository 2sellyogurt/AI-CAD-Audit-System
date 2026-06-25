# -*- coding: utf-8 -*-
"""审查结果管理页面 — 问题列表/详情/状态管理/CSV导出/审查对比

导出的公共接口:
    render_page() -> str         返回完整 HTML（不含外层框架）
    handle_api(path, method, body, qs)
        -> (status, data, content_type) | None
"""

import json
import csv
import io
import re
import copy
from datetime import datetime
from collections import OrderedDict

# ══════════════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════════════

from v7.constants import (
    DISCIPLINE_LABELS as _DISCIPLINE_MAP,
    SEVERITY_META,
    ISSUE_STATUS_COLORS as _STATUS_COLORS,
)

_SEVERITY_ORDER = {k: v["order"] + 1 for k, v in SEVERITY_META.items()}
_SEVERITY_COLORS = {k: v["color"] for k, v in SEVERITY_META.items()}


def _normalize_issue(item):
    """将缓存或 db 行统一为前端格式。"""
    if isinstance(item, dict):
        out = {}
        out["id"] = item.get("id", "")
        out["review_id"] = item.get("review_id", 0)
        out["issue_id"] = item.get("issue_id", item.get("id", ""))
        out["discipline"] = item.get("discipline", "")
        out["severity"] = item.get("severity", "")
        out["standard_code"] = item.get("standard_code", "")
        out["finding"] = item.get("finding", "")
        out["fix"] = item.get("fix", "")
        out["drawing_name"] = item.get("drawing_name", "")
        out["location"] = item.get("location", "")
        out["confidence"] = item.get("confidence", "")
        out["route_used"] = item.get("route_used", "")
        rationality = item.get("rationality", {})
        if isinstance(rationality, dict):
            out["rationality"] = rationality.get("level", "")
            out["rationality_score"] = rationality.get("score", 0)
        else:
            out["rationality"] = str(rationality) if rationality else ""
            out["rationality_score"] = item.get("rationality_score", 0)
        out["status"] = item.get("status", "new")
        out["note"] = item.get("note", "")
        out["checkpoint_id"] = item.get("checkpoint_id", "")
        return out
    # sqlite3.Row
    try:
        d = dict(item)
        d["rationality"] = d.get("rationality", "")
        d["rationality_score"] = d.get("rationality_score", 0)
        d["note"] = d.get("note", "")
        d["issue_id"] = d.get("issue_id", str(d.get("id", "")))
        return d
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"问题数据标准化失败: {e}")
        return {"id": str(item), "severity": "", "status": "new",
                "discipline": "", "finding": "", "rationality": "",
                "rationality_score": 0, "note": ""}


def _get_issues_from_cache():
    """从 admin/server.py 共享缓存读取 issues（深拷贝避免污染缓存）。"""
    try:
        from v7.admin.server import _review_cache
        if _review_cache.get("ready") and _review_cache.get("issues"):
            return [copy.deepcopy(item) for item in _review_cache["issues"]]
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"读取审查缓存失败: {e}")
    return []


def _get_issues_from_db():
    """从 review_issues 表读取。"""
    try:
        from v7.db import get_db
        db = get_db()
        rows = db.execute(
            "SELECT * FROM review_issues ORDER BY severity, id"
        ).fetchall()
        return [_normalize_issue(r) for r in rows]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"从数据库读取问题失败: {e}")
        return []


def _get_all_issues():
    """以数据库为唯一数据源，缓存仅作为性能加速层。"""
    db_issues = _get_issues_from_db()
    if db_issues:
        return db_issues
    # 数据库为空时回退到缓存（兼容旧数据）
    cached = _get_issues_from_cache()
    if cached:
        result = []
        seen = set()
        for item in cached:
            n = _normalize_issue(item)
            key = str(n.get("id", "")) or n.get("finding", "")[:40]
            if key not in seen:
                seen.add(key)
                result.append(n)
        return result
    return []


def _get_stats(issues):
    total = len(issues)
    a_count = sum(1 for i in issues if i.get("severity") == "A")
    b_count = sum(1 for i in issues if i.get("severity") == "B")
    c_count = sum(1 for i in issues if i.get("severity") == "C")
    d_count = sum(1 for i in issues if i.get("severity") == "D")
    try:
        from v7.admin.server import _review_cache
        spatial_count = len(_review_cache.get("conflicts", []))
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"读取空间冲突计数失败: {e}")
        spatial_count = 0
    disciplines = sorted(set(
        i.get("discipline", "") for i in issues if i.get("discipline")
    ))
    return {
        "total": total,
        "aCount": a_count,
        "bCount": b_count,
        "cCount": c_count,
        "dCount": d_count,
        "spatialConflicts": spatial_count,
        "disciplines": disciplines,
        "byStatus": {
            "new": sum(1 for i in issues if i.get("status") == "new"),
            "confirmed": sum(1 for i in issues if i.get("status") == "confirmed"),
            "rejected": sum(1 for i in issues if i.get("status") == "rejected"),
            "fixed": sum(1 for i in issues if i.get("status") == "fixed"),
        },
    }


# ══════════════════════════════════════════════════════════════
#  内联 CSS
# ══════════════════════════════════════════════════════════════

_RESULTS_CSS = """
<style>
/* ── 审查结果页样式 ── */
#results-app{font:14px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#333}
#results-app *{box-sizing:border-box}

/* 筛选栏 */
.filter-bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;
  background:#fff;border-radius:8px;padding:14px 18px;margin-bottom:16px;
  box-shadow:0 1px 3px rgba(0,0,0,.08)}
.filter-bar select,.filter-bar input{
  padding:7px 12px;border:1px solid #d1d5db;border-radius:6px;font-size:13px;
  background:#fff;color:#333;outline:none;transition:border-color .2s}
.filter-bar select:focus,.filter-bar input:focus{border-color:#16213e}
.filter-bar input[type=text]{min-width:220px}
.filter-bar label{font-size:12px;color:#666;margin-right:4px;white-space:nowrap}
.filter-bar .btn{padding:7px 16px;border:none;border-radius:6px;
  font-size:13px;cursor:pointer;font-weight:500;transition:opacity .2s}
.filter-bar .btn:hover{opacity:.85}

/* 统计卡片 */
.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}
.stat-card{background:#fff;border-radius:8px;padding:18px 16px;text-align:center;
  box-shadow:0 1px 3px rgba(0,0,0,.08);border-left:4px solid #16213e}
.stat-card.a-card{border-left-color:#e74c3c}
.stat-card.b-card{border-left-color:#e67e22}
.stat-card.conflict-card{border-left-color:#e94560}
.stat-card .num{font-size:28px;font-weight:700;color:#1a1a2e;line-height:1.2}
.stat-card .label{font-size:12px;color:#555;margin-top:4px;text-transform:uppercase;letter-spacing:.5px}

/* 问题表格 */
.table-wrap{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden}
.results-table{width:100%;border-collapse:collapse;font-size:13px}
.results-table thead{background:#1a1a2e;color:#fff}
.results-table th{padding:10px 12px;text-align:left;font-weight:600;font-size:12px;
  text-transform:uppercase;letter-spacing:.5px;white-space:nowrap}
.results-table td{padding:10px 12px;border-bottom:1px solid #eee;vertical-align:top}
.results-table tbody tr{cursor:pointer;transition:background .15s}
.results-table tbody tr:hover{background:#f0f4ff}
.results-table tbody tr.expanded{background:#eef2ff}

/* 徽章 */
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;
  font-weight:700;color:#fff;text-align:center;min-width:28px}
.badge-A{background:#e74c3c}
.badge-B{background:#e67e22}
.badge-C{background:#f39c12}
.badge-D{background:#95a5a6}
.badge-new{background:#3498db}
.badge-confirmed{background:#27ae60}
.badge-rejected{background:#c0392b}
.badge-fixed{background:#8e44ad}

/* 展开详情面板 */
.detail-panel{display:none;padding:20px 24px;background:#f8fafc;
  border-bottom:2px solid #16213e}
.detail-panel.active{display:block}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.detail-grid .full{grid-column:1/-1}
.detail-field{margin-bottom:12px}
.detail-field .f-label{font-size:11px;color:#555;text-transform:uppercase;
  letter-spacing:.5px;margin-bottom:2px}
.detail-field .f-value{font-size:14px;color:#1a1a2e;line-height:1.5}
.detail-rationality{display:flex;gap:6px;margin-top:8px}
.detail-rationality .r-dot{width:14px;height:14px;border-radius:50%;
  background:#d1d5db;transition:background .2s}
.detail-rationality .r-dot.active{background:#e94560}
.detail-actions{display:flex;gap:10px;align-items:flex-end;margin-top:16px;flex-wrap:wrap}
.detail-actions .btn{padding:8px 18px;border:none;border-radius:6px;
  font-size:13px;cursor:pointer;font-weight:500;transition:opacity .2s}
.detail-actions .btn:hover{opacity:.85}
.detail-actions textarea{flex:1;min-width:260px;min-height:60px;
  padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;
  font-size:13px;font-family:inherit;resize:vertical}
.detail-actions textarea:focus{outline:none;border-color:#16213e}

/* 按钮配色 */
.btn-primary{background:#16213e;color:#fff}
.btn-success{background:#27ae60;color:#fff}
.btn-danger{background:#e74c3c;color:#fff}
.btn-warning{background:#e67e22;color:#fff}
.btn-outline{background:transparent;color:#16213e;border:1px solid #16213e}

/* 对比模式 */
.diff-container{display:none;margin-top:16px}
.diff-container.active{display:block}
.diff-bar{display:flex;gap:10px;align-items:center;background:#fff;
  border-radius:8px;padding:14px 18px;margin-bottom:14px;
  box-shadow:0 1px 3px rgba(0,0,0,.08)}
.diff-bar select{padding:7px 12px;border:1px solid #d1d5db;border-radius:6px;font-size:13px}
.diff-bar label{font-size:12px;color:#666}
.diff-results{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.diff-col{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden}
.diff-col h4{padding:10px 14px;margin:0;font-size:13px;color:#fff}
.diff-col h4.review-a{background:#16213e}
.diff-col h4.review-b{background:#e94560}
.diff-note{padding:10px 14px;font-size:12px;color:#555;border-bottom:1px solid #eee}
.diff-col .diff-item{padding:8px 14px;border-bottom:1px solid #eee;font-size:13px}
.diff-added{border-left:3px solid #27ae60;background:#f0faf4}
.diff-removed{border-left:3px solid #e74c3c;background:#fef5f5}
.diff-changed{border-left:3px solid #e67e22;background:#fef9f3}

/* 加载 & 空状态 */
.loading-state{text-align:center;padding:40px;color:#555}
.empty-state{text-align:center;padding:40px;color:#666}
.empty-state .icon{font-size:40px;margin-bottom:8px}

/* toast */
.toast{position:fixed;top:20px;right:20px;padding:12px 20px;border-radius:6px;
  color:#fff;font-size:13px;z-index:9999;opacity:0;transition:opacity .3s;
  pointer-events:none}
.toast.show{opacity:1}
.toast-success{background:#27ae60}
.toast-error{background:#e74c3c}

@media(max-width:768px){
  .stats-row{grid-template-columns:repeat(2,1fr)}
  .detail-grid{grid-template-columns:1fr}
  .diff-results{grid-template-columns:1fr}
  .filter-bar{flex-direction:column;align-items:stretch}
  .filter-bar input[type=text]{min-width:auto}
}
</style>
"""

# ══════════════════════════════════════════════════════════════
#  HTML 模板
# ══════════════════════════════════════════════════════════════

def _html_filter_bar():
    return """
<div class="filter-bar">
  <div>
    <label>严重度</label>
    <select id="filter-severity" onchange="applyFilters()">
      <option value="all">全部</option>
      <option value="A">A — 严重</option>
      <option value="B">B — 较严重</option>
      <option value="C">C — 一般</option>
      <option value="D">D — 建议</option>
    </select>
  </div>
  <div>
    <label>专业</label>
    <select id="filter-discipline" onchange="applyFilters()">
      <option value="all">全部专业</option>
    </select>
  </div>
  <div>
    <label>状态</label>
    <select id="filter-status" onchange="applyFilters()">
      <option value="all">全部状态</option>
      <option value="new">新建</option>
      <option value="confirmed">已确认</option>
      <option value="rejected">已驳回</option>
      <option value="fixed">已修复</option>
    </select>
  </div>
  <div style="flex:1;min-width:220px">
    <label>&nbsp;</label>
    <input type="text" id="filter-search" placeholder="搜索问题描述关键词..."
      style="width:100%" onkeyup="debounceSearch()">
  </div>
  <div>
    <label>&nbsp;</label>
    <button class="btn btn-outline" onclick="exportCSV()" title="导出当前筛选结果为 CSV">导出 CSV</button>
  </div>
  <div>
    <label>&nbsp;</label>
    <button class="btn btn-warning" id="diff-toggle-btn" onclick="toggleDiffMode()">对比模式</button>
  </div>
</div>"""


def _html_stats_cards():
    return """
<div class="stats-row">
  <div class="stat-card"><div class="num" id="stat-total">—</div><div class="label">总问题数</div></div>
  <div class="stat-card a-card"><div class="num" id="stat-a">—</div><div class="label">A 级 (严重)</div></div>
  <div class="stat-card b-card"><div class="num" id="stat-b">—</div><div class="label">B 级 (较严重)</div></div>
  <div class="stat-card conflict-card"><div class="num" id="stat-spatial">—</div><div class="label">空间冲突</div></div>
</div>"""


def _html_issue_table():
    return """
<div class="table-wrap">
  <table class="results-table">
    <thead>
      <tr>
        <th style="width:50px">#</th>
        <th style="width:70px">严重度</th>
        <th style="width:80px">专业</th>
        <th style="width:110px">规范条文</th>
        <th>问题描述</th>
        <th style="width:70px">状态</th>
        <th style="width:60px">操作</th>
      </tr>
    </thead>
    <tbody id="issue-tbody">
      <tr><td colspan="7" class="loading-state">加载中...</td></tr>
    </tbody>
  </table>
</div>"""


def _html_diff_mode():
    """对比模式 HTML。"""
    return """
<div class="diff-container" id="diff-container">
  <div class="diff-bar">
    <label>基准审查:</label>
    <select id="diff-review-a"><option value="">— 选择审查 —</option></select>
    <label style="margin-left:10px">对比审查:</label>
    <select id="diff-review-b"><option value="">— 选择审查 —</option></select>
    <button class="btn btn-primary" onclick="loadDiff()">开始对比</button>
    <button class="btn btn-outline" onclick="toggleDiffMode()" style="margin-left:auto">关闭对比</button>
  </div>
  <div class="diff-results">
    <div class="diff-col">
      <h4 class="review-a">基准审查</h4>
      <div id="diff-col-a"><div class="diff-note">请选择两次审查后点击"开始对比"</div></div>
    </div>
    <div class="diff-col">
      <h4 class="review-b">对比审查</h4>
      <div id="diff-col-b"><div class="diff-note">请选择两次审查后点击"开始对比"</div></div>
    </div>
  </div>
</div>"""


# ══════════════════════════════════════════════════════════════
#  JavaScript
# ══════════════════════════════════════════════════════════════

_RESULTS_JS = r"""
(function(){
  var allIssues = [];
  var expandedRow = null;
  var diffMode = false;

  /* ── 工具 ── */
  function trunc(s, n){ return s && s.length>n ? s.substring(0,n)+'...' : (s||''); }
  function esc(s){ var d=document.createElement('div');d.textContent=s;return d.innerHTML; }
  function $id(id){ return document.getElementById(id); }

  /* ── 加载 ── */
  function loadStats(){
    fetch('/admin/api/results/stats').then(function(r){return r.json()}).then(function(d){
      $id('stat-total').innerText = d.total||0;
      $id('stat-a').innerText = d.aCount||0;
      $id('stat-b').innerText = d.bCount||0;
      $id('stat-spatial').innerText = d.spatialConflicts||0;
      /* 填充专业下拉 */
      var sel = $id('filter-discipline');
      var cur = sel.value;
      sel.innerHTML = '<option value="all">全部专业</option>';
      (d.disciplines||[]).forEach(function(disc){
        sel.innerHTML += '<option value="'+esc(disc)+'">'+esc(disc)+'</option>';
      });
      sel.value = cur;
    }).catch(function(e){ console.error('stats load error',e); });
  }

  function loadIssues(params){
    var qs = [];
    var sev = $id('filter-severity').value;
    var disc = $id('filter-discipline').value;
    var st = $id('filter-status').value;
    var search = $id('filter-search').value.trim();
    if(sev && sev!=='all') qs.push('severity='+encodeURIComponent(sev));
    if(disc && disc!=='all') qs.push('discipline='+encodeURIComponent(disc));
    if(st && st!=='all') qs.push('status='+encodeURIComponent(st));
    if(search) qs.push('search='+encodeURIComponent(search));
    var url = '/admin/api/results/list' + (qs.length?'?'+qs.join('&'):'');
    fetch(url).then(function(r){return r.json()}).then(function(d){
      allIssues = d.items||[];
      renderTable(allIssues);
    }).catch(function(e){
      console.error('issues load error',e);
      $id('issue-tbody').innerHTML = '<tr><td colspan="7" class="empty-state"><div class="icon">!</div>加载失败，请确认审查数据已就绪</td></tr>';
    });
  }

  /* ── 渲染表格 ── */
  function renderTable(items){
    var tbody = $id('issue-tbody');
    if(!items.length){
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><div class="icon">&#128269;</div>暂无匹配的问题记录</td></tr>';
      return;
    }
    var html = '';
    for(var i=0;i<items.length;i++){
      var item = items[i];
      var sev = item.severity||'?';
      var disc = item.discipline||'';
      var code = item.standard_code||'';
      var finding = item.finding||'';
      var status = item.status||'new';
      var statusLabel = {new:'新建',confirmed:'已确认',rejected:'已驳回',fixed:'已修复'}[status]||status;
      html += '<tr data-idx="'+i+'" onclick="toggleDetail(event,'+i+')">';
      html += '<td>'+(i+1)+'</td>';
      html += '<td><span class="badge badge-'+sev+'">'+esc(sev)+'</span></td>';
      html += '<td>'+esc(disc)+'</td>';
      html += '<td style="font-size:11px">'+esc(code)+'</td>';
      html += '<td>'+esc(trunc(finding,60))+'</td>';
      html += '<td><span class="badge badge-'+status+'">'+esc(statusLabel)+'</span></td>';
      html += '<td><button class="btn btn-primary" style="padding:3px 10px;font-size:11px" onclick="event.stopPropagation();openDetail('+i+')">详情</button></td>';
      html += '</tr>';
      /* 详情面板行 */
      html += '<tr class="detail-row" id="detail-'+i+'" style="display:none"><td colspan="7" style="padding:0">';
      html += '<div class="detail-panel" id="panel-'+i+'">';
      html += _renderDetailHTML(item);
      html += '</div></td></tr>';
    }
    tbody.innerHTML = html;
  }

  function _renderDetailHTML(item){
    var rat = item.rationality||'R2';
    var score = item.rationality_score||60;
    var dots = '';
    var levels = ['R0','R1','R2','R3'];
    for(var j=0;j<levels.length;j++){
      dots += '<div class="r-dot'+(levels[j]===rat?' active':'')+'" title="'+levels[j]+'"></div>';
    }
    return (
      '<div class="detail-grid">'+
        '<div class="detail-field">'+
          '<div class="f-label">完整问题描述</div>'+
          '<div class="f-value">'+esc(item.finding||'—')+'</div>'+
        '</div>'+
        '<div class="detail-field">'+
          '<div class="f-label">整改建议</div>'+
          '<div class="f-value">'+esc(item.fix||'—')+'</div>'+
        '</div>'+
        '<div class="detail-field">'+
          '<div class="f-label">图纸来源</div>'+
          '<div class="f-value">'+esc(item.drawing_name||'—')+'</div>'+
        '</div>'+
        '<div class="detail-field">'+
          '<div class="f-label">位置信息</div>'+
          '<div class="f-value">'+esc(item.location||'—')+'</div>'+
        '</div>'+
        '<div class="detail-field full">'+
          '<div class="f-label">合理性评分</div>'+
          '<div class="detail-rationality">'+dots+'</div>'+
          '<div style="font-size:12px;color:#555;margin-top:2px">'+esc(rat)+' / 分值: '+score+'</div>'+
        '</div>'+
      '</div>'+
      '<div class="detail-actions">'+
        '<textarea id="note-'+item.id+'" placeholder="备注说明（可选）..."></textarea>'+
        '<button class="btn btn-success" onclick="updateStatus(\''+esc(item.id)+'\',\'confirmed\')">确认</button>'+
        '<button class="btn btn-danger" onclick="updateStatus(\''+esc(item.id)+'\',\'rejected\')">驳回</button>'+
        '<button class="btn btn-primary" onclick="updateStatus(\''+esc(item.id)+'\',\'fixed\')">已修复</button>'+
      '</div>'
    );
  }

  /* ── 行展开/折叠 ── */
  window.toggleDetail = function(e, idx){
    e.stopPropagation();
    var detailRow = $id('detail-'+idx);
    var panel = $id('panel-'+idx);
    if(!detailRow || !panel) return;
    var isOpen = detailRow.style.display !== 'none';
    /* 关闭之前展开的 */
    if(expandedRow !== null && expandedRow !== idx){
      var prevRow = $id('detail-'+expandedRow);
      var prevPanel = $id('panel-'+expandedRow);
      if(prevRow) prevRow.style.display = 'none';
      if(prevPanel) prevPanel.classList.remove('active');
    }
    if(isOpen){
      detailRow.style.display = 'none';
      panel.classList.remove('active');
      expandedRow = null;
    } else {
      detailRow.style.display = '';
      panel.classList.add('active');
      expandedRow = idx;
    }
  };

  window.openDetail = function(idx){
    var detailRow = $id('detail-'+idx);
    var panel = $id('panel-'+idx);
    if(!detailRow || !panel) return;
    if(expandedRow !== null && expandedRow !== idx){
      var prevRow = $id('detail-'+expandedRow);
      var prevPanel = $id('panel-'+expandedRow);
      if(prevRow) prevRow.style.display = 'none';
      if(prevPanel) prevPanel.classList.remove('active');
    }
    detailRow.style.display = '';
    panel.classList.add('active');
    expandedRow = idx;
    detailRow.scrollIntoView({behavior:'smooth',block:'center'});
  };

  /* ── 状态更新 ── */
  window.updateStatus = function(id, newStatus){
    var note = ($id('note-'+id)||{}).value||'';
    fetch('/admin/api/results/'+encodeURIComponent(id)+'/status',{
      method:'PUT',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({status:newStatus,note:note})
    }).then(function(r){return r.json()}).then(function(d){
      if(d.ok){
        showToast('状态已更新为: '+newStatus,'success');
        loadStats();
        loadIssues();
      } else {
        showToast('更新失败: '+(d.error||'未知错误'),'error');
      }
    }).catch(function(e){
      showToast('请求失败: '+e.message,'error');
    });
  };

  /* ── 筛选 ── */
  window.applyFilters = function(){ loadIssues(); };
  var searchTimer = null;
  window.debounceSearch = function(){
    if(searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(function(){ loadIssues(); }, 350);
  };

  /* ── CSV 导出 ── */
  window.exportCSV = function(){
    var sev = $id('filter-severity').value;
    var disc = $id('filter-discipline').value;
    var st = $id('filter-status').value;
    var search = $id('filter-search').value.trim();
    var qs = ['format=csv'];
    if(sev && sev!=='all') qs.push('severity='+encodeURIComponent(sev));
    if(disc && disc!=='all') qs.push('discipline='+encodeURIComponent(disc));
    if(st && st!=='all') qs.push('status='+encodeURIComponent(st));
    if(search) qs.push('search='+encodeURIComponent(search));
    var url = '/admin/api/results/export?'+qs.join('&');
    window.open(url, '_blank');
  };

  /* ── 对比模式 ── */
  window.toggleDiffMode = function(){
    diffMode = !diffMode;
    var container = $id('diff-container');
    var btn = $id('diff-toggle-btn');
    if(diffMode){
      container.classList.add('active');
      btn.textContent = '关闭对比';
      btn.classList.remove('btn-warning');
      btn.classList.add('btn-danger');
      loadReviewList();
    } else {
      container.classList.remove('active');
      btn.textContent = '对比模式';
      btn.classList.remove('btn-danger');
      btn.classList.add('btn-warning');
    }
  };

  function loadReviewList(){
    fetch('/admin/api/results/reviews').then(function(r){return r.json()}).then(function(d){
      var reviews = d.reviews||[];
      var selA = $id('diff-review-a');
      var selB = $id('diff-review-b');
      var opts = '';
      for(var i=0;i<reviews.length;i++){
        var rv = reviews[i];
        opts += '<option value="'+rv.id+'">#'+rv.id+' — '+esc(rv.created_at||'')+' ('+rv.total_issues+'项)</option>';
      }
      selA.innerHTML = '<option value="">— 选择审查 —</option>'+opts;
      selB.innerHTML = '<option value="">— 选择审查 —</option>'+opts;
    }).catch(function(e){ console.error('load reviews error',e); });
  }

  window.loadDiff = function(){
    var id1 = $id('diff-review-a').value;
    var id2 = $id('diff-review-b').value;
    if(!id1||!id2){ showToast('请选择两次审查','error'); return; }
    if(id1===id2){ showToast('请选择两次不同的审查','error'); return; }
    fetch('/admin/api/results/diff?id1='+id1+'&id2='+id2).then(function(r){return r.json()}).then(function(d){
      renderDiff(d);
    }).catch(function(e){ showToast('对比请求失败','error'); });
  };

  function renderDiff(d){
    var colA = $id('diff-col-a');
    var colB = $id('diff-col-b');
    var htmlA = '', htmlB = '';

    var summary = '';
    if(d.summary){
      summary = '<div class="diff-note">新增 '+d.summary.added+' 项 | 消除 '+d.summary.removed+' 项 | 变化 '+d.summary.changed+' 项</div>';
    }

    /* 基准审查（A）*/
    htmlA += summary;
    var removed = d.removed||[];
    if(removed.length){
      htmlA += '<div style="padding:6px 14px;font-size:11px;color:#e74c3c;font-weight:600">已消除 ('+removed.length+'项)</div>';
      for(var i=0;i<removed.length;i++){
        htmlA += '<div class="diff-item diff-removed"><span class="badge badge-'+esc(removed[i].severity||'?')+'">'+esc(removed[i].severity||'?')+'</span> '+esc(trunc(removed[i].finding||'',80))+'</div>';
      }
    }
    var changed = d.changed||[];
    if(changed.length){
      htmlA += '<div style="padding:6px 14px;font-size:11px;color:#e67e22;font-weight:600">已变化 ('+changed.length+'项)</div>';
      for(var i=0;i<changed.length;i++){
        htmlA += '<div class="diff-item diff-changed"><span class="badge badge-'+esc(changed[i].old_severity||'?')+'">'+esc(changed[i].old_severity||'?')+'</span> '+esc(trunc(changed[i].old_finding||'',80))+'</div>';
      }
    }
    if(!removed.length && !changed.length){
      htmlA += '<div class="diff-note">无消除或变化的问题</div>';
    }

    /* 对比审查（B）*/
    htmlB += summary;
    var added = d.added||[];
    if(added.length){
      htmlB += '<div style="padding:6px 14px;font-size:11px;color:#27ae60;font-weight:600">新增 ('+added.length+'项)</div>';
      for(var i=0;i<added.length;i++){
        htmlB += '<div class="diff-item diff-added"><span class="badge badge-'+esc(added[i].severity||'?')+'">'+esc(added[i].severity||'?')+'</span> '+esc(trunc(added[i].finding||'',80))+'</div>';
      }
    }
    if(changed.length){
      htmlB += '<div style="padding:6px 14px;font-size:11px;color:#e67e22;font-weight:600">已变化 ('+changed.length+'项)</div>';
      for(var i=0;i<changed.length;i++){
        htmlB += '<div class="diff-item diff-changed"><span class="badge badge-'+esc(changed[i].new_severity||'?')+'">'+esc(changed[i].new_severity||'?')+'</span> '+esc(trunc(changed[i].new_finding||'',80))+'</div>';
      }
    }
    if(!added.length && !changed.length){
      htmlB += '<div class="diff-note">无新增或变化的问题</div>';
    }

    colA.innerHTML = htmlA;
    colB.innerHTML = htmlB;
  }

  /* ── Toast ── */
  function showToast(msg, type){
    var t = $id('results-toast') || (function(){
      var el = document.createElement('div');
      el.id = 'results-toast';
      el.className = 'toast';
      document.getElementById('results-app').appendChild(el);
      return el;
    })();
    t.textContent = msg;
    t.className = 'toast toast-'+(type||'success')+' show';
    setTimeout(function(){ t.classList.remove('show'); }, 2500);
  }

  /* ── 初始化 ── */
  loadStats();
  loadIssues();

})();
"""


# ══════════════════════════════════════════════════════════════
#  render_page() — 公共接口
# ══════════════════════════════════════════════════════════════

def render_page() -> str:
    """返回审查结果页完整 HTML（不含外层导航框架）。"""
    return f"""
{_RESULTS_CSS}
<div id="results-app">
  <div id="results-toast" class="toast"></div>
  {_html_filter_bar()}
  {_html_stats_cards()}
  {_html_issue_table()}
  {_html_diff_mode()}
</div>
<script>
{_RESULTS_JS}
</script>
"""


# ══════════════════════════════════════════════════════════════
#  handle_api() — 公共接口
# ══════════════════════════════════════════════════════════════

def handle_api(path: str, method: str, body: dict, qs: dict):
    """处理 /admin/api/results/* 的 API 请求。

    Args:
        path: 请求路径，如 /admin/api/results/list
        method: HTTP 方法 (GET/PUT/POST)
        body: 解析后的 JSON body，无 body 时为 {}
        qs: parse_qs 解析后的查询参数字典，如 {"severity":["A"]}

    Returns:
        (status_code, data, content_type) 如果匹配到路由
        None 如果不匹配此模块的路由
    """
    # ── 路径匹配 ──
    prefix = "/admin/api/results"
    if not path.startswith(prefix):
        return None

    # 去掉前缀
    sub = path[len(prefix):].rstrip("/")
    if not sub:
        sub = "/"

    # ── 辅助: 从 qs 提取单值 ──
    def q(name):
        vals = qs.get(name, [])
        return vals[0] if vals else ""

    # ════════════════════════════════════════════════════════
    #  GET /admin/api/results/list
    # ════════════════════════════════════════════════════════
    if method == "GET" and sub in ("/list", "/list/"):
        return _api_list(q)

    # ════════════════════════════════════════════════════════
    #  GET /admin/api/results/stats
    # ════════════════════════════════════════════════════════
    if method == "GET" and sub in ("/stats", "/stats/"):
        return _api_stats()

    # ════════════════════════════════════════════════════════
    #  GET /admin/api/results/reviews  (供对比模式获取审查列表)
    # ════════════════════════════════════════════════════════
    if method == "GET" and sub in ("/reviews", "/reviews/"):
        return _api_reviews()

    # ════════════════════════════════════════════════════════
    #  GET /admin/api/results/export
    # ════════════════════════════════════════════════════════
    if method == "GET" and sub in ("/export", "/export/"):
        return _api_export(q)

    # ════════════════════════════════════════════════════════
    #  GET /admin/api/results/diff?id1=N&id2=M
    # ════════════════════════════════════════════════════════
    if method == "GET" and sub in ("/diff", "/diff/"):
        return _api_diff(q)

    # ════════════════════════════════════════════════════════
    #  PUT /admin/api/results/batch
    # ════════════════════════════════════════════════════════
    if method == "PUT" and sub in ("/batch", "/batch/"):
        return _api_batch_status(body if body else {})

    # ════════════════════════════════════════════════════════
    #  PUT /admin/api/results/{id}/status
    #  GET /admin/api/results/{id}
    # ════════════════════════════════════════════════════════
    m_status = re.match(r"^/([^/]+)/status$", sub)
    m_detail = re.match(r"^/([^/]+)$", sub)
    if m_status and method == "PUT":
        issue_id = m_status.group(1)
        return _api_update_status(issue_id, body if body else {})
    if m_detail and method == "GET":
        issue_id = m_detail.group(1)
        return _api_issue_detail(issue_id)

    # 未匹配
    return None


# ── API 实现 ────────────────────────────────────────────

def _api_list(q):
    """GET /admin/api/results/list"""
    issues = _get_all_issues()
    sev = q("severity")
    disc = q("discipline")
    status = q("status")
    search = q("search")

    if sev and sev != "all":
        issues = [i for i in issues if i.get("severity") == sev]
    if disc and disc != "all":
        issues = [i for i in issues if i.get("discipline") == disc]
    if status and status != "all":
        issues = [i for i in issues if i.get("status") == status]
    if search:
        s = search.lower()
        issues = [
            i for i in issues
            if s in (i.get("finding") or "").lower()
            or s in (i.get("fix") or "").lower()
            or s in (i.get("standard_code") or "").lower()
            or s in (i.get("drawing_name") or "").lower()
        ]

    # 按严重度排序
    issues.sort(key=lambda x: _SEVERITY_ORDER.get(x.get("severity", "D"), 99))

    return (200, {"total": len(issues), "items": issues}, "application/json")


def _api_stats():
    """GET /admin/api/results/stats"""
    issues = _get_all_issues()
    stats = _get_stats(issues)
    return (200, stats, "application/json")


def _api_reviews():
    """GET /admin/api/results/reviews — 获取审查会话列表。"""
    reviews = []
    try:
        from v7.db import get_db
        db = get_db()
        rows = db.execute(
            "SELECT id, status, total_issues, created_at, started_at, finished_at "
            "FROM reviews ORDER BY id DESC LIMIT 50"
        ).fetchall()
        for r in rows:
            reviews.append({
                "id": r["id"],
                "status": r["status"],
                "total_issues": r["total_issues"],
                "created_at": r["created_at"] or "",
                "started_at": r["started_at"] or "",
                "finished_at": r["finished_at"] or "",
            })
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"读取审查记录失败2: {e}")
    return (200, {"reviews": reviews}, "application/json")


def _api_issue_detail(issue_id):
    """GET /admin/api/results/{id}"""
    issues = _get_all_issues()
    for item in issues:
        if str(item.get("id", "")) == issue_id or str(item.get("issue_id", "")) == issue_id:
            return (200, item, "application/json")
    return (404, {"error": "未找到该问题", "id": issue_id}, "application/json")


def _api_update_status(issue_id, body):
    """PUT /admin/api/results/{id}/status"""
    new_status = (body.get("status") or "").strip()
    note = (body.get("note") or "").strip()

    valid_statuses = {"new", "confirmed", "rejected", "fixed"}
    if new_status not in valid_statuses:
        return (400, {"error": "无效状态值，有效值: new/confirmed/rejected/fixed"}, "application/json")

    updated = False

    # 1. 更新缓存
    try:
        from v7.admin.server import _review_cache
        for item in _review_cache.get("issues", []):
            if str(item.get("id", "")) == issue_id or str(item.get("issue_id", "")) == issue_id:
                item["status"] = new_status
                if note:
                    item["note"] = note
                updated = True
                break
    except Exception as e:
        pass  # already logged above

    # 2. 更新数据库
    try:
        from v7.db import get_db
        db = get_db()
        db.execute(
            "UPDATE review_issues SET status = ? WHERE CAST(id AS TEXT) = ? OR issue_id = ?",
            (new_status, issue_id, issue_id)
        )
        db.commit()
        if db.total_changes > 0:
            updated = True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"更新数据库状态失败: {e}")

    if updated:
        return (200, {"ok": True, "status": new_status, "note": note}, "application/json")
    return (404, {"ok": False, "error": "未找到该问题"}, "application/json")


def _api_batch_status(body):
    """PUT /admin/api/results/batch"""
    ids = body.get("ids") or []
    new_status = (body.get("status") or "").strip()
    note = (body.get("note") or "").strip()

    valid_statuses = {"new", "confirmed", "rejected", "fixed"}
    if new_status not in valid_statuses:
        return (400, {"error": "无效状态值"}, "application/json")
    if not ids or not isinstance(ids, list):
        return (400, {"error": "需要提供 ids 数组"}, "application/json")

    count = 0
    # 1. 缓存
    try:
        from v7.admin.server import _review_cache
        for item in _review_cache.get("issues", []):
            iid = str(item.get("id", "")) or str(item.get("issue_id", ""))
            if iid in ids:
                item["status"] = new_status
                if note:
                    item["note"] = note
                count += 1
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"更新缓存状态失败: {e}")

    # 2. 数据库
    try:
        from v7.db import get_db
        db = get_db()
        # SQL注入防护：确保ids元素都是字符串或整数
        safe_ids = []
        for iid in ids:
            if isinstance(iid, (str, int)):
                safe_ids.append(str(iid))
            else:
                return (400, {"error": f"非法ID类型: {type(iid).__name__}"}, "application/json")
        if not safe_ids:
            return (200, {"ok": True, "updated": 0}, "application/json")
        placeholders = ",".join("?" * len(safe_ids))
        db.execute(
            f"UPDATE review_issues SET status = ? WHERE CAST(id AS TEXT) IN ({placeholders}) OR issue_id IN ({placeholders})",
            [new_status] + safe_ids + safe_ids
        )
        db.commit()
        count = max(count, db.total_changes)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"批量更新数据库状态失败: {e}")

    return (200, {"ok": True, "updated": count}, "application/json")


def _api_export(q):
    """GET /admin/api/results/export?format=csv"""
    issues = _get_all_issues()
    sev = q("severity")
    disc = q("discipline")
    status = q("status")
    search = q("search")

    if sev and sev != "all":
        issues = [i for i in issues if i.get("severity") == sev]
    if disc and disc != "all":
        issues = [i for i in issues if i.get("discipline") == disc]
    if status and status != "all":
        issues = [i for i in issues if i.get("status") == status]
    if search:
        s = search.lower()
        issues = [
            i for i in issues
            if s in (i.get("finding") or "").lower()
        ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["编号", "严重度", "专业", "规范条文", "问题描述", "整改建议",
                      "图纸来源", "位置", "合理性", "合理性分值", "状态"])
    for item in issues:
        writer.writerow([
            item.get("id", ""),
            item.get("severity", ""),
            item.get("discipline", ""),
            item.get("standard_code", ""),
            item.get("finding", ""),
            item.get("fix", ""),
            item.get("drawing_name", ""),
            item.get("location", ""),
            item.get("rationality", ""),
            item.get("rationality_score", ""),
            item.get("status", ""),
        ])

    csv_content = buf.getvalue()
    buf.close()

    return (200, csv_content, "text/csv; charset=utf-8-sig")


def _api_diff(q):
    """GET /admin/api/results/diff?id1=N&id2=M"""
    id1_str = q("id1")
    id2_str = q("id2")
    if not id1_str or not id2_str:
        return (400, {"error": "需要提供 id1 和 id2 参数"}, "application/json")

    try:
        id1 = int(id1_str)
        id2 = int(id2_str)
    except (ValueError, TypeError):
        return (400, {"error": "id1/id2 必须为整数"}, "application/json")

    issues1 = _get_issues_by_review(id1)
    issues2 = _get_issues_by_review(id2)

    # 按 issue_id 或 finding 前 60 字符建立索引
    def _key(item):
        return item.get("issue_id", "") or (item.get("finding", "")[:60])

    map1 = {}  # key -> item
    map2 = {}
    for it in issues1:
        k = _key(it)
        if k:
            map1[k] = it
    for it in issues2:
        k = _key(it)
        if k:
            map2[k] = it

    keys1 = set(map1.keys())
    keys2 = set(map2.keys())

    added_keys = keys2 - keys1
    removed_keys = keys1 - keys2
    common_keys = keys1 & keys2

    added = [map2[k] for k in added_keys]
    removed = [map1[k] for k in removed_keys]

    changed = []
    for k in common_keys:
        a = map1[k]
        b = map2[k]
        if (a.get("severity") != b.get("severity")
                or a.get("status") != b.get("status")
                or a.get("finding", "")[:200] != b.get("finding", "")[:200]):
            changed.append({
                "key": k,
                "old_severity": a.get("severity"),
                "new_severity": b.get("severity"),
                "old_status": a.get("status"),
                "new_status": b.get("status"),
                "old_finding": a.get("finding", ""),
                "new_finding": b.get("finding", ""),
                "old_fix": a.get("fix", ""),
                "new_fix": b.get("fix", ""),
            })

    return (200, {
        "id1": id1,
        "id2": id2,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "total1": len(issues1),
            "total2": len(issues2),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }, "application/json")


def _get_issues_by_review(review_id):
    """按 review_id 获取问题列表。"""
    items = []
    try:
        from v7.db import get_db
        db = get_db()
        rows = db.execute(
            "SELECT * FROM review_issues WHERE review_id = ? ORDER BY severity, id",
            (review_id,)
        ).fetchall()
        items = [_normalize_issue(r) for r in rows]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"从数据库读取审查问题失败: {e}")
    return items
