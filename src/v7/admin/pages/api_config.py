# -*- coding: utf-8 -*-
"""API 配置页面模块 — 生产级实现（内置国产最新模型）

核心设计：
- 内置智谱、DeepSeek、通义千问最新模型（来自官方文档）
- 用户只需：选择厂商 → 选择模型 → 输入 KEY
- URL 和限流策略自动匹配
- 支持自定义模型（高级模式）

导出:
  render_page() -> str
  handle_api(path, method, body, qs) -> (status, data, content_type) or None
"""

import json
from datetime import datetime


# ══════════════════════════════════════════════════════════
#  内置模型库（来自各厂商官方文档，2026-06-22）
# ══════════════════════════════════════════════════════════

_BUILTIN_PROVIDERS = {
    "zhipu": {
        "name": "智谱AI",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "text_models": [
            {"id": "glm-4.7-flash", "name": "GLM-4.7-Flash", "price": "免费", "context": "200K", "rpm": 1000, "concurrent": 100},
            {"id": "glm-4.7-flashx", "name": "GLM-4.7-FlashX", "price": "¥0.5/百万token", "context": "200K", "rpm": 500, "concurrent": 50},
            {"id": "glm-4.5-air", "name": "GLM-4.5-Air", "price": "¥0.8/百万token", "context": "128K", "rpm": 300, "concurrent": 30},
            {"id": "glm-4.7", "name": "GLM-4.7", "price": "¥2-4/百万token", "context": "200K", "rpm": 200, "concurrent": 20},
            {"id": "glm-5", "name": "GLM-5", "price": "¥4-6/百万token", "context": "128K", "rpm": 100, "concurrent": 10},
            {"id": "glm-5-turbo", "name": "GLM-5-Turbo", "price": "¥5-7/百万token", "context": "128K", "rpm": 100, "concurrent": 10},
            {"id": "glm-5.1", "name": "GLM-5.1", "price": "¥6-8/百万token", "context": "128K", "rpm": 80, "concurrent": 8},
            {"id": "glm-5.2", "name": "GLM-5.2", "price": "¥8-28/百万token", "context": "1M", "rpm": 50, "concurrent": 5},
        ],
        "vision_models": [
            {"id": "glm-4.6v-flash", "name": "GLM-4.6V-Flash", "price": "免费", "context": "8K", "rpm": 1000, "concurrent": 100},
            {"id": "glm-4.6v-flashx", "name": "GLM-4.6V-FlashX", "price": "¥0.15-0.3/百万token", "context": "8K", "rpm": 500, "concurrent": 50},
            {"id": "glm-4.5v", "name": "GLM-4.5V", "price": "¥2-4/百万token", "context": "64K", "rpm": 300, "concurrent": 30},
            {"id": "glm-4.6v", "name": "GLM-4.6V", "price": "¥1-2/百万token", "context": "8K", "rpm": 200, "concurrent": 20},
            {"id": "glm-5v-turbo", "name": "GLM-5V-Turbo", "price": "¥5-7/百万token", "context": "32K", "rpm": 100, "concurrent": 10},
        ],
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "text_models": [
            {"id": "deepseek-v4-flash", "name": "DeepSeek-V4-Flash", "price": "约¥1/百万token", "context": "128K", "rpm": 2500, "concurrent": 2500},
            {"id": "deepseek-v4-pro", "name": "DeepSeek-V4-Pro", "price": "约¥5/百万token", "context": "128K", "rpm": 500, "concurrent": 500},
        ],
        "vision_models": [],
        "vision_note": "DeepSeek 暂不支持视觉模型，图纸识别请配合智谱/通义千问使用",
    },
    "qwen": {
        "name": "通义千问（阿里云百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "text_models": [
            {"id": "qwen3.6-flash", "name": "Qwen3.6-Flash", "price": "免费（100万token/月）", "context": "128K", "rpm": 1000, "concurrent": 100},
            {"id": "qwen3.6-plus", "name": "Qwen3.6-Plus", "price": "¥2/百万token", "context": "128K", "rpm": 500, "concurrent": 50},
            {"id": "qwen3.6-max-preview", "name": "Qwen3.6-Max", "price": "¥10/百万token", "context": "128K", "rpm": 200, "concurrent": 20},
        ],
        "vision_models": [
            {"id": "qwen3.6-plus", "name": "Qwen3.6-Plus（多模态）", "price": "¥2/百万token", "context": "128K", "rpm": 500, "concurrent": 50},
            {"id": "qwen3.5-omni-plus", "name": "Qwen3.5-Omni-Plus", "price": "¥5/百万token", "context": "128K", "rpm": 300, "concurrent": 30},
        ],
    },
    "doubao": {
        "name": "豆包（火山方舟）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "text_models": [
            {"id": "ep-20250101-text-001", "name": "Doubao-Seed-1.6（文本）", "price": "按量计费", "context": "128K", "rpm": 500, "concurrent": 50, "note": "需替换为您的Endpoint ID"},
        ],
        "vision_models": [
            {"id": "ep-20250101-vision-001", "name": "Doubao-Seed-Vision-1.6（视觉）", "price": "按量计费", "context": "128K", "rpm": 300, "concurrent": 30, "note": "需替换为您的Endpoint ID"},
        ],
        "note": "⚠ 豆包必须使用Endpoint ID（非模型名）。请在火山方舟控制台创建推理接入点后，将Endpoint ID填入下方'自定义模型名称'字段。",
        "endpoint_guide": [
            "1. 登录火山方舟控制台: https://console.volcengine.com/ark",
            "2. 左侧菜单选择'在线推理' → '推理接入点'",
            "3. 点击'创建接入点'，选择模型（如 Doubao-Seed-1.6）",
            "4. 创建完成后，复制接入点ID（格式如 ep-20250101-xxxx）",
            "5. 将Endpoint ID粘贴到下方'自定义模型名称'字段",
            "6. 从'API Key管理'创建并复制Key，粘贴到API Key字段",
        ],
    },
}

