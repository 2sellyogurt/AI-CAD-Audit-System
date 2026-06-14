# -*- coding: utf-8 -*-
"""API 配置与费用统计页面模块

导出:
  render_page() -> str                    返回完整HTML内容（不含外层框架）
  handle_api(path, method, body, qs) -> (status, data, content_type) or None
"""

import json
import time
from datetime import datetime

# ── 预定义 5 个 LLM 提供商 ────────────────────────────────

_PROVIDERS = [
    {
        "provider": "zhipu",
        "name": "智谱 (Zhipu)",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "default_text_model": "glm-4-flash",
        "default_vision_model": "glm-4v",
        "color": "#1677ff",
    },
    {
        "provider": "deepseek",
        "name": "DeepSeek",
        "default_base_url": "https://api.deepseek.com/v1",
        "default_text_model": "deepseek-chat",
        "default_vision_model": "",
        "color": "#536dfe",
    },
    {
        "provider": "openai",
        "name": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "default_text_model": "gpt-4o",
        "default_vision_model": "gpt-4o",
        "color": "#10a37f",
    },
    {
        "provider": "doubao",
        "name": "豆包 (Doubao)",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_text_model": "doubao-1.5-pro-32k",
        "default_vision_model": "doubao-1.5-vision-pro",
        "color": "#ff6b35",
    },
    {
        "provider": "ollama",
        "name": "Ollama (本地)",
        "default_base_url": "http://localhost:11434/v1",
        "default_text_model": "qwen2.5:7b",
        "default_vision_model": "llava:latest",
        "color": "#000000",
    },
]

_PROVIDER_MAP = {p["provider"]: p for p in _PROVIDERS}


# ── 密钥脱敏 ────────────────────────────────────────────

def mask_key(key: str) -> str:
    """API Key 脱敏显示：前4后4可见，中间*号遮挡。"""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "*" * (len(key) - 4) + key[-2:] if len(key) >= 4 else "****"
    return key[:4] + "*" * min(len(key) - 8, 12) + key[-4:]


# ── 数据库操作 ──────────────────────────────────────────

def _get_db():
    from v7.db import get_db
    return get_db()


