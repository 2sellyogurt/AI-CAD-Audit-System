# -*- coding: utf-8 -*-
"""图纸管理页面模块 — 图纸上传/分组/预览/发起审查

两个导出函数:
  render_page() -> str         返回完整 HTML 内容（不含外层框架，仅内容区）
  handle_api(path, method, body, qs) -> (status, data, content_type) | None
"""

import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime

# ── 内联 CSS ──────────────────────────────────────────────

_CSS = """
<style>
/* 图纸管理专用样式 */
.drawings-wrap * { box-sizing:border-box; margin:0; padding:0; }
.drawings-wrap { font:14px/1.6 -apple-system,BlinkMacSystemFont,sans-serif; color:#333; }

/* 顶部操作栏 */
.toolbar { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:18px; align-items:center; }
.toolbar .spacer { flex:1; }

/* 统计卡片 */
.stats-row { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:20px; }
.stat-card { background:#fff; border-radius:8px; padding:18px; text-align:center;
             box-shadow:0 1px 3px rgba(0,0,0,.08); border-left:4px solid #16213e; }
.stat-card .stat-num { font-size:28px; font-weight:bold; color:#16213e; }
.stat-card .stat-label { font-size:12px; color:#888; margin-top:4px; }

/* 卡片 */
.card { background:#fff; border-radius:8px; padding:20px; margin-bottom:16px;
        box-shadow:0 1px 3px rgba(0,0,0,.08); }
.card h3 { font-size:15px; margin-bottom:12px; color:#1a1a2e; }

/* 按钮 */
.btn { padding:8px 20px; border:none; border-radius:4px; font-size:14px; cursor:pointer;
       display:inline-flex; align-items:center; gap:6px; text-decoration:none; }
.btn:hover { opacity:0.88; }
.btn:disabled { opacity:0.5; cursor:not-allowed; }
.btn-primary { background:#16213e; color:#fff; }
.btn-success { background:#27ae60; color:#fff; }
.btn-danger { background:#c0392b; color:#fff; }
.btn-warning { background:#e67e22; color:#fff; }
.btn-accent { background:#e94560; color:#fff; }
.btn-sm { padding:4px 12px; font-size:12px; }
.btn-xs { padding:2px 8px; font-size:11px; }

/* 表格 */
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { padding:9px 14px; border-bottom:1px solid #eee; text-align:left; }
th { background:#f8f9fa; font-weight:600; white-space:nowrap; }
tr:hover { background:#f0f2f5; }
tr.expanded { background:#eef2ff; }

/* 状态标签 */
.status-tag { display:inline-block; padding:2px 10px; border-radius:10px; font-size:11px;
              font-weight:500; }
.status-pending { background:#fff3cd; color:#856404; }
.status-scanning { background:#cce5ff; color:#004085; }
.status-ready { background:#d4edda; color:#155724; }
.status-error { background:#f8d7da; color:#721c24; }

/* 展开区域 */
.expand-area { display:none; padding:0 0 12px 24px; }
.expand-area.open { display:table-row; }
.expand-area td { padding-top:0; }

/* 模态框 */
.modal-overlay { display:none; position:fixed; top:0; left:0; width:100%; height:100%;
                 background:rgba(0,0,0,0.45); z-index:1000; justify-content:center;
                 align-items:center; }
.modal-overlay.show { display:flex; }
.modal-box { background:#fff; border-radius:10px; padding:24px; width:90%; max-width:560px;
             max-height:85vh; overflow-y:auto; box-shadow:0 8px 30px rgba(0,0,0,.18); }
.modal-box h3 { font-size:17px; margin-bottom:16px; color:#1a1a2e; }
.modal-box .btn-row { display:flex; gap:10px; justify-content:flex-end; margin-top:18px; }

/* 表单 */
.form-group { margin-bottom:14px; }
.form-group label { display:block; font-size:13px; color:#555; margin-bottom:4px; }
.form-group input, .form-group select, .form-group textarea {
    width:100%; padding:9px 12px; border:1px solid #ddd; border-radius:4px; font-size:14px; }
.form-group textarea { font-family:Consolas,monospace; min-height:80px; resize:vertical; }

/* 拖拽上传区 */
.drop-zone { border:2px dashed #ccc; border-radius:8px; padding:36px 20px; text-align:center;
             color:#888; cursor:pointer; transition:all .2s; margin-bottom:12px; }
.drop-zone:hover, .drop-zone.dragover { border-color:#16213e; color:#16213e; background:#f0f4ff; }
.drop-zone .drop-icon { font-size:40px; margin-bottom:8px; }

/* 上传进度 */
.progress-bar-wrap { background:#eee; border-radius:6px; height:10px; margin:10px 0; overflow:hidden; }
.progress-bar-fill { background:#16213e; height:100%; border-radius:6px; transition:width .3s; width:0; }

/* 预览区 */
.preview-text { font-family:Consolas,monospace; font-size:12px; white-space:pre-wrap;
                max-height:400px; overflow:auto; background:#f5f5f5; padding:14px; border-radius:4px;
                border:1px solid #e0e0e0; }

/* 提示信息 */
.alert { padding:12px 16px; border-radius:4px; margin:12px 0; font-size:13px; }
.alert-success { background:#d4edda; color:#155724; }
.alert-error { background:#f8d7da; color:#721c24; }
.alert-info { background:#cce5ff; color:#004085; }
.alert-warning { background:#fff3cd; color:#856404; }

/* 空状态 */
.empty-state { text-align:center; padding:50px 20px; color:#888; }
.empty-state .empty-icon { font-size:48px; margin-bottom:10px; }

/* 加载 */
.loading { text-align:center; padding:30px; color:#888; }

/* 快捷标签 */
.mr-1 { margin-right:6px; }
.mt-1 { margin-top:6px; }
.mt-2 { margin-top:12px; }
.mb-2 { margin-bottom:12px; }
.text-sm { font-size:12px; }
.text-muted { color:#888; }
</style>
"""