_ALL_MODELS = []
for prov_id, prov in _BUILTIN_PROVIDERS.items():
    for m in prov.get("text_models", []):
        _ALL_MODELS.append({**m, "provider": prov_id, "provider_name": prov["name"], "type": "text", "base_url": prov["base_url"]})
    for m in prov.get("vision_models", []):
        _ALL_MODELS.append({**m, "provider": prov_id, "provider_name": prov["name"], "type": "vision", "base_url": prov["base_url"]})


def _get_db():
    from v7.db import get_db
    return get_db()


def _load_config():
    """加载文本和视觉模型的独立配置。"""
    db = _get_db()
    from v7.crypto_utils import is_encrypted, decrypt_text
    result = {"text": {}, "vision": {}}
    for purpose in ("text", "vision"):
        row = db.execute(
            "SELECT provider, api_key, base_url, model FROM llm_configs WHERE purpose=?",
            (purpose,),
        ).fetchone()
        if row:
            key = row["api_key"]
            if key and is_encrypted(key):
                key = decrypt_text(key)
            result[purpose] = {
                "provider": row["provider"],
                "api_key": key,
                "base_url": row["base_url"],
                "model": row["model"],
            }
    return result


def _save_config(purpose: str, data: dict):
    """保存单个用途的配置到数据库。"""
    db = _get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    from v7.crypto_utils import encrypt_text, is_encrypted

    api_key = data.get("api_key", "")
    if api_key and not is_encrypted(api_key):
        api_key = encrypt_text(api_key)

    db.execute(
        """INSERT INTO llm_configs (purpose, provider, api_key, base_url, model, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(purpose) DO UPDATE SET
           provider=excluded.provider, api_key=excluded.api_key,
           base_url=excluded.base_url, model=excluded.model,
           updated_at=excluded.updated_at""",
        (purpose, data.get("provider", ""), api_key,
         data.get("base_url", ""), data.get("model", ""), now),
    )
    db.commit()


