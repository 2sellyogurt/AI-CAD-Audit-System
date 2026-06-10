# -*- coding: utf-8 -*-
"""
安全配置管理 v1.0
- API密钥的Fernet对称加密存储
- 双模式切换：内置LLM代理 / 外部API
- 主密钥来源：环境变量 AI_REVIEW_MASTER_KEY 或机器指纹
"""

import os, json, hashlib, base64, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, ".encrypted_keys.json")

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


def _get_master_key():
    """获取主密钥：优先环境变量，否则用机器标识派生"""
    env_key = os.environ.get("AI_REVIEW_MASTER_KEY")
    if env_key:
        return base64.urlsafe_b64encode(hashlib.sha256(env_key.encode()).digest())

    # 机器指纹方式
    fingerprint = f"{os.environ.get('COMPUTERNAME','')}-{os.environ.get('USERNAME','')}"
    return base64.urlsafe_b64encode(hashlib.sha256(fingerprint.encode()).digest())


def _ensure_fernet():
    """确保cryptography可用，否则降级为简单混淆"""
    if HAS_CRYPTO:
        return Fernet(_get_master_key())
    return None


def _load_raw():
    """加载原始配置文件"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"provider": "", "mode": "proxy", "keys": {}}


def _save_raw(data):
    """保存原始配置文件"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.chmod(CONFIG_FILE, 0o600)  # 仅拥有者可读写


# ── 公开API ────────────────────────────────────────────

def get_mode():
    """获取当前运行模式: 'proxy' 或 'external'"""
    data = _load_raw()
    return data.get("mode", "proxy")


def get_provider():
    """获取当前API提供商"""
    data = _load_raw()
    return data.get("provider", "")


def get_api_key(provider=None):
    """
    获取解密后的API Key
    Args:
        provider: 指定提供商，默认用当前激活的
    Returns:
        str or None
    """
    data = _load_raw()
    provider = provider or data.get("provider", "")
    if not provider:
        return None

    encrypted = data.get("keys", {}).get(provider, "")
    if not encrypted:
        return None

    fernet = _ensure_fernet()
    if fernet:
        try:
            return fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            return None
    else:
        # 无cryptography库时的简单base64解码（不加密，仅编码）
        try:
            return base64.b64decode(encrypted).decode()
        except Exception:
            return None


def set_api_key(provider, api_key, set_active=True):
    """
    加密存储API Key
    Args:
        provider: 'zhipu'/'deepseek'/'openai'/'doubao'
        api_key: 明文密钥
        set_active: 是否同时激活该提供商
    """
    data = _load_raw()

    fernet = _ensure_fernet()
    if fernet:
        encrypted = fernet.encrypt(api_key.encode()).decode()
    else:
        # 无cryptography时的简单编码（警告：非加密，仅编码）
        encrypted = base64.b64encode(api_key.encode()).decode()

    data["keys"][provider] = encrypted
    if set_active:
        data["provider"] = provider
        data["mode"] = "external"

    _save_raw(data)
    return True


def set_mode(mode):
    """切换运行模式: 'proxy' 或 'external'"""
    if mode not in ("proxy", "external"):
        raise ValueError("mode must be 'proxy' or 'external'")
    data = _load_raw()
    data["mode"] = mode
    _save_raw(data)


def get_all_providers():
    """获取所有已配置的提供商列表（不含密钥）"""
    data = _load_raw()
    return {
        "mode": data.get("mode", "proxy"),
        "provider": data.get("provider", ""),
        "configured_providers": list(data.get("keys", {}).keys()),
        "encryption_available": HAS_CRYPTO
    }


def delete_api_key(provider):
    """删除指定提供商的密钥"""
    data = _load_raw()
    data["keys"].pop(provider, None)
    if data.get("provider") == provider:
        data["provider"] = ""
        data["mode"] = "proxy"
    _save_raw(data)
