"""生图任务请求体模型。响应统一由路由按接口文档手工组装。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class SampleGenerationRequest(BaseModel):
    """创建示例批次（沿用 2 号 demo 请求契约）。"""

    model_config = ConfigDict(extra="ignore")

    client_request_id: str
    session_id: int | None = None
    product_name: str
    style_text: str | None = None
    width: int | None = None
    height: int | None = None
    template_id: int | None = None
    upload_ids: list[int] | None = None
    requirement_summary: dict[str, Any] | None = None


class ConfirmGenerationRequest(BaseModel):
    """确认示例并生成全套。"""

    model_config = ConfigDict(extra="ignore")

    client_request_id: str


class RegenerateImageRequest(BaseModel):
    """单张重试 / 重生成。"""

    model_config = ConfigDict(extra="ignore")

    client_request_id: str
