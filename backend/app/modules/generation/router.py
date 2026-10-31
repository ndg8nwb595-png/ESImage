"""生图任务模块路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.generation import config_router, generation_router

router = APIRouter()
router.include_router(config_router.router)
router.include_router(generation_router.router)
