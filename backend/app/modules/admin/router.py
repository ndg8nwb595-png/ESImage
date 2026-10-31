"""管理后台路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.admin.accounts.router import router as accounts_router
from app.modules.admin.assets.router import router as assets_router
from app.modules.admin.audit.router import router as audit_router
from app.modules.admin.chat_records.router import router as chat_records_router
from app.modules.admin.content.chat_router import router as chat_content_router
from app.modules.admin.content.router import router as content_router
from app.modules.admin.dashboard.router import router as dashboard_router
from app.modules.admin.dashboard.tokens import router as tokens_router
from app.modules.admin.prompts.router import router as prompts_router

router = APIRouter()
# dashboard / tokens / content 自��� /admin/... 前缀；
# 其余子路由只定义资源路径，统一挂到 /admin 下。
router.include_router(dashboard_router)
router.include_router(tokens_router)
router.include_router(content_router)
router.include_router(accounts_router, prefix="/admin")
# 8 号聊天记录：当前实现位于 content/chat_router.py；
# chat_records 为并行 agent 的骨架模块，保留挂载以便后续接管。
router.include_router(chat_content_router, prefix="/admin")
router.include_router(chat_records_router, prefix="/admin")
router.include_router(assets_router, prefix="/admin")
router.include_router(prompts_router, prefix="/admin")
router.include_router(audit_router, prefix="/admin")
