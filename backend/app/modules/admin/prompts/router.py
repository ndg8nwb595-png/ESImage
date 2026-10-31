"""Agent 配置：模型配置与系统提示词版本管理。

对应 `docs/prd/8-管理后台-聊天记录/接口文档-聊天记录最小demo.md` §7~§8。
- 模型配置仅超管可读写；API Key 使用 AES-256-GCM 加密存储，只返回脱敏值。
- 系统提示词管理员/超管均可读写；保存与回滚都会生成新版本并写操作日志。
"""

from __future__ import annotations

import logging
import math
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.crypto import (
    ModelConfigCryptoError,
    decrypt_api_key,
    encrypt_api_key,
    mask_api_key,
)
from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.config import ModelConfig, PromptVersion, SystemPrompt
from app.models.user import User
from app.modules.admin.prompts.schemas import ModelConfigRequest, PromptSaveRequest
from app.modules.workspace.service import to_iso

logger = logging.getLogger("esimage.admin.prompts")

router = APIRouter(tags=["admin-prompts"])

PROVIDER = "volcengine_ark"
PROVIDER_LABEL = "豆包（火山方舟）"
PROMPT_MAX_LENGTH = 20000
PREVIEW_MAX_LENGTH = 60

# 8 个 Agent 的固定顺序与中文名（接口文档 §2.6）
AGENT_ORDER: tuple[str, ...] = (
    "planner",
    "product_understanding",
    "copywriter",
    "prompt_builder",
    "image_generator",
    "quality_reviewer",
    "repairer",
    "platform_rule",
)
AGENT_NAMES: dict[str, str] = {
    "planner": "规划 Agent",
    "product_understanding": "商品理解 Agent",
    "copywriter": "文案 Agent",
    "prompt_builder": "提示词 Agent",
    "image_generator": "生图执行 Agent",
    "quality_reviewer": "质量审核 Agent",
    "repairer": "修复 Agent",
    "platform_rule": "平台规范 Agent",
}

# 全局可用变量（接口文档 §2.6）
GLOBAL_VARIABLES: tuple[str, ...] = (
    "product_name",
    "params",
    "requirement_summary",
    "chat_summary",
    "product_profile",
    "plan",
    "copy_blocks",
    "review_issues",
    "platform_rules",
)
_GLOBAL_VARIABLE_SET = set(GLOBAL_VARIABLES)

# 每个 Agent 的建议变量
SUGGESTED_VARIABLES: dict[str, tuple[str, ...]] = {
    "planner": ("product_name", "params", "requirement_summary", "chat_summary"),
    "product_understanding": (
        "product_name",
        "params",
        "requirement_summary",
        "chat_summary",
    ),
    "copywriter": (
        "product_name",
        "params",
        "requirement_summary",
        "chat_summary",
        "product_profile",
        "plan",
        "platform_rules",
    ),
    "prompt_builder": (
        "product_name",
        "params",
        "requirement_summary",
        "product_profile",
        "plan",
        "copy_blocks",
    ),
    "image_generator": (),
    "quality_reviewer": ("product_profile",),
    "repairer": ("product_profile", "review_issues"),
    "platform_rule": ("copy_blocks", "platform_rules"),
}

# 变量语法：{{变量名}}，允许花括号内两侧有空格
VARIABLE_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


# ---- 公共序列化 ----

def _user_payload(user: User | None) -> dict | None:
    """用户摘要；用户不存在时返回 None。"""
    if user is None:
        return None
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
    }


def _users_by_id(db: Session, user_ids: set[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    return {
        user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids)))
    }


def _extract_variables(content: str) -> list[str]:
    """提取正文引用的变量，按首次出现顺序去重。"""
    seen: dict[str, None] = {}
    for match in VARIABLE_RE.finditer(content or ""):
        seen.setdefault(match.group(1), None)
    return list(seen)


def _prompt_warnings(content: str, agent_code: str) -> dict[str, list[str]]:
    """未知变量与缺失建议变量；两类警告都不阻止保存。"""
    variables = _extract_variables(content)
    variable_set = set(variables)
    unknown = [name for name in variables if name not in _GLOBAL_VARIABLE_SET]
    missing = [
        name for name in SUGGESTED_VARIABLES.get(agent_code, ()) if name not in variable_set
    ]
    return {
        "unknown_variables": unknown,
        "missing_suggested_variables": missing,
    }