# ── 专业名称映射 ──────────────────────────────────────────

DISCIPLINE_LABELS = {
    "building": "建筑", "structure": "结构", "hvac": "暖通",
    "plumbing": "给排水", "electrical": "电气", "fire": "消防",
    "curtain_wall": "幕墙", "decoration": "装饰", "landscape": "景观",
    "foundation_pit": "基坑", "cross": "综合", "unknown": "未分类",
}

STATUS_LABELS = {
    "pending": "待处理", "scanning": "扫描中", "ready": "就绪", "error": "异常",
}

# ── 专业分类规则 (基于文件名关键词) ───────────────────────

DISCIPLINE_KEYWORDS = [
    ("电气", "electrical"),
    ("暖通", "hvac"),
    ("空调", "hvac"),
    ("通风", "hvac"),
    ("给排水", "plumbing"),
    ("水施", "plumbing"),
    ("给水", "plumbing"),
    ("消防", "fire"),
    ("灭火", "fire"),
    ("结构", "structure"),
    ("基础", "structure"),
    ("基坑", "foundation_pit"),
    ("围护", "foundation_pit"),
    ("幕墙", "curtain_wall"),
    ("门窗", "curtain_wall"),
    ("装饰", "decoration"),
    ("装修", "decoration"),
    ("景观", "landscape"),
    ("绿化", "landscape"),
    ("海绵", "landscape"),
    ("建筑总说明", "building"),
    ("总说明", "building"),
    ("建筑", "building"),
    ("立面", "building"),
    ("剖面", "building"),
    ("平面", "building"),
    ("装配式", "building"),
    ("BA", "electrical"),
    ("变配电", "electrical"),
    ("标识", "decoration"),
]


def _classify_discipline(filename: str) -> str:
    """根据文件名关键词分类专业。"""
    name_lower = filename.lower()
    for keyword, disc in DISCIPLINE_KEYWORDS:
        if keyword.lower() in name_lower:
            return disc
    return "unknown"


# ── HTML 渲染 ──────────────────────────────────────────────

