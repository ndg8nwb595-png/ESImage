"""生成配置只读服务：模板、尺寸、素材、模型配置与系统提示词。

进程内缓存 60 秒，提供手动刷新入口；停用项不返回（接口文档 §2.3）。
"""

from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import MaterialAsset, ModelConfig, SizePreset, SystemPrompt, Template

CACHE_TTL_SECONDS = 60

_lock = threading.RLock()
_cache: dict[str, Any] = {"expires_at": 0.0}
_cache_hits = 0


def refresh() -> None:
    """手动刷新缓存（后台变更或种子后调用）。"""
    global _cache_hits
    with _lock:
        _cache.clear()
        _cache["expires_at"] = 0.0
        _cache_hits = 0


def _valid() -> bool:
    return bool(_cache) and _cache.get("expires_at", 0) > time.monotonic()


def _ensure_loaded(db: Session) -> None:
    global _cache_hits
    with _lock:
        if _valid():
            _cache_hits += 1
            return

        templates = [
            {
                "id": row.id,
                "name": row.name,
                "style_text": row.style_text,
                "thumbnail_path": row.thumbnail_path,
                "prompt_template": row.prompt_template,
                "layout_ref": row.layout_ref,
                "sort_order": row.sort_order,
            }
            for row in db.scalars(
                select(Template)
                .where(Template.status == "active")
                .order_by(Template.sort_order.asc(), Template.id.asc())
            )
        ]
        sizes = [
            {
                "id": row.id,
                "platform_name": row.platform_name,
                "width": row.width,
                "height": row.height,
                "sort_order": row.sort_order,
            }
            for row in db.scalars(
                select(SizePreset)
                .where(SizePreset.status == "active")
                .order_by(SizePreset.sort_order.asc(), SizePreset.id.asc())
            )
        ]
        materials = [
            {
                "id": row.id,
                "name": row.name,
                "file_path": row.file_path,
                "tags": row.tags or [],
                "style_tags": row.style_tags or [],
                "sort_order": row.sort_order,
            }
            for row in db.scalars(
                select(MaterialAsset)
                .where(MaterialAsset.status == "active")
                .order_by(MaterialAsset.sort_order.asc(), MaterialAsset.id.asc())
            )
        ]
        prompts = {
            row.agent_code: row.content
            for row in db.scalars(
                select(SystemPrompt).where(SystemPrompt.is_active.is_(True))
            )
        }
        model = db.scalar(
            select(ModelConfig).where(ModelConfig.is_active.is_(True)).limit(1)
        )
        model_data = None
        if model is not None:
            model_data = {
                "id": model.id,
                "provider": model.provider,
                "base_url": model.base_url,
                "text_model": model.text_model,
                "image_model": model.image_model,
                "vision_model": model.vision_model,
                "temperature": float(model.temperature),
                "timeout_seconds": model.timeout_seconds,
                "concurrency": model.concurrency,
                "retry_count": model.retry_count,
                "max_context_tokens": model.max_context_tokens,
            }

        _cache.clear()
        _cache.update(
            {
                "templates": templates,
                "sizes": sizes,
                "materials": materials,
                "prompts": prompts,
                "model": model_data,
                "expires_at": time.monotonic() + CACHE_TTL_SECONDS,
            }
        )


def get_templates(db: Session) -> list[dict[str, Any]]:
    _ensure_loaded(db)
    return list(_cache["templates"])


def get_sizes(db: Session) -> list[dict[str, Any]]:
    _ensure_loaded(db)
    return list(_cache["sizes"])


def get_materials(db: Session) -> list[dict[str, Any]]:
    _ensure_loaded(db)
    return list(_cache["materials"])


def get_prompt(db: Session, agent_code: str) -> str | None:
    _ensure_loaded(db)
    return (_cache.get("prompts") or {}).get(agent_code)


def get_model_config(db: Session) -> dict[str, Any] | None:
    _ensure_loaded(db)
    return _cache.get("model")
