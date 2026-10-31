"""生图任务纯函数单测：默认版式、文字合成与状态机。"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.models.workspace import GeneratedImage, GenerationBatch
from app.modules.generation.composition import build_default_layout, compose_text
from app.modules.generation.pipeline import (
    _only_whitespace_issue,
    _regenerate_prompt_item,
    _with_whitespace_instruction,
)
from app.modules.generation.state import (
    IllegalTransition,
    can_transition_batch,
    transition_batch,
    transition_image,
)


def test_build_default_layout_matches_prd():
    print("[测试] 默认版式：标题上方 15%，卖点下方 20%，左右边距 8%")
    layout = build_default_layout(
        {"title": "轻盈透气 一整天", "selling_points": ["冰感面料", "不易起球", "通勤百搭"]},
        1000,
        1000,
    )
    assert layout["canvas"] == {"width": 1000, "height": 1000}
    title, points = layout["blocks"]
    assert title["type"] == "title"
    assert title["box"] == {"x": 80, "y": 20, "width": 840, "height": 130}
    assert title["font_size"] == 64
    assert title["font_weight"] == "bold"
    assert title["color"] == "#1A1A1A"
    assert points["type"] == "selling_points"
    assert points["box"] == {"x": 80, "y": 780, "width": 840, "height": 180}
    assert points["font_size"] == 36
    assert points["items"] == ["冰感面料", "不易起球", "通勤百搭"]


def test_build_default_layout_scales_and_limits():
    print("[测试] 512 画布字号按比例缩放，卖点最多 3 条")
    layout = build_default_layout(
        {"title": "标题", "selling_points": ["一", "二", "三", "四"]}, 512, 512
    )
    title, points = layout["blocks"]
    assert title["font_size"] == 33
    assert title["min_font_size"] == 20
    assert points["font_size"] == 18
    assert points["items"] == ["一", "二", "三"]


def test_compose_text_outputs_correct_png_and_warnings():
    print("[测试] 深色底图加半透明白底，输出同尺寸 PNG")
    base = Image.new("RGB", (1000, 1000), (30, 30, 30))
    buffer = BytesIO()
    base.save(buffer, format="PNG")

    layout = build_default_layout(
        {"title": "轻盈透气 一整天", "selling_points": ["冰感面料", "不易起球", "通勤百搭"]},
        1000,
        1000,
    )
    result = compose_text(buffer.getvalue(), layout)
    assert result.warnings == []
    image = Image.open(BytesIO(result.png))
    assert image.size == (1000, 1000)
    assert image.format == "PNG"
    # 深色标题区被半透明白底提亮（取文字左侧的面板区域，避开文字笔画）
    assert image.convert("L").getpixel((100, 40)) > 150

    print("[测试] 超长标题与超过 3 条卖点被记录警告")
    long_layout = build_default_layout(
        {"title": "超" * 100, "selling_points": ["卖点一", "卖点二", "卖点三", "卖点四"]},
        1000,
        1000,
    )
    long_result = compose_text(buffer.getvalue(), long_layout)
    assert any("截断" in warning for warning in long_result.warnings)
    assert any("卖点超过 3 条" in warning for warning in long_result.warnings)


def test_state_machine_illegal_transitions():
    print("[测试] 批次与图片非法流转被拒绝")
    batch = GenerationBatch(status="sample_ready")
    with pytest.raises(IllegalTransition):
        transition_batch(batch, "running")
    transition_batch(batch, "confirmed")
    assert batch.status == "confirmed"

    assert can_transition_batch("running", "sample_ready")
    assert not can_transition_batch("cancelled", "running")

    image = GeneratedImage(status="success")
    with pytest.raises(IllegalTransition):
        transition_image(image, "generating")
    transition_image(image, "superseded")
    assert image.status == "superseded"


def test_only_whitespace_issue_detection():
    print("[测试] 只有留白不足时才走合成兜底，其他硬性项失败仍需修复")
    assert _only_whitespace_issue(
        {
            "passed": False,
            "issues": ["顶部留白不足"],
            "checks": {
                "product_fidelity": "pass",
                "deformity": "pass",
                "whitespace_available": "fail",
                "compliance": "pass",
            },
        }
    )
    assert not _only_whitespace_issue(
        {
            "passed": False,
            "checks": {
                "product_fidelity": "fail",
                "deformity": "pass",
                "whitespace_available": "fail",
            },
        }
    )
    assert not _only_whitespace_issue(
        {"passed": False, "checks": {"whitespace_available": "pass"}}
    )


def test_with_whitespace_instruction_is_idempotent():
    print("[测试] 生图提示词追加显式留白比例，重复调用不重复追加")
    item = {
        "prompt": "简洁白底，商品居中",
        "whitespace": {"top_ratio": 0.18, "bottom_ratio": 0.22},
    }
    first = _with_whitespace_instruction(item)
    assert "【构图留白要求】" in first["prompt"]
    assert "18%" in first["prompt"] and "22%" in first["prompt"]
    second = _with_whitespace_instruction(first)
    assert second["prompt"] == first["prompt"]


def test_compose_text_force_panel_on_light_background():
    print("[测试] 留白不足时强制加半透明底，浅色背景也会提亮文字区")
    base = Image.new("RGB", (1000, 1000), (245, 245, 245))
    buffer = BytesIO()
    base.save(buffer, format="PNG")
    layout = build_default_layout(
        {"title": "轻盈透气 一整天", "selling_points": ["冰感面料"]}, 1000, 1000
    )
    result = compose_text(buffer.getvalue(), layout, force_panel=True)
    assert result.png.startswith(b"\x89PNG")
    assert Image.open(BytesIO(result.png)).size == (1000, 1000)


def test_regenerate_prompt_prefers_image_final_prompt():
    print("[测试] 重试优先沿用图片自身保存的最终（修复后）提示词")
    image = GeneratedImage(
        index_no=2,
        prompt="修复后的提示词",
        negative_prompt="修复后的负面词",
    )
    prompt_output = {
        "images": [
            {
                "index": 2,
                "prompt": "示例批次的原始提示词",
                "negative_prompt": "原始负面词",
                "whitespace": {"top_ratio": 0.18, "bottom_ratio": 0.22},
                "reference_asset_ids": [4],
            }
        ]
    }
    item = _regenerate_prompt_item(image, prompt_output)
    assert item["prompt"] == "修复后的提示词"
    assert item["negative_prompt"] == "修复后的负面词"
    assert item["reference_asset_ids"] == [4]
    assert item["whitespace"]["top_ratio"] == 0.18
