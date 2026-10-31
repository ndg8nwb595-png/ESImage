"""最小 demo 的图像处理：占位 PNG、缩略图与可解码校验。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.modules.workspace.service import MAX_IMAGE_PIXELS

# Pillow 自身的解压炸弹阈值；业务层还会对宽高乘积做显式校验
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

# 优先使用 Windows 自带中文字体，找不到时回退到默认字体
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_font(size: int) -> ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def decode_image(data: bytes) -> tuple[int, int]:
    """读取图片宽高；损坏、非图片或像素数超限时抛 ValueError。"""
    try:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("图片尺寸过大，请重新上传")
            image.load()
            return image.width, image.height
    except ValueError:
        raise
    except Exception as exc:  # Pillow 对损坏文件抛出的异常类型不统一
        raise ValueError("图片文件损坏，请重新上传") from exc


def make_thumbnail_webp(data: bytes, max_width: int = 400) -> bytes:
    """生成最大宽度 400px 的 WebP 缩略图。"""
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("图片尺寸过大，请重新上传")
        image.load()
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        if image.width > max_width:
            ratio = max_width / float(image.width)
            image = image.resize((max_width, max(1, int(image.height * ratio))))
        buffer = BytesIO()
        image.save(buffer, format="WEBP", quality=80, method=4)
        return buffer.getvalue()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """按像素宽度简单折行，避免长商品名溢出画布。"""
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines or [""]


def render_placeholder_png(
    *,
    product_name: str,
    role_label: str,
    index_no: int,
    batch_id: int,
    width: int,
    height: int,
    image_type: str,
) -> bytes:
    """生成 1000×1000（或指定宽高）的演示占位 PNG。"""
    palette = [
        (236, 244, 255),
        (255, 244, 232),
        (235, 250, 240),
        (250, 238, 248),
        (245, 245, 235),
        (238, 242, 250),
    ]
    background = palette[(index_no - 1) % len(palette)]
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    title_font = _load_font(max(28, width // 22))
    body_font = _load_font(max(20, width // 34))
    small_font = _load_font(max(16, width // 48))

    # 顶部色条，便于区分不同序号的占位图
    draw.rectangle([0, 0, width, max(8, height // 80)], fill=(58, 110, 200))

    margin = int(width * 0.1)
    max_text_width = width - margin * 2

    title_lines = _wrap_text(draw, product_name, title_font, max_text_width)
    body_lines = [
        f"{role_label} · 第 {index_no} 张",
        f"批次 #{batch_id} · {image_type}",
        "ESImage 演示占位图",
    ]
    all_lines = [(line, title_font) for line in title_lines] + [
        (line, body_font) for line in body_lines[:2]
    ] + [(body_lines[2], small_font)]

    # 计算整体高度并垂直居中
    line_heights = []
    for text, font in all_lines:
        bbox = draw.textbbox((0, 0), text, font=font)
        line_heights.append(bbox[3] - bbox[1])
    spacing = int(height * 0.035)
    total_height = sum(line_heights) + spacing * (len(all_lines) - 1)
    y = (height - total_height) // 2

    for (text, font), line_height in zip(all_lines, line_heights):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        draw.text((x, y - bbox[1]), text, font=font, fill=(40, 52, 70))
        y += line_height + spacing

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