def _content_preview(content: str) -> str:
    """折叠空白后取前 60 字符。"""
    folded = re.sub(r"\s+", " ", content or "").strip()
    if len(folded) <= PREVIEW_MAX_LENGTH:
        return folded
    return folded[:PREVIEW_MAX_LENGTH] + "…"


def _prompt_versions(db: Session, prompt: SystemPrompt) -> list[dict]:
    """版本历史（版本号倒序），含全文与修改人。"""
    versions = list(
        db.scalars(
            select(PromptVersion)
            .where(PromptVersion.prompt_id == prompt.id)
            .order_by(PromptVersion.version.desc())
        )
    )
    users = _users_by_id(
        db, {version.created_by for version in versions if version.created_by is not None}
    )
    return [
        {
            "version": version.version,
            "content": version.content,
            "created_by": _user_payload(users.get(version.created_by)),
            "created_at": to_iso(version.created_at),
            "is_current": version.version == prompt.current_version,
        }
        for version in versions
    ]


def _prompt_payload(
    db: Session,
    prompt: SystemPrompt,
    *,
    warnings: dict[str, list[str]] | None = None,
) -> dict:
    """提示词详情；保存/回滚时附带 warnings。"""
    updated_by = _users_by_id(
        db, {prompt.updated_by} if prompt.updated_by is not None else set()
    ).get(prompt.updated_by)
    payload = {
        "agent_code": prompt.agent_code,
        "name": prompt.name,
        "content": prompt.content,
        "current_version": prompt.current_version,
        "updated_by": _user_payload(updated_by),
        "updated_at": to_iso(prompt.updated_at),
        "suggested_variables": list(SUGGESTED_VARIABLES.get(prompt.agent_code, ())),
        "variables_in_content": _extract_variables(prompt.content),
        "versions": _prompt_versions(db, prompt),
    }
    if warnings is not None:
        payload["warnings"] = warnings
    return payload


def _get_prompt(db: Session, agent_code: str, *, for_update: bool = False) -> SystemPrompt:
    """按 agent_code 读取提示词；未知 Agent 返回 30021。"""
    if agent_code not in AGENT_ORDER:
        raise ApiError(404, 30021, "系统提示词不存在")
    statement = select(SystemPrompt).where(SystemPrompt.agent_code == agent_code)
    if for_update:
        statement = statement.with_for_update()
    prompt = db.scalar(statement)
    if prompt is None:
        logger.error("系统提示词缺失: %s（请执行种子脚本修复）", agent_code)
        raise ApiError(500, 50002, "系统提示词配置不完整")
    return prompt


# ---- 模型配置 ----

def _model_payload(db: Session, config: ModelConfig | None) -> dict:
    """模型配置响应；无启用配置时返回默认骨架。"""
    if config is None:
        return {
            "provider": PROVIDER,
            "provider_label": PROVIDER_LABEL,
            "base_url": None,
            "api_key_masked": None,
            "api_key_configured": False,
            "text_model": None,
            "image_model": None,
            "vision_model": None,
            "temperature": None,
            "timeout_seconds": None,
            "concurrency": None,
            "retry_count": None,
            "max_context_tokens": None,
            "updated_by": None,
            "updated_at": None,
        }

    masked = None
    if config.api_key_ciphertext:
        try:
            masked = mask_api_key(decrypt_api_key(config.api_key_ciphertext))
        except ModelConfigCryptoError as exc:
            logger.exception("模型配置 API Key 解密失败: %s", exc)
            raise ApiError(500, 50001, "系统内部错误") from exc

    updated_by = (
        _users_by_id(db, {config.updated_by}).get(config.updated_by)
        if config.updated_by is not None
        else None
    )
    return {
        "provider": config.provider,
        "provider_label": PROVIDER_LABEL,
        "base_url": config.base_url,
        "api_key_masked": masked,
        "api_key_configured": bool(config.api_key_ciphertext),
        "text_model": config.text_model,
        "image_model": config.image_model,
        "vision_model": config.vision_model,
        "temperature": float(config.temperature) if config.temperature is not None else None,
        "timeout_seconds": config.timeout_seconds,
        "concurrency": config.concurrency,
        "retry_count": config.retry_count,
        "max_context_tokens": config.max_context_tokens,
        "updated_by": _user_payload(updated_by),
        "updated_at": to_iso(config.updated_at),
    }


def _validate_base_url(value: str | None) -> str:
    if value is None or value.strip() == "":
        raise ApiError(400, 10002, "缺少 base_url")
    base_url = value.strip()
    if len(base_url) > 500:
        raise ApiError(400, 10003, "base_url 格式不合法")
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError(400, 10003, "base_url 需为合法的 http/https 地址")
    return base_url


