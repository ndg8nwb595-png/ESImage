"""豆包（火山方舟）文本模型接入与确定性演示桩。

- 配置了 `ARK_API_KEY` 且未开启 `CHAT_USE_STUB` 时调用真实模型；
- 否则使用演示桩，保证本地与测试环境可运行且不产生真实调用费用；
- 两条路径返回相同的结构，SSE 事件与落库字段不变。
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.modules.chat.agents import (
    PLANNER_SYSTEM_PROMPT,
    PRODUCT_UNDERSTANDING_SYSTEM_PROMPT,
    build_reply,
    merge_agent_summary,
    run_planner as run_planner_stub,
)

SUMMARY_SENTINEL = "<<<SUMMARY>>>"


class ModelCallError(Exception):
    """模型调用失败；上层转换为 SSE error 30001。"""


@dataclass
class PlannerOutput:
    """规划 Agent 的结构化输出。"""

    plan: dict[str, Any]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    model_name: str | None = None


class ProductStream:
    """商品理解 Agent 的流式输出与最终结果。"""

    def __init__(self) -> None:
        self.reply = ""
        self.summary: dict[str, Any] = {}
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.latency_ms = 0
        self.model_name: str | None = None

    def __iter__(self) -> Iterator[str]:
        raise NotImplementedError


def real_model_enabled() -> bool:
    """是否使用真实豆包模型。"""
    return bool(settings.ARK_API_KEY) and bool(settings.ARK_TEXT_MODEL) and not settings.CHAT_USE_STUB


def _client() -> OpenAI:
    """创建 OpenAI 兼容客户端；单测会 monkeypatch 本函数。"""
    return OpenAI(
        base_url=settings.ARK_BASE_URL,
        api_key=settings.ARK_API_KEY,
        timeout=settings.ARK_TIMEOUT_SECONDS,
    )


def _context_prompt(context: dict[str, Any]) -> str:
    """把参数、需求摘要与已确认示例拼成一条系统消息。"""
    params = context.get("params") or {}
    summary = context.get("requirement_summary") or {}
    lines = [
        "当前参数："
        f"商品名称={params.get('product_name') or '未填写'}；"
        f"风格={params.get('style_text') or '未填写'}；"
        f"尺寸={params.get('width')}x{params.get('height')}；"
        f"模板={params.get('template_id') or '未使用'}。",
        f"当前需求摘要：{json.dumps(summary, ensure_ascii=False)}。",
    ]
    if context.get("confirmed_sample"):
        lines.append(f"已确认示例图：{context['confirmed_sample']}。")
    return "\n".join(lines)


def _messages(context: dict[str, Any], system_prompt: str) -> list[dict[str, str]]:
    """把上下文转换为 OpenAI chat 消息数组。"""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": _context_prompt(context)},
    ]
    for item in context.get("messages") or []:
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant", "system") and content:
            messages.append({"role": role, "content": content})
    return messages


def _extract_json(text: str) -> dict[str, Any] | None:
    """从模型输出中提取 JSON 对象，容忍代码块与前后说明。"""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except ValueError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def _usage_tokens(usage: Any) -> tuple[int, int]:
    if usage is None:
        return 0, 0
    return (
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
    )


def run_planner(context: dict[str, Any], content: str) -> PlannerOutput:
    """规划 Agent：真实模型优先；未配置或调用失败时按调用方要求处理。"""
    if not real_model_enabled():
        return PlannerOutput(plan=run_planner_stub(context, content))

    system_prompt = (
        PLANNER_SYSTEM_PROMPT
        + "\n只输出一个 JSON 对象，不要输出 Markdown 代码块，字段："
        '{"intent": "chat|modify_style|modify_size|add_selling_point|ask_advice", '
        '"ask_follow_up": true/false, "style_suggestions": ["..."]}。'
    )
    started = time.perf_counter()
    try:
        completion = _client().chat.completions.create(
            model=settings.ARK_TEXT_MODEL,
            messages=_messages(context, system_prompt),
            temperature=0.3,
            max_tokens=400,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        raw = completion.choices[0].message.content if completion.choices else ""
        plan = _extract_json(raw or "") or run_planner_stub(context, content)
        prompt_tokens, completion_tokens = _usage_tokens(completion.usage)
        return PlannerOutput(
            plan=plan,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            model_name=settings.ARK_TEXT_MODEL,
        )
    except Exception as exc:
        raise ModelCallError(f"规划 Agent 调用失败: {exc}") from exc


class _StubProductStream(ProductStream):
    """未配置真实模型时的固定回复，仍按固定长度切片模拟流式输出。"""

    def __init__(self, context: dict[str, Any]) -> None:
        super().__init__()
        self._context = context

    def __iter__(self) -> Iterator[str]:
        params = self._context.get("params") or {}
        reply = build_reply(
            params.get("product_name") or "",
            params.get("style_text"),
        )
        self.reply = reply
        self.summary = merge_agent_summary(
            self._context.get("requirement_summary"),
            {"product_name": params.get("product_name") or ""},
        )
        for start in range(0, len(reply), 12):
            yield reply[start : start + 12]


class _RealProductStream(ProductStream):
    """真实豆包流式输出：正文实时下发，摘要 JSON 在哨兵之后缓冲解析。"""

    def __init__(self, context: dict[str, Any]) -> None:
        super().__init__()
        self._context = context
        self._buffer = ""
        self._summary_buffer = ""
        self._summary_started = False
        self.model_name = settings.ARK_TEXT_MODEL

    def _consume(self, delta: str) -> Iterator[str]:
        if self._summary_started:
            self._summary_buffer += delta
            return
        self._buffer += delta
        index = self._buffer.find(SUMMARY_SENTINEL)
        if index == -1:
            # 保留可能被截断的哨兵前缀，避免把哨兵拆成正文下发；
            # 同时把末尾空白留在缓冲区，避免把哨兵前的换行发给用户
            keep = len(SUMMARY_SENTINEL) - 1
            safe = max(0, len(self._buffer) - keep)
            if safe:
                candidate = self._buffer[:safe]
                stripped = candidate.rstrip()
                trailing = candidate[len(stripped) :]
                if stripped:
                    self.reply += stripped
                    yield stripped
                self._buffer = trailing + self._buffer[safe:]
            return
        if index > 0:
            piece = self._buffer[:index].rstrip()
            if piece:
                self.reply += piece
                yield piece
        self._summary_started = True
        self._summary_buffer = self._buffer[index + len(SUMMARY_SENTINEL) :]
        self._buffer = ""

    def _finish(self) -> Iterator[str]:
        if not self._summary_started and self._buffer:
            piece = self._buffer.rstrip()
            if piece:
                self.reply += piece
                yield piece
            self._buffer = ""

        parsed = _extract_json(self._summary_buffer) or {}
        params = self._context.get("params") or {}
        if not parsed.get("product_name"):
            parsed["product_name"] = params.get("product_name")
        self.summary = merge_agent_summary(
            self._context.get("requirement_summary"),
            parsed,
        )

    def __iter__(self) -> Iterator[str]:
        system_prompt = (
            PRODUCT_UNDERSTANDING_SYSTEM_PROMPT
            + "\n你是对话中的商品理解 Agent，不是生图服务。"
            + "\n先输出自然、简洁的中文回复：确认你对商品与需求的理解；"
            "如有 1~2 个关键信息缺失，最多追问 1~2 个问题；给出 1~2 条可执行建议。"
            + "\n若用户未填写风格，列出 3~5 个适合该商品的风格建议，等待用户选择。"
            + "\n不要声称你会直接生成或制作图片，也不要承诺马上出图；"
            "如需生成，请引导用户点击界面上的「生成示例图」。"
            + "\n不要输出 Markdown 代码块。"
            + f"\n回复结束后另起一行输出 {SUMMARY_SENTINEL}，然后输出一个合法 JSON 对象，字段："
            '{"product_name": string|null, "category": string|null, '
            '"selling_points": string[], "target_audience": string|null, '
            '"scenes": string[], "tone": string|null, "constraints": string[]}。'
            + "\n字段语义：category 是推断类目；tone 是文案语气（如专业、轻松、活泼），"
            "不要把风格文本直接当作 tone；constraints 只记录用户明确提出的限制，"
            "不要重复尺寸、模板等界面参数；无法判断的字段用 null 或 []。"
        )
        started = time.perf_counter()
        try:
            stream = _client().chat.completions.create(
                model=settings.ARK_TEXT_MODEL,
                messages=_messages(self._context, system_prompt),
                temperature=0.7,
                max_tokens=1200,
                stream=True,
                stream_options={"include_usage": True},
            )
            for chunk in stream:
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    self.prompt_tokens, self.completion_tokens = _usage_tokens(usage)
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue
                yield from self._consume(delta)
            yield from self._finish()
            self.latency_ms = int((time.perf_counter() - started) * 1000)
        except Exception as exc:
            raise ModelCallError(f"商品理解 Agent 调用失败: {exc}") from exc


def stream_product(context: dict[str, Any]) -> ProductStream:
    """商品理解 Agent 工厂：真实模型或演示桩。"""
    if real_model_enabled():
        return _RealProductStream(context)
    return _StubProductStream(context)
