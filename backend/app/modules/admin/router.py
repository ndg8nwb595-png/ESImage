"""管理后台路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.admin.accounts import router as accounts_router
from app.modules.admin.assets import router as assets_router
from app.modules.admin.audit import router as audit_router
from app.modules.admin.content import router as content_router
from app.modules.admin.dashboard import router as dashboard_router
from app.modules.admin.prompts import router as prompts_router

router = APIRouter()
router.include_router(dashboard_router)
router.include_router(accounts_router)
router.include_router(content_router)
router.include_router(assets_router)
router.include_router(prompts_router)
router.include_router(audit_router)