def _validate_model_name(value: str | None, field: str) -> str:
    if value is None or value.strip() == "":
        raise ApiError(400, 10002, f"缺少 {field}")
    name = value.strip()
    if len(name) > 100:
        raise ApiError(400, 10003, f"{field} 不能超过 100 个字符")
    return name


def _validate_optional_model_name(value: str | None, field: str) -> str | None:
    if value is None or value.strip() == "":
        return None
    name = value.strip()
    if len(name) > 100:
        raise ApiError(400, 10003, f"{field} 不能超过 100 个字符")
    return name


def _validate_temperature(value: float | None) -> float:
    if value is None:
        raise ApiError(400, 10002, "缺少 temperature")
    if not math.isfinite(value) or value < 0 or value > 2:
        raise ApiError(400, 10004, "温度需在 0~2 之间")
    if abs(value * 10 - round(value * 10)) > 1e-9:
        raise ApiError(400, 10003, "温度步长需为 0.1")
    return float(round(value, 1))


def _validate_int_range(
    value: int | None, field: str, minimum: int, maximum: int
) -> int:
    if value is None:
        raise ApiError(400, 10002, f"缺少 {field}")
    if not minimum <= value <= maximum:
        raise ApiError(400, 10004, f"{field} 需在 {minimum}~{maximum} 之间")
    return value


@router.get("/model-config")
def get_model_config(
    auth: AuthContext = Depends(require_permission("admin.model.view")),
    db: Session = Depends(get_db),
) -> dict:
    """读取当前启用模型配置（Key 脱敏）。"""
    config = db.scalar(select(ModelConfig).where(ModelConfig.is_active.is_(True)))
    return ok(_model_payload(db, config))


@router.put("/model-config")
def save_model_config(
    payload: ModelConfigRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.model.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """保存模型配置；api_key 为空表示不修改。"""
    if payload.provider is not None and payload.provider != PROVIDER:
        raise ApiError(400, 10001, "服务商不可修改")

    base_url = _validate_base_url(payload.base_url)
    text_model = _validate_model_name(payload.text_model, "text_model")
    image_model = _validate_model_name(payload.image_model, "image_model")
    vision_model = _validate_optional_model_name(payload.vision_model, "vision_model")
    temperature = _validate_temperature(payload.temperature)
    timeout_seconds = _validate_int_range(
        payload.timeout_seconds, "timeout_seconds", 30, 300
    )
    concurrency = _validate_int_range(payload.concurrency, "concurrency", 1, 16)
    retry_count = _validate_int_range(payload.retry_count, "retry_count", 0, 3)

    max_context_tokens = payload.max_context_tokens
    if max_context_tokens is not None and not 1024 <= max_context_tokens <= 128000:
        raise ApiError(400, 10004, "max_context_tokens 需在 1024~128000 之间")

    if payload.api_key is not None and len(payload.api_key) > 512:
        raise ApiError(400, 10003, "api_key 不能超过 512 个字符")

    config = db.scalar(
        select(ModelConfig).where(ModelConfig.is_active.is_(True)).with_for_update()
    )
    is_new = config is None
    if is_new:
        config = ModelConfig(
            provider=PROVIDER,
            base_url=base_url,
            text_model=text_model,
            image_model=image_model,
            vision_model=vision_model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            concurrency=concurrency,
            retry_count=retry_count,
            max_context_tokens=max_context_tokens,
            is_active=True,
        )
        db.add(config)

    new_values = {
        "base_url": base_url,
        "text_model": text_model,
        "image_model": image_model,
        "vision_model": vision_model,
        "temperature": temperature,
        "timeout_seconds": timeout_seconds,
        "concurrency": concurrency,
        "retry_count": retry_count,
        "max_context_tokens": max_context_tokens,
    }
    old_values = (
        {
            field: getattr(config, field)
            for field in new_values
        }
        if not is_new
        else {field: None for field in new_values}
    )
    if "temperature" in old_values and old_values["temperature"] is not None:
        old_values["temperature"] = float(old_values["temperature"])

    changed_fields = sorted(
        field for field, value in new_values.items() if old_values.get(field) != value
    )

    api_key_changed = bool(payload.api_key)
    if api_key_changed:
        try:
            config.api_key_ciphertext = encrypt_api_key(payload.api_key)
        except ModelConfigCryptoError as exc:
            logger.exception("模型配置 API Key 加密失败: %s", exc)
            raise ApiError(500, 50001, "系统内部错误") from exc

    config.provider = PROVIDER
    config.base_url = base_url
    config.text_model = text_model
    config.image_model = image_model
    config.vision_model = vision_model
    config.temperature = temperature
    config.timeout_seconds = timeout_seconds
    config.concurrency = concurrency
    config.retry_count = retry_count
    config.max_context_tokens = max_context_tokens
    config.updated_by = auth.user.id
    db.flush()

    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action="model_config.update",
        result="success",
        target_type="model_config",
        target_id=str(config.id),
        # 只记录变更字段名与是否修改 Key，不记录 Key 明文/密文
        detail={"changed_fields": changed_fields, "api_key_changed": api_key_changed},
    )
    db.commit()
    db.refresh(config)
    return ok(_model_payload(db, config))