def render_page() -> str:
    """返回图纸管理页面的完整 HTML 内容（不含外层框架）。"""
    return f"""<div class="drawings-wrap">
{_CSS}

<!-- 顶部操作栏 -->
<div class="toolbar">
  <button class="btn btn-primary" onclick="openNewProjectModal()">
    <span>+</span> 新建项目
  </button>
  <button class="btn btn-success" onclick="openUploadModal()" id="btn-upload" disabled>
    <span>&#8593;</span> 上传图纸
  </button>
  <button class="btn btn-accent" onclick="startReviewFromPage()" id="btn-review" disabled>
    <span>&#9654;</span> 启动审查
  </button>
  <span class="spacer"></span>
  <span class="text-sm text-muted" id="status-text">就绪</span>
</div>

<!-- 统计卡片 -->
<div class="stats-row">
  <div class="stat-card">
    <div class="stat-num" id="stat-projects">0</div>
    <div class="stat-label">项目总数</div>
  </div>
  <div class="stat-card" style="border-left-color:#27ae60;">
    <div class="stat-num" id="stat-drawings">0</div>
    <div class="stat-label">图纸总数</div>
  </div>
  <div class="stat-card" style="border-left-color:#e67e22;">
    <div class="stat-num" id="stat-pending">0</div>
    <div class="stat-label">待处理图纸</div>
  </div>
  <div class="stat-card" style="border-left-color:#e94560;">
    <div class="stat-num" id="stat-ready">0</div>
    <div class="stat-label">就绪图纸</div>
  </div>
</div>

<!-- 项目列表 -->
<div class="card">
  <h3>项目列表</h3>
  <div id="project-table-container">
    <div class="loading">加载中...</div>
  </div>
</div>

<!-- ====== 模态框：新建项目 ====== -->
<div class="modal-overlay" id="modal-project">
  <div class="modal-box">
    <h3>新建项目</h3>
    <div class="form-group">
      <label>项目名称 *</label>
      <input type="text" id="proj-name" placeholder="如：XX大学教学楼" maxlength="200">
    </div>
    <div class="form-group">
      <label>DXF 图纸目录</label>
      <input type="text" id="proj-dxf-dir" placeholder="如：C:\\projects\\drawings (可选)">
    </div>
    <div class="form-group">
      <label>输出目录</label>
      <input type="text" id="proj-output-dir" placeholder="留空使用默认目录">
    </div>
    <div class="form-group">
      <label>项目描述</label>
      <textarea id="proj-desc" placeholder="项目简要描述（可选）"></textarea>
    </div>
    <div class="btn-row">
      <button class="btn" onclick="closeModal('modal-project')">取消</button>
      <button class="btn btn-primary" onclick="createProject()">创建项目</button>
    </div>
    <div id="proj-msg"></div>
  </div>
</div>

<!-- ====== 模态框：上传图纸 ====== -->
<div class="modal-overlay" id="modal-upload">
  <div class="modal-box">
    <h3>上传图纸</h3>
    <div class="form-group">
      <label>目标项目 *</label>
      <select id="upload-project-id"></select>
    </div>
    <div class="form-group">
      <label>图纸文件路径</label>
      <input type="text" id="upload-file-path" placeholder="输入 DXF 文件完整路径，如 C:\\drawings\\建筑平面图.dxf">
    </div>
    <div class="drop-zone" id="drop-zone" onclick="document.getElementById('upload-file-path').focus()">
      <div class="drop-icon">&#128196;</div>
      <div>点击此处并输入文件路径，或直接粘贴路径到输入框</div>
      <div class="text-sm text-muted mt-1">支持 .dxf 格式的图纸文件</div>
    </div>
    <div id="upload-progress-area" style="display:none;">
      <div style="font-size:13px;margin-bottom:4px;" id="upload-progress-text">正在上传...</div>
      <div class="progress-bar-wrap"><div class="progress-bar-fill" id="upload-progress-bar"></div></div>
    </div>
    <div class="btn-row">
      <button class="btn" onclick="closeModal('modal-upload')">取消</button>
      <button class="btn btn-success" onclick="uploadDrawing()">上传</button>
    </div>
    <div id="upload-msg"></div>
  </div>
</div>

<!-- ====== 模态框：图纸预览 ====== -->
<div class="modal-overlay" id="modal-preview">
  <div class="modal-box" style="max-width:800px;">
    <h3>图纸预览 <span id="preview-filename" class="text-sm text-muted"></span></h3>
    <div class="form-group">
      <label>文件信息</label>
      <div id="preview-info" class="text-sm"></div>
    </div>
    <div class="form-group">
      <label>文本内容</label>
      <div class="preview-text" id="preview-content">加载中...</div>
    </div>
    <div class="btn-row">
      <button class="btn" onclick="closeModal('modal-preview')">关闭</button>
    </div>
  </div>
</div>

<!-- ====== 模态框：确认删除 ====== -->
<div class="modal-overlay" id="modal-confirm">
  <div class="modal-box" style="max-width:400px;">
    <h3>确认删除</h3>
    <p id="confirm-msg" style="margin-bottom:16px;"></p>
    <div class="btn-row">
      <button class="btn" onclick="closeModal('modal-confirm')">取消</button>
      <button class="btn btn-danger" id="confirm-btn" onclick="">确认删除</button>
    </div>
  </div>
</div>

<script>
// ── 全局状态 ──
let _projects = [];
let _drawingsCache = {{}};
let _selectedProjectId = null;

// ── 页面初始化 ──
document.addEventListener('DOMContentLoaded', function() {{
  loadProjects();
}});

// ── 加载项目列表 ──
async function loadProjects() {{
  document.getElementById('status-text').innerText = '加载中...';
  try {{
    const res = await fetch('/admin/api/drawings/projects');
    const data = await res.json();
    _projects = data.projects || [];
    updateStats();
    renderProjectTable();
    populateUploadProjectSelect();
    updateButtons();
    document.getElementById('status-text').innerText = '就绪';
  }} catch (e) {{
    document.getElementById('project-table-container').innerHTML =
      '<div class="alert alert-error">加载项目列表失败: ' + e.message + '</div>';
    document.getElementById('status-text').innerText = '加载失败';
  }}
}}

// ── 更新统计 ──
function updateStats() {{
  document.getElementById('stat-projects').innerText = _projects.length;
  let totalDrawings = 0, totalPending = 0, totalReady = 0;
  _projects.forEach(function(p) {{
    totalDrawings += (p.drawing_count || 0);
    totalPending += (p.pending_count || 0);
    totalReady += (p.ready_count || 0);
  }});
  document.getElementById('stat-drawings').innerText = totalDrawings;
  document.getElementById('stat-pending').innerText = totalPending;
  document.getElementById('stat-ready').innerText = totalReady;
}}

// ── 更新按钮状态 ──
function updateButtons() {{
  document.getElementById('btn-upload').disabled = _projects.length === 0;
  document.getElementById('btn-review').disabled = _projects.length === 0;
}}

// ── 渲染项目表格 ──
function renderProjectTable() {{
  var container = document.getElementById('project-table-container');
  if (_projects.length === 0) {{
    container.innerHTML = '<div class="empty-state"><div class="empty-icon">&#128451;</div>' +
      '<div>暂无项目，请先创建新项目</div></div>';
    return;
  }}
  var html = '<table><thead><tr>' +
    '<th style="width:32px;"></th>' +
    '<th>项目名称</th>' +
    '<th>图纸数</th>' +
    '<th>上次审查</th>' +
    '<th>描述</th>' +
    '<th style="width:160px;">操作</th>' +
    '</tr></thead><tbody>';
  _projects.forEach(function(p, idx) {{
    var lastReview = p.last_review || '未审查';
    var desc = (p.description || '').substring(0, 40);
    if (p.description && p.description.length > 40) desc += '...';
    html += '<tr id="proj-row-' + p.id + '">' +
      '<td><span id="expand-icon-' + p.id +
      '" style="cursor:pointer;user-select:none;" onclick="toggleProject(' + p.id + ')">&#9654;</span></td>' +
      '<td><strong>' + escapeHtml(p.name) + '</strong></td>' +
      '<td>' + (p.drawing_count || 0) + '</td>' +
      '<td class="text-sm text-muted">' + escapeHtml(lastReview) + '</td>' +
      '<td class="text-sm text-muted">' + escapeHtml(desc) + '</td>' +
      '<td>' +
        '<button class="btn btn-sm btn-primary mr-1" onclick="toggleProject(' + p.id + ')">查看</button>' +
        '<button class="btn btn-sm btn-danger" onclick="confirmDeleteProject(' + p.id + ',\\'' +
          escapeJs(p.name) + '\\')">删除</button>' +
      '</td>' +
      '</tr>' +
      '<tr class="expand-area" id="expand-' + p.id + '">' +
        '<td></td>' +
        '<td colspan="5"><div id="drawings-' + p.id +
        '" class="text-sm text-muted">点击展开加载图纸列表...</div></td>' +
      '</tr>';
  }});
  html += '</tbody></table>';
  container.innerHTML = html;
}}

// ── 展开/收起项目 ──
async function toggleProject(projectId) {{
  var expandRow = document.getElementById('expand-' + projectId);
  var icon = document.getElementById('expand-icon-' + projectId);
  if (!expandRow || !icon) return;

  if (expandRow.classList.contains('open')) {{
    expandRow.classList.remove('open');
    icon.innerHTML = '&#9654;';
    return;
  }}

  // 收起所有其他展开
  document.querySelectorAll('.expand-area.open').forEach(function(el) {{
    el.classList.remove('open');
  }});
  document.querySelectorAll('[id^="expand-icon-"]').forEach(function(el) {{
    el.innerHTML = '&#9654;';
  }});

  expandRow.classList.add('open');
  icon.innerHTML = '&#9660;';
  _selectedProjectId = projectId;

  var container = document.getElementById('drawings-' + projectId);
  container.innerHTML = '<div class="loading">加载图纸列表...</div>';

  try {{
    var res = await fetch('/admin/api/drawings/list?project_id=' + projectId);
    var data = await res.json();
    var drawings = data.drawings || [];
    _drawingsCache[projectId] = drawings;

    if (drawings.length === 0) {{
      container.innerHTML = '<div class="empty-state" style="padding:20px;">暂无图纸，请上传图纸文件</div>';
      return;
    }}

    var html = '<table style="margin-top:4px;"><thead><tr>' +
      '<th>文件名</th>' +
      '<th>专业</th>' +
      '<th>大小(KB)</th>' +
      '<th>状态</th>' +
      '<th>上传时间</th>' +
      '<th style="width:140px;">操作</th>' +
      '</tr></thead><tbody>';
    drawings.forEach(function(d) {{
      var discLabel = d.discipline_label || '未分类';
      var statusLabel = d.status_label || '待处理';
      var statusCls = 'status-' + (d.status || 'pending');
      html += '<tr>' +
        '<td>' + escapeHtml(d.filename) + '</td>' +
        '<td>' + escapeHtml(discLabel) + '</td>' +
        '<td>' + (d.file_size_kb || 0) + '</td>' +
        '<td><span class="status-tag ' + statusCls + '">' + escapeHtml(statusLabel) + '</span></td>' +
        '<td class="text-sm text-muted">' + escapeHtml(d.uploaded_at || '') + '</td>' +
        '<td>' +
          '<button class="btn btn-xs btn-primary mr-1" onclick="previewDrawing(' + d.id + ')">预览</button>' +
          '<button class="btn btn-xs btn-danger" onclick="confirmDeleteDrawing(' + d.id + ',\\'' +
            escapeJs(d.filename) + '\\', ' + projectId + ')">删除</button>' +
        '</td>' +
        '</tr>';
    }});
    html += '</tbody></table>';
    html += '<div class="mt-1"><button class="btn btn-xs btn-warning" onclick="scanProjectDrawings(' + projectId + ')">' +
      '&#128269; 扫描分类图纸专业</button></div>';
    container.innerHTML = html;
  }} catch (e) {{
    container.innerHTML = '<div class="alert alert-error">加载失败: ' + e.message + '</div>';
  }}
}}

// ── 模态框操作 ──
function openModal(id) {{
  document.getElementById(id).classList.add('show');
}}
function closeModal(id) {{
  document.getElementById(id).classList.remove('show');
}}

// ── 新建项目 ──
function openNewProjectModal() {{
  document.getElementById('proj-name').value = '';
  document.getElementById('proj-dxf-dir').value = '';
  document.getElementById('proj-output-dir').value = '';
  document.getElementById('proj-desc').value = '';
  document.getElementById('proj-msg').innerHTML = '';
  openModal('modal-project');
  document.getElementById('proj-name').focus();
}}

async function createProject() {{
  var name = document.getElementById('proj-name').value.trim();
  if (!name) {{
    document.getElementById('proj-msg').innerHTML =
      '<div class="alert alert-error">请输入项目名称</div>';
    return;
  }}
  try {{
    var res = await fetch('/admin/api/drawings/projects', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        name: name,
        dxf_dir: document.getElementById('proj-dxf-dir').value.trim(),
        output_dir: document.getElementById('proj-output-dir').value.trim(),
        description: document.getElementById('proj-desc').value.trim()
      }})
    }});
    var data = await res.json();
    if (res.ok && data.ok) {{
      closeModal('modal-project');
      await loadProjects();
    }} else {{
      document.getElementById('proj-msg').innerHTML =
        '<div class="alert alert-error">' + escapeHtml(data.error || '创建失败') + '</div>';
    }}
  }} catch (e) {{
    document.getElementById('proj-msg').innerHTML =
      '<div class="alert alert-error">请求失败: ' + e.message + '</div>';
  }}
}}

// ── 上传图纸 ──
function openUploadModal() {{
  if (_projects.length === 0) {{
    alert('请先创建项目');
    return;
  }}
  document.getElementById('upload-file-path').value = '';
  document.getElementById('upload-msg').innerHTML = '';
  document.getElementById('upload-progress-area').style.display = 'none';
  populateUploadProjectSelect();
  openModal('modal-upload');
}}

function populateUploadProjectSelect() {{
  var sel = document.getElementById('upload-project-id');
  sel.innerHTML = '';
  _projects.forEach(function(p) {{
    var opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name;
    sel.appendChild(opt);
  }});
}}

async function uploadDrawing() {{
  var projectId = parseInt(document.getElementById('upload-project-id').value);
  var filePath = document.getElementById('upload-file-path').value.trim();
  if (!filePath) {{
    document.getElementById('upload-msg').innerHTML =
      '<div class="alert alert-error">请输入图纸文件路径</div>';
    return;
  }}
  if (!projectId) {{
    document.getElementById('upload-msg').innerHTML =
      '<div class="alert alert-error">请选择目标项目</div>';
    return;
  }}

  document.getElementById('upload-msg').innerHTML = '';
  var progressArea = document.getElementById('upload-progress-area');
  var progressBar = document.getElementById('upload-progress-bar');
  var progressText = document.getElementById('upload-progress-text');
  progressArea.style.display = 'block';
  progressBar.style.width = '10%';
  progressText.innerText = '正在上传...';

  try {{
    var res = await fetch('/admin/api/drawings/upload', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ project_id: projectId, file_path: filePath }})
    }});
    progressBar.style.width = '80%';
    progressText.innerText = '处理中...';
    var data = await res.json();
    progressBar.style.width = '100%';
    progressText.innerText = '完成';
    if (res.ok && data.ok) {{
      setTimeout(function() {{
        closeModal('modal-upload');
        loadProjects();
        if (_selectedProjectId) {{
          toggleProject(_selectedProjectId);
        }}
      }}, 400);
    }} else {{
      document.getElementById('upload-msg').innerHTML =
        '<div class="alert alert-error">' + escapeHtml(data.error || '上传失败') + '</div>';
      progressArea.style.display = 'none';
    }}
  }} catch (e) {{
    document.getElementById('upload-msg').innerHTML =
      '<div class="alert alert-error">请求失败: ' + e.message + '</div>';
    progressArea.style.display = 'none';
  }}
}}

// ── 预览图纸 ──
async function previewDrawing(drawingId) {{
  openModal('modal-preview');
  document.getElementById('preview-filename').innerText = '';
  document.getElementById('preview-info').innerHTML = '加载中...';
  document.getElementById('preview-content').innerText = '加载中...';
  try {{
    var res = await fetch('/admin/api/drawings/' + drawingId);
    var data = await res.json();
    if (!res.ok || data.error) {{
      document.getElementById('preview-content').innerText = '加载失败: ' + (data.error || '未知错误');
      return;
    }}
    document.getElementById('preview-filename').innerText = data.filename || '';
    document.getElementById('preview-info').innerHTML =
      '<strong>专业:</strong> ' + escapeHtml(data.discipline_label || '未分类') +
      ' &nbsp;|&nbsp; <strong>大小:</strong> ' + (data.file_size_kb || 0) + ' KB' +
      ' &nbsp;|&nbsp; <strong>文本实体:</strong> ' + (data.text_entities || 0) +
      ' &nbsp;|&nbsp; <strong>状态:</strong> ' + escapeHtml(data.status_label || '');
    document.getElementById('preview-content').innerText = data.text_content || '(无文本内容)';
  }} catch (e) {{
    document.getElementById('preview-content').innerText = '请求失败: ' + e.message;
  }}
}}

// ── 删除确认 ──
function confirmDeleteProject(id, name) {{
  document.getElementById('confirm-msg').innerText = '确定要删除项目 "' + name + '" 吗？该项目下的所有图纸也将被删除，此操作不可撤销。';
  document.getElementById('confirm-btn').onclick = function() {{ deleteProject(id); }};
  openModal('modal-confirm');
}}

function confirmDeleteDrawing(id, filename, projectId) {{
  document.getElementById('confirm-msg').innerText = '确定要删除图纸 "' + filename + '" 吗？此操作不可撤销。';
  document.getElementById('confirm-btn').onclick = function() {{ deleteDrawing(id, projectId); }};
  openModal('modal-confirm');
}}

async function deleteProject(id) {{
  try {{
    var res = await fetch('/admin/api/drawings/projects/' + id, {{ method: 'DELETE' }});
    var data = await res.json();
    closeModal('modal-confirm');
    if (res.ok && data.ok) {{
      await loadProjects();
    }} else {{
      alert('删除失败: ' + (data.error || '未知错误'));
    }}
  }} catch (e) {{
    closeModal('modal-confirm');
    alert('请求失败: ' + e.message);
  }}
}}

async function deleteDrawing(id, projectId) {{
  try {{
    var res = await fetch('/admin/api/drawings/' + id, {{ method: 'DELETE' }});
    var data = await res.json();
    closeModal('modal-confirm');
    if (res.ok && data.ok) {{
      await loadProjects();
      if (projectId === _selectedProjectId) {{
        await toggleProject(projectId);
      }}
    }} else {{
      alert('删除失败: ' + (data.error || '未知错误'));
    }}
  }} catch (e) {{
    closeModal('modal-confirm');
    alert('请求失败: ' + e.message);
  }}
}}

// ── 扫描分类 ──
async function scanProjectDrawings(projectId) {{
  var container = document.getElementById('drawings-' + projectId);
  container.innerHTML = '<div class="loading">正在扫描并分类图纸专业...</div>';
  try {{
    var res = await fetch('/admin/api/drawings/scan', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ project_id: projectId }})
    }});
    var data = await res.json();
    await toggleProject(projectId);
  }} catch (e) {{
    container.innerHTML = '<div class="alert alert-error">扫描失败: ' + e.message + '</div>';
  }}
}}

// ── 启动审查 ──
async function startReviewFromPage() {{
  if (_projects.length === 0) {{
    alert('请先创建项目并上传图纸');
    return;
  }}
  try {{
    var res = await fetch('/admin/api/review/start', {{ method: 'POST' }});
    var data = await res.json();
    if (res.ok) {{
      document.getElementById('status-text').innerText = '审查已启动 (Task: ' + (data.taskId || '') + ')';
      alert('审查已启动！可在"审查结果"页面查看进度。');
    }} else {{
      alert('启动失败: ' + (data.error || ''));
    }}
  }} catch (e) {{
    alert('请求失败: ' + e.message);
  }}
}}

// ── 工具函数 ──
function escapeHtml(str) {{
  if (!str) return '';
  var div = document.createElement('div');
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}}

function escapeJs(str) {{
  if (!str) return '';
  return str.replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'").replace(/"/g, '\\\\"');
}}

// ── 点击模态框外部关闭 ──
document.addEventListener('click', function(e) {{
  if (e.target.classList.contains('modal-overlay')) {{
    e.target.classList.remove('show');
  }}
}});

// ── ESC 关闭模态框 ──
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') {{
    document.querySelectorAll('.modal-overlay.show').forEach(function(m) {{
      m.classList.remove('show');
    }});
  }}
}});
</script>
</div>"""


