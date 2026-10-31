"""文字留白合成与默认版式（PRD §7.4 / 接口文档 §8）。

生图模型只负责画面，中文由后端用内置中文字体合成，保证文字正确可控。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageStat

from app.core.config import settings

logger = logging.getLogger("esimage.generation.composition")

# 可商用中文字体候选；生产环境用 FONT_PATH 指向已授权字体
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/Deng.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]
_BOLD_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/Dengb.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansSC-Bold.otf",
]

TITLE_COLOR = "#1A1A1A"
POINT_COLOR = "#333333"
MAX_SELLING_POINTS = 3


class CompositionError(RuntimeError):
    """文字合成失败，原因写入图片 error_message。"""


@dataclass
class CompositionResult:
    png: bytes
    warnings: list[str] = field(default_factory=list)


def resolve_font_path(bold: bool = False) -> Path | None:
    """按 FONT_PATH -> 系统候选 的顺序解析可用中文字体。"""
    candidates: list[str] = []
    if settings.FONT_PATH:
        candidates.append(settings.FONT_PATH)
    if bold:
        candidates.extend(_BOLD_FONT_CANDIDATES)
    candidates.extend(_FONT_CANDIDATES)
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def validate_font() -> None:
    """启动校验：生产环境缺少中文字体时 fail-fast。"""
    if resolve_font_path(bold=False) is not None:
        return
    if settings.APP_ENV == "test":
        logger.warning("测试环境未找到中文字体，文字合成将使用 Pillow 默认字体")
        return
    raise RuntimeError(
        "未找到中文字体，请通过 FONT_PATH 指定可商用中文字体文件后重启。"
    )


def _load_font(size: int, *, bold: bool) -> ImageFont.ImageFont:
    path = resolve_font_path(bold=bold)
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError as exc:
            raise CompositionError(f"字体加载失败：{exc}") from exc
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow 旧版本
        return ImageFont.load_default()


def _scale(width: int, height: int) -> float:
    return min(width, height) / 1000.0


def build_default_layout(copy_block: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    """按默认版式生成 layout_instruction（接口文档 §8.2）。"""
    if width <= 0 or height <= 0:
        raise CompositionError("画布尺寸非法")

    scale = _scale(width, height)
    margin = int(round(width * 0.08))
    title_font_size = max(int(round(40 * scale)), int(round(64 * scale)))
    point_font_size = max(int(round(24 * scale)), int(round(36 * scale)))

    title = str(copy_block.get("title") or "").strip()
    all_points = [
        str(item).strip()
        for item in (copy_block.get("selling_points") or [])
        if str(item).strip()
    ]
    layout_warnings: list[str] = []
    if len(all_points) > MAX_SELLING_POINTS:
        layout_warnings.append("卖点超过 3 条，只渲染前 3 条")
    points = all_points[:MAX_SELLING_POINTS]

    blocks: list[dict[str, Any]] = []
    if title:
        blocks.append(
            {
                "type": "title",
                "text": title,
                "box": {
                    "x": margin,
                    "y": int(round(height * 0.02)),
                    "width": width - margin * 2,
                    "height": int(round(height * 0.13)),
                },
                "font_size": title_font_size,
                "min_font_size": max(1, int(round(40 * scale))),
                "font_weight": "bold",
                "color": TITLE_COLOR,
                "align": "center",
            }
        )
    if points:
        blocks.append(
            {
                "type": "selling_points",
                "items": points,
                "box": {
                    "x": margin,
                    "y": int(round(height * 0.78)),
                    "width": width - margin * 2,
                    "height": int(round(height * 0.18)),
                },
                "font_size": point_font_size,
                "min_font_size": max(1, int(round(24 * scale))),
                "color": POINT_COLOR,
                "align": "center",
            }
        )

    return {
        "canvas": {"width": width, "height": height},
        "blocks": blocks,
        "warnings": layout_warnings,
    }


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font_size: int,
    min_font_size: int,
    max_width: int,
    bold: bool,
    warnings: list[str],
    label: str,
) -> tuple[str, ImageFont.ImageFont]:
    """缩小字号直到放得下；仍放不下则截断并记录警告。"""
    size = font_size
    while size >= min_font_size:
        font = _load_font(size, bold=bold)
        if draw.textlength(text, font=font) <= max_width:
            return text, font
        size -= 2

    font = _load_font(min_font_size, bold=bold)
    if draw.textlength(text, font=font) <= max_width:
        return text, font

    truncated = text
    while len(truncated) > 1 and draw.textlength(truncated + "…", font=font) > max_width:
        truncated = truncated[:-1]
    truncated = truncated + "…" if truncated != text else truncated
    warnings.append(f"{label}超长已截断")
    return truncated, font


def _region_luminance(image: Image.Image, box: dict[str, int]) -> float:
    """计算文字区平均亮度，用于决定是否加半透明白底。"""
    left = max(0, box["x"])
    top = max(0, box["y"])
    right = min(image.width, box["x"] + box["width"])
    bottom = min(image.height, box["y"] + box["height"])
    if right <= left or bottom <= top:
        return 255.0
    region = image.crop((left, top, right, bottom)).convert("L")
    if region.width == 0 or region.height == 0:
        return 255.0
    return float(ImageStat.Stat(region).mean[0])


def _draw_readability_panel(
    image: Image.Image, box: dict[str, int], alpha: int = 180
) -> None:
    """在文字区叠加半透明白底，保证深色文字可读。"""
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    radius = max(4, int(min(box["width"], box["height"]) * 0.08))
    draw.rounded_rectangle(
        [
            box["x"],
            box["y"],
            box["x"] + box["width"],
            box["y"] + box["height"],
        ],
        radius=radius,
        fill=(255, 255, 255, alpha),
    )
    image.alpha_composite(overlay)


def compose_text(
    base_image: bytes,
    layout_instruction: dict[str, Any],
    *,
    force_panel: bool = False,
) -> CompositionResult:
    """把标题与卖点合成到基础图，输出 PNG。"""
    try:
        canvas = layout_instruction.get("canvas") or {}
        width = int(canvas.get("width") or 0)
        height = int(canvas.get("height") or 0)
        if width <= 0 or height <= 0:
            raise CompositionError("画布尺寸非法")

        with Image.open(BytesIO(base_image)) as source:
            source.load()
            if source.width <= 0 or source.height <= 0:
                raise CompositionError("基础图尺寸非法")
            image = source.convert("RGBA")
            if image.size != (width, height):
                image = image.resize((width, height), Image.Resampling.LANCZOS)

        warnings: list[str] = list(layout_instruction.get("warnings") or [])
        draw = ImageDraw.Draw(image)

        for block in layout_instruction.get("blocks") or []:
            box = block.get("box") or {}
            if not all(key in box for key in ("x", "y", "width", "height")):
                raise CompositionError("版式区块缺少 box")
            box = {key: int(box[key]) for key in ("x", "y", "width", "height")}
            if box["width"] <= 0 or box["height"] <= 0:
                raise CompositionError("版式区块尺寸非法")

            # 背景过暗，或质量审核提示留白不足时，加半透明白底兜底
            if force_panel or _region_luminance(image, box) < 128:
                _draw_readability_panel(image, box, alpha=200 if force_panel else 180)
                draw = ImageDraw.Draw(image)

            color = str(block.get("color") or TITLE_COLOR)
            if block.get("type") == "title":
                text = str(block.get("text") or "").strip()
                if not text:
                    continue
                fitted, font = _fit_text(
                    draw,
                    text,
                    font_size=int(block.get("font_size") or 64),
                    min_font_size=int(block.get("min_font_size") or 40),
                    max_width=box["width"],
                    bold=True,
                    warnings=warnings,
                    label="标题",
                )
                center = (box["x"] + box["width"] // 2, box["y"] + box["height"] // 2)
                draw.text(center, fitted, font=font, fill=color, anchor="mm")

            elif block.get("type") == "selling_points":
                items = [
                    str(item).strip()
                    for item in (block.get("items") or [])
                    if str(item).strip()
                ][:MAX_SELLING_POINTS]
                if len(block.get("items") or []) > MAX_SELLING_POINTS:
                    warnings.append("卖点超过 3 条，只渲染前 3 条")
                if not items:
                    continue

                fitted_items: list[tuple[str, ImageFont.ImageFont]] = []
                for item in items:
                    fitted_items.append(
                        _fit_text(
                            draw,
                            item,
                            font_size=int(block.get("font_size") or 36),
                            min_font_size=int(block.get("min_font_size") or 24),
                            max_width=box["width"],
                            bold=False,
                            warnings=warnings,
                            label="卖点",
                        )
                    )

                line_heights = []
                for _, font in fitted_items:
                    bbox = draw.textbbox((0, 0), "国", font=font)
                    line_heights.append(bbox[3] - bbox[1])
                spacing = max(2, int(round(box["height"] * 0.06)))
                total_height = sum(line_heights) + spacing * (len(fitted_items) - 1)
                y = box["y"] + (box["height"] - total_height) // 2
                for (text, font), line_height in zip(fitted_items, line_heights):
                    draw.text(
                        (box["x"] + box["width"] // 2, y + line_height // 2),
                        text,
                        font=font,
                        fill=color,
                        anchor="mm",
                    )
                    y += line_height + spacing

        output = BytesIO()
        image.convert("RGB").save(output, format="PNG", optimize=True)
        return CompositionResult(png=output.getvalue(), warnings=warnings)
    except CompositionError:
        raise
    except Exception as exc:  # 图片损坏、写文件、渲染异常等统一转业务失败
        raise CompositionError(f"文字合成失败：{exc}") from exc
