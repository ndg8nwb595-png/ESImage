"""创作工作台请求体模型。

响应统一由路由按接口文档手工组装，保证字段与文档逐字一致。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkspaceParams(BaseModel):
    """参数面板快照。"""

    model_config = ConfigDict(extra="ignore")

    product_name: str
    style_text: str | None = None
    width: int | None = None
    height: int | None = None
    template_id: int | None = None
    # 3 号增量：聊天参数可携带上传图 ID，仅校验归属与数量，不分析图片内容
    upload_ids: list[int] | None = None


class ChatMessageRequest(BaseModel):
    """发送聊天消息。"""

    model_config = ConfigDict(extra="ignore")

    client_message_id: str
    content: str
    params: WorkspaceParams
    session_id: int | None = None


class SampleGenerationRequest(BaseModel):
    """创建示例批次。"""

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
