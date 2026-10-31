"""8 Agent 运行时：系统提示词、结构化输出校验、重试与 agent_runs 落库。"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.workspace import AgentRun, GeneratedImage, GenerationBatch
from app.modules.generation import config_service
from app.modules.generation.doubao import (
    ChatResult,
    ImageResult,
    ModelGateway,
    ModerationResult,
    image_data_url,
    parse_json_object,
)

logger = logging.getLogger("esimage.generation.agents")

AGENT_ORDER = [
    "planner",
    "product_understanding",
    "copywriter",
    "prompt_builder",
    "image_generator",
    "quality_reviewer",
    "repairer",
    "platform_rule",
]
CORE_AGENTS = {"planner", "product_understanding", "copywriter", "prompt_builder"}
TEXT_ATTEMPTS = 10
IMAGE_ATTEMPTS = 2
BACKOFF_SECONDS = [1, 2, 4, 8, 16, 30, 30, 30, 30, 30]

PLATFORM_RULES_TEXT = (
    "1) 主图与详情图均为 1000×1000 或用户指定尺寸，宽高为正整数；\n"
    "2) 禁止使用“最”“第一”“国家级”“顶级”“绝对”“100%”等绝对化、虚假宣传用语；\n"
    "3) 服饰鞋包类目不得出现真人正脸，不得暗示医疗、保健功效；\n"
    "4) 不得出现二维码、联系方式、外部平台水印。"
)


class AgentFailure(RuntimeError):
    """Agent 连续失败，按核心/非核心策略由管线处理。"""

    def __init__(self, agent_code: str, message: str) -> None:
        super().__init__(message)
        self.agent_code = agent_code


class ImageGenerationFailure(AgentFailure):
    """生图执行连续 2 次失败。"""


@dataclass
class AgentContext:
    db: Session
    batch: GenerationBatch
    gateway: ModelGateway
    model_config: dict[str, Any]
    materials: list[dict[str, Any]] = field(default_factory=list)
    chat_summary: str = ""
    requirement_summary: dict[str, Any] | None = None
    image: GeneratedImage | None = None


@dataclass
class ImageAttempt:
    result: ImageResult
    moderation: ModerationResult


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[:limit] + "…"


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def log_agent_run(
    ctx: AgentContext,
    *,
    agent_code: str,
    status: str,
    model_name: str | None = None,
    input_payload: Any = None,
    output: Any = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int | None = None,
    error_message: str | None = None,
) -> None:
    """每次 Agent 调用（含每次重试）写一条 agent_runs。"""
    input_text = _json_text(input_payload) if input_payload is not None else None
    output_text = _json_text(output) if output is not None else None
    run = AgentRun(
        session_id=ctx.batch.session_id,
        batch_id=ctx.batch.id,
        image_id=ctx.image.id if ctx.image else None,
        agent_code=agent_code,
        status=status,
        model_name=model_name,
        input_summary=_truncate(input_text, 500),
        output_summary=_truncate(output_text, 500),
        input_full=input_text,
        output_full=output_text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        error_message=error_message,
    )
    ctx.db.add(run)
    ctx.db.commit()


def _system_prompt(ctx: AgentContext, agent_code: str) -> str:
    content = config_service.get_prompt(ctx.db, agent_code)
    if not content or not content.strip():
        raise AgentFailure(agent_code, f"缺少启用的系统提示词：{agent_code}")
    if "{{platform_rules}}" in content:
        content = content.replace("{{platform_rules}}", PLATFORM_RULES_TEXT)
    return content


def _messages(
    system_prompt: str,
    payload: dict[str, Any],
    images: list[bytes] | None = None,
) -> list[dict[str, Any]]:
    user_text = _json_text(payload)
    if not images:
        user_content: Any = user_text
    else:
        user_content = [{"type": "text", "text": user_text}]
        for data in images[:4]:
            user_content.append(
                {"type": "image_url", "image_url": {"url": image_data_url(data)}}
            )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _model_for(ctx: AgentContext, agent_code: str, has_images: bool) -> str:
    vision_model = ctx.model_config.get("vision_model")
    if has_images and vision_model and agent_code in {
        "product_understanding",
        "quality_reviewer",
    }:
        return str(vision_model)
    return str(ctx.model_config.get("text_model"))


def _call_text_agent(
    ctx: AgentContext,
    *,
    agent_code: str,
    input_payload: dict[str, Any],
    validator: Callable[[dict[str, Any], AgentContext], dict[str, Any]],
    images: list[bytes] | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    """文本/视觉 Agent：10 次尝试，指数退避，每次尝试写 agent_runs。"""
    system_prompt = _system_prompt(ctx, agent_code)
    messages = _messages(system_prompt, input_payload, images)
    model_name = _model_for(ctx, agent_code, bool(images))
    last_error: Exception | None = None

    for attempt in range(1, TEXT_ATTEMPTS + 1):
        started = time.perf_counter()
        result: ChatResult | None = None
        try:
            result = ctx.gateway.complete(
                agent_code=agent_code,
                messages=messages,
                model=model_name,
            )
            parsed = parse_json_object(result.content)
            output = validator(parsed, ctx)
            log_agent_run(
                ctx,
                agent_code=agent_code,
                status="success",
                model_name=result.model_name,
                input_payload=input_payload,
                output=output,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=result.latency_ms,
            )
            return output
        except Exception as exc:  # 网络、解析、契约校验都按一次失败处理
            last_error = exc
            latency = (
                result.latency_ms
                if result is not None
                else int((time.perf_counter() - started) * 1000)
            )
            log_agent_run(
                ctx,
                agent_code=agent_code,
                status="failed",
                model_name=result.model_name if result else model_name,
                input_payload=input_payload,
                output=result.content if result else None,
                prompt_tokens=result.prompt_tokens if result else 0,
                completion_tokens=result.completion_tokens if result else 0,
                latency_ms=latency,
                error_message=str(exc)[:1000],
            )
            if attempt >= TEXT_ATTEMPTS:
                break
            delay = BACKOFF_SECONDS[attempt - 1] * settings.AGENT_RETRY_BACKOFF_SCALE
            if delay > 0:
                time.sleep(delay)

    raise AgentFailure(
        agent_code,
        f"{agent_code} 连续 {TEXT_ATTEMPTS} 次失败（阶段 {stage or agent_code}）：{last_error}",
    )


def log_skipped(
    ctx: AgentContext,
    *,
    agent_code: str,
    reason: str,
    model_name: str | None = None,
    input_payload: Any = None,
) -> None:
    log_agent_run(
        ctx,
        agent_code=agent_code,
        status="skipped",
        model_name=model_name,
        input_payload=input_payload,
        output=None,
        error_message=reason,
    )


# ---------------------------------------------------------------- 契约校验


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} 必须是数组")
    return value


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")
    return value.strip()


def _validate_planner(data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    images = _require_list(data.get("images"), "images")
    if len(images) != 6:
        raise ValueError("images 必须固定 6 项")
    indexes = []
    roles = []
    themes = []
    for item in images:
        if not isinstance(item, dict):
            raise ValueError("images 元素必须是对象")
        index = item.get("index")
        if not isinstance(index, int):
            raise ValueError("index 必须是整数")
        role = item.get("role")
        if role not in ("main", "detail"):
            raise ValueError("role 必须是 main/detail")
        theme = _require_str(item.get("theme"), "theme")
        indexes.append(index)
        roles.append(role)
        themes.append(theme)
    if indexes != [1, 2, 3, 4, 5, 6]:
        raise ValueError("images 序号必须为 1~6")
    if roles.count("main") != 1 or roles.count("detail") != 5:
        raise ValueError("图片角色必须为 1 个 main + 5 个 detail")
    if len(set(themes)) != 6:
        raise ValueError("6 张图主题不能重复")
    order = _require_list(data.get("order"), "order")
    required = {"product_understanding", "copywriter", "prompt_builder", "image_generator"}
    if not required.issubset(set(order)):
        raise ValueError("order 缺少必需 Agent")
    data["image_count"] = 6
    return data


def _validate_product_understanding(
    data: dict[str, Any], ctx: AgentContext
) -> dict[str, Any]:
    _require_str(data.get("category"), "category")
    _require_str(data.get("target_audience"), "target_audience")
    for name in ("selling_points", "scenes", "constraints"):
        items = _require_list(data.get(name), name)
        if not all(isinstance(item, str) and item.strip() for item in items):
            raise ValueError(f"{name} 元素必须是非空字符串")
    material_ids = _require_list(data.get("material_ids"), "material_ids")
    allowed = {int(material["id"]) for material in ctx.materials}
    normalized = []
    for value in material_ids:
        try:
            material_id = int(value)
        except (TypeError, ValueError):
            continue
        if material_id in allowed and material_id not in normalized:
            normalized.append(material_id)
    data["material_ids"] = normalized
    return data


def _validate_copywriter(data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    images = _require_list(data.get("images"), "images")
    if len(images) != 6:
        raise ValueError("文案 images 必须固定 6 项")
    indexes = []
    for item in images:
        if not isinstance(item, dict):
            raise ValueError("文案元素必须是对象")
        index = item.get("index")
        if not isinstance(index, int):
            raise ValueError("文案 index 必须是整数")
        indexes.append(index)
        title = _require_str(item.get("title"), "title")
        if not 4 <= len(title) <= 16:
            raise ValueError("标题长度需在 4~16 字")
        points = _require_list(item.get("selling_points"), "selling_points")
        if not points:
            raise ValueError("卖点不能为空")
        for point in points:
            text = _require_str(point, "selling_point")
            if not 2 <= len(text) <= 12:
                raise ValueError("每条卖点长度需在 2~12 字")
        _require_str(item.get("body"), "body")
    if indexes != [1, 2, 3, 4, 5, 6]:
        raise ValueError("文案序号必须为 1~6")
    return data


def _validate_prompt_builder(data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    images = _require_list(data.get("images"), "images")
    if len(images) != 6:
        raise ValueError("提示词 images 必须固定 6 项")
    indexes = []
    for item in images:
        if not isinstance(item, dict):
            raise ValueError("提示词元素必须是对象")
        index = item.get("index")
        if not isinstance(index, int):
            raise ValueError("提示词 index 必须是整数")
        indexes.append(index)
        _require_str(item.get("prompt"), "prompt")
        item.setdefault("negative_prompt", "")
        whitespace = item.get("whitespace")
        if not isinstance(whitespace, dict):
            whitespace = {"top_ratio": 0.18, "bottom_ratio": 0.22}
        for key in ("top_ratio", "bottom_ratio"):
            try:
                ratio = float(whitespace.get(key))
            except (TypeError, ValueError):
                ratio = 0.2
            whitespace[key] = min(0.5, max(0.0, ratio))
        item["whitespace"] = whitespace
        model_params = item.get("model_params")
        if not isinstance(model_params, dict):
            model_params = {}
        model_params["width"] = int(model_params.get("width") or ctx.batch.width)
        model_params["height"] = int(model_params.get("height") or ctx.batch.height)
        item["model_params"] = model_params
        refs = item.get("reference_asset_ids")
        if not isinstance(refs, list):
            refs = []
        item["reference_asset_ids"] = [int(ref) for ref in refs if str(ref).isdigit()]
    if indexes != [1, 2, 3, 4, 5, 6]:
        raise ValueError("提示词序号必须为 1~6")
    return data


def _validate_quality(data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    if not isinstance(data.get("passed"), bool):
        raise ValueError("passed 必须是布尔值")
    data.setdefault("issues", [])
    data.setdefault("checks", {})
    return data


def _validate_repair(data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    _require_str(data.get("prompt"), "prompt")
    data.setdefault("negative_prompt", "")
    if not isinstance(data.get("whitespace"), dict):
        data["whitespace"] = {"top_ratio": 0.18, "bottom_ratio": 0.22}
    if not isinstance(data.get("reference_asset_ids"), list):
        data["reference_asset_ids"] = []
    return data


def _validate_platform(data: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    if not isinstance(data.get("passed"), bool):
        raise ValueError("passed 必须是布尔值")
    data.setdefault("issues", [])
    data.setdefault("checks", {})
    return data


# ---------------------------------------------------------------- Agent 入口


def run_planner(ctx: AgentContext, input_payload: dict[str, Any]) -> dict[str, Any]:
    return _call_text_agent(
        ctx,
        agent_code="planner",
        input_payload=input_payload,
        validator=_validate_planner,
        stage="planner",
    )


def run_product_understanding(
    ctx: AgentContext,
    input_payload: dict[str, Any],
    images: list[bytes],
) -> dict[str, Any]:
    return _call_text_agent(
        ctx,
        agent_code="product_understanding",
        input_payload=input_payload,
        validator=_validate_product_understanding,
        images=images,
        stage="product_understanding",
    )


def run_copywriter(ctx: AgentContext, input_payload: dict[str, Any]) -> dict[str, Any]:
    return _call_text_agent(
        ctx,
        agent_code="copywriter",
        input_payload=input_payload,
        validator=_validate_copywriter,
        stage="copywriter",
    )


def run_prompt_builder(ctx: AgentContext, input_payload: dict[str, Any]) -> dict[str, Any]:
    return _call_text_agent(
        ctx,
        agent_code="prompt_builder",
        input_payload=input_payload,
        validator=_validate_prompt_builder,
        stage="prompt_builder",
    )


def run_quality_reviewer(
    ctx: AgentContext,
    input_payload: dict[str, Any],
    image_bytes: bytes,
) -> dict[str, Any]:
    return _call_text_agent(
        ctx,
        agent_code="quality_reviewer",
        input_payload=input_payload,
        validator=_validate_quality,
        images=[image_bytes],
        stage="quality_reviewer",
    )


def run_repairer(ctx: AgentContext, input_payload: dict[str, Any]) -> dict[str, Any]:
    return _call_text_agent(
        ctx,
        agent_code="repairer",
        input_payload=input_payload,
        validator=_validate_repair,
        stage="repairer",
    )


def run_platform_rule(ctx: AgentContext, input_payload: dict[str, Any]) -> dict[str, Any]:
    return _call_text_agent(
        ctx,
        agent_code="platform_rule",
        input_payload=input_payload,
        validator=_validate_platform,
        stage="platform_rule",
    )


def run_image_generation(
    ctx: AgentContext,
    *,
    prompt_item: dict[str, Any],
    reference_images: list[bytes],
) -> ImageAttempt:
    """生图 + 生成图内容审核；每张最多 2 次，审核接口失败也计入尝试。"""
    prompt = str(prompt_item.get("prompt") or "")
    negative_prompt = str(prompt_item.get("negative_prompt") or "")
    last_error: Exception | None = None

    for attempt in range(1, IMAGE_ATTEMPTS + 1):
        started = time.perf_counter()
        result: ImageResult | None = None
        try:
            result = ctx.gateway.generate_image(
                prompt=prompt,
                negative_prompt=negative_prompt or None,
                width=ctx.batch.width,
                height=ctx.batch.height,
                reference_images=reference_images,
            )
            moderation = ctx.gateway.moderate_image(image_bytes=result.data)
            log_agent_run(
                ctx,
                agent_code="image_generator",
                status="success",
                model_name=result.model_name,
                input_payload={
                    "index": ctx.image.index_no if ctx.image else None,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "attempt": attempt,
                },
                output={
                    "width": result.width,
                    "height": result.height,
                    "moderation_passed": not moderation.blocked,
                    "moderation_message": moderation.reason,
                },
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=result.latency_ms,
            )
            return ImageAttempt(result=result, moderation=moderation)
        except Exception as exc:
            last_error = exc
            latency = (
                result.latency_ms
                if result is not None
                else int((time.perf_counter() - started) * 1000)
            )
            log_agent_run(
                ctx,
                agent_code="image_generator",
                status="failed",
                model_name=result.model_name if result else ctx.model_config.get("image_model"),
                input_payload={
                    "index": ctx.image.index_no if ctx.image else None,
                    "prompt": prompt,
                    "attempt": attempt,
                },
                output=None,
                prompt_tokens=result.prompt_tokens if result else 0,
                completion_tokens=result.completion_tokens if result else 0,
                latency_ms=latency,
                error_message=str(exc)[:1000],
            )
            if attempt >= IMAGE_ATTEMPTS:
                break

    raise ImageGenerationFailure(
        "image_generator",
        f"生图失败（最多 {IMAGE_ATTEMPTS} 次）：{last_error}",
    )
