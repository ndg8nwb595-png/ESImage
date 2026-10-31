"""3 号增量接口的请求体模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class RenameSessionRequest(BaseModel):
    """重命名会话。

    title 保持 Any，由路由按接口文档区分：
    - 未传 / null / 纯空格 -> 10002；
    - 非字符串 -> 10003；
    - 超长 -> 10004。
    """

    model_config = ConfigDict(extra="ignore")

    title: Any = None
