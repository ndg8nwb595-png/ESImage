"""素材与模板请求体模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TemplateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    style_text: str | None = None
    prompt_template: str | None = None
    layout_ref: str | None = None
    sort_order: int | None = None


class MaterialRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    tags: list[str] | None = None
    style_tags: list[str] | None = None
    sort_order: int | None = None


class SizeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    platform_name: str | None = None
    width: int | None = None
    height: int | None = None
    sort_order: int | None = None


class StatusRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
