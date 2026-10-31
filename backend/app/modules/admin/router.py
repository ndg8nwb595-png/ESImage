"""管理后台路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.admin.accounts import router as accounts_router
from app.modules.admin.dashboard import router as dashboard_router

router = APIRouter()
router.include_router(dashboard_router)
router.include_router(accounts_router)
