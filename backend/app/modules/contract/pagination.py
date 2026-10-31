"""共享分页契约：`page` / `page_size` 校验与错误码映射。

9 号接口文档 §4：
- `page` 默认 1，从 1 开始；`page < 1` 返回 400 `10001`。
- `page_size` 默认 20，范围 1~100；越界返回 400 `10004`。
- 分页参数只接受整数；非整数返回 400 `10003`（由 FastAPI 的 `int` 类型解析触发，
  全局 `RequestValidationError` 处理器映射为 `10003`）。

用法：在分页接口的参数列表里加 `page: PageParams = Depends(pagination)`，
随后用 `page.page` / `page.page_size` / `page.offset`。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query

from app.core.response import ApiError


@dataclass(frozen=True)
class PageParams:
    """已通过契约校验的分页参数。"""

    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination(
    page: int | None = Query(None, description="页码，从 1 开始，默认 1"),
    page_size: int | None = Query(None, description="每页条数，默认 20，最大 100"),
) -> PageParams:
    """解析并校验分页参数，返回统一结构；非法值抛出对应业务码。"""
    if page is None:
        page = 1
    if page_size is None:
        page_size = 20

    # 契约：page < 1 属「参数错误」，page_size 越界属「超出范围」，二者不能混用
    if page < 1:
        raise ApiError(400, 10001, "page 必须大于等于 1")
    if not 1 <= page_size <= 100:
        raise ApiError(400, 10004, "page_size 必须在 1~100 之间")
    return PageParams(page=page, page_size=page_size)


def paginated_response(items: list, total: int, page: PageParams) -> dict:
    """组装统一分页响应体；`items` 为空时仍是 `[]` 而非 `null`。"""
    return {
        "items": items,
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }
