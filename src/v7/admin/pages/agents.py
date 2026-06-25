# -*- coding: utf-8 -*-
"""Agent 配置页面模块

导出:
  render_page() -> str                             返回 Agent 配置页面 HTML body
  handle_api(path, method, body, qs) -> tuple|None 处理 /admin/api/agents/* 请求
"""

import json
import logging
from datetime import datetime

from v7.constants import LLM_PROVIDERS, LLM_PROVIDER_MAP

logger = logging.getLogger(__name__)

# ── 动态加载默认值 ─────────────────────────────────────────

def _load_default_system_prompts():
    """从 AGENT_REGISTRY 动态加载默认系统提示词。"""
    try:
        from v7.agents import AGENT_REGISTRY
        prompts = {}
        for aid, Cls in AGENT_REGISTRY.items():
            try:
                inst = Cls()
                prompts[aid] = inst.build_system_prompt()
            except Exception as e:
                logger.warning(f"加载Agent {aid} 系统提示词失败: {e}")
        return prompts
    except ImportError:
        return {}


def _load_discipline_labels():
    """从 AGENT_REGISTRY 动态加载专业标签。"""
    try:
        from v7.agents import AGENT_REGISTRY
        labels = {}
        for aid, Cls in AGENT_REGISTRY.items():
            try:
                inst = Cls()
                labels[inst.config.discipline] = getattr(inst.config, 'discipline_label', inst.config.name)
            except Exception as e:
                logger.warning(f"加载Agent {aid} 专业标签失败: {e}")
        return labels
    except ImportError:
        return {}


def _load_llm_providers():
    """从数据库 llm_configs 表动态加载已配置的 LLM 提供商列表（与 API 配置页面联动）。"""
    from v7.constants import LLM_PROVIDER_MAP
    try:
        from v7.db import get_db
        db = get_db()
        # 优先从新表 llm_configs 读取（按用途分离存储）
        rows = db.execute(
            "SELECT DISTINCT provider FROM llm_configs WHERE api_key IS NOT NULL AND api_key != ''"
        ).fetchall()
        result = []
        for row in rows:
            pid = row["provider"]
            if not pid:
                continue
            name = LLM_PROVIDER_MAP.get(pid, {}).get("name", pid)
            result.append((pid, name))
        # 兼容旧表 api_keys
        if not result:
            rows = db.execute(
                "SELECT provider FROM api_keys WHERE api_key IS NOT NULL AND api_key != ''"
            ).fetchall()
            for row in rows:
                pid = row["provider"]
                if not pid:
                    continue
                name = LLM_PROVIDER_MAP.get(pid, {}).get("name", pid)
                result.append((pid, name))
        # 始终保留自定义选项
        if not any(p[0] == "custom" for p in result):
            result.append(("custom", "自定义"))
        return result
    except Exception:
        # 数据库不可用时返回常量中的默认列表
        return [(p["provider"], p["name"]) for p in LLM_PROVIDERS] + [("custom", "自定义")]


# ── 数据访问 ─────────────────────────────────────────────

def _get_all_agents():
    from v7.db import get_db
    db = get_db()
    rows = db.execute(
        "SELECT id, name, discipline, role_title, experience_years, "
        "system_prompt, llm_provider, llm_model, max_concurrent, enabled "
        "FROM agent_configs ORDER BY discipline, id"
    ).fetchall()
    return [dict(r) for r in rows]


def _get_agent(agent_id):
    from v7.db import get_db
    db = get_db()
    row = db.execute(
        "SELECT id, name, discipline, role_title, experience_years, "
        "system_prompt, llm_provider, llm_model, max_concurrent, enabled "
        "FROM agent_configs WHERE id = ?", (agent_id,)
    ).fetchone()
    return dict(row) if row else None


