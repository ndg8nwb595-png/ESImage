"""豆包模型测试用的假 OpenAI 客户端。

只用于单测，不会发起真实网络请求。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

PLANNER_JSON = '{"intent": "chat", "ask_follow_up": false, "style_suggestions": []}'

PRODUCT_SUMMARY = {
    "product_name": "秋季通勤衬衫",
    "category": "衬衫",
    "selling_points": ["轻便"],
    "target_audience": "通勤女性",
    "scenes": ["通勤"],
    "tone": "专业",
    "constraints": [],
}


def chunk(content: str | None = None, usage=None) -> SimpleNamespace:
    choices = (
        [SimpleNamespace(delta=SimpleNamespace(content=content))]
        if content is not None
        else []
    )
    return SimpleNamespace(choices=choices, usage=usage)


def product_chunks(
    reply: str = "已了解商品。",
    summary: dict | None = None,
):
    """模拟把哨兵拆到多个 chunk 的真实流式输出。"""
    data = summary if summary is not None else PRODUCT_SUMMARY
    yield chunk(reply)
    yield chunk("\n<<<SUM")
    yield chunk("MARY>>>\n")
    yield chunk(json.dumps(data, ensure_ascii=False))
    yield chunk(usage=SimpleNamespace(prompt_tokens=20, completion_tokens=30))


class FakeClient:
    """OpenAI 兼容客户端的假实现。"""

    def __init__(
        self,
        *,
        planner_content: str = PLANNER_JSON,
        product_factory=product_chunks,
        error: Exception | None = None,
    ) -> None:
        self.planner_content = planner_content
        self.product_factory = product_factory
        self.error = error
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create)
        )

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if kwargs.get("stream"):
            return iter(self.product_factory())
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.planner_content)
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )
