"""生成配置只读接口：模板、模板缩略图与尺寸预设。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext
from app.core.response import ApiError, ok
from app.modules.generation import config_service
from app.modules.workspace.service import media_response
from app.modules.generation.service import (
    get_active_template,
    require_permission,
    template_thumbnail_url,
)

router = APIRouter(tags=["generation"])


@router.get("/templates")
def list_templates(
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """启用中的模板列表；按 sort_order、id 升序，最多 50 条。"""
    items = [
        {
            "template_id": template["id"],
            "name": template["name"],
            "style_text": template["style_text"],
            "thumbnail_url": template_thumbnail_url(template["id"]),
            "sort_order": template["sort_order"],
        }
        for template in config_service.get_templates(db)[:50]
    ]
    return ok({"items": items, "total": len(items)})


@router.get("/templates/{template_id}/thumbnail")
def get_template_thumbnail(
    template_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> Response:
    """模板缩略图（只读）；不存在或已停用返回 30016。"""
    template = get_active_template(db, template_id)
    if template is None or not template.thumbnail_path:
        raise ApiError(404, 30016, "模板/素材/尺寸不存在")
    return media_response(
        template.thumbnail_path,
        media_type="image/webp",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
        },
    )


@router.get("/sizes")
def list_sizes(
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """启用中的尺寸预设；用户端始终保留自定义宽高。"""
    items = [
        {
            "size_id": size["id"],
            "platform_name": size["platform_name"],
            "width": size["width"],
            "height": size["height"],
            "sort_order": size["sort_order"],
        }
        for size in config_service.get_sizes(db)
    ]
    return ok({"items": items, "total": len(items)})