# ── API 处理 ──────────────────────────────────────────────

def _json_response(status, data):
    return (status, data, "application/json")


def _error(status, message):
    return _json_response(status, {"ok": False, "error": message})


def handle_api(path, method, body, qs):
    """处理图纸管理 API 请求。

    Args:
        path: 请求路径，如 /admin/api/drawings/projects
        method: HTTP 方法 (GET/POST/DELETE)
        body: 已解析的 JSON body (dict)，GET 请求时为 {}
        qs: query string 参数字典 parse_qs 结果，如 {"project_id": ["1"]}

    Returns:
        (status, data, content_type) 或 None（路径不匹配时）
    """
    prefix = "/admin/api/drawings"
    if not path.startswith(prefix):
        return None

    # 去掉前缀后的路径部分
    sub = path[len(prefix):].rstrip("/") or "/"

    try:
        # ── GET /projects ──
        if method == "GET" and sub == "/projects":
            return _handle_get_projects()

        # ── POST /projects ──
        if method == "POST" and sub == "/projects":
            return _handle_create_project(body)

        # ── DELETE /projects/{id} ──
        if method == "DELETE" and sub.startswith("/projects/"):
            pid = _extract_int(sub, "/projects/")
            return _handle_delete_project(pid)

        # ── GET /list?project_id=N ──
        if method == "GET" and sub == "/list":
            pid_str = (qs.get("project_id", [None]) or [None])[0]
            if pid_str is None:
                return _error(400, "缺少 project_id 参数")
            return _handle_get_drawings(int(pid_str))

        # ── POST /upload ──
        if method == "POST" and sub == "/upload":
            return _handle_upload_drawing(body)

        # ── POST /scan ──
        if method == "POST" and sub == "/scan":
            return _handle_scan_drawings(body)

        # ── GET /{id} (图纸详情/预览) ──
        if method == "GET":
            did = _try_extract_int(sub, "/")
            if did is not None:
                return _handle_get_drawing_detail(did)

        # ── DELETE /{id} ──
        if method == "DELETE":
            did = _try_extract_int(sub, "/")
            if did is not None:
                return _handle_delete_drawing(did)

    except ValueError as e:
        return _error(400, str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _error(500, f"服务器内部错误: {str(e)}")

    return _error(404, "未知的 API 端点")


def _extract_int(sub_path, prefix):
    """从子路径中提取整数 ID。"""
    raw = sub_path[len(prefix):].strip("/")
    if not raw:
        raise ValueError("缺少 ID 参数")
    return int(raw)


def _try_extract_int(sub_path, prefix):
    """从子路径中安全提取整数 ID，失败返回 None。"""
    raw = sub_path[len(prefix):].strip("/")
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


# ── GET /projects ─────────────────────────────────────────

def _handle_get_projects():
    from v7.db import get_db
    db = get_db()
    rows = db.execute(
        "SELECT id, name, dxf_dir, output_dir, description, created_at FROM projects ORDER BY id DESC"
    ).fetchall()

    projects = []
    for r in rows:
        pid = r["id"]
        dcount = db.execute(
            "SELECT COUNT(*) FROM drawings WHERE project_id=?", (pid,)
        ).fetchone()[0]
        pending = db.execute(
            "SELECT COUNT(*) FROM drawings WHERE project_id=? AND status='pending'", (pid,)
        ).fetchone()[0]
        ready_cnt = db.execute(
            "SELECT COUNT(*) FROM drawings WHERE project_id=? AND status='ready'", (pid,)
        ).fetchone()[0]

        # 最近一次审查时间
        last_rev = db.execute(
            "SELECT MAX(finished_at) FROM reviews WHERE project_id=?", (pid,)
        ).fetchone()[0]
        last_review = ""
        if last_rev:
            try:
                dt = datetime.strptime(last_rev, "%Y-%m-%d %H:%M:%S")
                last_review = dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                last_review = last_rev[:16]

        projects.append({
            "id": pid,
            "name": r["name"],
            "dxf_dir": r["dxf_dir"] or "",
            "output_dir": r["output_dir"] or "",
            "description": r["description"] or "",
            "created_at": r["created_at"] or "",
            "drawing_count": dcount,
            "pending_count": pending,
            "ready_count": ready_cnt,
            "last_review": last_review,
        })

    return _json_response(200, {"ok": True, "projects": projects})


# ── POST /projects ────────────────────────────────────────

def _handle_create_project(body):
    name = (body or {}).get("name", "").strip()
    if not name:
        return _error(400, "项目名称不能为空")
    if len(name) > 200:
        return _error(400, "项目名称不能超过200个字符")

    dxf_dir = (body or {}).get("dxf_dir", "").strip()
    output_dir = (body or {}).get("output_dir", "").strip()
    description = (body or {}).get("description", "").strip()

    from v7.db import get_db
    db = get_db()
    cursor = db.execute(
        "INSERT INTO projects (name, dxf_dir, output_dir, description) VALUES (?, ?, ?, ?)",
        (name, dxf_dir, output_dir, description),
    )
    db.commit()
    return _json_response(201, {"ok": True, "id": cursor.lastrowid, "name": name})


# ── DELETE /projects/{id} ─────────────────────────────────

def _handle_delete_project(pid):
    from v7.db import get_db
    db = get_db()

    proj = db.execute("SELECT id, dxf_dir FROM projects WHERE id=?", (pid,)).fetchone()
    if not proj:
        return _error(404, "项目不存在")

    # 级联删除图纸记录（数据库有 ON DELETE CASCADE，但显式处理更安全）
    db.execute("DELETE FROM drawings WHERE project_id=?", (pid,))
    db.execute("DELETE FROM projects WHERE id=?", (pid,))
    db.commit()
    return _json_response(200, {"ok": True})


# ── GET /list?project_id=N ────────────────────────────────

def _handle_get_drawings(pid):
    from v7.db import get_db
    db = get_db()

    proj = db.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone()
    if not proj:
        return _error(404, "项目不存在")

    rows = db.execute(
        "SELECT id, project_id, filename, file_path, discipline, file_size_kb, "
        "text_entities, status, uploaded_at FROM drawings WHERE project_id=? "
        "ORDER BY id DESC",
        (pid,),
    ).fetchall()

    drawings = []
    for r in rows:
        drawings.append({
            "id": r["id"],
            "project_id": r["project_id"],
            "filename": r["filename"],
            "file_path": r["file_path"],
            "discipline": r["discipline"],
            "discipline_label": DISCIPLINE_LABELS.get(r["discipline"], r["discipline"]),
            "file_size_kb": r["file_size_kb"] or 0,
            "text_entities": r["text_entities"] or 0,
            "status": r["status"],
            "status_label": STATUS_LABELS.get(r["status"], r["status"]),
            "uploaded_at": r["uploaded_at"] or "",
        })

    return _json_response(200, {"ok": True, "drawings": drawings, "project_id": pid})


# ── GET /{id} 图纸详情 ────────────────────────────────────

def _handle_get_drawing_detail(did):
    from v7.db import get_db
    db = get_db()

    row = db.execute(
        "SELECT id, project_id, filename, file_path, discipline, text_content, "
        "file_size_kb, text_entities, status, uploaded_at "
        "FROM drawings WHERE id=?",
        (did,),
    ).fetchone()

    if not row:
        return _error(404, "图纸不存在")

    return _json_response(200, {
        "id": row["id"],
        "project_id": row["project_id"],
        "filename": row["filename"],
        "file_path": row["file_path"],
        "discipline": row["discipline"],
        "discipline_label": DISCIPLINE_LABELS.get(row["discipline"], row["discipline"]),
        "text_content": row["text_content"] or "",
        "file_size_kb": row["file_size_kb"] or 0,
        "text_entities": row["text_entities"] or 0,
        "status": row["status"],
        "status_label": STATUS_LABELS.get(row["status"], row["status"]),
        "uploaded_at": row["uploaded_at"] or "",
    })


# ── POST /upload ──────────────────────────────────────────

def _handle_upload_drawing(body):
    project_id = (body or {}).get("project_id")
    file_path = (body or {}).get("file_path", "").strip()

    if not project_id:
        return _error(400, "缺少 project_id")
    if not file_path:
        return _error(400, "缺少 file_path")

    from v7.db import get_db
    db = get_db()

    proj = db.execute("SELECT id, name, dxf_dir FROM projects WHERE id=?", (project_id,)).fetchone()
    if not proj:
        return _error(404, "项目不存在")

    # 检查源文件是否存在
    if not os.path.isfile(file_path):
        return _error(400, f"文件不存在: {file_path}")

    filename = os.path.basename(file_path)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".dxf", ".dwg"):
        return _error(400, f"不支持的文件格式 ({ext})，仅支持 .dxf 和 .dwg")

    file_size_kb = int(os.path.getsize(file_path) / 1024)

    # 确定目标存储目录
    review_dir = os.environ.get("DXF_REVIEW_DIR", "")
    if review_dir and os.path.isdir(review_dir):
        # 使用项目名创建子目录
        dest_dir = os.path.join(review_dir, proj["name"].replace(" ", "_"))
    elif proj["dxf_dir"] and os.path.isdir(proj["dxf_dir"]):
        dest_dir = proj["dxf_dir"]
    else:
        # 默认存储到 v7/output_v7.0/dxf/{project_name}
        from v7.db import schema
        v7_parent = os.path.dirname(os.path.abspath(schema.__file__))
        root = os.path.dirname(v7_parent)
        dest_dir = os.path.join(root, "output_v7.0", "dxf", proj["name"].replace(" ", "_"))

    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)

    # 如果同名文件已存在，添加序号
    counter = 1
    base, ext_part = os.path.splitext(filename)
    while os.path.exists(dest_path):
        dest_path = os.path.join(dest_dir, f"{base}_{counter}{ext_part}")
        counter += 1

    # 复制文件
    try:
        shutil.copy2(file_path, dest_path)
    except PermissionError:
        return _error(403, "文件权限不足，无法复制")
    except OSError as e:
        return _error(500, f"文件复制失败: {str(e)}")

    # 尝试提取文本内容（如果文件是 DXF 格式）
    text_content = ""
    text_entities = 0
    if ext == ".dxf":
        try:
            text_content, text_entities = _extract_dxf_text(dest_path)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"提取DXF文本失败: {dest_path}, {e}")

    # 基于文件名初步分类专业
    discipline = _classify_discipline(filename)

    # 写入数据库
    cursor = db.execute(
        "INSERT INTO drawings (project_id, filename, file_path, discipline, "
        "text_content, file_size_kb, text_entities, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (project_id, filename, dest_path, discipline, text_content, file_size_kb, text_entities),
    )
    db.commit()

    return _json_response(201, {
        "ok": True,
        "id": cursor.lastrowid,
        "filename": filename,
        "dest_path": dest_path,
        "file_size_kb": file_size_kb,
        "discipline": discipline,
        "discipline_label": DISCIPLINE_LABELS.get(discipline, discipline),
    })


