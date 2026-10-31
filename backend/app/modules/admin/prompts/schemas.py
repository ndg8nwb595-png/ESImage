"""Agent 配置请求体模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ModelConfigRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    text_model: str | None = None
    image_model: str | None = None
    vision_model: str | None = None
    temperature: float | None = None
    timeout_seconds: int | None = None
    concurrency: int | None = None
    retry_count: int | None = None
    max_context_tokens: int | None = None


class PromptSaveRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = None
