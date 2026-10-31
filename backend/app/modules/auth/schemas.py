"""请求体模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    """登录请求。

    字段保持可选，由接口内按 PRD 文案做精确校验；多余字段忽略。
    """

    model_config = ConfigDict(extra="ignore")

    username: str | None = None
    password: str | None = None
    remember_me: bool = False