# ── CSS ─────────────────────────────────────────────────
_CSS = """
<style>
.apic-wrap { max-width:1200px; margin:0 auto; padding:20px; }
.apic-card { background:#fff; border:1px solid #e0e0e0; border-radius:10px; padding:20px; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,0.06); }
.apic-card h3 { margin:0 0 16px 0; font-size:16px; color:#333; }
.apic-field { margin-bottom:14px; }
.apic-field label { display:block; font-size:13px; font-weight:600; color:#444; margin-bottom:5px; }
.apic-field input, .apic-field select { width:100%; padding:8px 12px; border:1px solid #d0d0d0; border-radius:6px; font-size:14px; box-sizing:border-box; }
.apic-field input:focus, .apic-field select:focus { outline:none; border-color:#1677ff; }
.apic-field .hint { font-size:11px; color:#888; margin-top:3px; }
.apic-btn { padding:8px 20px; border:none; border-radius:6px; font-size:14px; cursor:pointer; margin-right:8px; }
.apic-btn-save { background:#1677ff; color:#fff; }
.apic-btn-save:hover { background:#125fd9; }
.apic-btn-test { background:#f0f0f0; color:#333; border:1px solid #d0d0d0; }
.apic-btn-test:hover { background:#e0e0e0; }
.apic-toast { position:fixed; top:20px; right:20px; padding:12px 20px; border-radius:8px; color:#fff; font-size:14px; display:none; z-index:9999; }
.apic-toast.ok { background:#27ae60; display:block; }
.apic-toast.err { background:#e74c3c; display:block; }
.apic-toast.warn { background:#f39c12; display:block; }
.apic-result { margin-top:10px; padding:10px; border-radius:6px; font-size:13px; display:none; }
.apic-result.ok { background:#e8f5e9; color:#2e7d32; border:1px solid #a5d6a7; display:block; }
.apic-result.err { background:#ffebee; color:#c62828; border:1px solid #ef9a9a; display:block; }
.model-info { background:#f8f9fa; border:1px solid #e9ecef; border-radius:6px; padding:10px; margin-top:8px; font-size:12px; color:#555; }
.model-info table { width:100%; border-collapse:collapse; }
.model-info td { padding:3px 8px; }
.model-info td:first-child { color:#888; width:80px; }
.tag-free { background:#27ae60; color:#fff; font-size:10px; padding:1px 6px; border-radius:10px; margin-left:4px; }
.tag-rec { background:#e67e22; color:#fff; font-size:10px; padding:1px 6px; border-radius:10px; margin-left:4px; }
</style>
"""