def _load_providers_from_db():
    """从数据库加载所有提供商配置。"""
    db = _get_db()
    rows = db.execute(
        "SELECT provider, api_key, base_url, text_model, vision_model, is_default, "
        "created_at, updated_at FROM api_keys"
    ).fetchall()

    result = {}
    for row in rows:
        result[row["provider"]] = {
            "provider": row["provider"],
            "api_key": row["api_key"],
            "base_url": row["base_url"],
            "text_model": row["text_model"],
            "vision_model": row["vision_model"],
            "is_default": bool(row["is_default"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    return result


def _save_provider_to_db(provider: str, data: dict):
    """保存单个提供商配置到数据库。"""
    db = _get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 记录版本：保存 API 密钥配置前先读取旧值 ──
    old_row = db.execute(
        "SELECT * FROM api_keys WHERE provider = ?", (provider,)
    ).fetchone()
    if old_row:
        old_dict = dict(old_row)
        # 对旧密钥进行脱敏处理
        if "api_key" in old_dict and old_dict["api_key"]:
            old_dict["api_key"] = mask_key(old_dict["api_key"])
        old_val = json.dumps(old_dict, ensure_ascii=False, default=str)
    else:
        old_val = ""
    # 对新密钥进行脱敏处理
    new_data = data.copy()
    if "api_key" in new_data and new_data["api_key"]:
        new_data["api_key"] = mask_key(new_data["api_key"])
    new_val = json.dumps(new_data, ensure_ascii=False, default=str)
    db.execute(
        "INSERT INTO config_versions (target_type, target_id, old_value, new_value) VALUES (?, ?, ?, ?)",
        ("api_key", provider, old_val, new_val),
    )

    db.execute(
        """INSERT INTO api_keys (provider, api_key, base_url, text_model, vision_model,
           is_default, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 0, ?, ?)
           ON CONFLICT(provider) DO UPDATE SET
           api_key=excluded.api_key, base_url=excluded.base_url,
           text_model=excluded.text_model, vision_model=excluded.vision_model,
           updated_at=excluded.updated_at""",
        (
            provider,
            data.get("api_key", ""),
            data.get("base_url", ""),
            data.get("text_model", ""),
            data.get("vision_model", ""),
            now, now,
        ),
    )
    db.commit()


def _set_default_provider(provider: str):
    """设置默认提供商。"""
    db = _get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE api_keys SET is_default=0")
    db.execute(
        "UPDATE api_keys SET is_default=1, updated_at=? WHERE provider=?",
        (now, provider),
    )
    db.commit()


# ── 连接测试 ────────────────────────────────────────────

def _test_connection(provider: str, api_key: str, base_url: str,
                     text_model: str) -> dict:
    """测试 LLM 提供商连通性。"""
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=base_url.rstrip("/") + "/" if base_url else "https://api.openai.com/v1/",
            api_key=api_key or "ollama",
            timeout=15,
        )

        start = time.time()
        models = client.models.list()
        elapsed_ms = int((time.time() - start) * 1000)

        model_ids = [m.id for m in (models.data or [])]
        return {
            "ok": True,
            "models": model_ids[:20],
            "model_count": len(model_ids),
            "elapsed_ms": elapsed_ms,
            "message": f"连接成功，获取到 {len(model_ids)} 个模型",
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "message": f"连接失败: {e}",
        }


# ── 费用估算 ────────────────────────────────────────────

_PRICE_PER_MTOK = {
    "zhipu": {"input": 0.003, "output": 0.006},
    "deepseek": {"input": 0.001, "output": 0.002},
    "openai": {"input": 0.015, "output": 0.060},
    "doubao": {"input": 0.0008, "output": 0.002},
    "ollama": {"input": 0, "output": 0},
}

_session_tokens = {"input": 0, "output": 0, "calls": 0}


def _get_cost_stats() -> dict:
    """获取费用统计。"""
    providers_data = _load_providers_from_db()
    stats = []
    total_cost = 0.0
    total_input = 0
    total_output = 0
    total_calls = 0

    try:
        from v7.llm import LLMFactory
        factory = LLMFactory()
        adapter_stats = factory.get_stats()

        for key, adapter_stat in adapter_stats.items():
            parts = key.split("_", 1)
            provider = parts[1] if len(parts) > 1 else parts[0]
            calls = adapter_stat.get("total_calls", 0)
            success_rate = adapter_stat.get("success_rate", 0)
            avg_latency = adapter_stat.get("avg_latency_ms", 0)
            estimated_tokens = calls * 2000
            price = _PRICE_PER_MTOK.get(provider, {"input": 0.001, "output": 0.002})
            est_cost = (estimated_tokens / 1_000_000) * (
                price["input"] + price["output"]
            )
            stats.append({
                "provider": provider,
                "name": _PROVIDER_MAP.get(provider, {}).get("name", provider),
                "calls": calls,
                "success_rate": round(success_rate * 100, 1),
                "avg_latency_ms": round(avg_latency, 1),
                "est_tokens": estimated_tokens,
                "est_cost": round(est_cost, 4),
                "is_default": providers_data.get(provider, {}).get("is_default", False),
            })
            total_cost += est_cost
            total_calls += calls
            total_input += int(estimated_tokens * 0.6)
            total_output += int(estimated_tokens * 0.4)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"统计费用失败: {e}")
        stats = []

    return {
        "by_provider": stats,
        "total_cost": round(total_cost, 4),
        "total_calls": total_calls,
        "total_tokens": total_input + total_output,
        "session_tokens": _session_tokens,
    }


# ══════════════════════════════════════════════════════════
#  HTML 渲染
# ══════════════════════════════════════════════════════════

_CSS = """
<style>
.apic-wrap{font:14px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;color:#333}
.apic-wrap h2{font-size:17px;margin:0 0 14px;padding-bottom:8px;border-bottom:2px solid #16213e}
.apic-wrap h3{font-size:15px;margin:0 0 10px}
.apic-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px;margin-bottom:20px}
.apic-card{background:#fff;border-radius:8px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,.08);border-left:4px solid #ccc}
.apic-card h4{font-size:14px;margin:0 0 12px;display:flex;align-items:center;gap:6px}
.apic-card .dot{display:inline-block;width:10px;height:10px;border-radius:50%;flex-shrink:0}
.apic-field{margin-bottom:10px}
.apic-field label{display:block;font-size:12px;color:#666;margin-bottom:3px}
.apic-field input[type=text],.apic-field input[type=password]{width:100%;padding:6px 10px;border:1px solid #ddd;border-radius:4px;font-size:13px;box-sizing:border-box}
.apic-field input:focus{border-color:#16213e;outline:none;box-shadow:0 0 0 2px rgba(22,33,62,.1)}
.apic-field input[readonly]{background:#f9f9f9;color:#999}
.apic-actions{display:flex;gap:8px;margin-top:12px}
.apic-btn{padding:6px 16px;border:none;border-radius:4px;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;gap:4px}
.apic-btn-save{background:#16213e;color:#fff}
.apic-btn-save:hover{background:#0f1a30}
.apic-btn-test{background:#27ae60;color:#fff}
.apic-btn-test:hover{background:#1e8449}
.apic-btn-default{background:#e67e22;color:#fff}
.apic-btn-default:hover{background:#c0651f}
.apic-btn:disabled{opacity:.5;cursor:not-allowed}
.apic-default-badge{font-size:11px;background:#e67e22;color:#fff;padding:1px 7px;border-radius:10px;margin-left:6px}
.apic-toast{position:fixed;top:20px;right:20px;padding:12px 20px;border-radius:6px;color:#fff;font-size:14px;z-index:9999;display:none;max-width:400px;word-break:break-all}
.apic-toast-success{background:#27ae60}
.apic-toast-error{background:#c0392b}
.apic-toast-info{background:#2980b9}
.apic-test-result{margin-top:8px;font-size:12px;padding:8px;border-radius:4px;display:none}
.apic-test-result .ok{color:#27ae60}
.apic-test-result .fail{color:#c0392b}

/* 费用统计面板 */
.apic-cost-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:18px}
.apic-cost-card{background:#fff;border-radius:8px;padding:18px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.apic-cost-card .cost-num{font-size:28px;font-weight:bold;color:#16213e}
.apic-cost-card .cost-label{font-size:12px;color:#888;margin-top:4px}
.apic-cost-card .cost-sub{font-size:11px;color:#aaa;margin-top:2px}

/* SVG 饼图 */
.apic-chart-row{display:flex;gap:20px;flex-wrap:wrap}
.apic-pie-wrap{flex:0 0 280px}
.apic-table-wrap{flex:1;min-width:300px}
.apic-table{table-layout:fixed}
.apic-table th,.apic-table td{padding:7px 10px;font-size:12px;border-bottom:1px solid #eee;text-align:left}
.apic-table th{background:#f8f9fa;font-weight:600}
.apic-table tr:hover{background:#f5f6fa}
.apic-color-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle}
.apic-bar-wrap{display:inline-block;width:80px;height:6px;background:#eee;border-radius:3px;vertical-align:middle;margin:0 6px;overflow:hidden}
.apic-bar{display:block;height:100%;border-radius:3px;background:#16213e}
</style>
"""


def _provider_card(prov: dict, db_data: dict) -> str:
    """渲染单个提供商卡片。"""
    p = prov["provider"]
    db = db_data.get(p, {})
    api_key = db.get("api_key", "")
    base_url = db.get("base_url") or prov["default_base_url"]
    text_model = db.get("text_model") or prov["default_text_model"]
    vision_model = db.get("vision_model") or prov["default_vision_model"]
    is_default = db.get("is_default", False)

    masked = mask_key(api_key)
    default_html = ' <span class="apic-default-badge">默认</span>' if is_default else ""
    checked_attr = ' checked' if is_default else ""

    return f"""
<div class="apic-card" style="border-left-color:{prov['color']}" data-provider="{p}">
  <h4>
    <span class="dot" style="background:{prov['color']}"></span>
    {prov['name']}{default_html}
  </h4>
  <div class="apic-field">
    <label>API Base URL</label>
    <input type="text" class="apic-base-url" value="{_h(base_url)}" placeholder="API地址">
  </div>
  <div class="apic-field">
    <label>Text Model</label>
    <input type="text" class="apic-text-model" value="{_h(text_model)}" placeholder="文本模型">
  </div>
  <div class="apic-field">
    <label>Vision Model</label>
    <input type="text" class="apic-vision-model" value="{_h(vision_model)}" placeholder="视觉模型（可选）">
  </div>
  <div class="apic-field">
    <label>API Key</label>
    <input type="password" class="apic-api-key" value="{_h(api_key)}" data-masked="{_h(masked)}" placeholder="sk-..." style="font-family:Consolas,monospace">
  </div>
  <div class="apic-field" style="margin-bottom:8px">
    <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
      <input type="radio" name="default-provider" value="{p}" class="apic-default-radio" onchange="setDefault(this.value)"{checked_attr}>
      <span style="font-size:12px">设为默认提供商</span>
    </label>
  </div>
  <div class="apic-actions">
    <button class="apic-btn apic-btn-save" onclick="saveConfig('{p}')">保存</button>
    <button class="apic-btn apic-btn-test" onclick="testConnection('{p}')">测试连接</button>
  </div>
  <div class="apic-test-result" id="test-{p}"></div>
</div>"""


def _cost_panel() -> str:
    """渲染费用统计面板。"""
    stats = _get_cost_stats()
    by_provider = stats["by_provider"]

    # 总费用卡片
    cost_cards = f"""
<div class="apic-cost-card">
  <div class="cost-num">¥{stats['total_cost']:.4f}</div>
  <div class="cost-label">累计费用估算</div>
</div>
<div class="apic-cost-card">
  <div class="cost-num">{stats['total_calls']}</div>
  <div class="cost-label">总调用次数</div>
</div>
<div class="apic-cost-card">
  <div class="cost-num">{stats['total_tokens']:,}</div>
  <div class="cost-label">累计Token</div>
</div>
<div class="apic-cost-card">
  <div class="cost-num">{stats['session_tokens']['input'] + stats['session_tokens']['output']:,}</div>
  <div class="cost-label">本次会话Token</div>
  <div class="cost-sub">调用 {stats['session_tokens']['calls']} 次</div>
</div>
"""

    # SVG 饼图
    pie_html = _render_pie_chart(by_provider)

    # 按提供商表格
    table_rows = ""
    for item in by_provider:
        calls = item["calls"]
        pct = (calls / stats["total_calls"] * 100) if stats["total_calls"] > 0 else 0
        table_rows += f"""
<tr>
  <td><span class="apic-color-dot" style="background:{_PROVIDER_MAP.get(item['provider'], {}).get('color', '#999')}"></span>{item['name']}</td>
  <td>{calls}</td>
  <td>{item['est_tokens']:,}</td>
  <td>¥{item['est_cost']:.4f}</td>
  <td>{item['success_rate']}%</td>
  <td>{item['avg_latency_ms']}ms</td>
  <td><span class="apic-bar-wrap"><span class="apic-bar" style="width:{min(pct,100)}%"></span></span>{pct:.1f}%</td>
</tr>"""

    if not table_rows:
        table_rows = '<tr><td colspan="7" style="text-align:center;color:#999;padding:20px">暂无调用记录</td></tr>'

    return f"""
<h2 style="margin-top:28px">费用统计</h2>
<div class="apic-cost-grid">{cost_cards}</div>
<div class="apic-chart-row">
  <div class="apic-pie-wrap">
    <div class="apic-card" style="border-left-color:#16213e">
      <h3>各提供商费用分布</h3>
      {pie_html}
    </div>
  </div>
  <div class="apic-table-wrap">
    <div class="apic-card" style="border-left-color:#16213e">
      <h3>各提供商调用详情</h3>
      <table class="apic-table" style="width:100%">
        <thead><tr>
          <th>提供商</th><th>调用数</th><th>Token</th><th>费用</th><th>成功率</th><th>延迟</th><th>占比</th>
        </tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>
  </div>
</div>
"""


def _render_pie_chart(by_provider: list) -> str:
    """用纯 SVG 渲染费用饼图。"""
    if not by_provider or sum(p["est_cost"] for p in by_provider) == 0:
        return '<div style="text-align:center;padding:30px;color:#999">暂无费用数据</div>'

    total = sum(p["est_cost"] for p in by_provider)
    if total <= 0:
        return '<div style="text-align:center;padding:30px;color:#999">暂无费用数据</div>'

    cx, cy, r = 100, 100, 80
    slices = []
    current_angle = 0

    for item in by_provider:
        pct = item["est_cost"] / total
        if pct <= 0:
            continue
        color = _PROVIDER_MAP.get(item["provider"], {}).get("color", "#999")
        sweep = pct * 360
        start_angle = current_angle
        end_angle = current_angle + sweep
        current_angle = end_angle

        x1 = cx + r * _cos_deg(start_angle)
        y1 = cy + r * _sin_deg(start_angle)
        x2 = cx + r * _cos_deg(end_angle)
        y2 = cy + r * _sin_deg(end_angle)

        large = 1 if sweep > 180 else 0
        path = f"M {cx} {cy} L {x1:.2f} {y1:.2f} A {r} {r} 0 {large} 1 {x2:.2f} {y2:.2f} Z"
        slices.append(f'<path d="{path}" fill="{color}" stroke="#fff" stroke-width="1.5"><title>{_h(item["name"])}: ¥{item["est_cost"]:.4f} ({pct*100:.1f}%)</title></path>')

    # 图例
    legend_items = ""
    for i, item in enumerate(by_provider):
        if item["est_cost"] <= 0:
            continue
        color = _PROVIDER_MAP.get(item["provider"], {}).get("color", "#999")
        pct = item["est_cost"] / total * 100
        legend_items += f"""
      <div style="display:inline-flex;align-items:center;margin:3px 10px;font-size:11px">
        <span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:{color};margin-right:4px"></span>
        {_h(item['name'])} {pct:.1f}%
      </div>"""

    return f"""
<svg viewBox="0 0 200 200" style="width:200px;height:200px;display:block;margin:0 auto">
  {"".join(slices)}
</svg>
<div style="text-align:center;margin-top:6px;color:#888;font-size:11px">共 ¥{total:.4f}</div>
<div style="text-align:center;margin-top:8px">{legend_items}</div>
"""


def _h(s: str) -> str:
    """HTML 转义。"""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _cos_deg(angle: float) -> float:
    import math
    return math.cos(math.radians(angle - 90))


def _sin_deg(angle: float) -> float:
    import math
    return math.sin(math.radians(angle - 90))


# ── JS 脚本 ────────────────────────────────────────────

_SCRIPT = """
function toast(msg, type) {
  var el = document.getElementById('apic-toast');
  el.textContent = msg;
  el.className = 'apic-toast apic-toast-' + (type || 'info');
  el.style.display = 'block';
  setTimeout(function() { el.style.display = 'none'; }, 3000);
}

async function saveConfig(provider) {
  var card = document.querySelector('.apic-card[data-provider="' + provider + '"]');
  var baseUrl = card.querySelector('.apic-base-url').value.trim();
  var textModel = card.querySelector('.apic-text-model').value.trim();
  var visionModel = card.querySelector('.apic-vision-model').value.trim();
  var apiKey = card.querySelector('.apic-api-key').value.trim();

  try {
    var res = await fetch('/admin/api/api-config/' + provider, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: baseUrl,
        text_model: textModel,
        vision_model: visionModel,
        api_key: apiKey
      })
    });
    var data = await res.json();
    if (data.ok) {
      toast('[' + provider + '] 保存成功', 'success');
      // 更新脱敏显示
      var masked = data.masked_key || '';
      card.querySelector('.apic-api-key').setAttribute('data-masked', masked);
    } else {
      toast('保存失败: ' + (data.error || '未知错误'), 'error');
    }
  } catch (e) {
    toast('请求异常: ' + e.message, 'error');
  }
}

async function testConnection(provider) {
  var card = document.querySelector('.apic-card[data-provider="' + provider + '"]');
  var resultEl = document.getElementById('test-' + provider);
  var apiKey = card.querySelector('.apic-api-key').value.trim();
  var baseUrl = card.querySelector('.apic-base-url').value.trim();
  var textModel = card.querySelector('.apic-text-model').value.trim();

  resultEl.style.display = 'block';
  resultEl.innerHTML = '<span style="color:#888">正在测试连接...</span>';

  try {
    var res = await fetch('/admin/api/api-config/' + provider + '/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: apiKey,
        base_url: baseUrl,
        text_model: textModel
      })
    });
    var data = await res.json();
    if (data.ok) {
      resultEl.innerHTML = '<span class="ok">连接成功! 获取到 ' + data.model_count + ' 个模型 (' + data.elapsed_ms + 'ms)</span>';
      toast('[' + provider + '] 连接测试成功', 'success');
    } else {
      resultEl.innerHTML = '<span class="fail">连接失败: ' + (data.error || '未知错误') + '</span>';
      toast('[' + provider + '] ' + (data.message || '连接失败'), 'error');
    }
  } catch (e) {
    resultEl.innerHTML = '<span class="fail">请求异常: ' + _h_js(e.message) + '</span>';
  }
}

async function setDefault(provider) {
  if (!confirm('确定将 ' + provider + ' 设为默认LLM提供商吗？')) return;

  try {
    var res = await fetch('/admin/api/api-config/default', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: provider })
    });
    var data = await res.json();
    if (data.ok) {
      toast(provider + ' 已设为默认提供商', 'success');
      setTimeout(function() { location.reload(); }, 800);
    } else {
      toast('设置失败: ' + (data.error || '未知错误'), 'error');
    }
  } catch (e) {
    toast('请求异常: ' + e.message, 'error');
  }
}

// 密码框悬停/聚焦时显示部分明文（数据已脱敏存储，此处为UX辅助）
document.addEventListener('DOMContentLoaded', function() {
  var inputs = document.querySelectorAll('.apic-api-key');
  inputs.forEach(function(inp) {
    var realValue = inp.value;
    inp.addEventListener('focus', function() {
      this.type = 'text';
    });
    inp.addEventListener('blur', function() {
      this.type = 'password';
    });
  });
});

function _h_js(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
"""


# ══════════════════════════════════════════════════════════
#  公开 API
# ══════════════════════════════════════════════════════════

def render_page() -> str:
    """返回 API 配置与费用统计页面的 HTML 内容（不含外层框架）。"""
    db_data = _load_providers_from_db()

    cards = ""
    for prov in _PROVIDERS:
        cards += _provider_card(prov, db_data)

    cost_html = _cost_panel()

    return f"""<div class="apic-wrap">
{_CSS}
<div id="apic-toast" class="apic-toast"></div>

<h2>LLM 提供商配置</h2>
<div class="apic-grid">
{cards}
</div>

{cost_html}

<script>
{_SCRIPT}
</script>
</div>"""


def handle_api(path: str, method: str, body: dict, qs: dict) -> tuple:
    """处理 API 配置相关的 API 请求。

    Args:
        path: 请求路径
        method: HTTP 方法 (GET/POST/PUT)
        body: JSON 请求体 (dict)
        qs: 查询参数字典

    Returns:
        (status_code, data, content_type) 或 None（不匹配此模块）
    """
    prefix = "/admin/api/api-config"
    if not path.startswith(prefix):
        return None

    sub = path[len(prefix):].rstrip("/")
    content_type = "application/json; charset=utf-8"

    # ── GET /admin/api/api-config/list ──
    if method == "GET" and sub in ("", "/list"):
        db_data = _load_providers_from_db()
        items = []
        for prov in _PROVIDERS:
            p = prov["provider"]
            db = db_data.get(p, {})
            raw_key = db.get("api_key", "")
            items.append({
                "provider": p,
                "name": prov["name"],
                "base_url": db.get("base_url") or prov["default_base_url"],
                "text_model": db.get("text_model") or prov["default_text_model"],
                "vision_model": db.get("vision_model") or prov["default_vision_model"],
                "api_key_masked": mask_key(raw_key),
                "has_key": bool(raw_key),
                "is_default": db.get("is_default", False),
                "updated_at": db.get("updated_at", ""),
            })
        return 200, {"ok": True, "providers": items, "total": len(items)}, content_type

    # ── PUT /admin/api/api-config/{provider} ──
    if method == "PUT" and sub.startswith("/") and "/test" not in sub and sub != "/default":
        provider = sub.lstrip("/")
        if provider not in _PROVIDER_MAP:
            return 400, {"ok": False, "error": f"未知提供商: {provider}"}, content_type

        try:
            _save_provider_to_db(provider, body)
            return 200, {
                "ok": True,
                "provider": provider,
                "masked_key": mask_key(body.get("api_key", "")),
            }, content_type
        except Exception as e:
            return 500, {"ok": False, "error": str(e)}, content_type

    # ── POST /admin/api/api-config/{provider}/test ──
    if method == "POST" and sub.startswith("/") and sub.endswith("/test"):
        provider = sub[1:-len("/test")]
        if provider not in _PROVIDER_MAP:
            return 400, {"ok": False, "error": f"未知提供商: {provider}"}, content_type

        api_key = body.get("api_key", "")
        base_url = body.get("base_url", _PROVIDER_MAP[provider]["default_base_url"])
        text_model = body.get("text_model", _PROVIDER_MAP[provider]["default_text_model"])

        result = _test_connection(provider, api_key, base_url, text_model)
        status = 200 if result["ok"] else 502
        return status, result, content_type

    # ── PUT /admin/api/api-config/default ──
    if method == "PUT" and sub == "/default":
        provider = body.get("provider", "")
        if provider not in _PROVIDER_MAP:
            return 400, {"ok": False, "error": f"未知提供商: {provider}"}, content_type

        try:
            _set_default_provider(provider)
            return 200, {"ok": True, "provider": provider}, content_type
        except Exception as e:
            return 500, {"ok": False, "error": str(e)}, content_type

    # ── GET /admin/api/api-config/costs ──
    if method == "GET" and sub == "/costs":
        stats = _get_cost_stats()
        return 200, {"ok": True, **stats}, content_type

    return 404, {"ok": False, "error": "unknown api-config endpoint"}, content_type