# ---- 系统提示词 ----

@router.get("/prompts")
def list_prompts(
    auth: AuthContext = Depends(require_permission("admin.prompts.view")),
    db: Session = Depends(get_db),
) -> dict:
    """8 个 Agent 提示词列表（固定顺序，不分页）。"""
    prompts = {
        prompt.agent_code: prompt
        for prompt in db.scalars(select(SystemPrompt))
    }
    missing = [code for code in AGENT_ORDER if code not in prompts]
    if missing:
        logger.error("系统提示词缺失: %s（请执行种子脚本修复）", ",".join(missing))
        raise ApiError(500, 50002, "系统提示词配置不完整")

    users = _users_by_id(
        db,
        {
            prompts[code].updated_by
            for code in AGENT_ORDER
            if prompts[code].updated_by is not None
        },
    )
    return ok(
        {
            "items": [
                {
                    "agent_code": code,
                    "name": prompts[code].name or AGENT_NAMES[code],
                    "current_version": prompts[code].current_version,
                    "content_preview": _content_preview(prompts[code].content),
                    "updated_by": _user_payload(users.get(prompts[code].updated_by)),
                    "updated_at": to_iso(prompts[code].updated_at),
                }
                for code in AGENT_ORDER
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
    prompt = _get_prompt(db, agent_code)
    return ok(_prompt_payload(db, prompt))


@router.put("/prompts/{agent_code}")
def save_prompt(
    agent_code: str,
    payload: PromptSaveRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.prompts.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """保存新版本并设为当前。"""
    prompt = _get_prompt(db, agent_code, for_update=True)

    content = (payload.content or "").strip()
    if not content:
        raise ApiError(400, 10002, "提示词不能为空")
    if len(content) > PROMPT_MAX_LENGTH:
        raise ApiError(400, 10004, "提示词不能超过 20000 个字符")

    warnings = _prompt_warnings(content, agent_code)
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
    db.flush()

    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action="prompt.update",
        result="success",
        target_type="system_prompt",
        target_id=agent_code,
        detail={
            "agent_code": agent_code,
            "version": new_version,
            "unknown_variables": warnings["unknown_variables"],
            "missing_suggested_variables": warnings["missing_suggested_variables"],
        },
    )
    db.commit()
    db.refresh(prompt)
    return ok(_prompt_payload(db, prompt, warnings=warnings))


@router.post("/prompts/{agent_code}/versions/{version}/activate")
def activate_prompt_version(
    agent_code: str,
    version: int,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.prompts.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """回滚到指定版本：复制目标内容生成新版本，不删除历史。"""
    prompt = _get_prompt(db, agent_code, for_update=True)
    target = db.scalar(
        select(PromptVersion).where(
            PromptVersion.prompt_id == prompt.id,
            PromptVersion.version == version,
        )
    )
    if target is None:
        raise ApiError(404, 30022, "提示词版本不存在")

    warnings = _prompt_warnings(target.content, agent_code)
    new_version = prompt.current_version + 1
    prompt.content = target.content
    prompt.current_version = new_version
    prompt.updated_by = auth.user.id
    db.add(
        PromptVersion(
            prompt_id=prompt.id,
            agent_code=agent_code,
            version=new_version,
            content=target.content,
            created_by=auth.user.id,
        )
    )
    db.flush()

    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action="prompt.rollback",
        result="success",
        target_type="system_prompt",
        target_id=agent_code,
        detail={
            "agent_code": agent_code,
            "source_version": version,
            "new_version": new_version,
            "unknown_variables": warnings["unknown_variables"],
            "missing_suggested_variables": warnings["missing_suggested_variables"],
        },
    )
    db.commit()
    db.refresh(prompt)
    return ok(_prompt_payload(db, prompt, warnings=warnings))
