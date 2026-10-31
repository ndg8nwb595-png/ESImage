"""OpenAPI 契约标注：Bearer 鉴权、统一响应/分页结构、错误码表与权限码。

9 号 §9 / 08 号切片要求 `/api/docs` 与 `/api/openapi.json` 包含：
- Bearer 安全方案；
- 统一响应 `{ code, message, data }` 与分页 `{ items, total, page, page_size }`；
- 9 号 §3.1 错误码表；
- 每个接口的权限码（`x-permission` 扩展字段）。

本模块只做文档标注，不改变任何接口的运行时行为。权限码映射是「接口契约」的
单一来源，供 OpenAPI 与契约回归套件共同引用。
"""

from __future__ import annotations

from fastapi import FastAPI

from app.modules.contract.errors import error_code_table

# 权限码标注用的特殊值
AUTH_LOGIN = "login"  # 登录即可，无需具体权限码

# (method, path) -> 权限码 / AUTH_LOGIN / None(无需鉴权)。
# 以 9 号 PRD 与 6 号 demo 权限点目录为准，与本模块 README 的契约载体表一致。
PERMISSION_MAP: dict[tuple[str, str], str | tuple[str, ...] | None] = {
    # ---- 无需鉴权 ----
    ("GET", "/api/health"): None,
    ("GET", "/api/v1/health"): None,
    ("POST", "/api/v1/auth/login"): None,
    ("GET", "/api/v1/sessions/_probe/stream"): None,
    # ---- 登录即可 ----
    ("GET", "/api/v1/auth/me"): AUTH_LOGIN,
    ("POST", "/api/v1/auth/logout"): AUTH_LOGIN,
    ("PUT", "/api/v1/auth/password"): AUTH_LOGIN,
    # ---- 用户端：创作工作台 ----
    ("GET", "/api/v1/sessions"): "user.workspace",
    ("GET", "/api/v1/sessions/{session_id}/messages"): "user.workspace",
    ("POST", "/api/v1/sessions/messages"): "user.workspace",
    ("POST", "/api/v1/sessions/{session_id}/messages"): "user.workspace",
    ("PATCH", "/api/v1/sessions/{session_id}"): "user.workspace",
    ("DELETE", "/api/v1/sessions/{session_id}"): "user.workspace",
    # ---- 用户端：上传 ----
    ("POST", "/api/v1/uploads"): "user.generate",
    ("GET", "/api/v1/uploads/{upload_id}"): "user.generate",
    ("DELETE", "/api/v1/uploads/{upload_id}"): "user.generate",
    ("GET", "/api/v1/uploads/{upload_id}/content"): "user.generate",
    ("GET", "/api/v1/uploads/{upload_id}/thumbnail"): "user.generate",
    # ---- 用户端：生成 ----
    ("POST", "/api/v1/generations/sample"): "user.generate",
    ("GET", "/api/v1/generations/{batch_id}"): "user.generate",
    ("POST", "/api/v1/generations/{batch_id}/confirm"): "user.generate",
    # ---- 用户端：图片（预览/缩略图任一用户权限，下载按 2 号 demo 用 user.history）----
    ("GET", "/api/v1/images/{image_id}/content"): ("user.history", "user.generate"),
    ("GET", "/api/v1/images/{image_id}/thumbnail"): ("user.history", "user.generate"),
    ("GET", "/api/v1/images/{image_id}/download"): "user.history",
    # ---- 用户端：历史 ----
    ("GET", "/api/v1/history"): "user.history",
    ("GET", "/api/v1/history/{batch_id}"): "user.history",
    ("GET", "/api/v1/batches/{batch_id}/download"): "user.history",
    # ---- 用户端：个人中心 ----
    ("GET", "/api/v1/profile"): "user.profile",
    ("PATCH", "/api/v1/profile"): "user.profile",
    # ---- 管理端：概览与 Token ----
    ("GET", "/api/v1/admin/dashboard/summary"): "admin.dashboard.view",
    ("GET", "/api/v1/admin/tokens/stats"): "admin.tokens.view",
    # ---- 管理端：账号与权限 ----
    ("GET", "/api/v1/admin/users"): "admin.accounts.view",
    ("POST", "/api/v1/admin/users"): "admin.accounts.create",
    ("GET", "/api/v1/admin/users/{user_id}"): "admin.accounts.view",
    ("PATCH", "/api/v1/admin/users/{user_id}"): "admin.accounts.edit",
    ("DELETE", "/api/v1/admin/users/{user_id}"): "admin.accounts.delete",
    ("POST", "/api/v1/admin/users/{user_id}/disable"): "admin.accounts.disable",
    ("POST", "/api/v1/admin/users/{user_id}/enable"): "admin.accounts.disable",
    ("POST", "/api/v1/admin/users/{user_id}/reset-password"): "admin.accounts.reset_password",
    ("POST", "/api/v1/admin/users/{user_id}/restore"): "admin.accounts.delete",
    ("GET", "/api/v1/admin/roles"): "admin.roles.view",
    ("PUT", "/api/v1/admin/roles/{code}/permissions"): "admin.roles.edit",
    # ---- 管理端：内容追溯与聊天记录 ----
    ("GET", "/api/v1/admin/content/users"): "admin.content.view",
    ("GET", "/api/v1/admin/content/users/{user_id}/sessions"): "admin.content.view",
    ("GET", "/api/v1/admin/content/sessions/{session_id}/batches"): "admin.content.view",
    ("GET", "/api/v1/admin/content/batches/{batch_id}/images"): "admin.content.view",
    ("GET", "/api/v1/admin/content/images/{image_id}"): "admin.content.view",
    ("GET", "/api/v1/admin/content/images/{image_id}/content"): "admin.content.view",
    ("GET", "/api/v1/admin/content/images/{image_id}/download"): "admin.content.view",
    ("GET", "/api/v1/admin/content/images/{image_id}/thumbnail"): "admin.content.view",
    ("GET", "/api/v1/admin/chat/sessions"): "admin.content.view",
    ("GET", "/api/v1/admin/chat/sessions/{session_id}"): "admin.content.view",
    ("GET", "/api/v1/admin/chat/messages/search"): "admin.content.view",
    ("GET", "/api/v1/admin/agent-runs/{run_id}"): "admin.content.view",
    # ---- 用户端：生图配置只读 ----
    ("GET", "/api/v1/templates"): "user.generate",
    ("GET", "/api/v1/templates/{template_id}/thumbnail"): "user.generate",
    ("GET", "/api/v1/sizes"): "user.generate",
    # ---- 管理端：Agent 配置 ----
    ("GET", "/api/v1/admin/model-config"): "admin.model.view",
    ("PUT", "/api/v1/admin/model-config"): "admin.model.edit",
    ("GET", "/api/v1/admin/prompts"): "admin.prompts.view",
    ("GET", "/api/v1/admin/prompts/{agent_code}"): "admin.prompts.view",
    ("PUT", "/api/v1/admin/prompts/{agent_code}"): "admin.prompts.edit",
    ("POST", "/api/v1/admin/prompts/{agent_code}/versions/{version}/activate"): "admin.prompts.edit",
    # ---- 管理端：素材与模板 ----
    ("GET", "/api/v1/admin/templates"): "admin.assets.view",
    ("POST", "/api/v1/admin/templates"): "admin.assets.edit",
    ("PATCH", "/api/v1/admin/templates/{template_id}"): "admin.assets.edit",
    ("POST", "/api/v1/admin/templates/{template_id}/status"): "admin.assets.edit",
    ("GET", "/api/v1/admin/materials"): "admin.assets.view",
    ("POST", "/api/v1/admin/materials"): "admin.assets.edit",
    ("PATCH", "/api/v1/admin/materials/{material_id}"): "admin.assets.edit",
    ("POST", "/api/v1/admin/materials/{material_id}/status"): "admin.assets.edit",
    ("GET", "/api/v1/admin/sizes"): "admin.assets.view",
    ("POST", "/api/v1/admin/sizes"): "admin.assets.edit",
    ("PATCH", "/api/v1/admin/sizes/{size_id}"): "admin.assets.edit",
    # ---- 管理端：操作日志 ----
    ("GET", "/api/v1/admin/audit-logs"): "admin.audit.view",
    ("GET", "/api/v1/admin/audit-logs/{log_id}"): "admin.audit.view",
}


