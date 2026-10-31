"""豆包（火山方舟）模型适配层。

最小 demo 只走真实豆包；测试环境可通过 GENERATION_MODEL_PROVIDER=fake
使用确定性替身，避免访问外网。适配层覆盖：
- 文本/视觉对话（chat/completions）
- 图像生成（images/generations，Seedream）
- 生成图内容审核（用视觉模型做结构化判定）
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol

import httpx
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.generation import config_service


class ModelCallError(RuntimeError):
    """模型调用失败（网络、HTTP、响应格式）。"""


@dataclass
class ChatResult:
    content: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


@dataclass
class ImageResult:
    data: bytes
    model_name: str
    width: int
    height: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


@dataclass
class ModerationResult:
    blocked: bool
    reason: str


class ModelGateway(Protocol):
    """生成管线依赖的最小模型接口。"""

    def complete(
        self,
        *,
        agent_code: str,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float | None = None,
    ) -> ChatResult: ...

    def generate_image(
        self,
        *,
        prompt: str,
        negative_prompt: str | None,
        width: int,
        height: int,
        reference_images: list[bytes] | None = None,
    ) -> ImageResult: ...

    def moderate_image(self, *, image_bytes: bytes) -> ModerationResult: ...


def _compress_for_request(data: bytes, max_side: int = 1024) -> tuple[str, bytes]:
    """压缩图片并返回 (mime, bytes)，避免 base64 请求体过大。"""
    with Image.open(BytesIO(data)) as image:
        image.load()
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        if max(image.width, image.height) > max_side:
            ratio = max_side / float(max(image.width, image.height))
            image = image.resize(
                (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
            )
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        return "image/jpeg", buffer.getvalue()


def _data_url(data: bytes, max_side: int = 1024) -> str:
    mime, compressed = _compress_for_request(data, max_side)
    encoded = base64.b64encode(compressed).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def image_data_url(data: bytes, max_side: int = 1024) -> str:
    """公开的图片 data URL 编码，供 Agent 组装多模态消息。"""
    return _data_url(data, max_side=max_side)


def _seedream_size(width: int, height: int) -> tuple[int, int]:
    """把目标尺寸放大到 Seedream 可接受的总像素范围，保持宽高比。"""
    target_pixels = 1_000_000
    scale = 1
    while True:
        candidate_w = width * scale
        candidate_h = height * scale
        if candidate_w * candidate_h >= target_pixels or max(candidate_w, candidate_h) >= 4096:
            break
        scale += 1
    # 对齐到 8 的倍数，并确保不超过 4096
    final_w = min(4096, max(64, (candidate_w + 7) // 8 * 8))
    final_h = min(4096, max(64, (candidate_h + 7) // 8 * 8))
    return final_w, final_h


class DoubaoGateway:
    """火山方舟 OpenAI 兼容接口适配层。"""

    def __init__(self, model_config: dict[str, Any] | None) -> None:
        config = model_config or {}
        self.base_url = (config.get("base_url") or settings.DOUBAO_BASE_URL).rstrip("/")
        self.api_key = settings.DOUBAO_API_KEY
        self.text_model = config.get("text_model") or settings.DOUBAO_TEXT_MODEL
        self.image_model = config.get("image_model") or settings.DOUBAO_IMAGE_MODEL
        self.vision_model = config.get("vision_model") or settings.DOUBAO_VISION_MODEL
        self.moderation_model = settings.DOUBAO_MODERATION_MODEL
        self.temperature = float(config.get("temperature", 0.7))
        self.timeout_seconds = int(config.get("timeout_seconds", 120))
        self.retry_count = int(config.get("retry_count", 1))
        self._client = httpx.Client(timeout=self.timeout_seconds)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST 请求；HTTP 瞬态错误立即重试 retry_count 次。"""
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                response = self._client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.retry_count:
                    continue
                raise ModelCallError(f"模型请求失败：{exc}") from exc

            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.retry_count:
                last_error = ModelCallError(f"模型返回 {response.status_code}")
                continue
            if response.status_code >= 400:
                raise ModelCallError(
                    f"模型返回 {response.status_code}：{response.text[:500]}"
                )
            try:
                return response.json()
            except ValueError as exc:
                raise ModelCallError("模型返回非 JSON 响应") from exc
        raise ModelCallError(f"模型请求失败：{last_error}")

    def complete(
        self,
        *,
        agent_code: str,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float | None = None,
    ) -> ChatResult:
        started = time.perf_counter()
        payload = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        data = self._post("/chat/completions", payload)
        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelCallError("模型响应缺少 choices[0].message.content") from exc
        usage = data.get("usage") or {}
        return ChatResult(
            content=content or "",
            model_name=str(data.get("model") or model),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
        )

    def generate_image(
        self,
        *,
        prompt: str,
        negative_prompt: str | None,
        width: int,
        height: int,
        reference_images: list[bytes] | None = None,
    ) -> ImageResult:
        started = time.perf_counter()
        send_w, send_h = _seedream_size(width, height)
        final_prompt = prompt
        if negative_prompt:
            final_prompt = f"{prompt}\n不要出现：{negative_prompt}"

        # 只传各版本 Seedream 都支持的最小参数集：
        # 5.0 Pro 不支持 sequential_image_generation / stream，传了会 400。
        payload: dict[str, Any] = {
            "model": self.image_model,
            "prompt": final_prompt,
            "size": f"{send_w}x{send_h}",
            "response_format": "b64_json",
            "watermark": False,
        }
        if reference_images:
            # 最多 5 张上传图 + 1 张素材；每张压缩到 1024px JPEG，避免请求体过大
            payload["image"] = [_data_url(data) for data in reference_images[:6]]

        data = self._post("/images/generations", payload)
        latency_ms = int((time.perf_counter() - started) * 1000)
        items = data.get("data") or []
        if not items:
            raise ModelCallError("图像生成响应缺少 data")
        item = items[0]
        if item.get("b64_json"):
            try:
                raw = base64.b64decode(item["b64_json"])
            except (ValueError, TypeError) as exc:
                raise ModelCallError("图像生成返回的 b64_json 无法解码") from exc
        elif item.get("url"):
            try:
                response = self._client.get(item["url"])
                response.raise_for_status()
                raw = response.content
            except httpx.HTTPError as exc:
                raise ModelCallError(f"下载生成图失败：{exc}") from exc
        else:
            raise ModelCallError("图像生成响应缺少 b64_json/url")

        usage = data.get("usage") or {}
        return ImageResult(
            data=raw,
            model_name=str(data.get("model") or self.image_model),
            width=send_w,
            height=send_h,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(
                usage.get("completion_tokens") or usage.get("output_tokens") or 0
            ),
            latency_ms=latency_ms,
        )

    def moderate_image(self, *, image_bytes: bytes) -> ModerationResult:
        if not self.moderation_model:
            raise ModelCallError("未配置审核模型 DOUBAO_MODERATION_MODEL")
        messages = [
            {
                "role": "system",
                "content": (
                    "你是电商图片内容审核员。判断图片是否包含色情、暴力、违法、"
                    "侵权、二维码或明显水印等不允许的内容。只输出 JSON："
                    '{"blocked": true/false, "reason": "简短中文原因"}'
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请审核这张生成图。"},
                    {
                        "type": "image_url",
                        "image_url": {"url": _data_url(image_bytes)},
                    },
                ],
            },
        ]
        result = self.complete(
            agent_code="moderation",
            messages=messages,
            model=self.moderation_model,
            temperature=0.0,
        )
        parsed = _parse_json_object(result.content)
        blocked = parsed.get("blocked")
        if not isinstance(blocked, bool):
            raise ModelCallError("审核模型未返回 blocked 布尔值")
        return ModerationResult(blocked=blocked, reason=str(parsed.get("reason") or ""))


