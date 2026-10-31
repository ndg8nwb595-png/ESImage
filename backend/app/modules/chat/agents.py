"""聊天轻链路的确定性演示桩与上下文组装。

最小 demo 未配置文本模型时，由本模块给出固定回复与最小需求摘要；
事件类型、落库字段与正式模型保持一致。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.workspace import ChatMessage, CreativeSession, GenerationBatch

PLANNER_SYSTEM_PROMPT = (
    "你是电商主图规划 Agent。判断用户意图（补充需求/修改风格/询问建议/闲聊），"
    "决定是否需要追问，并输出下一轮对话策略；不要生成图片。"
)

PRODUCT_UNDERSTANDING_SYSTEM_PROMPT = (
    "你是商品理解 Agent。从商品名称、上传图与对话中提取商品画像与需求摘要；"
    "每轮返回完整摘要，未返回的顶层字段保留上一轮值。"
)

OMISSION_NOTE = "更早的对话已省略，需求摘要以当前 requirement_summary 为准"

STYLE_SUGGESTIONS = ["简洁白底", "高级质感", "生活场景", "国潮"]

SUMMARY_KEYS = (
    "product_name",
    "category",
    "selling_points",
    "target_audience",
    "scenes",
    "tone",
    "constraints",
)


@dataclass(frozen=True)
class ChatParams:
    """本轮聊天使用的参数快照；只进入上下文，不落库。"""

    product_name: str
    style_text: str | None
    width: int
    height: int
    template_id: int | None = None
    upload_ids: tuple[int, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "style_text": self.style_text,
            "width": self.width,
            "height": self.height,
            "template_id": self.template_id,
            "upload_ids": list(self.upload_ids),
        }


def latest_confirmed_sample(db: Session, session_id: int) -> GenerationBatch | None:
    """当前会话最近一个已确认的示例批次。"""
    return db.scalar(
        select(GenerationBatch)
        .where(
            GenerationBatch.session_id == session_id,
            GenerationBatch.batch_type == "sample",
            GenerationBatch.status == "confirmed",
        )
        .order_by(GenerationBatch.created_at.desc(), GenerationBatch.id.desc())
        .limit(1)
    )


def _sample_description(batch: GenerationBatch | None) -> str | None:
    """把已确认示例批次拼成一段可注入上下文的描述。"""
    if batch is None:
        return None
    summary = batch.requirement_summary if isinstance(batch.requirement_summary, dict) else {}
    return (
        f"商品名称：{batch.product_name}；"
        f"风格：{batch.style_text or '未填写'}；"
        f"需求摘要：{json.dumps(summary, ensure_ascii=False)}"
    )


def build_context(
    db: Session,
    session: CreativeSession,
    params: ChatParams,
    *,
    rounds: int = 10,
    exclude_message_id: int | None = None,
) -> dict[str, Any]:
    """按 3 号接口文档 §2.3 组装本次轻链路上下文。

    顺序：系统提示词、当前参数、需求摘要、最近 rounds 轮对话、已确认示例图描述。
    超过 rounds 轮时丢弃最早对话，并注入一条只存在于本次请求的省略说明。
    """
    limit = max(rounds, 1) * 2
    base = select(ChatMessage).where(
        ChatMessage.session_id == session.id,
        ChatMessage.role != "system",
    )
    if exclude_message_id is not None:
        base = base.where(ChatMessage.id != exclude_message_id)

    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(
        db.scalars(base.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit))
    )
    rows.reverse()

    omitted = total > limit
    system_note = OMISSION_NOTE if omitted else None
    messages: list[dict[str, str]] = []
    if system_note:
        messages.append({"role": "system", "content": system_note})
    messages.extend({"role": row.role, "content": row.content} for row in rows)

    batch = latest_confirmed_sample(db, session.id)
    return {
        "system_prompts": {
            "planner": PLANNER_SYSTEM_PROMPT,
            "product_understanding": PRODUCT_UNDERSTANDING_SYSTEM_PROMPT,
        },
        "params": params.as_dict(),
        "requirement_summary": session.requirement_summary or {},
        "confirmed_sample": _sample_description(batch),
        "messages": messages,
        "rounds": sum(1 for row in rows if row.role == "user"),
        "omitted": omitted,
        "system_note": system_note,
    }


def context_as_text(context: dict[str, Any]) -> str:
    """把上下文序列化为 agent_runs.input_full。"""
    return json.dumps(context, ensure_ascii=False)


def run_planner(context: dict[str, Any], content: str) -> dict[str, Any]:
    """规划 Agent 演示桩：只判断意图与追问策略，不生成图片。"""
    if any(keyword in content for keyword in ("风格", "样式", "改成", "换成")):
        intent = "modify_style"
    elif any(keyword in content for keyword in ("尺寸", "大小", "宽", "高")):
        intent = "modify_size"
    elif any(keyword in content for keyword in ("卖点", "优势", "特点")):
        intent = "add_selling_point"
    elif any(keyword in content for keyword in ("建议", "推荐", "怎么")):
        intent = "ask_advice"
    else:
        intent = "chat"

    style_text = (context.get("params") or {}).get("style_text")
    need_style = not style_text
    return {
        "intent": intent,
        "ask_follow_up": need_style,
        "style_suggestions": STYLE_SUGGESTIONS if need_style else [],
        "rounds_in_context": context.get("rounds", 0),
    }


def build_reply(product_name: str, style_text: str | None) -> str:
    """未配置文本模型时的固定演示回复；与 2 号 demo 文案保持一致。"""
    if style_text:
        return f"已了解商品「{product_name}」，风格按「{style_text}」处理。可以继续补充卖点、目标人群或使用场景。"
    return (
        f"已了解商品「{product_name}」。建议风格：简洁白底、高级质感、生活场景、国潮。"
        "你可以用自然语言选择或自行补充。"
    )


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _text_list(value: Any) -> list[str]:
    """把模型返回的数组字段归一为字符串列表；单字符串也接受。"""
    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if isinstance(item, (str, int, float)) and str(item).strip()
        ]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def merge_agent_summary(
    existing: dict[str, Any] | None, agent_summary: dict[str, Any] | None
) -> dict[str, Any]:
    """合并商品理解结果：未返回的顶层字段保留旧值，返回的字段整体替换。"""
    base = existing if isinstance(existing, dict) else {}
    result: dict[str, Any] = {
        "product_name": _text_or_none(base.get("product_name")),
        "category": _text_or_none(base.get("category")),
        "selling_points": _text_list(base.get("selling_points")),
        "target_audience": _text_or_none(base.get("target_audience")),
        "scenes": _text_list(base.get("scenes")),
        "tone": _text_or_none(base.get("tone")),
        "constraints": _text_list(base.get("constraints")),
    }
    if isinstance(agent_summary, dict):
        for key in SUMMARY_KEYS:
            if key not in agent_summary:
                continue
            value = agent_summary[key]
            if key in ("selling_points", "scenes", "constraints"):
                result[key] = _text_list(value)
            else:
                result[key] = _text_or_none(value)
    if not result["product_name"]:
        result["product_name"] = _text_or_none(base.get("product_name"))
    return result


def run_product_understanding(
    context: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """商品理解 Agent 演示桩：返回固定回复与更新后的完整需求摘要。"""
    params = context.get("params") or {}
    product_name = params.get("product_name") or ""
    style_text = params.get("style_text")
    summary = merge_agent_summary(
        context.get("requirement_summary"),
        {"product_name": product_name},
    )
    return build_reply(product_name, style_text), summary
