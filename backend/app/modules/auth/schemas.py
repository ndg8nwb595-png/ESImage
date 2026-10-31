"""请求体模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictBool


class LoginRequest(BaseModel):
    """登录请求。

    字段保持可选，由接口内按 PRD 文案做精确校验；多余字段忽略。
    """

    model_config = ConfigDict(extra="ignore")

    username: str | None = None
    password: str | None = None
    # 接口文档规定为 boolean；StrictBool 避免 "yes"/1 等值被宽松转换为 true
    remember_me: StrictBool = False


class PasswordChangeRequest(BaseModel):
    """修改密码请求。"""

    model_config = ConfigDict(extra="ignore")

    old_password: str | None = None
    new_password: str | None = None