def _parse_json_object(text: str) -> dict[str, Any]:
    """解析模型输出中的 JSON 对象，兼容 ```json 代码块。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = [line for line in cleaned.splitlines() if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ModelCallError("模型输出不是 JSON")
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ModelCallError("模型输出不是 JSON") from exc
    if not isinstance(value, dict):
        raise ModelCallError("模型输出不是 JSON 对象")
    return value


def parse_json_object(text: str) -> dict[str, Any]:
    """公开的 JSON 对象解析入口。"""
    return _parse_json_object(text)


class FakeGateway:
    """测试环境专用替身：不访问外网，输出符合各 Agent 契约的确定性数据。"""

    def __init__(self) -> None:
        self.faults = {
            item.strip()
            for item in (settings.GENERATION_FAULT_MODE or "").split(",")
            if item.strip()
        }
        self.text_model = "fake-text-model"
        self.image_model = "fake-image-model"
        self.vision_model = "fake-vision-model"
        self.moderation_model = "fake-moderation-model"

    def complete(
        self,
        *,
        agent_code: str,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float | None = None,
    ) -> ChatResult:
        if "core" in self.faults and agent_code in {
            "planner",
            "product_understanding",
            "copywriter",
            "prompt_builder",
        }:
            raise ModelCallError("故障注入：核心 Agent 失败")
        content = json.dumps(self._payload(agent_code), ensure_ascii=False)
        return ChatResult(
            content=content,
            model_name=model or self.text_model,
            prompt_tokens=11,
            completion_tokens=22,
            latency_ms=1,
        )

    def _payload(self, agent_code: str) -> dict[str, Any]:
        if agent_code == "planner":
            return {
                "image_count": 6,
                "images": [
                    {
                        "index": index,
                        "role": "main" if index == 1 else "detail",
                        "theme": "白底商品主视觉" if index == 1 else f"卖点展示 {index}",
                        "copy_focus": "整体外观" if index == 1 else "核心卖点",
                        "layout_hint": "标题上方，卖点下方",
                    }
                    for index in range(1, 7)
                ],
                "order": [
                    "product_understanding",
                    "copywriter",
                    "prompt_builder",
                    "image_generator",
                ],
            }
        if agent_code == "product_understanding":
            return {
                "category": "服饰鞋包",
                "selling_points": ["透气", "不易起球", "百搭"],
                "target_audience": "25~35 岁通勤女性",
                "scenes": ["办公室", "周末出行"],
                "constraints": ["不要出现真人正脸"],
                "material_ids": [],
            }
        if agent_code == "copywriter":
            return {
                "images": [
                    {
                        "index": index,
                        "title": f"轻盈透气 第{index}张" if len(f"轻盈透气 第{index}张") <= 12 else "轻盈透气",
                        "selling_points": ["冰感面料", "不易起球", "通勤百搭"],
                        "body": "适合日常通勤的轻薄款",
                        "tone": "简洁有力",
                    }
                    for index in range(1, 7)
                ]
            }
        if agent_code == "prompt_builder":
            return {
                "images": [
                    {
                        "index": index,
                        "prompt": "电商商品图，浅色背景，商品居中，柔和棚拍光，上方与下方留出文字区域",
                        "negative_prompt": "文字乱码，水印，低清晰度，主体变形",
                        "whitespace": {"top_ratio": 0.18, "bottom_ratio": 0.22},
                        "reference_asset_ids": [],
                        "model_params": {"width": 1000, "height": 1000},
                    }
                    for index in range(1, 7)
                ]
            }
        if agent_code == "quality_reviewer":
            passed = "quality" not in self.faults
            return {
                "passed": passed,
                "issues": [] if passed else ["商品变形"],
                "checks": {
                    "product_fidelity": "pass" if passed else "fail",
                    "deformity": "pass" if passed else "fail",
                    "whitespace_available": "pass",
                    "compliance": "pass",
                },
            }
        if agent_code == "repairer":
            return {
                "index": 1,
                "prompt": "电商商品图，浅色背景，商品居中，柔和棚拍光，留出上方与下方文字区域，主体不变形",
                "negative_prompt": "文字乱码，水印，低清晰度，主体变形",
                "whitespace": {"top_ratio": 0.18, "bottom_ratio": 0.22},
                "reference_asset_ids": [],
                "model_params": {"width": 1000, "height": 1000},
            }
        if agent_code == "platform_rule":
            passed = "platform" not in self.faults
            return {
                "passed": passed,
                "issues": [] if passed else ["文案含绝对化用语"],
                "checks": {
                    "size": "pass",
                    "prohibited_words": "pass" if passed else "fail",
                    "category_rules": "pass",
                },
            }
        if agent_code == "moderation":
            blocked = "moderation" in self.faults
            return {
                "blocked": blocked,
                "reason": "内容未通过审核" if blocked else "",
            }
        return {}

    def generate_image(
        self,
        *,
        prompt: str,
        negative_prompt: str | None,
        width: int,
        height: int,
        reference_images: list[bytes] | None = None,
    ) -> ImageResult:
        if "image" in self.faults:
            raise ModelCallError("故障注入：生图失败")
        image = Image.new("RGB", (width, height), (225, 235, 245))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return ImageResult(
            data=buffer.getvalue(),
            model_name=self.image_model,
            width=width,
            height=height,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=1,
        )

    def moderate_image(self, *, image_bytes: bytes) -> ModerationResult:
        if "moderation" in self.faults:
            return ModerationResult(blocked=True, reason="内容未通过审核")
        return ModerationResult(blocked=False, reason="")


def build_gateway(db: Session) -> ModelGateway:
    """按运行环境选择真实豆包或测试替身。"""
    if settings.APP_ENV == "test" and settings.GENERATION_MODEL_PROVIDER == "fake":
        return FakeGateway()
    return DoubaoGateway(config_service.get_model_config(db))


def validate_model_settings() -> None:
    """启动校验：真实模式缺少必需环境变量时 fail-fast。"""
    if settings.GENERATION_MODEL_PROVIDER == "fake":
        if settings.APP_ENV != "test":
            raise RuntimeError("GENERATION_MODEL_PROVIDER=fake 仅允许在 APP_ENV=test 时使用")
        return

    missing = []
    if not settings.DOUBAO_API_KEY:
        missing.append("DOUBAO_API_KEY 或 ARK_API_KEY")
    if not settings.DOUBAO_BASE_URL:
        missing.append("DOUBAO_BASE_URL")
    if not settings.DOUBAO_TEXT_MODEL:
        missing.append("DOUBAO_TEXT_MODEL")
    if not settings.DOUBAO_IMAGE_MODEL:
        missing.append("DOUBAO_IMAGE_MODEL")
    if not settings.DOUBAO_MODERATION_MODEL:
        missing.append("DOUBAO_MODERATION_MODEL")
    if missing:
        raise RuntimeError(
            "缺少生图任务必需的模型环境变量：" + "、".join(missing)
            + "。请在 backend/.env 中配置后重启。"
        )