# ── POST /scan ────────────────────────────────────────────

def _handle_scan_drawings(body):
    project_id = (body or {}).get("project_id")
    if not project_id:
        return _error(400, "缺少 project_id")

    from v7.db import get_db
    db = get_db()

    proj = db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
    if not proj:
        return _error(404, "项目不存在")

    rows = db.execute(
        "SELECT id, filename, file_path FROM drawings WHERE project_id=?",
        (project_id,),
    ).fetchall()

    updated = 0
    for r in rows:
        # 基于文件名重新分类
        discipline = _classify_discipline(r["filename"])

        # 如果有文本内容且分类为 unknown，尝试更深入的扫描
        if discipline == "unknown" and r["file_path"]:
            try:
                text_content, _ = _extract_dxf_text(r["file_path"])
                if text_content:
                    discipline = _classify_by_text_content(text_content, r["filename"])
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"文本内容分类失败: {r.get('filename')}, {e}")

        db.execute(
            "UPDATE drawings SET discipline=?, status='ready' WHERE id=?",
            (discipline, r["id"]),
        )
        updated += 1

    db.commit()
    return _json_response(200, {"ok": True, "scanned": updated})


def _classify_by_text_content(text, filename):
    """基于文本内容辅助分类（与文件名分类互补）。"""
    text_lower = text.lower() if text else ""
    name_lower = filename.lower() if filename else ""

    # 电气特征
    if any(kw in text_lower for kw in ["配电", "照明", "插座", "弱电", "火灾自动报警", "防雷"]):
        return "electrical"
    # 暖通特征
    if any(kw in text_lower for kw in ["空调", "通风", "排烟", "防烟", "供暖", "冷热源"]):
        return "hvac"
    # 给排水特征
    if any(kw in text_lower for kw in ["给水", "排水", "消防栓", "喷淋", "污水", "雨水"]):
        return "plumbing"
    # 消防特征
    if any(kw in text_lower for kw in ["防火分区", "疏散", "消防电梯", "防火门"]):
        return "fire"
    # 结构特征
    if any(kw in text_lower for kw in ["配筋", "混凝土", "钢筋", "梁柱", "基础", "抗震"]):
        return "structure"
    # 回退到文件名分类
    return _classify_discipline(filename)


