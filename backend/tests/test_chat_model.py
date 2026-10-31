"""豆包模型接入单测（使用假客户端，不产生真实调用）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.modules.chat import model as chat_model
from tests.chat_model_fakes import FakeClient, chunk


def _context() -> dict:
    return {
        "system_prompts": {"planner": "p", "product_understanding": "u"},
        "params": {
            "product_name": "秋季通勤衬衫",
            "style_text": "简洁白底",
            "width": 1000,
            "height": 1000,
            "template_id": None,
            "upload_ids": [],
        },
        "requirement_summary": {
            "product_name": "秋季通勤衬衫",
            "category": None,
            "selling_points": [],
            "target_audience": None,
            "scenes": [],
            "tone": None,
            "constraints": [],
        },
        "confirmed_sample": None,
        "messages": [{"role": "user", "content": "你好"}],
        "rounds": 1,
        "omitted": False,
        "system_note": None,
    }


def _enable_real_model(monkeypatch, fake: FakeClient) -> None:
    monkeypatch.setattr(settings, "ARK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ARK_TEXT_MODEL", "test-model")
    monkeypatch.setattr(settings, "CHAT_USE_STUB", False)
    monkeypatch.setattr(chat_model, "_client", lambda: fake)


def test_real_planner_and_product_stream(monkeypatch):
    fake = FakeClient()
    _enable_real_model(monkeypatch, fake)

    print("[测试] 规划 Agent 返回 JSON 与 Token")
    planner = chat_model.run_planner(_context(), "你好")
    assert planner.plan["intent"] == "chat"
    assert planner.prompt_tokens == 10 and planner.completion_tokens == 5
    assert planner.model_name == "test-model"

    print("[测试] 商品理解 Agent 流式输出：哨兵与摘要 JSON 不下发给用户")
    stream = chat_model.stream_product(_context())
    deltas = list(stream)
    assert "".join(deltas) == "已了解商品。"
    assert stream.summary["selling_points"] == ["轻便"]
    assert stream.summary["product_name"] == "秋季通勤衬衫"
    assert stream.prompt_tokens == 20 and stream.completion_tokens == 30
    assert stream.model_name == "test-model"

    print("[测试] 规划调用不带 stream，商品理解调用带 stream 与 usage")
    assert fake.calls[0].get("stream") is None
    assert fake.calls[1]["stream"] is True
    assert fake.calls[1]["stream_options"] == {"include_usage": True}


def test_real_product_stream_without_sentinel_preserves_summary(monkeypatch):
    fake = FakeClient(
        product_factory=lambda: [
            chunk("这是完整回复"),
            chunk(usage=SimpleNamespace(prompt_tokens=7, completion_tokens=8)),
        ]
    )
    _enable_real_model(monkeypatch, fake)

    context = _context()
    context["requirement_summary"]["selling_points"] = ["轻便"]
    print("[测试] 模型没有输出哨兵时，整段文本作为回复，摘要保留旧字段")
    stream = chat_model.stream_product(context)
    deltas = list(stream)
    assert "".join(deltas) == "这是完整回复"
    assert stream.summary["selling_points"] == ["轻便"]
    assert stream.summary["product_name"] == "秋季通勤衬衫"
    assert stream.prompt_tokens == 7 and stream.completion_tokens == 8


def test_real_model_error_raises_model_call_error(monkeypatch):
    fake = FakeClient(error=RuntimeError("boom"))
    _enable_real_model(monkeypatch, fake)

    print("[测试] 规划 Agent 调用异常应包装为 ModelCallError")
    with pytest.raises(chat_model.ModelCallError):
        chat_model.run_planner(_context(), "你好")


def test_stub_used_when_model_disabled(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_USE_STUB", True)
    print("[测试] 演示桩模式下返回固定回复，不调用客户端")
    planner = chat_model.run_planner(_context(), "你好")
    assert planner.plan["intent"] == "chat"
    assert planner.model_name is None
    assert planner.prompt_tokens == 0 and planner.completion_tokens == 0

    stream = chat_model.stream_product(_context())
    assert "".join(stream) == (
        "已了解商品「秋季通勤衬衫」，风格按「简洁白底」处理。"
        "可以继续补充卖点、目标人群或使用场景。"
    )
    assert stream.model_name is None
    assert stream.prompt_tokens == 0 and stream.completion_tokens == 0
