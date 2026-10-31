"""管理后台路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.admin.accounts.router import router as accounts_router
from app.modules.admin.content.router import router as content_router
from app.modules.admin.dashboard.router import router as dashboard_router
from app.modules.admin.dashboard.tokens import router as tokens_router

router = APIRouter()
router.include_router(dashboard_router)
router.include_router(tokens_router)
router.include_router(content_router)
router.include_router(accounts_router)
