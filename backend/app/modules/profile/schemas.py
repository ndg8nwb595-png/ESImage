"""个人中心请求体模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProfileUpdateRequest(BaseModel):
    """修改显示名与邮箱（头像本期不做）。"""

    model_config = ConfigDict(extra="ignore")

    display_name: str | None = None
    email: str | None = None