def _update_agent(agent_id, data):
    from v7.db import get_db
    db = get_db()

    # ── 记录版本：system_prompt 变更前保存旧值 ──
    if "system_prompt" in data:
        old_row = db.execute(
            "SELECT system_prompt FROM agent_configs WHERE id = ?", (agent_id,)
        ).fetchone()
        if old_row:
            old_prompt = old_row["system_prompt"] or ""
            new_prompt = data["system_prompt"]
            db.execute(
                "INSERT INTO config_versions (target_type, target_id, field_name, old_value, new_value) "
                "VALUES (?, ?, ?, ?, ?)",
                ("agent", agent_id, "system_prompt", old_prompt, new_prompt),
            )

    allowed = ["system_prompt", "llm_provider", "llm_model", "max_concurrent", "enabled"]
    sets = []
    params = []
    for k in allowed:
        if k in data:
            sets.append(f"{k} = ?")
            params.append(data[k])
    if not sets:
        return None
    sets.append("updated_at = ?")
    params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    params.append(agent_id)
    db.execute(
        f"UPDATE agent_configs SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    db.commit()
    return _get_agent(agent_id)


def _reset_agent(agent_id):
    from v7.db import get_db
    db = get_db()
    default_prompts = _load_default_system_prompts()
    default_prompt = default_prompts.get(agent_id, "")

    # ── 记录版本：重置前保存旧 system_prompt ──
    old_row = db.execute(
        "SELECT system_prompt FROM agent_configs WHERE id = ?", (agent_id,)
    ).fetchone()
    if old_row:
        old_prompt = old_row["system_prompt"] or ""
        db.execute(
            "INSERT INTO config_versions (target_type, target_id, field_name, old_value, new_value) "
            "VALUES (?, ?, ?, ?, ?)",
            ("agent", agent_id, "system_prompt", old_prompt, default_prompt),
        )

    db.execute(
        "UPDATE agent_configs SET system_prompt = ?, updated_at = ? WHERE id = ?",
        (default_prompt, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), agent_id),
    )
    db.commit()
    return _get_agent(agent_id)


# ── API 处理器 ───────────────────────────────────────────

def handle_api(path, method, body, qs):
    """处理 Agent 相关 API 请求。

    Args:
        path:   请求路径 (e.g. "/admin/api/agents/list")
        method: HTTP 方法 ("GET"/"PUT"/"POST"等)
        body:   已解析的 JSON body (dict 或 None)
        qs:     查询参数字典 (dict)

    Returns:
        匹配时返回 (status_code, data_dict, content_type_str)
        不匹配时返回 None
    """
    if not path.startswith("/admin/api/agents"):
        return None

    # GET /admin/api/agents/list
    if method == "GET" and path == "/admin/api/agents/list":
        agents = _get_all_agents()
        return 200, {"agents": agents}, "application/json"

    # GET /admin/api/agents/{id}
    if method == "GET" and path.startswith("/admin/api/agents/"):
        agent_id = path[len("/admin/api/agents/"):]
        if "/" in agent_id:
            return None
        agent = _get_agent(agent_id)
        if agent is None:
            return 404, {"error": "Agent 不存在"}, "application/json"
        return 200, agent, "application/json"

    # PUT /admin/api/agents/{id}
    if method == "PUT" and path.startswith("/admin/api/agents/"):
        agent_id = path[len("/admin/api/agents/"):]
        if "/" in agent_id:
            return None
        if not isinstance(body, dict):
            return 400, {"error": "请求体必须是 JSON 对象"}, "application/json"
        agent = _update_agent(agent_id, body)
        if agent is None:
            return 404, {"error": "Agent 不存在或无可更新字段"}, "application/json"
        return 200, agent, "application/json"

    # POST /admin/api/agents/{id}/reset
    if method == "POST":
        parts = path[len("/admin/api/agents/"):].split("/")
        if len(parts) == 2 and parts[1] == "reset":
            agent_id = parts[0]
            agent = _reset_agent(agent_id)
            if agent is None:
                return 404, {"error": "Agent 不存在"}, "application/json"
            return 200, agent, "application/json"

    return None


# ── HTML 渲染 ────────────────────────────────────────────

