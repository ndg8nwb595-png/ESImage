"""X-Request-ID 中间件。

- 入站头匹配 `^[A-Za-z0-9_-]{8,64}$` 时复用，否则忽略并生成 UUIDv4。
- 每个 HTTP 响应头返回最终使用的 `X-Request-ID`。
- 该 ID 写入请求级上下文，供 JSON 日志关联。
"""

from __future__ import annotations

import re
import uuid

from starlette.datastructures import MutableHeaders

from app.core.context import request_id_var, user_id_var

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _valid_request_id(value: str) -> bool:
    return bool(_REQUEST_ID_RE.match(value))


class RequestIDMiddleware:
    """纯 ASGI 中间件，不包裹响应体，避免破坏 SSE 流式输出。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_headers = dict(scope.get("headers") or [])
        raw = raw_headers.get(b"x-request-id", b"")
        value = raw.decode("latin-1", "replace")
        request_id = value if _valid_request_id(value) else str(uuid.uuid4())

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)
            user_id_var.set(None)
