"""概览四张统计卡片与进程内 60 秒缓存。"""

from __future__ import annotations

import threading
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.workspace import AgentRun, GeneratedImage
from app.modules.admin.service import local_day_end_exclusive, local_day_start, today_local

# 进程内单实例缓存；正式实现替换为 Redis（9 号 §2.7）
_CACHE: dict[str, tuple[float, dict[str, int]]] = {}
_CACHE_LOCK = threading.Lock()


def clear_dashboard_cache() -> None:
    """清空概览缓存；供测试与本地调试调用，不暴露 HTTP 接口。"""
    with _CACHE_LOCK:
        _CACHE.clear()


def _cache_key() -> str:
    """缓存键包含 Asia/Shanghai 当天日期，跨天自然失效。"""
    return f"dashboard_summary:{today_local().isoformat()}"


def _aggregate(db: Session) -> dict[str, int]:
    """分别聚合四张卡片；任一查询失败由全局处理器返回 500。"""
    user_total = int(
        db.scalar(
            select(func.count()).select_from(User).where(User.status != "deleted")
        )
        or 0
    )

    today = today_local()
    start = local_day_start(today)
    end = local_day_end_exclusive(today)
    today_image_count = int(
        db.scalar(
            select(func.count())
            .select_from(GeneratedImage)
            .where(
                GeneratedImage.image_type == "final",
                GeneratedImage.status == "success",
                GeneratedImage.created_at >= start,
                GeneratedImage.created_at < end,
            )
        )
        or 0
    )

    total_image_count = int(
        db.scalar(
            select(func.count())
            .select_from(GeneratedImage)
            .where(
                GeneratedImage.image_type == "final",
                GeneratedImage.status == "success",
            )
        )
        or 0
    )

    today_token_total = int(
        db.scalar(
            select(
                func.coalesce(
                    func.sum(AgentRun.prompt_tokens + AgentRun.completion_tokens), 0
                )
            ).where(
                AgentRun.created_at >= start,
                AgentRun.created_at < end,
            )
        )
        or 0
    )

    return {
        "user_total": user_total,
        "today_image_count": today_image_count,
        "total_image_count": total_image_count,
        "today_token_total": today_token_total,
    }


def get_summary(db: Session) -> dict[str, int]:
    """读取概览四卡；60 秒内重复请求返回同一快照。"""
    key = _cache_key()
    now_monotonic = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            expires_at, payload = cached
            if expires_at > now_monotonic:
                print(f"[概览] 缓存命中 key={key}")
                return dict(payload)

    payload = _aggregate(db)
    ttl = max(0, settings.DASHBOARD_CACHE_TTL_SECONDS)
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic() + ttl, dict(payload))
    print(f"[概览] 重新聚合并写入缓存 key={key} ttl={ttl}s")
    return payload
