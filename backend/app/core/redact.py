"""敏感字段脱敏。

写入 ``audit_logs.detail``、``agent_runs.input_full/output_full``、
``agent_runs.input_summary/output_summary`` 之前调用 :func:`redact`，
把密码、API Key、JWT 等字段替换为 ``[REDACTED]``。

规则对齐 docs/prd/10-数据模型与存储/接口文档-数据模型与存储最小demo.md §4.5。
"""

from __future__ import annotations

import json
import re
from typing import Any

# 需要脱敏的键名；匹配时忽略大小写与下划线/连字符/驼峰差异。
_REDACT_KEYS = {
    "password",
    "password_hash",
    "api_key",
    "api_key_ciphertext",
    "authorization",
    "access_token",
    "refresh_token",
    "jwt",
    "secret",
    "client_secret",
    "cookie",
    "set-cookie",
}

# 只保留小写字母与数字，消除下划线、连字符与大小写差异
_NORMALIZE_RE = re.compile(r"[^a-z0-9]")


def _normalize(key: str) -> str:
    return _NORMALIZE_RE.sub("", key.lower())


_REDACT_KEYS_NORMALIZED = {_normalize(key) for key in _REDACT_KEYS}


def _is_sensitive_key(key: str) -> bool:
    return _normalize(key) in _REDACT_KEYS_NORMALIZED


def redact(value: Any) -> Any:
    """递归脱敏：遍历 dict / list，对敏感键的值替换为 ``[REDACTED]``。

    字符串值若本身是合法 JSON，则先解析再递归，避免嵌套 JSON 中的敏感字段漏网。
    非 dict/list/str 的值原样返回。
    """
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if _is_sensitive_key(key) else redact(val))
                for key, val in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                return value
            return json.dumps(redact(parsed), ensure_ascii=False)
        return value
    return value
