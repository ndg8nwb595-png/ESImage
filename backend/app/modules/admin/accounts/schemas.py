"""账号与权限请求体模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str | None = None
    display_name: str | None = None
    password: str | None = None
    roles: list[str] | None = None
    status: str | None = None


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    display_name: str | None = None
    roles: list[str] | None = None
    status: str | None = None


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    new_password: str | None = None


class RolePermissionsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # 允许为空以返回接口文档要求的 10002「请选择权限点」，而不是框架 422
    permissions: list[str] | None = None
