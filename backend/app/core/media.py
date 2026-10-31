"""跨模块共用的图像处理工具。"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

# 上传图与生成图的像素上限，防止解压炸弹
MAX_IMAGE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def make_thumbnail_webp(data: bytes, max_width: int = 400) -> bytes:
    """生成最大宽度 400px 的 WebP 缩略图。"""
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("图片尺寸过大")
        image.load()
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        if image.width > max_width:
            ratio = max_width / float(image.width)
            image = image.resize((max_width, max(1, int(image.height * ratio))))
        buffer = BytesIO()
        image.save(buffer, format="WEBP", quality=80, method=4)
        return buffer.getvalue()


def to_png_bytes(image: Image.Image) -> bytes:
    """把 PIL 图像编码为 PNG。"""
    buffer = BytesIO()
    output = image if image.mode in ("RGB", "RGBA") else image.convert("RGB")
    output.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def fit_to_size(data: bytes, width: int, height: int) -> Image.Image:
    """解码图片并缩放到目标尺寸（不裁剪），返回 RGB 图像。"""
    with Image.open(BytesIO(data)) as image:
        image.load()
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError("图片尺寸过大")
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        return image.convert("RGB")
