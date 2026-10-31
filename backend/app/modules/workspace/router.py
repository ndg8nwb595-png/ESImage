"""创作工作台路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.workspace import generations, sessions, uploads

router = APIRouter()
router.include_router(sessions.router)
router.include_router(uploads.router)
router.include_router(generations.router)
