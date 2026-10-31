"""Agent 配置：模型配置与系统提示词版本管理（9 号 §6.5）。"""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.config import ModelConfig, PromptVersion, SystemPrompt
from app.modules.admin.prompts.schemas import ModelConfigRequest, PromptSaveRequest
from app.modules.workspace.service import to_iso

router = APIRouter(tags=["admin-prompts"])


def _mask_api_key(key: str | None) -> str | None:
    """脱敏展示；不返回真实 Key。"""
    if not key:
        return None
    return "******"


def _decode_api_key(ciphertext: str | None) -> str:
    """最小 demo 用 base64 充当加密；正式实现应使用对称加密。"""
    if not ciphertext:
        return ""
    try:
        return base64.b64decode(ciphertext).decode("utf-8")
    except Exception:
        return ""


def _model_payload(m: ModelConfig) -> dict:
    return {
        "id": m.id,
        "provider": m.provider,
        "base_url": m.base_url,
        "api_key": _mask_api_key(m.api_key_ciphertext),
        "text_model": m.text_model,
        "image_model": m.image_model,
        "vision_model": m.vision_model,
        "temperature": float(m.temperature),
        "timeout_seconds": m.timeout_seconds,
        "concurrency": m.concurrency,
        "retry_count": m.retry_count,
        "max_context_tokens": m.max_context_tokens,
        "is_active": m.is_active,
        "updated_at": to_iso(m.updated_at),
    }


@router.get("/model-config")
def get_model_config(
    auth: AuthContext = Depends(require_permission("admin.model.view")),
    db: Session = Depends(get_db),
) -> dict:
    """读取当前启用模型配置（Key 脱敏）。"""
    config = db.scalar(select(ModelConfig).where(ModelConfig.is_active.is_(True)))
    if config is None:
        return ok(None)
    return ok(_model_payload(config))


@router.put("/model-config")
def save_model_config(
    payload: ModelConfigRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.model.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """保存模型配置；api_key 为空表示不修改。"""
    config = db.scalar(select(ModelConfig).where(ModelConfig.is_active.is_(True)))

    if config is None:
        if not payload.base_url or not payload.text_model or not payload.image_model:
            raise ApiError(400, 10002, "缺少必要配置")
        config = ModelConfig(
            base_url=payload.base_url,
            text_model=payload.text_model,
            image_model=payload.image_model,
            is_active=True,
        )
        db.add(config)

    if payload.provider is not None:
        config.provider = payload.provider
    if payload.base_url is not None:
        config.base_url = payload.base_url
    if payload.api_key:
        config.api_key_ciphertext = base64.b64encode(payload.api_key.encode("utf-8")).decode("utf-8")
    if payload.text_model is not None:
        config.text_model = payload.text_model
    if payload.image_model is not None:
        config.image_model = payload.image_model
    if payload.vision_model is not None:
        config.vision_model = payload.vision_model
    if payload.temperature is not None:
        if not 0 <= payload.temperature <= 2:
            raise ApiError(400, 10004, "温度需在 0~2 之间")
        config.temperature = payload.temperature
    if payload.timeout_seconds is not None:
        if not 30 <= payload.timeout_seconds <= 300:
            raise ApiError(400, 10004, "超时需在 30~300 之间")
        config.timeout_seconds = payload.timeout_seconds
    if payload.concurrency is not None:
        if not 1 <= payload.concurrency <= 16:
            raise ApiError(400, 10004, "并发需在 1~16 之间")
        config.concurrency = payload.concurrency
    if payload.retry_count is not None:
        if not 0 <= payload.retry_count <= 3:
            raise ApiError(400, 10004, "重试次数需在 0~3 之间")
        config.retry_count = payload.retry_count
    if payload.max_context_tokens is not None:
        config.max_context_tokens = payload.max_context_tokens
    config.updated_by = auth.user.id

    write_audit(db, request, user_id=auth.user.id, username_snapshot=auth.user.username, action="model_config.update", result="success", detail=None)
    db.commit()
    db.refresh(config)
    return ok(_model_payload(config))


@router.get("/prompts")
def list_prompts(
    auth: AuthContext = Depends(require_permission("admin.prompts.view")),
    db: Session = Depends(get_db),
) -> dict:
    """8 个 Agent 提示词列表。"""
    prompts = list(db.scalars(select(SystemPrompt).order_by(SystemPrompt.id)))
    return ok(
        {
            "items": [
                {
                    "agent_code": p.agent_code,
                    "name": p.name,
                    "current_version": p.current_version,
                    "is_active": p.is_active,
                    "updated_at": to_iso(p.updated_at),
                }
                for p in prompts
            ]
        }
    )


@router.get("/prompts/{agent_code}")
def get_prompt(
    agent_code: str,
    auth: AuthContext = Depends(require_permission("admin.prompts.view")),
    db: Session = Depends(get_db),
) -> dict:
    """当前提示词与版本历史。"""
    prompt = db.scalar(select(SystemPrompt).where(SystemPrompt.agent_code == agent_code))
    if prompt is None:
        raise ApiError(404, 30016, "提示词不存在")
    versions = list(
        db.scalars(
            select(PromptVersion)
            .where(PromptVersion.prompt_id == prompt.id)
            .order_by(PromptVersion.version.desc())
        )
    )
    return ok(
        {
            "agent_code": prompt.agent_code,
            "name": prompt.name,
            "content": prompt.content,
            "current_version": prompt.current_version,
            "is_active": prompt.is_active,
            "updated_at": to_iso(prompt.updated_at),
            "versions": [
                {
                    "version": v.version,
                    "content": v.content,
                    "created_at": to_iso(v.created_at),
                }
                for v in versions
            ],
        }
    )


@router.put("/prompts/{agent_code}")
def save_prompt(
    agent_code: str,
    payload: PromptSaveRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.prompts.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """保存新版本。"""
    content = (payload.content or "").strip()
    if not content:
        raise ApiError(400, 10002, "提示词不能为空")

    prompt = db.scalar(select(SystemPrompt).where(SystemPrompt.agent_code == agent_code))
    if prompt is None:
        raise ApiError(404, 30016, "提示词不存在")

    new_version = prompt.current_version + 1
    prompt.content = content
    prompt.current_version = new_version
    prompt.updated_by = auth.user.id
    db.add(
        PromptVersion(
            prompt_id=prompt.id,
            agent_code=agent_code,
            version=new_version,
            content=content,
            created_by=auth.user.id,
        )
    )
    write_audit(db, request, user_id=auth.user.id, username_snapshot=auth.user.username, action="prompt.save", result="success", detail={"agent_code": agent_code, "version": new_version})
    db.commit()
    return ok({"agent_code": agent_code, "current_version": new_version})


@router.post("/prompts/{agent_code}/versions/{version}/activate")
def activate_prompt_version(
    agent_code: str,
    version: int,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.prompts.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """回滚到指定版本。"""
    prompt = db.scalar(select(SystemPrompt).where(SystemPrompt.agent_code == agent_code))
    if prompt is None:
        raise ApiError(404, 30016, "提示词不存在")
    target = db.scalar(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt.id, PromptVersion.version == version)
    )
    if target is None:
        raise ApiError(404, 30016, "版本不存在")

    prompt.content = target.content
    prompt.current_version = target.version
    prompt.updated_by = auth.user.id
    write_audit(db, request, user_id=auth.user.id, username_snapshot=auth.user.username, action="prompt.activate", result="success", detail={"agent_code": agent_code, "version": version})
    db.commit()
    return ok({"agent_code": agent_code, "current_version": version})