def _permission_of(method: str, path: str) -> str | tuple[str, ...] | None:
    return PERMISSION_MAP.get((method, path))


def _unified_response_schema() -> dict:
    return {
        "type": "object",
        "description": "统一响应结构；除文件流、ZIP 流与 SSE 外所有接口均返回该结构。",
        "properties": {
            "code": {"type": "integer", "description": "0 表示成功；非 0 为业务错误码（见 x-error-codes）"},
            "message": {"type": "string", "description": "面向用户的提示文案；成功固定为 ok"},
            "data": {"description": "成功时的数据；业务错误时为 null 或补充信息", "nullable": True},
        },
        "required": ["code", "message", "data"],
    }


def _paginated_response_schema() -> dict:
    return {
        "type": "object",
        "description": "统一分页响应结构；分页信息与 items 同级。",
        "properties": {
            "items": {"type": "array", "items": {}, "description": "当前页数据；无数据时为 []"},
            "total": {"type": "integer", "description": "满足筛选条件的总条数"},
            "page": {"type": "integer", "description": "当前页码，从 1 开始"},
            "page_size": {"type": "integer", "description": "当前页大小，1~100"},
        },
        "required": ["items", "total", "page", "page_size"],
    }


def customize_openapi(app: FastAPI) -> None:
    """在 FastAPI 自动生成的 OpenAPI 上补充契约标注（幂等，可重复调用）。"""

    original_openapi = app.openapi

    def openapi() -> dict:
        if app.openapi_schema is not None:
            return app.openapi_schema

        schema = original_openapi()

        components = schema.setdefault("components", {})
        components.setdefault("schemas", {})
        components["schemas"]["UnifiedResponse"] = _unified_response_schema()
        components["schemas"]["PaginatedResponse"] = _paginated_response_schema()
        components["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Authorization: Bearer <jwt>；除登录与健康探针外所有接口必须携带",
            }
        }

        # 错误码表：机器可读扩展 + 摘要说明
        schema["x-error-codes"] = error_code_table()
        info = schema.setdefault("info", {})
        info["description"] = (
            (info.get("description") or "")
            + "\n\n## 统一约定\n"
            "- 统一响应：`{ code, message, data }`，成功 `code=0`。\n"
            "- 分页：`page` 默认 1、`page_size` 默认 20、最大 100；响应 `{ items, total, page, page_size }`。\n"
            "- 鉴权：`Authorization: Bearer <jwt>`；每个接口的权限码见各操作的 `x-permission` 扩展字段。\n"
            "- 错误码表见 `x-error-codes`；HTTP 状态与业务码成对使用。\n"
        )

        # 逐操作标注权限码与安全要求
        for path, path_item in schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                permission = _permission_of(method.upper(), path)
                if permission is None:
                    # 无需鉴权：显式去掉安全要求
                    operation["security"] = []
                    operation["x-permission"] = "none"
                    continue
                operation["security"] = [{"BearerAuth": []}]
                operation["x-permission"] = (
                    list(permission) if isinstance(permission, tuple) else permission
                )
                operation["x-permission-note"] = (
                    "登录即可" if permission == AUTH_LOGIN else "需要该权限码"
                )
                if operation.get("summary") and permission != AUTH_LOGIN:
                    perm_text = (
                        " / ".join(permission)
                        if isinstance(permission, tuple)
                        else permission
                    )
                    operation["summary"] = f"{operation['summary']}（{perm_text}）"

        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
