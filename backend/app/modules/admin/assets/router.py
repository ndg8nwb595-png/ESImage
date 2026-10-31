"""素材与模板：模板、素材库、尺寸预设（9 号 §6.6 / 4 号 PRD）。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.config import MaterialAsset, SizePreset, Template
from app.modules.admin.assets.schemas import MaterialRequest, SizeRequest, StatusRequest, TemplateRequest
from app.modules.workspace.imaging import decode_image, make_thumbnail_webp
from app.modules.workspace.service import MAX_IMAGE_BYTES, to_iso
from app.modules.workspace.storage import storage

router = APIRouter(prefix="/admin", tags=["admin-assets"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _template_payload(t: Template) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "style_text": t.style_text,
        "thumbnail_path": t.thumbnail_path or None,
        "prompt_template": t.prompt_template,
        "layout_ref": t.layout_ref,
        "sort_order": t.sort_order,
        "status": t.status,
        "created_at": to_iso(t.created_at),
        "updated_at": to_iso(t.updated_at),
    }


def _material_payload(m: MaterialAsset) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "file_path": m.file_path,
        "thumbnail_path": m.thumbnail_path,
        "tags": m.tags,
        "style_tags": m.style_tags,
        "sort_order": m.sort_order,
        "status": m.status,
        "created_at": to_iso(m.created_at),
        "updated_at": to_iso(m.updated_at),
    }


def _size_payload(s: SizePreset) -> dict:
    return {
        "id": s.id,
        "platform_name": s.platform_name,
        "width": s.width,
        "height": s.height,
        "sort_order": s.sort_order,
        "status": s.status,
        "created_at": to_iso(s.created_at),
        "updated_at": to_iso(s.updated_at),
    }


def _validate_status(status: str) -> None:
    if status not in ("active", "disabled"):
        raise ApiError(400, 10003, "状态参数不合法")


# ---- 模板 ----

@router.get("/templates")
def list_templates(
    auth: AuthContext = Depends(require_permission("admin.assets.view")),
    db: Session = Depends(get_db),
) -> dict:
    templates = list(db.scalars(select(Template).order_by(Template.sort_order.asc(), Template.id.desc())))
    return ok({"items": [_template_payload(t) for t in templates]})


@router.post("/templates")
def create_template(
    payload: TemplateRequest,
    auth: AuthContext = Depends(require_permission("admin.assets.edit")),
    db: Session = Depends(get_db),
) -> dict:
    name = (payload.name or "").strip()
    if not name:
        raise ApiError(400, 10002, "请输入模板名称")
    if len(name) > 50:
        raise ApiError(400, 10004, "模板名称不能超过 50 个字符")

    template = Template(
        name=name,
        style_text=(payload.style_text or "").strip() or None,
        thumbnail_path="",
        prompt_template=payload.prompt_template,
        layout_ref=payload.layout_ref,
        sort_order=payload.sort_order or 0,
        status="active",
        created_by=auth.user.id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return ok(_template_payload(template))


@router.patch("/templates/{template_id}")
def update_template(
    template_id: int,
    payload: TemplateRequest,
    auth: AuthContext = Depends(require_permission("admin.assets.edit")),
    db: Session = Depends(get_db),
) -> dict:
    template = db.get(Template, template_id)
    if template is None:
        raise ApiError(404, 30016, "模板不存在")
    if payload.name is not None:
        name = payload.name.strip()
        if not name or len(name) > 50:
            raise ApiError(400, 10004, "模板名称需为 1~50 个字符")
        template.name = name
    if payload.style_text is not None:
        template.style_text = payload.style_text.strip() or None
    if payload.prompt_template is not None:
        template.prompt_template = payload.prompt_template
    if payload.layout_ref is not None:
        template.layout_ref = payload.layout_ref
    if payload.sort_order is not None:
        template.sort_order = payload.sort_order
    db.commit()
    return ok(_template_payload(template))


@router.post("/templates/{template_id}/status")
def set_template_status(
    template_id: int,
    payload: StatusRequest,
    auth: AuthContext = Depends(require_permission("admin.assets.edit")),
    db: Session = Depends(get_db),
) -> dict:
    _validate_status(payload.status)
    template = db.get(Template, template_id)
    if template is None:
        raise ApiError(404, 30016, "模板不存在")
    template.status = payload.status
    db.commit()
    return ok(_template_payload(template))


# ---- 素材 ----

@router.get("/materials")
def list_materials(
    auth: AuthContext = Depends(require_permission("admin.assets.view")),
    db: Session = Depends(get_db),
) -> dict:
    materials = list(db.scalars(select(MaterialAsset).order_by(MaterialAsset.sort_order.asc(), MaterialAsset.id.desc())))
    return ok({"items": [_material_payload(m) for m in materials]})


@router.post("/materials")
async def upload_material(
    file: UploadFile = File(...),
    name: str = Form(""),
    auth: AuthContext = Depends(require_permission("admin.assets.edit")),
    db: Session = Depends(get_db),
) -> dict:
    material_name = name.strip() or (file.filename or "素材")
    if len(material_name) > 50:
        raise ApiError(400, 10004, "素材名称不能超过 50 个字符")

    extension = Path(file.filename or "material").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ApiError(400, 30006, "仅支持 JPG、PNG、WEBP 格式")

    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise ApiError(400, 30006, "单张图片不能超过 10MB")
    try:
        decode_image(data)
    except ValueError as exc:
        raise ApiError(400, 30006, str(exc) or "图片文件损坏") from exc

    token = uuid.uuid4().hex
    file_path = f"materials/{token}{extension}"
    # MinIO 是同步网络调用，放到线程池避免阻塞事件循环
    await run_in_threadpool(storage.save, file_path, data)
    try:
        thumbnail_path = f"materials/{token}.webp"
        await run_in_threadpool(
            lambda: storage.save(thumbnail_path, make_thumbnail_webp(data))
        )
    except Exception:
        await run_in_threadpool(storage.delete, file_path)
        raise

    material = MaterialAsset(
        name=material_name,
        file_path=file_path,
        thumbnail_path=thumbnail_path,
        sort_order=0,
        status="active",
        created_by=auth.user.id,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return ok(_material_payload(material))


@router.patch("/materials/{material_id}")
def update_material(
    material_id: int,
    payload: MaterialRequest,
    auth: AuthContext = Depends(require_permission("admin.assets.edit")),
    db: Session = Depends(get_db),
) -> dict:
    material = db.get(MaterialAsset, material_id)
    if material is None:
        raise ApiError(404, 30016, "素材不存在")
    if payload.name is not None:
        name = payload.name.strip()
        if not name or len(name) > 50:
            raise ApiError(400, 10004, "素材名称需为 1~50 个字符")
        material.name = name
    if payload.tags is not None:
        material.tags = payload.tags
    if payload.style_tags is not None:
        material.style_tags = payload.style_tags
    if payload.sort_order is not None:
        material.sort_order = payload.sort_order
    db.commit()
    return ok(_material_payload(material))


@router.post("/materials/{material_id}/status")
def set_material_status(
    material_id: int,
    payload: StatusRequest,
    auth: AuthContext = Depends(require_permission("admin.assets.edit")),
    db: Session = Depends(get_db),
) -> dict:
    _validate_status(payload.status)
    material = db.get(MaterialAsset, material_id)
    if material is None:
        raise ApiError(404, 30016, "素材不存在")
    material.status = payload.status
    db.commit()
    return ok(_material_payload(material))


# ---- 尺寸预设 ----

@router.get("/sizes")
def list_sizes(
    auth: AuthContext = Depends(require_permission("admin.assets.view")),
    db: Session = Depends(get_db),
) -> dict:
    sizes = list(db.scalars(select(SizePreset).order_by(SizePreset.sort_order.asc(), SizePreset.id.asc())))
    return ok({"items": [_size_payload(s) for s in sizes]})


@router.post("/sizes")
def create_size(
    payload: SizeRequest,
    auth: AuthContext = Depends(require_permission("admin.assets.edit")),
    db: Session = Depends(get_db),
) -> dict:
    platform_name = (payload.platform_name or "").strip()
    if not platform_name or len(platform_name) > 50:
        raise ApiError(400, 10004, "平台名称需为 1~50 个字符")
    width = payload.width
    height = payload.height
    if not width or not height or width <= 0 or height <= 0:
        raise ApiError(400, 10003, "宽高需为正整数")

    size = SizePreset(
        platform_name=platform_name,
        width=width,
        height=height,
        sort_order=payload.sort_order or 0,
        status="active",
        created_by=auth.user.id,
    )
    db.add(size)
    db.commit()
    db.refresh(size)
    return ok(_size_payload(size))


@router.patch("/sizes/{size_id}")
def update_size(
    size_id: int,
    payload: SizeRequest,
    auth: AuthContext = Depends(require_permission("admin.assets.edit")),
    db: Session = Depends(get_db),
) -> dict:
    size = db.get(SizePreset, size_id)
    if size is None:
        raise ApiError(404, 30016, "尺寸不存在")
    if payload.platform_name is not None:
        name = payload.platform_name.strip()
        if not name or len(name) > 50:
            raise ApiError(400, 10004, "平台名称需为 1~50 个字符")
        size.platform_name = name
    if payload.width is not None:
        if payload.width <= 0:
            raise ApiError(400, 10003, "宽高需为正整数")
        size.width = payload.width
    if payload.height is not None:
        if payload.height <= 0:
            raise ApiError(400, 10003, "宽高需为正整数")
        size.height = payload.height
    if payload.sort_order is not None:
        size.sort_order = payload.sort_order
    db.commit()
    return ok(_size_payload(size))