# ── DELETE /{id} 删除图纸 ─────────────────────────────────

def _handle_delete_drawing(did):
    from v7.db import get_db
    db = get_db()

    row = db.execute("SELECT id, file_path FROM drawings WHERE id=?", (did,)).fetchone()
    if not row:
        return _error(404, "图纸不存在")

    db.execute("DELETE FROM drawings WHERE id=?", (did,))
    db.commit()

    # 尝试删除物理文件（不强制，失败不影响数据库删除）
    if row["file_path"] and os.path.isfile(row["file_path"]):
        try:
            os.remove(row["file_path"])
        except OSError:
            pass

    return _json_response(200, {"ok": True})


# ── DXF 文本提取辅助函数 ──────────────────────────────────

def _extract_dxf_text(filepath):
    """从 DXF 文件中提取 TEXT 和 MTEXT 实体内容。

    Returns:
        (text_content: str, entity_count: int)
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"UTF-8读文件失败，尝试GBK: {filepath}, {e}")
        try:
            with open(filepath, "r", encoding="gbk", errors="ignore") as f:
                content = f.read()
        except Exception as e2:
            import logging
            logging.getLogger(__name__).warning(f"文件读取失败: {filepath}, {e2}")
            return "", 0

    lines = content.split("\n")
    texts = []
    i = 0
    n = len(lines)
    in_text = False
    in_mtext = False
    mtext_parts = []
    current_text = ""

    while i < n:
        line = lines[i].strip()
        if line == "TEXT":
            in_text = True
            current_text = ""
            i += 1
            continue
        if line == "MTEXT":
            in_mtext = True
            mtext_parts = []
            i += 1
            continue

        if in_text:
            if line == "1" and i + 1 < n:
                current_text = lines[i + 1].strip()
                if current_text:
                    texts.append(current_text)
                in_text = False
            elif line == "0" and i + 1 < n and lines[i + 1].strip() != "1":
                in_text = False

        if in_mtext:
            if line == "1" and i + 1 < n:
                part = lines[i + 1].strip()
                if part:
                    mtext_parts.append(part)
                i += 1
            elif line == "0":
                if mtext_parts:
                    texts.append(" ".join(mtext_parts))
                in_mtext = False
                mtext_parts = []

        i += 1

    # 收集剩余
    if in_mtext and mtext_parts:
        texts.append(" ".join(mtext_parts))

    combined = "\n".join(texts)
    return combined, len(texts)
