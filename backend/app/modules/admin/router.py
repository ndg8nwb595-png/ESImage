"""管理后台路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.admin.accounts.router import router as accounts_router
from app.modules.admin.assets.router import router as assets_router
from app.modules.admin.audit.router import router as audit_router
from app.modules.admin.content.router import router as content_router
from app.modules.admin.dashboard.router import router as dashboard_router
from app.modules.admin.prompts.router import router as prompts_router

router = APIRouter()
router.include_router(dashboard_router)
router.include_router(accounts_router)
router.include_router(content_router)
router.include_router(assets_router)
router.include_router(prompts_router)
router.include_router(audit_router)
