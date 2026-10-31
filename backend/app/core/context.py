"""请求级上下文变量，供日志与中间件共享，避免循环依赖。"""

from __future__ import annotations

import contextvars

# 当前请求的 request_id；无请求时为 None
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
# 当前登录用户 ID；无用户时为 None
user_id_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "user_id", default=None
)