def _h(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _mask_key(key: str) -> str:
    """API Key掩码显示：前6位 + **** + 后4位"""
    if not key:
        return ""
    if len(key) <= 10:
        return "****"
    return key[:6] + "****" + key[-4:]


def _build_model_options(selected_model: str, model_type: str) -> str:
    """构建模型下拉选项，按厂商分组。"""
    options = ['<option value="">— 请选择模型 —</option>']
    current_prov = ""
    for m in _ALL_MODELS:
        if m["type"] != model_type:
            continue
        prov = m["provider"]
        if prov != current_prov:
            if current_prov:
                options.append("</optgroup>")
            prov_name = _BUILTIN_PROVIDERS[prov]["name"]
            options.append(f'<optgroup label="{_h(prov_name)}">')
            current_prov = prov
        sel = ' selected' if m["id"] == selected_model else ""
        free_tag = ' <span class="tag-free">免费</span>' if "免费" in m["price"] else ""
        rec_tag = ' <span class="tag-rec">推荐</span>' if m["id"] in ("glm-4.7-flash", "deepseek-v4-flash", "qwen3.6-flash") else ""
        options.append(f'<option value="{_h(m["id"])}" data-provider="{_h(prov)}" data-url="{_h(m["base_url"])}" data-rpm="{_h(str(m.get("rpm","")))}" data-concurrent="{_h(str(m.get("concurrent","")))}" data-price="{_h(m["price"])}" data-context="{_h(m["context"])}"{sel}>{_h(m["name"])}{free_tag}{rec_tag}</option>')
    if current_prov:
        options.append("</optgroup>")
    # 自定义选项
    sel = ' selected' if selected_model and not any(m["id"] == selected_model for m in _ALL_MODELS) else ""
    options.append(f'<option value="custom"{sel}>— 自定义模型（高级）—</option>')
    return "\n".join(options)


def render_page() -> str:
    cfg = _load_config()
    text_cfg = cfg.get("text", {})
    vision_cfg = cfg.get("vision", {})

    text_opts = _build_model_options(text_cfg.get("model", ""), "text")
    vision_opts = _build_model_options(vision_cfg.get("model", ""), "vision")

    # 检查是否有自定义模型
    text_is_custom = text_cfg.get("model") and not any(m["id"] == text_cfg.get("model") for m in _ALL_MODELS)
    vision_is_custom = vision_cfg.get("model") and not any(m["id"] == vision_cfg.get("model") for m in _ALL_MODELS)

    return f"""<div class="apic-wrap">
{_CSS}
<div id="apic-toast" class="apic-toast"></div>

<div style="background:#f0f7ff;border:1px solid #b3d8ff;border-radius:8px;padding:14px 18px;margin-bottom:16px;font-size:13px;line-height:1.7;color:#333">
  <div style="font-weight:600;margin-bottom:6px;color:#1677ff">📘 快速配置</div>
  <div>1. 选择内置模型（自动匹配 URL 和限流策略）</div>
  <div>2. 粘贴从厂商控制台获取的 API Key</div>
  <div>3. 点击保存即可</div>
</div>

<!-- 文本模型配置 -->
<div class="apic-card">
  <h3>📝 文本模型（规范条文审查）</h3>
  <div class="apic-field">
    <label>选择模型</label>
    <select id="text-model" onchange="onModelChange('text')">
      {text_opts}
    </select>
    <div class="hint">带 <span class="tag-free">免费</span> 标签的模型有免费额度；带 <span class="tag-rec">推荐</span> 标签的为综合性价比最高</div>
  </div>
  <div id="text-model-info" class="model-info" style="display:none"></div>
  <div class="apic-field" id="text-custom-model" style="display:{'block' if text_is_custom else 'none'}">
    <label>自定义模型名称</label>
    <input type="text" id="text-custom-name" value="{_h(text_cfg.get('model', '') if text_is_custom else '')}" placeholder="输入模型ID">
  </div>
  <div class="apic-field" id="text-custom-url" style="display:{'block' if text_is_custom else 'none'}">
    <label>自定义 API URL</label>
    <input type="text" id="text-custom-url-input" value="{_h(text_cfg.get('base_url', ''))}" placeholder="https://...">
  </div>
  <div class="apic-field">
    <label>API Key</label>
    <input type="password" id="text-key" value="{_h(_mask_key(text_cfg.get('api_key', '')))}" placeholder="从厂商控制台获取">
    <div class="hint">您的 Key 仅存储在本地数据库中，已加密保护</div>
  </div>
  <div>
    <button class="apic-btn apic-btn-save" id="btn-save-text">保存文本模型配置</button>
    <button class="apic-btn apic-btn-test" id="btn-test-text">测试连接</button>
  </div>
  <div id="text-result" class="apic-result"></div>
</div>

<!-- 视觉模型配置 -->
<div class="apic-card">
  <h3>🖼️ 视觉模型（图纸识别）</h3>
  <div class="apic-field">
    <label>选择模型</label>
    <select id="vision-model">
      {vision_opts}
    </select>
    <div class="hint">如需图纸识别功能，请选择带视觉能力的模型</div>
  </div>
  <div id="vision-model-info" class="model-info" style="display:none"></div>
  <div id="vision-note" style="font-size:12px;color:#e67e22;margin-bottom:10px"></div>
  <div class="apic-field" id="vision-custom-model" style="display:{'block' if vision_is_custom else 'none'}">
    <label>自定义模型名称</label>
    <input type="text" id="vision-custom-name" value="{_h(vision_cfg.get('model', '') if vision_is_custom else '')}" placeholder="输入模型ID">
  </div>
  <div class="apic-field" id="vision-custom-url" style="display:{'block' if vision_is_custom else 'none'}">
    <label>自定义 API URL</label>
    <input type="text" id="vision-custom-url-input" value="{_h(vision_cfg.get('base_url', ''))}" placeholder="https://...">
  </div>
  <div class="apic-field">
    <label>API Key</label>
    <input type="password" id="vision-key" value="{_h(_mask_key(vision_cfg.get('api_key', '')))}" placeholder="从厂商控制台获取">
    <div class="hint">您的 Key 仅存储在本地数据库中，已加密保护</div>
  </div>
  <div>
    <button class="apic-btn apic-btn-save" id="btn-save-vision">保存视觉模型配置</button>
    <button class="apic-btn apic-btn-test" id="btn-test-vision">测试连接</button>
  </div>
  <div id="vision-result" class="apic-result"></div>
</div>

<script src="/static/api_config.js"></script>
</div>"""


# ══════════════════════════════════════════════════════════
#  API 处理
# ══════════════════════════════════════════════════════════

def handle_api(path: str, method: str, body: dict, qs: dict):
    prefix = "/admin/api/api-config"
    if not path.startswith(prefix):
        return None

    sub = path[len(prefix):].rstrip("/")
    ct = "application/json; charset=utf-8"

    # GET /admin/api/api-config -> 返回当前配置
    if method == "GET" and sub == "":
        cfg = _load_config()
        return 200, {"ok": True, "config": cfg}, ct

    # PUT /admin/api/api-config/text 或 /vision
    if method == "PUT" and sub in ("/text", "/vision"):
        purpose = sub.lstrip("/")
        try:
            _save_config(purpose, body)
            return 200, {"ok": True}, ct
        except Exception as e:
            return 500, {"ok": False, "error": str(e)}, ct

    # POST /admin/api/api-config/text/test 或 /vision/test
    if method == "POST" and sub in ("/text/test", "/vision/test"):
        return _test_connection(body, ct)

    return 404, {"ok": False, "error": "unknown endpoint"}, ct


def _test_connection(body: dict, ct: str):
    """测试LLM连接，返回详细诊断信息。"""
    import openai
    import urllib.request
    import ssl

    api_key = body.get("api_key", "")
    base_url = body.get("base_url", "")
    model = body.get("model", "")

    if not api_key:
        return 400, {"ok": False, "error": "API Key 不能为空"}, ct
    if not base_url:
        return 400, {"ok": False, "error": "API URL 不能为空"}, ct
    if not model:
        return 400, {"ok": False, "error": "模型名称不能为空"}, ct

    # 豆包特殊校验：必须使用Endpoint ID
    provider = body.get("provider", "")
    if provider == "doubao" and not model.startswith("ep-"):
        return 200, {
            "ok": False,
            "error": "豆包必须使用 Endpoint ID 作为模型名称",
            "troubleshoot": "1. 登录火山方舟控制台 https://console.volcengine.com/ark\n"
                          "2. 进入「在线推理」→「推理接入点」\n"
                          "3. 创建接入点后复制 Endpoint ID（如 ep-20250101-xxxx）\n"
                          "4. 将 Endpoint ID 填入「自定义模型名称」字段",
        }, ct

    # 第一步：网络连通性测试（ping URL）
    try:
        test_url = base_url.rstrip("/") + "/"
        req = urllib.request.Request(test_url, method="HEAD")
        req.add_header("User-Agent", "AI-CAD-Audit-System/7.0")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        urllib.request.urlopen(req, timeout=10, context=ctx)
    except urllib.error.HTTPError as he:
        # HTTP错误但网络通（如401/404），说明能连上服务器
        pass
    except Exception as e:
        err_msg = str(e)
        troubleshoot = []
        if "getaddrinfo failed" in err_msg or "Name or service not known" in err_msg:
            troubleshoot.append("DNS解析失败：无法找到该域名")
            troubleshoot.append("→ 检查URL是否拼写正确")
            troubleshoot.append("→ 检查电脑DNS设置（可尝试改为 8.8.8.8）")
        elif "timed out" in err_msg or "Timeout" in err_msg:
            troubleshoot.append("连接超时：服务器无响应")
            troubleshoot.append("→ 检查电脑是否已连接互联网")
            troubleshoot.append("→ 如果是公司/学校网络，可能需要配置代理")
            troubleshoot.append("→ 检查防火墙是否拦截了该地址")
        elif "Connection refused" in err_msg:
            troubleshoot.append("连接被拒绝：服务器拒绝了连接")
            troubleshoot.append("→ 该服务可能暂时不可用，请稍后再试")
            troubleshoot.append("→ 检查URL端口是否正确")
        elif "certificate" in err_msg.lower() or "SSL" in err_msg:
            troubleshoot.append("SSL证书问题")
            troubleshoot.append("→ 系统时间可能不正确，请检查")
            troubleshoot.append("→ 如果是公司网络，可能需要配置代理")
        else:
            troubleshoot.append("网络不通，无法连接到API服务器")
            troubleshoot.append("→ 检查电脑是否已连接互联网")
            troubleshoot.append("→ 尝试在浏览器中访问该URL看能否打开")
            troubleshoot.append("→ 如果是公司网络，联系IT配置代理")

        return 200, {
            "ok": False,
            "error": f"网络不通：无法连接到 {base_url}",
            "troubleshoot": "\n".join(troubleshoot),
        }, ct

    # 第二步：API认证测试
    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "你好"}],
            max_tokens=10,
            timeout=15,
        )
        return 200, {"ok": True, "message": f"连接成功，模型: {model}"}, ct
    except openai.AuthenticationError:
        return 200, {
            "ok": False,
            "error": "API Key 无效或已过期",
            "troubleshoot": "1. 检查API Key是否复制完整（不要有多余空格）\n2. 确认Key未过期（厂商控制台可查看）\n3. 确认Key有该模型的调用权限",
        }, ct
    except openai.APIConnectionError as e:
        return 200, {
            "ok": False,
            "error": f"API连接失败: {str(e)[:100]}",
            "troubleshoot": "1. 检查URL是否正确（注意是否有/v1后缀）\n2. 如果是公司网络，可能需要配置代理\n3. 检查防火墙是否拦截",
        }, ct
    except openai.RateLimitError:
        return 200, {
            "ok": False,
            "error": "触发限流（Rate Limit）",
            "troubleshoot": "1. 该账号请求过于频繁，请稍后再试\n2. 检查账号是否有足够的额度\n3. 新账号通常有免费额度限制",
        }, ct
    except openai.NotFoundError:
        troubleshoot = "1. 检查模型名称是否拼写正确\n2. 确认该模型在该厂商已开通\n3. 部分模型需要单独申请权限"
        if provider == "doubao":
            troubleshoot = (
                "1. 豆包必须使用 Endpoint ID（非模型名称）\n"
                "2. 登录 https://console.volcengine.com/ark 创建推理接入点\n"
                "3. 复制接入点 ID（如 ep-20250101-xxxx）填入模型字段\n"
                "4. 确认接入点状态为「运行中」"
            )
        return 200, {
            "ok": False,
            "error": f"模型不存在: {model}",
            "troubleshoot": troubleshoot,
        }, ct
    except Exception as e:
        err_str = str(e)
        if "model" in err_str.lower() and ("not found" in err_str.lower() or "不存在" in err_str):
            troubleshoot = "1. 检查模型名称是否拼写正确\n2. 确认该模型在该厂商已开通"
            if provider == "doubao":
                troubleshoot = (
                    "1. 豆包必须使用 Endpoint ID（非模型名称）\n"
                    "2. 登录 https://console.volcengine.com/ark 创建推理接入点\n"
                    "3. 复制接入点 ID（如 ep-20250101-xxxx）填入模型字段"
                )
            return 200, {
                "ok": False,
                "error": f"模型不存在: {model}",
                "troubleshoot": troubleshoot,
            }, ct
        # 豆包特殊错误诊断
        if provider == "doubao":
            if "404" in err_str or "not found" in err_str.lower():
                return 200, {
                    "ok": False,
                    "error": f"豆包API调用失败: {err_str[:150]}",
                    "troubleshoot": (
                        "1. 确认使用的是 Endpoint ID（非模型名称）\n"
                        "2. 检查 Endpoint ID 是否拼写正确\n"
                        "3. 确认接入点在火山方舟控制台状态为「运行中」\n"
                        "4. 检查 API Key 是否有该接入点的调用权限\n"
                        "5. 豆包base_url应为: https://ark.cn-beijing.volces.com/api/v3"
                    ),
                }, ct
            if "400" in err_str:
                return 200, {
                    "ok": False,
                    "error": f"豆包API请求参数错误: {err_str[:150]}",
                    "troubleshoot": (
                        "1. 确认 Endpoint ID 格式正确（如 ep-20250101-xxxx）\n"
                        "2. 检查 API Key 是否有效\n"
                        "3. 确认已开通该模型的服务权限"
                    ),
                }, ct
        return 200, {
            "ok": False,
            "error": f"连接失败: {err_str[:150]}",
            "troubleshoot": "1. 检查API Key是否正确\n2. 检查模型名称是否正确\n3. 如果是公司网络，可能需要配置代理",
        }, ct
