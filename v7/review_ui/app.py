# -*- coding: utf-8 -*-
"""
人工复核Web界面

Flask单文件应用，提供：
  /                         问题列表（按严重度/专业/状态筛选）
  /review/<issue_id>        逐条审核（溯源链+CAD定位+截图）
  /api/confirm              确认问题
  /api/reject               驳回误报
  /api/modify               修改描述/严重度
  /api/add                  人工补充问题
  /report                   最终报告预览+导出

启动: python app.py --port 8080
"""

from __future__ import annotations

import os
import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, render_template_string, request, jsonify, send_file, redirect, url_for

logger = logging.getLogger("v7.review_ui")

app = Flask(__name__)
app.secret_key = os.environ.get("V7_SECRET_KEY", "v7-review-secret-development")

_pool = None
_audit_log_path = ""
_chart_data_cache: Dict[str, Any] = {}


def init_app(problem_pool, project_name: str = "", audit_log_dir: str = ""):
    global _pool, _audit_log_path
    _pool = problem_pool
    app.config["PROJECT_NAME"] = project_name or "施工图审查项目"

    audit_dir = audit_log_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output_v7.0", "audit_logs"
    )
    os.makedirs(audit_dir, exist_ok=True)
    _audit_log_path = os.path.join(audit_dir, f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl")


def _audit(user: str, action: str, target: str, before: str = "", after: str = "", reason: str = ""):
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
    if _audit_log_path:
        with open(_audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


_INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} - 人工复核</title>
<style>
:root{--bg-void:#050a14;--bg-card:#16233d;--bg-surface:#111d33;--bg-elevated:#1b2a4a;--bg-hover:#1f3055;--accent:#00e5ff;--accent-glow:rgba(0,229,255,.12);--sev-a:#E74C3C;--sev-b:#F39C12;--sev-c:#F1C40F;--sev-d:#95A5A6;--text-primary:#e8edf5;--text-secondary:#8fa4c4;--text-muted:#5a6e8a;--border-subtle:rgba(255,255,255,.06);--border-card:rgba(255,255,255,.08);--border-active:rgba(0,229,255,.25);--radius-sm:6px;--radius-md:10px}
*{box-sizing:border-box;margin:0;padding:0}body{font:14px/1.55 "PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg-void);color:var(--text-primary)}
a{color:var(--accent);text-decoration:none}a:hover{color:#5ef7ff}
.header{background:var(--bg-elevated);border-bottom:1px solid var(--border-subtle);padding:14px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.header h1{font-size:1.1rem;color:var(--accent)}.header .stats{font-size:.8rem;color:var(--text-secondary)}
.toolbar{background:var(--bg-surface);padding:10px 24px;border-bottom:1px solid var(--border-subtle);display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.toolbar select,.toolbar button,.toolbar input{padding:7px 14px;background:var(--bg-card);border:1px solid var(--border-card);border-radius:var(--radius-sm);font-size:.85rem;color:var(--text-primary);cursor:pointer}
.toolbar button{color:#fff;border:none}.toolbar button.danger{background:#c0392b}
.toolbar button.danger:hover{background:#e74c3c}
.issue-list{max-width:1400px;margin:0 auto;padding:20px 24px}
.issue-card{background:var(--bg-card);border:1px solid var(--border-card);border-left:4px solid var(--sev-d);margin-bottom:8px;border-radius:var(--radius-sm);padding:14px 18px;display:flex;align-items:flex-start;gap:14px;cursor:pointer;transition:all .15s ease}
.issue-card:hover{border-color:var(--border-active);transform:translateX(2px)}
.issue-card.sev-A{border-left-color:var(--sev-a)}.issue-card.sev-B{border-left-color:var(--sev-b)}
.issue-card.sev-C{border-left-color:var(--sev-c)}.issue-card.sev-D{border-left-color:var(--sev-d)}
.sev-badge{display:inline-block;padding:3px 10px;border-radius:10px;font-size:.75rem;font-weight:700;color:#fff;min-width:32px;text-align:center}
.sev-A .sev-badge{background:var(--sev-a)}.sev-B .sev-badge{background:var(--sev-b);color:#000}
.sev-C .sev-badge{background:var(--sev-c);color:#000}.sev-D .sev-badge{background:var(--sev-d);color:#000}
.issue-meta{flex:1;min-width:0}.issue-meta strong{font-size:.9rem;color:var(--text-primary)}
.issue-meta .sub{font-size:.78rem;color:var(--text-muted);margin-top:3px}
.issue-meta .finding{font-size:.82rem;color:var(--text-secondary);margin-top:4px}
.issue-actions{display:flex;flex-direction:column;gap:4px;min-width:70px}
.issue-actions span{font-size:.7rem;padding:3px 8px;border-radius:8px;text-align:center;font-weight:600}
.status-pending{background:rgba(241,196,15,.15);color:#f1c40f;border:1px solid rgba(241,196,15,.25)}
.status-confirmed{background:rgba(39,174,96,.15);color:#2ecc71;border:1px solid rgba(39,174,96,.25)}
.status-rejected{background:rgba(231,76,60,.15);color:#e74c3c;border:1px solid rgba(231,76,60,.25)}
.empty-state{text-align:center;padding:60px 20px;color:var(--text-muted)}
@media(max-width:768px){.issue-card{flex-direction:column}.issue-actions{flex-direction:row}}
</style>
</head>
<body>
<a href="#review-list" class="skip-nav">跳到问题列表</a>
<div class="header" role="banner">
  <h1 id="review-title">{{ title }}</h1>
  <div class="stats" aria-live="polite" aria-label="审查统计">
    总计 <b>{{ stats.total }}</b> | 待审 <b style="color:#f39c12">{{ stats.pending }}</b> | 确认 <b style="color:#27ae60">{{ stats.confirmed }}</b> | 驳回 <b style="color:#e74c3c">{{ stats.rejected }}</b>
  </div>
</div>
<div class="toolbar">
  <select onchange="location.search='?severity='+this.value" aria-label="按严重度筛选">
    <option value="">全部严重度</option>
    <option value="A" {% if sev_filter=='A' %}selected{% endif %}>A-严重</option>
    <option value="B" {% if sev_filter=='B' %}selected{% endif %}>B-重要</option>
    <option value="C" {% if sev_filter=='C' %}selected{% endif %}>C-一般</option>
    <option value="D" {% if sev_filter=='D' %}selected{% endif %}>D-提示</option>
  </select>
  <select onchange="location.search='?status='+this.value" aria-label="按状态筛选">
    <option value="">全部状态</option>
    <option value="pending" {% if status_filter=='pending' %}selected{% endif %}>待审核</option>
    <option value="confirmed" {% if status_filter=='confirmed' %}selected{% endif %}>已确认</option>
    <option value="rejected" {% if status_filter=='rejected' %}selected{% endif %}>已驳回</option>
  </select>
  <button onclick="batchConfirm()" class="danger">批量确认</button>
  <a href="/report" style="text-decoration:none"><button>📄 报告预览</button></a>
</div>
<div class="issue-list" id="review-list" role="list" aria-label="审查问题列表">
{% if issues %}
{% for issue in issues %}
<a href="/review/{{ issue.issue_id }}" style="text-decoration:none;color:inherit" aria-label="问题 {{ issue.checkpoint_name or issue.issue_id }}，严重度 {{ issue.severity }}">
<div class="issue-card sev-{{ issue.severity }}" role="listitem">
  <span class="sev-badge">{{ issue.severity }}</span>
  <div class="issue-meta">
    <strong>[{{ issue.discipline or issue.professional }}] {{ issue.checkpoint_name or issue.checkpoint_id }}</strong>
    <div class="sub">
      {{ issue.drawing_name }} {% if issue.location %} · {{ issue.location }}{% endif %}
      {% if issue.confidence %} · 置信度:{{ issue.confidence }}{% endif %}
      {% if issue.route_used and issue.route_used == 'dual' %} · 双路径✓{% endif %}
    </div>
    <div class="finding">{{ issue.description[:120] }}{% if issue.description|length>120 %}...{% endif %}</div>
  </div>
  <div class="issue-actions">
    {% if issue.review_status == 'confirmed' %}
    <span class="status-confirmed">✓ 已确认</span>
    {% elif issue.review_status == 'rejected' %}
    <span class="status-rejected">✗ 已驳回</span>
    {% else %}
    <span class="status-pending">待审核</span>
    {% endif %}
  </div>
</div>
</a>
{% endfor %}
{% else %}
<div class="empty-state">没有匹配的问题记录</div>
{% endif %}
</div>
<script>
function batchConfirm(){if(confirm('确认批量确认当前筛选的所有待审核问题？')){fetch('/api/batch/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({severity:'{{ sev_filter }}',status:'{{ status_filter }}'})}).then(r=>r.json()).then(d=>{alert('已确认 '+d.count+' 个问题');location.reload()})}}
</script>
</body>
</html>"""

_DETAIL_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ issue.checkpoint_name or issue.issue_id }} - 复核详情</title>
<style>
.skip-nav{position:absolute;top:-100px;left:12px;background:#00e5ff;color:#000;padding:8px 16px;border-radius:6px;font-weight:700;z-index:300;transition:top .15s}
.skip-nav:focus{top:8px}
*:focus-visible{outline:2px solid #00e5ff;outline-offset:2px;border-radius:2px}
:root{--bg-void:#050a14;--bg-card:#16233d;--bg-surface:#111d33;--bg-elevated:#1b2a4a;--bg-hover:#1f3055;--accent:#00e5ff;--accent-dim:#0097a7;--accent-glow:rgba(0,229,255,.12);--sev-a:#E74C3C;--sev-b:#F39C12;--sev-c:#F1C40F;--sev-d:#95A5A6;--text-primary:#e8edf5;--text-secondary:#8fa4c4;--text-muted:#5a6e8a;--text-dim:#3a4a60;--border-subtle:rgba(255,255,255,.06);--border-card:rgba(255,255,255,.08);--border-active:rgba(0,229,255,.25);--radius-sm:6px;--radius-md:10px}
*{box-sizing:border-box;margin:0;padding:0}body{font:14px/1.55 "PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg-void);color:var(--text-primary)}
a{color:var(--accent);text-decoration:none}a:hover{color:#5ef7ff}
.header{background:var(--bg-elevated);border-bottom:1px solid var(--border-subtle);padding:12px 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}
.header a{color:var(--accent);text-decoration:none;font-size:1rem}
.container{max-width:1200px;margin:20px auto;display:flex;gap:16px;padding:0 20px}
.main{flex:2;background:var(--bg-card);border:1px solid var(--border-card);border-radius:var(--radius-md);padding:24px}
.sidebar{flex:1;background:var(--bg-card);border:1px solid var(--border-card);border-radius:var(--radius-md);padding:24px;position:sticky;top:80px;align-self:flex-start}
.field{margin-bottom:14px}.field label{font-weight:600;font-size:.78rem;color:var(--text-muted);display:block;text-transform:uppercase;letter-spacing:.04em}
.field .value{font-size:.9rem;margin-top:4px;color:var(--text-primary)}
.actions{display:flex;flex-direction:column;gap:8px;margin-top:20px}
.actions button{padding:12px 20px;border:none;border-radius:var(--radius-sm);font-size:.9rem;cursor:pointer;color:#fff;transition:all .15s ease}
.btn-confirm{background:#27ae60}.btn-confirm:hover{background:#2ecc71}
.btn-reject{background:#c0392b}.btn-reject:hover{background:#e74c3c}
.btn-modify{background:#2980b9}.btn-modify:hover{background:#3498db}
.btn-back{background:var(--bg-hover);color:var(--text-secondary)!important}.btn-back:hover{color:var(--text-primary)!important}
.provenance-box{background:var(--bg-surface);border:1px solid var(--border-card);border-radius:var(--radius-sm);padding:14px;font-size:.78rem;margin-top:14px}
.provenance-box strong{color:var(--accent)}
.provenance-box .step{padding:4px 0;border-bottom:1px solid var(--border-subtle);color:var(--text-secondary)}
.cad-script-box{background:#0a0f1a;color:#0f0;padding:12px;border-radius:var(--radius-sm);font:12px "Cascadia Code",monospace;margin-top:8px;white-space:pre-wrap;max-height:120px;overflow-y:auto;cursor:copy}
.modal-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.75);z-index:200;align-items:center;justify-content:center}
.modal-overlay.active{display:flex}
.modal{background:var(--bg-card);border:1px solid var(--border-active);border-radius:var(--radius-md);padding:24px;max-width:500px;width:90%}
.modal textarea,.modal select,.modal input{width:100%;padding:10px;background:var(--bg-surface);border:1px solid var(--border-card);border-radius:var(--radius-sm);margin:8px 0;font-size:.9rem;color:var(--text-primary)}
.modal button{padding:10px 18px;border:none;border-radius:var(--radius-sm);cursor:pointer;margin-right:8px;font-size:.85rem}
.notes{font-size:.78rem;color:var(--text-muted);margin-top:16px}
</style>
</head>
<body>
<a href="#detail-main" class="skip-nav">跳到详情内容</a>
<div class="header" role="banner">
  <a href="/" aria-label="返回问题列表">← 返回列表</a>
  <span style="flex:1;color:var(--text-primary)">{{ issue.checkpoint_name or issue.issue_id }}</span>
  <span style="font-weight:700;color:var(--sev-{{ issue.severity.lower() }})" aria-label="严重度 {{ issue.severity }}">严重度: {{ issue.severity }}</span>
</div>
<div class="container">
<div class="main" id="detail-main" role="main">
  <div class="field"><label>问题描述</label><div class="value">{{ issue.description }}</div></div>
  <div class="field"><label>规范依据</label><div class="value">{{ issue.standard_code }} 第{{ issue.standard_clause }}条</div></div>
  {% if issue.clause_text %}<div class="field"><label>条文全文</label><div class="value" style="font-size:.82rem;color:var(--text-secondary)">{{ issue.clause_text }}</div></div>{% endif %}
  <div class="field"><label>整改建议</label><div class="value" style="color:var(--accent)">{{ issue.suggestion or '请人工补充整改建议' }}</div></div>
  <div class="field"><label>图纸定位</label>
    <div class="value">{{ issue.drawing_name }}{% if issue.location %} · {{ issue.location }}{% endif %}</div>
  </div>
  {% if issue.cad_script %}
  <div class="field"><label>CAD一键定位脚本（点击复制）</label>
    <div class="cad-script-box" onclick="navigator.clipboard.writeText(this.textContent);alert('已复制')" title="点击复制">{{ issue.cad_script }}</div>
  </div>
  {% endif %}
  {% if issue.screenshot %}
  <div class="field"><label>问题截图</label><img src="{{ issue.screenshot }}" style="max-width:100%;border:1px solid var(--border-card);border-radius:var(--radius-sm)" onerror="this.style.display='none'"></div>
  {% endif %}
  <div class="provenance-box">
    <strong>📋 溯源链</strong>
    {% set p = issue.provenance %}
    <div class="step">数据来源: {{ p.data_source.type }} | {{ p.data_source.file }} | {{ p.data_source.extract_method }}</div>
    <div class="step">原始标注: {{ p.data_source.raw_text[:100] or '-' }}</div>
    {% for proc in p.processors %}
    <div class="step">→ {{ proc.module }} v{{ proc.version }}: {{ proc.output[:80] }}</div>
    {% endfor %}
    <div class="step">验证: 双路径={{ p.verification.is_dual_verified }}{% if p.verification.text_path %} | 文本:{{ p.verification.text_path.model }}={{ p.verification.text_path.verdict }}{% endif %}{% if p.verification.visual_path %} | 视觉:{{ p.verification.visual_path.model }}={{ p.verification.visual_path.verdict }}{% endif %}</div>
  </div>
  <div class="field" style="margin-top:8px"><label>审查状态</label><div class="value">{{ issue.review_status }}</div></div>
  {% if issue.review_comment %}<div class="field"><label>复核意见</label><div class="value">{{ issue.review_comment }}</div></div>{% endif %}
</div>
<div class="sidebar">
  <h3 style="margin-bottom:16px;color:var(--accent)">操作</h3>
  <div class="actions">
    <button class="btn-confirm" onclick="doAction('confirm')">✓ 确认问题</button>
    <button class="btn-reject" onclick="showReject()">✗ 驳回(误报)</button>
    <button class="btn-modify" onclick="showModify()">✎ 修改</button>
    <button class="btn-back" onclick="location.href='/'">← 返回列表</button>
  </div>
  <div class="notes">操作日志已自动记录，所有操作不可篡改。</div>
</div>
</div>

<div class="modal-overlay" id="rejectModal"><div class="modal">
  <h3>驳回问题</h3><p style="font-size:13px;color:#666">请说明驳回原因</p>
  <textarea id="rejectReason" rows="3" placeholder="如: 标注已被后续修改覆盖、与本项目无关..."></textarea>
  <div style="text-align:right;margin-top:8px">
    <button onclick="closeModal('rejectModal')" style="background:#eee;color:#333">取消</button>
    <button onclick="doAction('reject')" style="background:#e74c3c;color:#fff">确认驳回</button>
  </div>
</div></div>

<div class="modal-overlay" id="modifyModal"><div class="modal">
  <h3>修改问题</h3>
  <label>严重度</label><select id="modSeverity"><option value="A" {% if issue.severity=='A' %}selected{% endif %}>A-严重</option><option value="B" {% if issue.severity=='B' %}selected{% endif %}>B-重要</option><option value="C" {% if issue.severity=='C' %}selected{% endif %}>C-一般</option><option value="D" {% if issue.severity=='D' %}selected{% endif %}>D-提示</option></select>
  <label>问题描述</label><textarea id="modDesc" rows="3">{{ issue.description }}</textarea>
  <label>整改建议</label><textarea id="modSug" rows="2">{{ issue.suggestion or '' }}</textarea>
  <div style="text-align:right;margin-top:8px">
    <button onclick="closeModal('modifyModal')" style="background:#eee;color:#333">取消</button>
    <button onclick="doAction('modify')" style="background:#2980b9;color:#fff">确认修改</button>
  </div>
</div></div>

<script>
function doAction(action){
  let body={issue_id:'{{ issue.issue_id }}',action:action,user:'reviewer'};
  if(action==='reject'){body.reason=document.getElementById('rejectReason').value}
  if(action==='modify'){body.severity=document.getElementById('modSeverity').value;body.description=document.getElementById('modDesc').value;body.suggestion=document.getElementById('modSug').value}
  fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(r=>r.json()).then(d=>{if(d.ok){location.reload()}else{alert('操作失败: '+(d.error||'未知'))}})
  .catch(e=>alert('网络错误: '+e))
}
function showReject(){document.getElementById('rejectModal').classList.add('active')}
function showModify(){document.getElementById('modifyModal').classList.add('active')}
function closeModal(id){document.getElementById(id).classList.remove('active')}
</script>
</body>
</html>"""

_REPORT_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>审图报告预览</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}body{font:14px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;background:#f5f6fa;color:#333}
.header{background:#1a1a2e;color:#fff;padding:10px 20px;display:flex;align-items:center;gap:16px}
.header a{color:#fff;text-decoration:none}
.content{max-width:1000px;margin:20px auto;background:#fff;padding:40px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.content h1{font-size:22px;margin-bottom:8px}
.content h2{font-size:16px;margin-top:24px;margin-bottom:12px;border-bottom:2px solid #1a1a2e;padding-bottom:4px}
.content h3{font-size:14px;margin-top:16px}
.content p{margin:4px 0;line-height:1.8}
.content ul{margin-left:20px}
.content .sev-A{color:#e74c3c}.content .sev-B{color:#e67e22}
.actions{text-align:center;padding:20px}
.actions button{padding:10px 24px;border:none;border-radius:6px;font-size:14px;cursor:pointer;margin:0 8px}
.btn-export{background:#27ae60;color:#fff}
.btn-back{background:#7f8c8d;color:#fff}
@media print{.header,.actions{display:none}.content{box-shadow:none;padding:0}}
</style>
</head>
<body>
<div class="header"><a href="/">← 返回</a><span>{{ title }}</span></div>
<div class="content">
{{ report_html | safe }}
</div>
<div class="actions">
  <button class="btn-back" onclick="location.href='/'">返回列表</button>
  <button class="btn-export" onclick="window.print()">🖨️ 打印/导出PDF</button>
</div>
</body>
</html>"""


@app.route("/")
def index():
    if not _pool:
        return "<h2>问题池未加载</h2>"

    severity = request.args.get("severity", "")
    status = request.args.get("status", "")

    all_issues = _pool.to_list()
    if severity:
        all_issues = [i for i in all_issues if i.get("severity") == severity]
    if status:
        all_issues = [i for i in all_issues if i.get("review_status") == status]

    all_issues.sort(key=lambda i: {"A": 0, "B": 1, "C": 2, "D": 3}.get(i.get("severity", "D"), 9))

    stats = {
        "total": len(_pool._issues),
        "pending": sum(1 for i in _pool._issues.values() if i.review_status == "pending"),
        "confirmed": sum(1 for i in _pool._issues.values() if i.review_status == "confirmed"),
        "rejected": sum(1 for i in _pool._issues.values() if i.review_status == "rejected"),
    }

    return render_template_string(
        _INDEX_HTML,
        title=app.config.get("PROJECT_NAME", "施工图审查"),
        issues=all_issues,
        stats=stats,
        sev_filter=severity,
        status_filter=status,
    )


@app.route("/review/<issue_id>")
def review_detail(issue_id: str):
    if not _pool:
        return "<h2>问题池未加载</h2>"
    issue = _pool.get(issue_id)
    if not issue:
        return "<h2>问题不存在</h2>", 404
    return render_template_string(_DETAIL_HTML, issue=issue.to_dict())


@app.route("/api/confirm", methods=["POST"])
def api_confirm():
    data = request.get_json()
    issue_id = data.get("issue_id", "")
    issue = _pool.get(issue_id)
    if not issue:
        return jsonify({"ok": False, "error": "问题不存在"})
    issue.review_status = "confirmed"
    issue.reviewed_by = data.get("user", "unknown")
    _audit(data.get("user", ""), "confirm_review", issue_id, "pending", "confirmed")
    return jsonify({"ok": True, "status": "confirmed"})


@app.route("/api/reject", methods=["POST"])
def api_reject():
    data = request.get_json()
    issue_id = data.get("issue_id", "")
    reason = data.get("reason", "")
    issue = _pool.get(issue_id)
    if not issue:
        return jsonify({"ok": False, "error": "问题不存在"})
    issue.review_status = "rejected"
    issue.review_comment = reason
    issue.reviewed_by = data.get("user", "unknown")
    _audit(data.get("user", ""), "reject_review", issue_id, "pending", "rejected", reason)
    return jsonify({"ok": True, "status": "rejected"})


@app.route("/api/modify", methods=["POST"])
def api_modify():
    data = request.get_json()
    issue_id = data.get("issue_id", "")
    issue = _pool.get(issue_id)
    if not issue:
        return jsonify({"ok": False, "error": "问题不存在"})
    before = json.dumps({"severity": issue.severity, "description": issue.description[:100]}, ensure_ascii=False)
    if data.get("severity"):
        issue.severity = data["severity"]
    if data.get("description"):
        issue.description = data["description"]
    if data.get("suggestion"):
        issue.suggestion = data["suggestion"]
    issue.review_status = "confirmed"
    issue.reviewed_by = data.get("user", "unknown")
    after = json.dumps({"severity": issue.severity, "description": issue.description[:100]}, ensure_ascii=False)
    _audit(data.get("user", ""), "modify_review", issue_id, before, after)
    return jsonify({"ok": True, "status": "modified"})


@app.route("/api/add", methods=["POST"])
def api_add():
    if not _pool:
        return jsonify({"ok": False, "error": "问题池未加载"})
    data = request.get_json()
    from v7.problem_pool import UnifiedIssue, Provenance, DataSource
    new_id = f"MANUAL-{uuid.uuid4().hex[:8]}"
    issue = UnifiedIssue(
        issue_id=new_id,
        professional=data.get("professional", "手动"),
        description=data.get("description", ""),
        severity=data.get("severity", "C"),
        suggestion=data.get("suggestion", ""),
        standard_code=data.get("standard_code", ""),
        standard_clause=data.get("standard_clause", ""),
        drawing_name=data.get("drawing_name", ""),
        review_status="pending",
        create_time=datetime.now(timezone.utc).isoformat(),
        provenance=Provenance(data_source=DataSource(type="manual", extract_method="人工补充")),
    )
    _pool.add_issue(issue)
    _audit(data.get("user", ""), "add_review", new_id, "", json.dumps(data, ensure_ascii=False))
    return jsonify({"ok": True, "issue_id": new_id})


@app.route("/api/batch/confirm", methods=["POST"])
def api_batch_confirm():
    if not _pool:
        return jsonify({"ok": False})
    data = request.get_json() or {}
    severity = data.get("severity", "")
    status = data.get("status", "")
    confirm_count = 0
    for issue in _pool._issues.values():
        if issue.review_status != "pending":
            continue
        if severity and issue.severity != severity:
            continue
        issue.review_status = "confirmed"
        issue.reviewed_by = data.get("user", "batch")
        confirm_count += 1
    _audit(data.get("user", "batch"), "batch_confirm", f"count={confirm_count}")
    return jsonify({"ok": True, "count": confirm_count})


@app.route("/report")
def report():
    if not _pool:
        return "<h2>问题池未加载</h2>"

    from v7.agents.chief_agent import ChiefAgent
    chief = ChiefAgent(_pool)
    chief_report = chief.execute()
    md = chief_report.markdown_report

    html = _md_to_html(md)
    return render_template_string(_REPORT_HTML, title="审图报告", report_html=html)


def _md_to_html(md: str) -> str:
    lines = md.split("\n")
    html = []
    in_list = False
    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            html.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            html.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            html.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("- "):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{line[2:]}</li>")
        elif line.startswith("> "):
            html.append(f"<blockquote>{line[2:]}</blockquote>")
        elif line.startswith("---"):
            html.append("<hr>")
        else:
            if in_list:
                html.append("</ul>")
                in_list = False
            if line.strip():
                html.append(f"<p>{line}</p>")
            else:
                html.append("<br>")
    if in_list:
        html.append("</ul>")
    return "\n".join(html)


def run_server(problem_pool, project_name: str = "", port: int = 8080,
               audit_log_dir: str = "", debug: bool = False):
    init_app(problem_pool, project_name, audit_log_dir)
    print(f"\n{'='*50}")
    print(f"  v7.0 人工复核界面")
    print(f"  项目: {project_name or '未命名'}")
    print(f"  地址: http://localhost:{port}")
    print(f"  问题数: {len(problem_pool._issues) if problem_pool else 0}")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="v7.0 人工复核Web界面")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--project", default="施工图审查项目")
    args = parser.parse_args()

    from v7.problem_pool import ProblemPool, UnifiedIssue, Provenance, DataSource
    demo_pool = ProblemPool()
    for i in range(5):
        sevs = ["A", "B", "B", "C", "C"]
        issue = UnifiedIssue(
            issue_id=f"DEMO-00{i+1}",
            professional="建筑",
            checkpoint_name=f"检查点测试{i+1}",
            description="这是一条示例问题，用于演示人工复核界面。请审核后确认或驳回。",
            severity=sevs[i],
            suggestion="示例整改建议：按照规范要求修改。",
            standard_code="GB50016-2014(2018)",
            standard_clause="5.5.30",
            drawing_name=f"建施-0{i+1}.dwg",
            location="A轴/3-4轴",
            cad_script="_.ZOOM _C 12345.0,67890.0,0.0 5000\n_.CIRCLE 12345.0,67890.0,0.0 1000",
            provenance=Provenance(data_source=DataSource(type="dxf_text", file=f"建施-0{i+1}.dwg", extract_method="ezdxf_parse")),
            route_used="dual",
        )
        demo_pool.add_issue(issue)

    run_server(demo_pool, args.project, args.port, debug=True)
