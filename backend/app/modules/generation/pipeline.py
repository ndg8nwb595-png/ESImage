"""生图生成管线：示例批次、全套批次与单张重试/重生成。

异步形态为 FastAPI BackgroundTasks + 单实例；Worker 在每个检查点重新读取
批次状态，支持取消与整批超时。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.media import fit_to_size, make_thumbnail_webp, to_png_bytes
from app.core.storage import storage
from app.models.workspace import AgentRun, GeneratedImage, GenerationBatch, UploadedAsset
from app.modules.generation import agents, config_service, service
from app.modules.generation.composition import (
    CompositionError,
    build_default_layout,
    compose_text,
)
from app.modules.generation.doubao import build_gateway
from app.modules.generation.state import (
    current_success_images,
    recount_completed,
    summarize_full_status,
    transition_batch,
    transition_image,
)

logger = logging.getLogger("esimage.generation.pipeline")


class BatchCancelled(RuntimeError):
    """用户取消批次。"""


class BatchTimeout(RuntimeError):
    """整批超时。"""


# ---------------------------------------------------------------- 通用工具


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reload(db, batch: GenerationBatch) -> GenerationBatch:
    db.expire_all()
    refreshed = db.get(GenerationBatch, batch.id)
    if refreshed is None:
        raise RuntimeError(f"批次 {batch.id} 不存在")
    return refreshed


def _check_cancel(db, batch: GenerationBatch) -> None:
    """每个检查点读取最新批次状态，取消后停止创建新任务。"""
    db.refresh(batch)
    if batch.status == "cancelled":
        raise BatchCancelled()


def _check_timeout(batch: GenerationBatch) -> None:
    if (
        settings.APP_ENV == "test"
        and "timeout" in settings.GENERATION_FAULT_MODE.split(",")
    ):
        raise BatchTimeout("故障注入：批次超时")
    if batch.started_at is None:
        return
    elapsed = (_now() - batch.started_at).total_seconds()
    if elapsed > settings.BATCH_TIMEOUT_SECONDS:
        raise BatchTimeout(
            f"批次超时（已用 {int(elapsed)} 秒，上限 {settings.BATCH_TIMEOUT_SECONDS} 秒）"
        )


def _checkpoint(
    db,
    batch: GenerationBatch,
    *,
    check_cancel: bool = True,
    check_timeout: bool = True,
) -> None:
    if check_cancel:
        _check_cancel(db, batch)
    if check_timeout:
        _check_timeout(batch)


def _set_stage(db, batch: GenerationBatch, stage: str) -> None:
    batch.stage = stage
    db.commit()


def _mark_image_failed(db, image: GeneratedImage, message: str) -> None:
    if image.status == "success":
        return
    try:
        transition_image(image, "failed")
    except Exception:
        image.status = "failed"
    image.error_message = message
    image.is_history_visible = False
    db.commit()


def _mark_image_cancelled(db, image: GeneratedImage) -> None:
    if image.status not in ("pending", "generating"):
        return
    try:
        transition_image(image, "cancelled")
    except Exception:
        image.status = "cancelled"
    image.is_history_visible = False
    db.commit()


def _fail_unfinished_images(db, batch_id: int, reason: str) -> None:
    images = list(
        db.scalars(
            select(GeneratedImage).where(
                GeneratedImage.batch_id == batch_id,
                GeneratedImage.status.in_(("pending", "generating")),
            )
        )
    )
    for image in images:
        _mark_image_failed(db, image, reason)


def _finish_batch_failed(
    db,
    batch: GenerationBatch,
    message: str,
    *,
    stage: str | None = None,
    unfinished_reason: str = "批次已失败，未生成",
) -> None:
    if batch.status == "cancelled":
        return
    if stage:
        batch.stage = stage
    try:
        transition_batch(batch, "failed")
    except Exception:
        batch.status = "failed"
    batch.error_message = message[:1000]
    batch.finished_at = _now()
    db.commit()
    _fail_unfinished_images(db, batch.id, unfinished_reason)


def _emit_context(
    db, batch: GenerationBatch
) -> tuple[agents.AgentContext, dict[str, Any]]:
    model_config = config_service.get_model_config(db)
    if not model_config:
        raise agents.AgentFailure("model_config", "缺少启用的模型配置")
    ctx = agents.AgentContext(
        db=db,
        batch=batch,
        gateway=build_gateway(db),
        model_config=model_config,
        materials=config_service.get_materials(db),
        chat_summary=service.chat_summary(db, batch.session_id),
        requirement_summary=batch.requirement_summary,
    )
    return ctx, model_config


def _snapshot(batch: GenerationBatch) -> dict[str, Any]:
    return dict(batch.params_snapshot or {})


def _template_info(batch: GenerationBatch) -> dict[str, Any]:
    snapshot = _snapshot(batch)
    return {
        "name": snapshot.get("template_name"),
        "prompt_template": snapshot.get("template_prompt"),
        "layout_ref": snapshot.get("template_layout_ref"),
    }


def _material_candidates(ctx: agents.AgentContext) -> list[dict[str, Any]]:
    return [
        {
            "material_id": material["id"],
            "name": material["name"],
            "tags": material["tags"],
            "style_tags": material["style_tags"],
        }
        for material in ctx.materials
    ]


def _upload_files(db, batch: GenerationBatch) -> list[bytes]:
    """读取批次快照中的全部上传商品图（最多 5 张），按提交顺序返回。"""
    upload_ids = _snapshot(batch).get("upload_ids") or []
    if not upload_ids:
        return []
    rows = list(
        db.scalars(
            select(UploadedAsset).where(
                UploadedAsset.id.in_(upload_ids),
                UploadedAsset.user_id == batch.user_id,
                UploadedAsset.status == "active",
            )
        )
    )
    by_id = {row.id: row for row in rows}
    files: list[bytes] = []
    for upload_id in upload_ids[:5]:
        row = by_id.get(upload_id)
        if row is None:
            continue
        try:
            path = storage.path(row.file_path)
            if path.is_file():
                files.append(path.read_bytes())
        except ValueError:
            continue
    return files


def _material_files(ctx: agents.AgentContext, reference_ids: list[int]) -> list[bytes]:
    if not reference_ids:
        return []
    by_id = {int(material["id"]): material for material in ctx.materials}
    files: list[bytes] = []
    for material_id in reference_ids[:2]:
        material = by_id.get(int(material_id))
        if material is None:
            continue
        try:
            path = storage.path(material["file_path"])
            if path.is_file():
                files.append(path.read_bytes())
        except ValueError:
            continue
    return files


def _copy_block(copy_output: dict[str, Any], index: int) -> dict[str, Any]:
    for item in copy_output.get("images") or []:
        if int(item.get("index", 0)) == index:
            return item
    raise agents.AgentFailure("copywriter", f"缺少第 {index} 张文案")


def _prompt_item(prompt_output: dict[str, Any], index: int) -> dict[str, Any]:
    for item in prompt_output.get("images") or []:
        if int(item.get("index", 0)) == index:
            return dict(item)
    raise agents.AgentFailure("prompt_builder", f"缺少第 {index} 张提示词")


def _plan_item(plan_output: dict[str, Any], index: int) -> dict[str, Any]:
    for item in plan_output.get("images") or []:
        if int(item.get("index", 0)) == index:
            return item
    raise agents.AgentFailure("planner", f"缺少第 {index} 张计划")


def _persist_image(
    db,
    batch: GenerationBatch,
    image: GeneratedImage,
    *,
    composed_png: bytes,
    prompt_item: dict[str, Any],
    attempt: agents.ImageAttempt,
    final_prompt: str,
) -> None:
    """保存最终图与缩略图，并把图片置为成功。"""
    token = uuid.uuid4().hex
    file_path = f"generated/{batch.user_id}/{token}.png"
    thumbnail_path = f"thumbnails/{batch.user_id}/{token}.webp"
    storage.save(file_path, composed_png)
    storage.save(thumbnail_path, make_thumbnail_webp(composed_png))

    image.file_path = file_path
    image.thumbnail_path = thumbnail_path
    image.width = batch.width
    image.height = batch.height
    image.prompt = final_prompt
    image.negative_prompt = str(prompt_item.get("negative_prompt") or "")
    image.model_name = attempt.result.model_name
    image.latency_ms = attempt.result.latency_ms
    image.prompt_tokens = attempt.result.prompt_tokens
    image.completion_tokens = attempt.result.completion_tokens
    image.error_message = None
    if image.status != "success":
        transition_image(image, "success")
    image.is_history_visible = False
    db.commit()


# ---------------------------------------------------------------- 单张图片流程


def _only_whitespace_issue(quality: dict[str, Any]) -> bool:
    """质量审核是否仅因留白不足判失败；这种情况由文字合成兜底，不阻塞出图。"""
    checks = quality.get("checks") or {}
    if checks.get("whitespace_available") != "fail":
        return False
    return all(
        key == "whitespace_available" or str(value) == "pass"
        for key, value in checks.items()
    )


def _with_whitespace_instruction(prompt_item: dict[str, Any]) -> dict[str, Any]:
    """把留白比例写进生图提示词，降低 Seedream 忽略留白的概率。"""
    item = dict(prompt_item)
    whitespace = item.get("whitespace") or {}
    try:
        top = float(whitespace.get("top_ratio", 0.18))
        bottom = float(whitespace.get("bottom_ratio", 0.22))
    except (TypeError, ValueError):
        top, bottom = 0.18, 0.22
    marker = "【构图留白要求】"
    prompt = str(item.get("prompt") or "")
    if marker not in prompt:
        prompt = (
            f"{prompt}\n{marker}上方约 {top:.0%} 区域保持纯净留白，"
            f"下方约 {bottom:.0%} 区域保持纯净留白；商品主体完整位于中间区域，"
            "不与留白区重叠，顶部和底部不要出现商品或装饰。"
        )
    item["prompt"] = prompt
    return item


def _run_image_flow(
    ctx: agents.AgentContext,
    *,
    plan_item: dict[str, Any],
    copy_block: dict[str, Any],
    prompt_item: dict[str, Any],
    product_profile: dict[str, Any],
    check_cancel: bool = True,
    check_timeout: bool = True,
) -> bool:
    """单张图：生图 → 内容审核 → 质量审核（含修复复检）→ 平台规范 → 文字合成。

    返回 True 表示该张成功；False 表示非生图原因失败（该张继续由调用方汇总）。
    生图连续失败抛 ImageGenerationFailure，由调用方决定批次终态。
    """
    batch = ctx.batch
    image = ctx.image
    if image is None:
        raise RuntimeError("图片流程缺少 ctx.image")

    whitespace_warning = False
    # 把规划主题带入提示词上下文，便于质量审核与后台追溯
    prompt_item = dict(prompt_item)
    prompt_item.setdefault("theme", plan_item.get("theme"))

    _checkpoint(ctx.db, batch, check_cancel=check_cancel, check_timeout=check_timeout)
    _set_stage(ctx.db, batch, "image_generator")
    if image.status == "pending":
        transition_image(image, "generating")
    elif image.status != "generating":
        raise RuntimeError(f"图片 {image.id} 状态 {image.status} 不可生成")
    image.error_message = None
    ctx.db.commit()

    reference_images = _upload_files(ctx.db, batch) + _material_files(
        ctx, [int(value) for value in prompt_item.get("reference_asset_ids") or []]
    )
    prompt_item = _with_whitespace_instruction(prompt_item)

    attempt = agents.run_image_generation(
        ctx,
        prompt_item=prompt_item,
        reference_images=reference_images,
    )
    if attempt.moderation.blocked:
        message = "内容未通过审核，请调整描述或更换商品图"
        _mark_image_failed(ctx.db, image, message)
        return False

    base_png = to_png_bytes(
        fit_to_size(attempt.result.data, batch.width, batch.height)
    )

    _checkpoint(ctx.db, batch, check_cancel=False, check_timeout=check_timeout)
    vision_model = str(ctx.model_config.get("vision_model") or "")
    if not vision_model:
        agents.log_skipped(
            ctx,
            agent_code="quality_reviewer",
            reason="未配置视觉模型",
            model_name=None,
            input_payload={"index": image.index_no},
        )
    else:
        _set_stage(ctx.db, batch, "quality_reviewer")
        try:
            quality = agents.run_quality_reviewer(
                ctx,
                {
                    "index": image.index_no,
                    "product_profile": product_profile,
                    "prompt": prompt_item,
                },
                base_png,
            )
        except agents.AgentFailure as exc:
            agents.log_skipped(
                ctx,
                agent_code="quality_reviewer",
                reason=f"连续失败，跳过并标记未校验：{exc}",
                model_name=vision_model,
                input_payload={"index": image.index_no},
            )
            quality = {"passed": True, "issues": []}

        if not quality.get("passed"):
            if _only_whitespace_issue(quality):
                whitespace_warning = True
                agents.log_skipped(
                    ctx,
                    agent_code="repairer",
                    reason="仅留白不足，交由文字合成加半透明底兜底",
                    input_payload={"index": image.index_no},
                )
            else:
                issues = quality.get("issues") or ["质量审核未通过"]
                _checkpoint(ctx.db, batch, check_cancel=False, check_timeout=check_timeout)
                _set_stage(ctx.db, batch, "repairer")
                try:
                    repaired = agents.run_repairer(
                        ctx,
                        {
                            "index": image.index_no,
                            "issues": issues,
                            "prompt": prompt_item,
                            "product_profile": product_profile,
                        },
                    )
                except agents.AgentFailure as exc:
                    agents.log_skipped(
                        ctx,
                        agent_code="repairer",
                        reason=f"未修复：{exc}",
                        input_payload={"index": image.index_no},
                    )
                    _mark_image_failed(ctx.db, image, "质量问题未通过（未修复）")
                    return False

                repaired["index"] = image.index_no
                prompt_item = _with_whitespace_instruction(repaired)
                _set_stage(ctx.db, batch, "image_generator")
                second = agents.run_image_generation(
                    ctx,
                    prompt_item=prompt_item,
                    reference_images=reference_images,
                )
                if second.moderation.blocked:
                    _mark_image_failed(
                        ctx.db, image, "内容未通过审核，请调整描述或更换商品图"
                    )
                    return False
                attempt = second
                base_png = to_png_bytes(
                    fit_to_size(attempt.result.data, batch.width, batch.height)
                )

                _checkpoint(ctx.db, batch, check_cancel=False, check_timeout=check_timeout)
                _set_stage(ctx.db, batch, "quality_reviewer")
                try:
                    recheck = agents.run_quality_reviewer(
                        ctx,
                        {
                            "index": image.index_no,
                            "product_profile": product_profile,
                            "prompt": prompt_item,
                        },
                        base_png,
                    )
                except agents.AgentFailure as exc:
                    agents.log_skipped(
                        ctx,
                        agent_code="quality_reviewer",
                        reason=f"复检失败，跳过并标记未校验：{exc}",
                        model_name=vision_model,
                        input_payload={"index": image.index_no},
                    )
                    recheck = {"passed": True, "issues": []}
                if not recheck.get("passed"):
                    if _only_whitespace_issue(recheck):
                        whitespace_warning = True
                    else:
                        _mark_image_failed(ctx.db, image, "质量问题未通过")
                        return False

    _checkpoint(ctx.db, batch, check_cancel=False, check_timeout=check_timeout)
    _set_stage(ctx.db, batch, "platform_rule")
    try:
        platform = agents.run_platform_rule(
            ctx,
            {
                "index": image.index_no,
                "copy_block": copy_block,
                "width": batch.width,
                "height": batch.height,
                "category": product_profile.get("category"),
            },
        )
    except agents.AgentFailure as exc:
        agents.log_skipped(
            ctx,
            agent_code="platform_rule",
            reason=f"未校验：{exc}",
            input_payload={"index": image.index_no},
        )
        platform = {"passed": True, "issues": []}

    if not platform.get("passed"):
        issues = "；".join(str(item) for item in platform.get("issues") or [])
        _mark_image_failed(
            ctx.db, image, f"平台规范未通过：{issues}" if issues else "平台规范未通过"
        )
        return False

    _checkpoint(ctx.db, batch, check_cancel=False, check_timeout=check_timeout)
    _set_stage(ctx.db, batch, "text_composition")
    try:
        layout = build_default_layout(copy_block, batch.width, batch.height)
        composed = compose_text(base_png, layout, force_panel=whitespace_warning)
    except CompositionError as exc:
        logger.warning("批次 %s 第 %s 张文字合成失败：%s", batch.id, image.index_no, exc)
        _mark_image_failed(ctx.db, image, "文字合成失败")
        return False
    if composed.warnings:
        logger.info(
            "批次 %s 第 %s 张文字合成警告：%s",
            batch.id,
            image.index_no,
            "；".join(composed.warnings),
        )

    _persist_image(
        ctx.db,
        batch,
        image,
        composed_png=composed.png,
        prompt_item=prompt_item,
        attempt=attempt,
        final_prompt=str(prompt_item.get("prompt") or ""),
    )
    return True


# ---------------------------------------------------------------- 输入组装


def _planner_input(ctx: agents.AgentContext) -> dict[str, Any]:
    return {
        "params_snapshot": _snapshot(ctx.batch),
        "requirement_summary": ctx.requirement_summary,
        "chat_summary": ctx.chat_summary,
        "template": _template_info(ctx.batch),
    }


def _product_input(ctx: agents.AgentContext) -> dict[str, Any]:
    snapshot = _snapshot(ctx.batch)
    return {
        "product_name": snapshot.get("product_name") or ctx.batch.product_name,
        "has_uploaded_images": bool(snapshot.get("upload_ids")),
        "requirement_summary": ctx.requirement_summary,
        "chat_summary": ctx.chat_summary,
        "style_text": ctx.batch.style_text,
        "material_candidates": _material_candidates(ctx),
    }


def _copy_input(
    ctx: agents.AgentContext, plan: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    return {
        "product_profile": profile,
        "plan": plan,
        "style_text": ctx.batch.style_text,
        "template": _template_info(ctx.batch),
    }


def _prompt_input(
    ctx: agents.AgentContext,
    copy_output: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    return {
        "copy_blocks": copy_output.get("images"),
        "product_profile": profile,
        "style_text": ctx.batch.style_text,
        "width": ctx.batch.width,
        "height": ctx.batch.height,
        "template": _template_info(ctx.batch),
        "material_candidates": _material_candidates(ctx),
    }


# ---------------------------------------------------------------- 示例批次


def run_sample_pipeline(batch_id: int) -> None:
    """示例批次：queued → running → sample_ready / failed。"""
    with SessionLocal() as db:
        batch = db.get(GenerationBatch, batch_id)
        if batch is None or batch.status != "queued":
            logger.info("示例批次 %s 不是 queued，跳过", batch_id)
            return

        try:
            transition_batch(batch, "running")
            batch.started_at = _now()
            batch.stage = None
            db.commit()
        except Exception:
            logger.exception("示例批次 %s 启动失败", batch_id)
            return

        ctx: agents.AgentContext | None = None
        try:
            ctx, _ = _emit_context(db, batch)
            _checkpoint(db, batch)
            _set_stage(db, batch, "planner")
            plan = agents.run_planner(ctx, _planner_input(ctx))

            _checkpoint(db, batch)
            _set_stage(db, batch, "product_understanding")
            profile = agents.run_product_understanding(
                ctx, _product_input(ctx), _upload_files(db, batch)
            )

            _checkpoint(db, batch)
            _set_stage(db, batch, "copywriter")
            copy_output = agents.run_copywriter(
                ctx, _copy_input(ctx, plan, profile)
            )

            _checkpoint(db, batch)
            _set_stage(db, batch, "prompt_builder")
            prompt_output = agents.run_prompt_builder(
                ctx, _prompt_input(ctx, copy_output, profile)
            )

            image = db.scalar(
                select(GeneratedImage)
                .where(
                    GeneratedImage.batch_id == batch.id,
                    GeneratedImage.index_no == 1,
                    GeneratedImage.status != "superseded",
                )
                .order_by(GeneratedImage.attempt_no.desc())
            )
            if image is None:
                image = GeneratedImage(
                    batch_id=batch.id,
                    user_id=batch.user_id,
                    session_id=batch.session_id,
                    image_type="sample",
                    image_role="main",
                    index_no=1,
                    attempt_no=1,
                    status="pending",
                    width=batch.width,
                    height=batch.height,
                )
                db.add(image)
                db.commit()
            ctx.image = image

            ok = _run_image_flow(
                ctx,
                plan_item=_plan_item(plan, 1),
                copy_block=_copy_block(copy_output, 1),
                prompt_item=_prompt_item(prompt_output, 1),
                product_profile=profile,
            )
            if not ok:
                _finish_batch_failed(
                    db,
                    batch,
                    image.error_message or "示例图生成失败",
                    stage=batch.stage,
                    unfinished_reason=image.error_message or "示例图生成失败",
                )
                return

            # 生图开始后允许当前这张完成；完成后再检查取消，避免把在途图丢掉
            _check_cancel(db, batch)
            recount_completed(db, batch)
            transition_batch(batch, "sample_ready")
            batch.stage = "done"
            batch.finished_at = _now()
            db.commit()
            logger.info("示例批次 %s 生成完成", batch_id)
        except BatchCancelled:
            db.rollback()
            batch = _reload(db, batch)
            if batch.status != "cancelled":
                transition_batch(batch, "cancelled")
                batch.finished_at = _now()
                db.commit()
            for image in db.scalars(
                select(GeneratedImage).where(
                    GeneratedImage.batch_id == batch.id,
                    GeneratedImage.status.in_(("pending", "generating")),
                )
            ):
                _mark_image_cancelled(db, image)
        except BatchTimeout as exc:
            db.rollback()
            batch = _reload(db, batch)
            _finish_batch_failed(
                db, batch, f"批次超时：{exc}", stage=batch.stage, unfinished_reason="批次超时"
            )
        except agents.ImageGenerationFailure as exc:
            db.rollback()
            batch = _reload(db, batch)
            if ctx is not None and ctx.image is not None and ctx.image.status == "generating":
                _mark_image_failed(db, ctx.image, str(exc))
            _finish_batch_failed(
                db, batch, str(exc), stage="image_generator", unfinished_reason="批次已失败，未生成"
            )
        except agents.AgentFailure as exc:
            db.rollback()
            batch = _reload(db, batch)
            _finish_batch_failed(
                db,
                batch,
                f"{exc.agent_code}: {exc}",
                stage=batch.stage,
                unfinished_reason="批次已失败，未生成",
            )
        except Exception as exc:  # 兜底，避免后台线程静默退出
            logger.exception("示例批次 %s 生成异常", batch_id)
            db.rollback()
            batch = _reload(db, batch)
            _finish_batch_failed(
                db, batch, str(exc), stage=batch.stage, unfinished_reason="批次已失败，未生成"
            )


# ---------------------------------------------------------------- 全套批次


def _load_sample_outputs(
    db, full_batch: GenerationBatch
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """读取被确认示例批次的四类核心 Agent 输出；缺失返回 None。"""
    sample_id = full_batch.source_sample_batch_id
    if sample_id is None:
        return None, None, None, None

    def latest(agent_code: str) -> dict[str, Any] | None:
        run = db.scalar(
            select(AgentRun)
            .where(
                AgentRun.batch_id == sample_id,
                AgentRun.agent_code == agent_code,
                AgentRun.status == "success",
            )
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
        if run is None or not run.output_full:
            return None
        try:
            data = json.loads(run.output_full)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    return (
        latest("planner"),
        latest("product_understanding"),
        latest("copywriter"),
        latest("prompt_builder"),
    )


def run_full_pipeline(batch_id: int) -> None:
    """全套批次：复用示例四类 Agent 输出，串行生成 2~6 张详情图。"""
    with SessionLocal() as db:
        batch = db.get(GenerationBatch, batch_id)
        if batch is None or batch.status != "queued":
            logger.info("全套批次 %s 不是 queued，跳过", batch_id)
            return

        try:
            transition_batch(batch, "running")
            batch.started_at = _now()
            batch.stage = None
            db.commit()
        except Exception:
            logger.exception("全套批次 %s 启动失败", batch_id)
            return

        ctx: agents.AgentContext | None = None
        try:
            ctx, _ = _emit_context(db, batch)
            plan, profile, copy_output, prompt_output = _load_sample_outputs(db, batch)
            if not all((plan, profile, copy_output, prompt_output)):
                _finish_batch_failed(
                    db,
                    batch,
                    "示例结果不完整",
                    unfinished_reason="批次已失败，未生成",
                )
                return

            for index in range(2, batch.total_count + 1):
                _checkpoint(db, batch)
                image = db.scalar(
                    select(GeneratedImage)
                    .where(
                        GeneratedImage.batch_id == batch.id,
                        GeneratedImage.index_no == index,
                        GeneratedImage.status != "superseded",
                    )
                    .order_by(GeneratedImage.attempt_no.desc())
                )
                if image is None:
                    image = GeneratedImage(
                        batch_id=batch.id,
                        user_id=batch.user_id,
                        session_id=batch.session_id,
                        image_type="final",
                        image_role="detail",
                        index_no=index,
                        attempt_no=1,
                        status="pending",
                        width=batch.width,
                        height=batch.height,
                    )
                    db.add(image)
                    db.commit()
                ctx.image = image

                ok = _run_image_flow(
                    ctx,
                    plan_item=_plan_item(plan, index),
                    copy_block=_copy_block(copy_output, index),
                    prompt_item=_prompt_item(prompt_output, index),
                    product_profile=profile,
                )
                recount_completed(db, batch)
                db.commit()
                if not ok:
                    logger.info("全套批次 %s 第 %s 张失败，继续下一张", batch.id, index)

            _checkpoint(db, batch)
            recount_completed(db, batch)
            status = summarize_full_status(db, batch)
            transition_batch(batch, status)
            batch.stage = "done"
            batch.finished_at = _now()
            if status in ("completed", "partially_failed"):
                for image in current_success_images(db, batch.id):
                    if image.image_type == "final":
                        image.is_history_visible = True
                batch.error_message = (
                    "部分图片生成失败" if status == "partially_failed" else None
                )
            else:
                batch.error_message = "全部图片生成失败"
            db.commit()
            logger.info("全套批次 %s 结束，状态 %s", batch_id, status)
        except BatchCancelled:
            db.rollback()
            batch = _reload(db, batch)
            if batch.status != "cancelled":
                transition_batch(batch, "cancelled")
                batch.finished_at = _now()
                db.commit()
            for image in db.scalars(
                select(GeneratedImage).where(
                    GeneratedImage.batch_id == batch.id,
                    GeneratedImage.status.in_(("pending", "generating")),
                )
            ):
                _mark_image_cancelled(db, image)
        except BatchTimeout as exc:
            db.rollback()
            batch = _reload(db, batch)
            generating_stage = batch.stage == "image_generator"
            _fail_unfinished_images(db, batch.id, "批次超时")
            recount_completed(db, batch)
            target = "failed" if generating_stage else summarize_full_status(db, batch)
            try:
                transition_batch(batch, target)
            except Exception:
                batch.status = target
            batch.stage = batch.stage or "done"
            batch.error_message = f"批次超时：{exc}"
            batch.finished_at = _now()
            db.commit()
        except agents.ImageGenerationFailure as exc:
            db.rollback()
            batch = _reload(db, batch)
            if ctx is not None and ctx.image is not None and ctx.image.status == "generating":
                _mark_image_failed(db, ctx.image, str(exc))
            _finish_batch_failed(
                db, batch, f"生图失败：{exc}", stage="image_generator"
            )
        except Exception as exc:
            logger.exception("全套批次 %s 生成异常", batch_id)
            db.rollback()
            batch = _reload(db, batch)
            if isinstance(exc, agents.AgentFailure):
                message = f"{exc.agent_code}: {exc}"
            else:
                message = str(exc)
            _finish_batch_failed(db, batch, message, stage=batch.stage)


# ---------------------------------------------------------------- 单张重试/重生成


def _finalize_regenerate(
    db, batch: GenerationBatch, image: GeneratedImage, *, success: bool
) -> None:
    """重试结束后按当前图片结果汇总批次，并清理已恢复的批次错误。"""
    db.refresh(batch)
    recount_completed(db, batch)
    if batch.status == "cancelled":
        image.is_history_visible = False
        batch.stage = "done"
        db.commit()
        return

    target = summarize_full_status(db, batch)
    try:
        transition_batch(batch, target)
    except Exception:
        batch.status = target
    batch.finished_at = _now()
    if success and target in ("completed", "partially_failed") and image.status == "success":
        image.is_history_visible = True
    elif image.status != "success":
        image.is_history_visible = False

    if target == "completed":
        batch.error_message = None
    elif target == "partially_failed":
        batch.error_message = "部分图片生成失败"
    else:
        batch.error_message = "全部图片生成失败"
    batch.stage = "done"
    db.commit()


def _regenerate_prompt_item(
    image: GeneratedImage, prompt_output: dict[str, Any] | None
) -> dict[str, Any]:
    """优先沿用图片自身保存的最终提示词（修复后的），再用示例提示词补齐参数。"""
    if prompt_output is not None:
        item = _prompt_item(prompt_output, image.index_no)
    else:
        item = {
            "index": image.index_no,
            "prompt": image.prompt or "",
            "negative_prompt": image.negative_prompt or "",
            "whitespace": {"top_ratio": 0.18, "bottom_ratio": 0.22},
            "reference_asset_ids": [],
        }
    if image.prompt:
        item["prompt"] = image.prompt
        item["negative_prompt"] = image.negative_prompt or ""
    item.setdefault("index", image.index_no)
    return item


def run_regenerate_pipeline(new_image_id: int) -> None:
    """单张重试/重生成：只执行生图及后续，不调用前四个 Agent。"""
    with SessionLocal() as db:
        image = db.get(GeneratedImage, new_image_id)
        if image is None or image.status != "pending":
            logger.info("重试图片 %s 不是 pending，跳过", new_image_id)
            return
        batch = db.get(GenerationBatch, image.batch_id)
        if batch is None:
            return

        try:
            transition_image(image, "generating")
            db.commit()
            ctx, _ = _emit_context(db, batch)
            ctx.image = image

            plan, profile, copy_output, prompt_output = _load_sample_outputs(db, batch)
            if not all((plan, profile, copy_output, prompt_output)):
                # 兜底：没有示例输出时，沿用图片自身的提示词，文案用最小占位
                profile = {"category": None, "selling_points": []}
                copy_output = {
                    "images": [
                        {
                            "index": image.index_no,
                            "title": batch.product_name,
                            "selling_points": [],
                        }
                    ]
                }
                prompt_output = None
                plan = {
                    "images": [{"index": image.index_no, "role": image.image_role}]
                }

            ok = _run_image_flow(
                ctx,
                plan_item=_plan_item(plan, image.index_no),
                copy_block=_copy_block(copy_output, image.index_no),
                prompt_item=_regenerate_prompt_item(image, prompt_output),
                product_profile=profile,
                check_cancel=False,
                check_timeout=False,
            )

            _finalize_regenerate(db, batch, image, success=ok)
            logger.info(
                "重试图片 %s 结束，状态 %s，批次状态 %s",
                new_image_id,
                image.status,
                batch.status,
            )
        except agents.ImageGenerationFailure as exc:
            db.rollback()
            image = db.get(GeneratedImage, new_image_id)
            if image is not None:
                _mark_image_failed(db, image, str(exc))
            batch = db.get(GenerationBatch, image.batch_id if image else batch.id)
            if batch is not None and image is not None:
                _finalize_regenerate(db, batch, image, success=False)
        except BatchTimeout as exc:
            db.rollback()
            image = db.get(GeneratedImage, new_image_id)
            if image is not None:
                _mark_image_failed(db, image, "批次超时")
                batch = db.get(GenerationBatch, image.batch_id)
                if batch is not None:
                    _finalize_regenerate(db, batch, image, success=False)
            logger.warning("重试图片 %s 超时：%s", new_image_id, exc)
        except Exception as exc:
            logger.exception("重试图片 %s 异常", new_image_id)
            db.rollback()
            image = db.get(GeneratedImage, new_image_id)
            if image is not None:
                _mark_image_failed(db, image, f"重试失败：{exc}")
                batch = db.get(GenerationBatch, image.batch_id)
                if batch is not None:
                    _finalize_regenerate(db, batch, image, success=False)
