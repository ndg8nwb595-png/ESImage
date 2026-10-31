"""密码哈希与 JWT 签发/解析。"""

from __future__ import annotations

from datetime import datetime, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.models.user import User


def _password_bytes(password: str) -> bytes:
    """bcrypt 只处理前 72 字节；超长部分截断，保证哈希与校验行为一致。"""
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    """使用 bcrypt cost=12 生成不可逆哈希。"""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码；哈希格式异常时按不匹配处理。"""
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    user: User,
    role_codes: list[str],
    permission_codes: list[str],
    remember_me: bool,
) -> tuple[str, str, dict]:
    """签发 JWT。

    返回 (token, expires_at, payload)。expires_at 为东八区 ISO 8601 字符串。
    """
    now = datetime.now(timezone.utc)
    ttl = settings.TOKEN_TTL_REMEMBER if remember_me else settings.TOKEN_TTL_DEFAULT
    exp_dt = now + ttl

    payload = {
        "sub": str(user.id),
        "iat": int(now.timestamp()),
        "exp": int(exp_dt.timestamp()),
        "token_version": user.token_version,
        "roles": role_codes,
        "permissions": permission_codes,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    expires_at = exp_dt.astimezone(settings.TZ).isoformat()
    return token, expires_at, payload


def decode_access_token(token: str) -> dict:
    """解析并校验 JWT 签名与 exp；异常由调用方转换为业务错误码。"""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
