"""历史作品只读接口：列表、批次详情与整组 ZIP。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ok
from app.modules.history.service import (
    detail_payload,
    get_history_batch,
    list_history,
    parse_page,
    visible_images,
)
from app.modules.history.zip_export import build_batch_zip

router = APIRouter(tags=["history"])


@router.get("/history")
def get_history(
    page: str | None = Query(default=None, description="页码，从 1 开始"),
    auth: AuthContext = Depends(require_permission("user.history")),
    db: Session = Depends(get_db),
) -> dict:
    """当前用户的历史全套批次分页；固定每页 20 条。"""
    return ok(list_history(db, auth.user.id, parse_page(page)))


@router.get("/history/{batch_id}")
def get_history_detail(
    batch_id: int,
    auth: AuthContext = Depends(require_permission("user.history")),
    db: Session = Depends(get_db),
) -> dict:
    """批次详情与历史可见成功图，按序号升序。"""
    batch = get_history_batch(db, auth.user.id, batch_id)
    return ok(detail_payload(batch, visible_images(db, batch.id)))


@router.get("/batches/{batch_id}/download")
def download_batch_zip(
    batch_id: int,
    auth: AuthContext = Depends(require_permission("user.history")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """同步流式返回整组 ZIP 与 manifest.csv。"""
    result = build_batch_zip(db, auth.user.id, batch_id)

    def iter_zip():
        """分块输出 ZIP，响应结束后关闭临时文件。"""
        try:
            while chunk := result.stream.read(64 * 1024):
                yield chunk
        finally:
            result.stream.close()

    return StreamingResponse(
        iter_zip(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(result.filename)}"
            ),
            "Cache-Control": "no-store",
        },
    )
