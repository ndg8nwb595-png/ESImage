"""8 号管理后台-聊天记录：路由。

本模块承载聊天记录列表、会话详情、消息搜索与 Agent 调用明细。
接口路径与 `docs/prd/8-管理后台-聊天记录/接口文档-聊天记录最小demo.md` 保持一致。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["admin-chat-records"])
