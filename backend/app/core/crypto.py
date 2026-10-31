"""模型配置 API Key 的对称加密。

算法：AES-256-GCM；密钥来自环境变量 ``MODEL_CONFIG_ENCRYPTION_KEY``
（base64 编码的 32 字节），启动时由 :mod:`app.core.config` 校验。
存储格式：``base64(nonce + ciphertext + tag)``，nonce 为 12 字节。
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_BYTES = 12


class ModelConfigCryptoError(Exception):
    """模型配置加解密失败。"""


def _load_key() -> bytes:
    """读取并解码 32 字节密钥；启动阶段已校验，这里只做防御性检查。"""
    try:
        key = base64.b64decode(settings.MODEL_CONFIG_ENCRYPTION_KEY, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ModelConfigCryptoError("模型配置加密密钥格式错误") from exc
    if len(key) != 32:
        raise ModelConfigCryptoError("模型配置加密密钥长度必须为 32 字节")
    return key


def encrypt_api_key(plaintext: str) -> str:
    """加密 API Key，返回 base64(nonce + ciphertext + tag)。"""
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(_load_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_api_key(ciphertext: str) -> str:
    """解密 API Key；密文损坏或密钥不匹配时抛 :class:`ModelConfigCryptoError`。"""
    try:
        raw = base64.b64decode(ciphertext, validate=True)
        if len(raw) <= NONCE_BYTES:
            raise ValueError("密文长度不足")
        plaintext = AESGCM(_load_key()).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], None)
        return plaintext.decode("utf-8")
    except (binascii.Error, InvalidTag, ValueError, UnicodeDecodeError) as exc:
        raise ModelConfigCryptoError("模型配置 API Key 解密失败") from exc


def mask_api_key(plaintext: str | None) -> str | None:
    """脱敏展示：长度 ≥ 8 取前 3 位 + ``****`` + 后 4 位，否则 ``****``。"""
    if not plaintext:
        return None
    if len(plaintext) >= 8:
        return f"{plaintext[:3]}****{plaintext[-4:]}"
    return "****"