def render_page():
    """返回 Agent 配置页面的完整 HTML body（不含外层框架）。"""
    agents = _get_all_agents()
    providers = _load_llm_providers()
    prompts = _load_default_system_prompts()
    labels = _load_discipline_labels()
    providers_json = json.dumps(providers, ensure_ascii=False)
    agents_json = json.dumps(agents, ensure_ascii=False)
    prompts_json = json.dumps(prompts, ensure_ascii=False)
    labels_json = json.dumps(labels, ensure_ascii=False)

    return f"""<style>
.agents-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 14px;
}}
.agent-card {{
    background: #fff;
    border-radius: 8px;
    padding: 16px 18px;
    cursor: pointer;
    border: 2px solid transparent;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
    transition: border-color .15s, box-shadow .15s;
    position: relative;
}}
.agent-card:hover {{
    border-color: #16213e;
    box-shadow: 0 3px 10px rgba(22,33,62,.12);
}}
.agent-card.selected {{
    border-color: #e94560;
    box-shadow: 0 3px 14px rgba(233,69,96,.18);
}}
.agent-card .agent-name {{
    font-size: 15px;
    font-weight: 600;
    color: #1a1a2e;
    margin-bottom: 4px;
}}
.agent-card .agent-role {{
    font-size: 12px;
    color: #555;
    margin-bottom: 6px;
}}
.agent-card .agent-meta {{
    display: flex;
    gap: 12px;
    font-size: 11px;
    color: #666;
}}
.agent-card .agent-meta span {{
    background: #f5f6fa;
    padding: 2px 8px;
    border-radius: 10px;
}}
.agent-card .toggle-switch {{
    position: absolute;
    top: 14px;
    right: 14px;
}}
.toggle-switch {{
    display: inline-block;
    width: 40px;
    height: 22px;
    position: relative;
}}
.toggle-switch input {{
    opacity: 0;
    width: 0;
    height: 0;
}}
.toggle-slider {{
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: #ccc;
    border-radius: 22px;
    transition: .25s;
}}
.toggle-slider:before {{
    position: absolute;
    content: "";
    height: 16px;
    width: 16px;
    left: 3px;
    bottom: 3px;
    background-color: #fff;
    border-radius: 50%;
    transition: .25s;
}}
input:checked + .toggle-slider {{
    background-color: #27ae60;
}}
input:checked + .toggle-slider:before {{
    transform: translateX(18px);
}}
.detail-panel {{
    background: #fff;
    border-radius: 8px;
    padding: 20px 24px;
    margin-top: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
    border-left: 4px solid #e94560;
    display: none;
}}
.detail-panel.active {{
    display: block;
}}
.detail-panel h3 {{
    font-size: 16px;
    color: #1a1a2e;
    margin-bottom: 14px;
    border-bottom: 1px solid #eee;
    padding-bottom: 8px;
}}
.detail-panel .form-row {{
    display: flex;
    gap: 16px;
    margin-bottom: 12px;
}}
.detail-panel .form-row > div {{
    flex: 1;
}}
.detail-panel label {{
    display: block;
    font-size: 13px;
    color: #555;
    margin-bottom: 4px;
    font-weight: 500;
}}
.detail-panel input,
.detail-panel select,
.detail-panel textarea {{
    width: 100%;
    padding: 8px 12px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 13px;
    background: #fafafa;
    color: #1a1a2e;
}}
.detail-panel select option {{
    color: #1a1a2e;
    background: #fff;
}}
.detail-panel input:focus,
.detail-panel select:focus,
.detail-panel textarea:focus {{
    outline: none;
    border-color: #16213e;
    background: #fff;
}}
.detail-panel textarea {{
    font-family: "Cascadia Code", "Fira Code", Consolas, "Courier New", monospace;
    font-size: 13px;
    line-height: 1.6;
    min-height: 280px;
    resize: vertical;
    color: #1a1a2e;
    background: #fff;
}}
.char-count {{
    text-align: right;
    font-size: 11px;
    color: #666;
    margin-top: 2px;
}}
.btn-row {{
    display: flex;
    gap: 10px;
    margin-top: 14px;
    align-items: center;
}}
.btn {{
    padding: 8px 18px;
    border: none;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    transition: opacity .15s;
}}
.btn:hover {{ opacity: 0.85; }}
.btn:active {{ transform: scale(.97); }}
.btn-save {{
    background: #16213e;
    color: #fff;
}}
.btn-reset {{
    background: #e67e22;
    color: #fff;
}}
.btn-reset.danger {{
    background: #c0392b;
}}
.toast {{
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 10px 22px;
    border-radius: 6px;
    color: #fff;
    font-size: 13px;
    z-index: 9999;
    opacity: 0;
    transition: opacity .3s;
    pointer-events: none;
}}
.toast.show {{
    opacity: 1;
}}
.toast.success {{ background: #27ae60; }}
.toast.error {{ background: #c0392b; }}
.no-agents {{
    text-align: center;
    padding: 60px 20px;
    color: #666;
    font-size: 14px;
}}
</style>

<div class="toast" id="toast"></div>

<div class="agents-grid" id="agentsGrid"></div>

<div class="detail-panel" id="detailPanel">
    <h3 id="detailTitle">Agent 详情</h3>
    <div style="background:#f0f7ff;border:1px solid #b3d8ff;border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:12px;line-height:1.6;color:#333">
      <div style="font-weight:600;margin-bottom:4px;color:#1677ff">📘 配置说明</div>
      <div><b>LLM 提供商：</b>选择该Agent调用的大模型服务商（如智谱、DeepSeek、OpenAI等）。</div>
      <div><b>LLM 模型：</b>填写具体的模型名称，决定Agent的推理能力和回答风格。</div>
      <div><b>最大并发数：</b>该Agent同时处理多少张图纸，数值越大速度越快但费用越高。</div>
      <div><b>系统 Prompt：</b>给Agent的"角色设定"，定义它的专业身份、审查标准和关注重点。</div>
    </div>
    <div class="form-row">
        <div>
            <label>LLM 提供商 <span style="font-weight:normal;color:#555;font-size:11px">— 选择大模型服务商</span></label>
            <select id="editProvider"></select>
        </div>
        <div>
            <label>LLM 模型 <span style="font-weight:normal;color:#555;font-size:11px">— 填写模型名称</span></label>
            <input type="text" id="editModel" placeholder="例如 gpt-4o, qwen-max, deepseek-chat">
        </div>
        <div>
            <label>最大并发数 <span style="font-weight:normal;color:#555;font-size:11px">— 同时处理图纸数</span></label>
            <input type="number" id="editConcurrent" min="1" max="20" value="3">
        </div>
    </div>
    <div>
        <label>系统 Prompt <span style="font-weight:normal;color:#555;font-size:11px">— Agent的角色设定与审查标准</span></label>
        <textarea id="editPrompt" rows="15" placeholder="例如：你是一级注册建筑师，拥有15年设计经验。你精通GB50016《建筑设计防火规范》..."></textarea>
        <div class="char-count"><span id="charCount">0</span> 字符</div>
    </div>
    <div class="btn-row">
        <button class="btn btn-save" onclick="saveAgent()">保存</button>
        <button class="btn btn-reset" onclick="confirmReset()">重置为默认</button>
        <span id="saveStatus" style="font-size:12px;color:#555;margin-left:8px"></span>
    </div>
</div>

<script>
var agentsData = {agents_json};
var defaultPrompts = {prompts_json};
var providers = {providers_json};
var selectedAgentId = null;

function buildProviderSelect() {{
    var sel = document.getElementById('editProvider');
    sel.innerHTML = '';
    providers.forEach(function(p) {{
        var opt = document.createElement('option');
        opt.value = p[0];
        opt.textContent = p[1];
        sel.appendChild(opt);
    }});
}}

function renderCards() {{
    var grid = document.getElementById('agentsGrid');
    if (!agentsData || agentsData.length === 0) {{
        grid.innerHTML = '<div class="no-agents">暂无 Agent 配置，请先执行数据迁移</div>';
        return;
    }}
    grid.innerHTML = '';
    var disciplineLabels = {labels_json};
    agentsData.forEach(function(a) {{
        var discLabel = disciplineLabels[a.discipline] || a.discipline;
        var card = document.createElement('div');
        card.className = 'agent-card' + (a.id === selectedAgentId ? ' selected' : '');
        card.setAttribute('data-id', a.id);
        card.onclick = function(e) {{
            if (e.target.closest('.toggle-switch')) return;
            selectAgent(a.id);
        }};
        card.innerHTML =
            '<div class="toggle-switch" onclick="event.stopPropagation()">' +
            '<input type="checkbox" ' + (a.enabled ? 'checked' : '') +
            ' onchange="toggleAgent(\\'' + a.id + '\\', this.checked)">' +
            '<span class="toggle-slider"></span></div>' +
            '<div class="agent-name">' + escHtml(a.name) + '</div>' +
            '<div class="agent-role">' + escHtml(a.role_title || '') + '</div>' +
            '<div class="agent-meta">' +
            '<span>' + escHtml(discLabel) + '</span>' +
            '<span>' + (a.experience_years || 0) + '年</span>' +
            '</div>';
        grid.appendChild(card);
    }});
}}

function escHtml(s) {{
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function selectAgent(agentId) {{
    selectedAgentId = agentId;
    var agent = null;
    for (var i = 0; i < agentsData.length; i++) {{
        if (agentsData[i].id === agentId) {{ agent = agentsData[i]; break; }}
    }}
    if (!agent) return;
    renderCards();
    var panel = document.getElementById('detailPanel');
    panel.classList.add('active');
    document.getElementById('detailTitle').textContent = agent.name + ' — ' + (agent.role_title || '');
    document.getElementById('editProvider').value = agent.llm_provider || 'doubao';
    document.getElementById('editModel').value = agent.llm_model || '';
    document.getElementById('editConcurrent').value = agent.max_concurrent || 3;
    document.getElementById('editPrompt').value = agent.system_prompt || '';
    document.getElementById('charCount').textContent = (agent.system_prompt || '').length;
    document.getElementById('saveStatus').textContent = '';
    panel.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
}}

function toggleAgent(agentId, enabled) {{
    fetch('/admin/api/agents/' + agentId, {{
        method: 'PUT',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{enabled: enabled ? 1 : 0}})
    }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
        if (data.error) {{
            showToast('更新失败: ' + data.error, 'error');
            return;
        }}
        for (var i = 0; i < agentsData.length; i++) {{
            if (agentsData[i].id === agentId) {{
                agentsData[i].enabled = enabled ? 1 : 0;
                break;
            }}
        }}
        showToast((enabled ? '已启用 ' : '已禁用 ') + agentId, 'success');
    }}).catch(function(err) {{
        showToast('网络错误', 'error');
        renderCards();
    }});
}}

function saveAgent() {{
    if (!selectedAgentId) return;
    var body = {{
        system_prompt: document.getElementById('editPrompt').value,
        llm_provider: document.getElementById('editProvider').value,
        llm_model: document.getElementById('editModel').value.trim(),
        max_concurrent: parseInt(document.getElementById('editConcurrent').value, 10) || 3
    }};
    var statusEl = document.getElementById('saveStatus');
    statusEl.textContent = '保存中...';
    statusEl.style.color = '#888';
    fetch('/admin/api/agents/' + selectedAgentId, {{
        method: 'PUT',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(body)
    }}).then(function(r) {{ return r.json(); }}).then(function(data) {{
        if (data.error) {{
            statusEl.textContent = '错误: ' + data.error;
            statusEl.style.color = '#c0392b';
            return;
        }}
        for (var i = 0; i < agentsData.length; i++) {{
            if (agentsData[i].id === selectedAgentId) {{
                agentsData[i].system_prompt = data.system_prompt;
                agentsData[i].llm_provider = data.llm_provider;
                agentsData[i].llm_model = data.llm_model;
                agentsData[i].max_concurrent = data.max_concurrent;
                break;
            }}
        }}
        statusEl.textContent = '已保存';
        statusEl.style.color = '#27ae60';
        showToast('保存成功', 'success');
    }}).catch(function(err) {{
        statusEl.textContent = '网络错误';
        statusEl.style.color = '#c0392b';
    }});
}}

function confirmReset() {{
    if (!selectedAgentId) return;
    var statusEl = document.getElementById('saveStatus');
    statusEl.textContent = '再次点击确认重置...';
    statusEl.style.color = '#e67e22';
    var btn = document.querySelector('.btn-reset');
    btn.textContent = '确认重置';
    btn.classList.add('danger');
    btn.onclick = doReset;
    setTimeout(function() {{
        if (btn.classList.contains('danger')) {{
            btn.textContent = '重置为默认';
            btn.classList.remove('danger');
            btn.onclick = confirmReset;
            statusEl.textContent = '';
        }}
    }}, 5000);
}}

function doReset() {{
    if (!selectedAgentId) return;
    var statusEl = document.getElementById('saveStatus');
    statusEl.textContent = '重置中...';
    statusEl.style.color = '#888';
    var btn = document.querySelector('.btn-reset');
    btn.textContent = '重置为默认';
    btn.classList.remove('danger');
    btn.onclick = confirmReset;
    fetch('/admin/api/agents/' + selectedAgentId + '/reset', {{ method: 'POST' }})
    .then(function(r) {{ return r.json(); }}).then(function(data) {{
        if (data.error) {{
            statusEl.textContent = '错误: ' + data.error;
            statusEl.style.color = '#c0392b';
            return;
        }}
        for (var i = 0; i < agentsData.length; i++) {{
            if (agentsData[i].id === selectedAgentId) {{
                agentsData[i].system_prompt = data.system_prompt;
                break;
            }}
        }}
        document.getElementById('editPrompt').value = data.system_prompt || '';
        document.getElementById('charCount').textContent = (data.system_prompt || '').length;
        statusEl.textContent = '已重置为默认值';
        statusEl.style.color = '#27ae60';
        showToast('已重置为默认 Prompt', 'success');
    }}).catch(function(err) {{
        statusEl.textContent = '网络错误';
        statusEl.style.color = '#c0392b';
    }});
}}

function showToast(msg, type) {{
    var toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = 'toast ' + (type || 'success') + ' show';
    clearTimeout(toast._timer);
    toast._timer = setTimeout(function() {{
        toast.classList.remove('show');
    }}, 2500);
}}

document.getElementById('editPrompt').addEventListener('input', function() {{
    document.getElementById('charCount').textContent = this.value.length;
}});

document.addEventListener('DOMContentLoaded', function() {{
    buildProviderSelect();
    renderCards();
}});
</script>"""  # noqa: E501
