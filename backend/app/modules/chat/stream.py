"""SSE 事件输出与心跳包装。"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

_SENTINEL = object()


def sse(event: str, data: dict[str, Any]) -> str:
    """按 SSE 协议输出一个事件：event 行 + data 行 + 空行。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def with_heartbeat(events: Iterator[str], interval: float) -> Iterator[str]:
    """在事件流空闲超过 interval 秒时插入 ping。

    生成器放在后台线程执行，消费端按 interval 轮询队列：
    - 队列空 -> 输出一次 ping；
    - 客户端断开 -> 外层生成器收到 GeneratorExit，置停止标记并关闭内层生成器，
      内层生成器自己的 finally 会把未完成消息标记为 failed。
    """
    if not interval or interval <= 0:
        yield from events
        return

    events_queue: queue.Queue[Any] = queue.Queue()
    stop_event = threading.Event()

    def producer() -> None:
        try:
            for event in events:
                if stop_event.is_set():
                    break
                events_queue.put(event)
        except BaseException as exc:  # 交给消费端重新抛出，避免线程内吞异常
            events_queue.put(exc)
        finally:
            try:
                events.close()  # type: ignore[attr-defined]
            except Exception:
                pass
            events_queue.put(_SENTINEL)

    thread = threading.Thread(target=producer, name="sse-heartbeat", daemon=True)
    thread.start()
    try:
        while True:
            try:
                item = events_queue.get(timeout=interval)
            except queue.Empty:
                yield sse("ping", {})
                continue
            if item is _SENTINEL:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        stop_event.set()
        thread.join(timeout=1)
