# -*- coding: utf-8 -*-
"""加密工具模块

提供API Key等敏感数据的加密存储和解密读取。
使用Fernet对称加密，密钥从环境变量或文件获取。
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 全局缓存
_fernet_instance = None


def _get_or_create_key() -> bytes:
    """获取或创建加密密钥。
    
    优先级：
    1. V7_ENCRYPTION_KEY 环境变量
    2. .encryption_key 文件
    3. 自动生成并保存
    """
    # 1. 环境变量
    env_key = os.environ.get("V7_ENCRYPTION_KEY", "")
    if env_key:
        return base64.urlsafe_b64decode(env_key.encode())
    
    # 2. 密钥文件
    key_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".encryption_key")
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return base64.urlsafe_b64decode(f.read().strip())
    
    # 3. 自动生成
    key = Fernet.generate_key()
    with open(key_file, "wb") as f:
        f.write(key)
    # 设置文件权限（仅当前用户可读写）
    os.chmod(key_file, 0o600)
    return base64.urlsafe_b64decode(key)


def get_fernet() -> Fernet:
    """获取Fernet实例（单例）。"""
    global _fernet_instance
    if _fernet_instance is None:
        key = _get_or_create_key()
        _fernet_instance = Fernet(base64.urlsafe_b64encode(key))
    return _fernet_instance


def encrypt_text(plain_text: str) -> str:
    """加密文本。
    
    Args:
        plain_text: 明文
        
    Returns:
        加密后的base64字符串，前缀"enc:"标识已加密
    """
    if not plain_text:
        return ""
    if plain_text.startswith("enc:"):
        return plain_text  # 已经加密
    f = get_fernet()
    encrypted = f.encrypt(plain_text.encode("utf-8"))
    return "enc:" + encrypted.decode("utf-8")


def decrypt_text(cipher_text: str) -> str:
    """解密文本。
    
    Args:
        cipher_text: 密文（带"enc:"前缀）
        
    Returns:
        解密后的明文
    """
    if not cipher_text:
        return ""
    if not cipher_text.startswith("enc:"):
        return cipher_text  # 未加密，直接返回
    f = get_fernet()
    encrypted = cipher_text[4:].encode("utf-8")
    try:
        decrypted = f.decrypt(encrypted)
        return decrypted.decode("utf-8")
    except Exception:
        return cipher_text  # 解密失败，返回原文


def is_encrypted(text: str) -> bool:
    """检查文本是否已加密。"""
    return text and text.startswith("enc:")
