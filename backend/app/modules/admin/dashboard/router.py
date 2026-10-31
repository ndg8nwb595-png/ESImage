"""概览四卡接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext
from app.core.response import ok
from app.modules.admin.dashboard.service import get_summary
from app.modules.admin.service import require_permission

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


@router.get("/summary")
def dashboard_summary(
    auth: AuthContext = Depends(require_permission("admin.dashboard.view")),
    db: Session = Depends(get_db),
) -> dict:
    """概览四张统计卡片。"""
    return ok(get_summary(db))
