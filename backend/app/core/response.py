"""统一响应结构与业务异常。"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """带 HTTP 状态码与业务码的异常，由全局处理器转换为统一响应。"""

    def __init__(self, status_code: int, code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def ok(data: Any = None) -> dict[str, Any]:
    """成功响应体：code=0。"""
    return {"code": 0, "message": "ok", "data": data}


def error_body(code: int, message: str) -> dict[str, Any]:
    """失败响应体：data 固定为 null。"""
    return {"code": code, "message": message, "data": None}
