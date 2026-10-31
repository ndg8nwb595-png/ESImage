"""演示专用 SSE 探针（仅 `APP_ENV != production` 注册）。

事件顺序：`meta` → 多条 `delta`（每 1 秒一条）→ `done`；
无事件时每 15 秒发送 `ping`（演示流很短，实际不会触发）。
"""

from __future__ import annotations

import asyncio
import json
import os

from fastapi.responses import StreamingResponse

_DELTAS = ("逐", "字", "输", "出")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_probe_stream(request_id: str) -> StreamingResponse:
    interval = float(os.getenv("SSE_PROBE_INTERVAL", "1"))

    async def gen():
        yield _sse("meta", {"probe": True, "request_id": request_id})
        for seq, text in enumerate(_DELTAS, start=1):
            await asyncio.sleep(interval)
            yield _sse("delta", {"seq": seq, "text": text})
        yield _sse("done", {"probe": True, "seq": len(_DELTAS)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
