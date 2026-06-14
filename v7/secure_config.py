# -*- coding: utf-8 -*-
"""
安全配置管理 v1.0
- API密钥的Fernet对称加密存储
- 双模式切换：内置LLM代理 / 外部API
- 主密钥来源：环境变量 AI_REVIEW_MASTER_KEY 或机器指纹
"""

import os, json, hashlib, base64, uuid, logging

logger = logging.getLogger(__name__)

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
    hostname = os.environ.get('COMPUTERNAME') or os.environ.get('HOSTNAME')
    username = os.environ.get('USERNAME') or os.environ.get('USER')
    if not hostname or not username:
        raise EnvironmentError("无法获取主机名或用户名环境变量，无法生成安全密钥。请设置COMPUTERNAME/HOSTNAME和USERNAME/USER环境变量。")
    fingerprint = f"{hostname}-{username}"
    return base64.urlsafe_b64encode(hashlib.sha256(fingerprint.encode()).digest())


def _ensure_fernet():
    """确保cryptography可用，否则降级为简单混淆"""
    if HAS_CRYPTO:
        return Fernet(_get_master_key())
    return None


def _load_raw():
    """加载原始配置文件（带缓存）"""
    global _raw_cache, _raw_cache_mtime
    if os.path.exists(CONFIG_FILE):
        mtime = os.path.getmtime(CONFIG_FILE)
        if _raw_cache is not None and _raw_cache_mtime == mtime:
            return _raw_cache
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            _raw_cache = json.load(f)
            _raw_cache_mtime = mtime
            return _raw_cache
    return {"provider": "", "mode": "proxy", "keys": {}}


def _save_raw(data):
    """保存原始配置文件"""
    global _raw_cache, _raw_cache_mtime
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.chmod(CONFIG_FILE, 0o600)
    _raw_cache = data
    _raw_cache_mtime = os.path.getmtime(CONFIG_FILE) if os.path.exists(CONFIG_FILE) else 0


# 配置文件缓存
_raw_cache = None
_raw_cache_mtime = 0


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
        except Exception as e:
            logger.warning(f"API密钥解密失败: {e}")
            return None
    else:
        logger.warning("未安装cryptography库，无法解密API密钥")
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
        logger.error("未安装cryptography库，拒绝存储API密钥（明文存储不安全）")
        raise EnvironmentError("需要安装cryptography库才能存储API密钥，请执行: pip install cryptography")

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
