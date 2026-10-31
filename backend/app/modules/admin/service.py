"""管理后台公共能力：权限、时间、分页、媒体与存储工具。

本文件只服务 6/7/8 号管理后台模块，避免各子模块重复实现同一套边界校验。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from fastapi import Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import AuthContext, get_current_auth
from app.core.response import ApiError
from app.models.user import Role, User
from app.modules.workspace.storage import storage

SUPER_ADMIN_ROLE = "super_admin"
MAX_PAGE_SIZE = 100

# 8 个 Agent 的中文名，供 Token 统计展示
AGENT_NAMES: dict[str, str] = {
    "planner": "规划",
    "product_understanding": "商品理解",
    "copywriter": "文案",
    "prompt_builder": "提示词",
    "image_generator": "生图执行",
    "quality_reviewer": "质量审核",
    "repairer": "修复",
    "platform_rule": "平台规范",
}

BATCH_STATUSES = {
    "queued",
    "running",
    "sample_ready",
    "confirmed",
    "completed",
    "partially_failed",
    "failed",
    "cancelled",
}
BATCH_TYPES = {"sample", "full"}
IMAGE_ROLES = {"main", "detail"}
IMAGE_STATUSES = {"pending", "generating", "success", "failed", "cancelled", "superseded"}
USER_STATUSES = {"active", "disabled", "deleted"}

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def is_super_admin(auth: AuthContext) -> bool:
    """当前登录用户是否为超管。"""
    return SUPER_ADMIN_ROLE in auth.roles


def require_permission(code: str) -> Callable[..., AuthContext]:
    """生成管理端权限依赖。

    超管按角色即时拥有全部权限；其他角色沿用 role_permissions 并集。
    缺失权限统一返回 403/20005。
    """

    def dependency(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        if is_super_admin(auth) or code in auth.permissions:
            return auth
        raise ApiError(403, 20005, "无权限")

    return dependency


def user_has_super_admin_role(db: Session, user_id: int) -> bool:
    """目标用户是否拥有 super_admin 角色。"""
    return bool(
        db.scalar(
            select(Role.id)
            .join(Role.users)
            .where(User.id == user_id, Role.code == SUPER_ADMIN_ROLE)
            .limit(1)
        )
    )


def ensure_content_access(db: Session, auth: AuthContext, owner_user_id: int) -> None:
    """管理员不能查看超管账号的内容；超管可查看全部。"""
    if is_super_admin(auth):
        return
    if user_has_super_admin_role(db, owner_user_id):
        raise ApiError(403, 20006, "无权查看超管账号内容")


def now() -> datetime:
    """当前时间（UTC，数据库统一 TIMESTAMPTZ）。"""
    return datetime.now(timezone.utc)


def today_local() -> date:
    """Asia/Shanghai 的今天。"""
    return now().astimezone(settings.TZ).date()


def local_day_start(value: date) -> datetime:
    """Asia/Shanghai 当天 00:00:00。"""
    return datetime.combine(value, time.min, tzinfo=settings.TZ)


def local_day_end_exclusive(value: date) -> datetime:
    """Asia/Shanghai 次日 00:00:00（开区间上界）。"""
    return local_day_start(value) + timedelta(days=1)


def parse_date(value: str | None, message: str = "参数格式错误") -> date | None:
    """解析 YYYY-MM-DD；空值返回 None。"""
    if value is None or value.strip() == "":
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ApiError(400, 10003, message) from exc


def parse_date_range(
    start_date: str | None,
    end_date: str | None,
    *,
    message: str = "参数格式错误",
) -> tuple[date | None, date | None]:
    """解析日期范围；起止倒置返回 400/10003。"""
    start = parse_date(start_date, message)
    end = parse_date(end_date, message)
    if start is not None and end is not None and start > end:
        raise ApiError(400, 10003, message)
    return start, end


def to_iso(value: datetime | None) -> str | None:
    """统一输出东八区 ISO 8601；数据库返回 UTC 时自动转换。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(settings.TZ).isoformat()


def validate_keyword(value: str | None, max_length: int = 50) -> str | None:
    """关键词：去首尾空格，空串视为不筛选；超长返回 10004。"""
    if value is None:
        return None
    keyword = value.strip()
    if keyword == "":
        return None
    if len(keyword) > max_length:
        raise ApiError(400, 10004, f"关键词不能超过 {max_length} 个字符")
    return keyword


def validate_pagination(
    page: int,
    page_size: int,
    *,
    max_page_size: int = MAX_PAGE_SIZE,
) -> tuple[int, int]:
    """分页参数：page 小于 1 按 1 处理；page_size 越界返回 10004。"""
    final_page = 1 if page < 1 else page
    if page_size < 1 or page_size > max_page_size:
        raise ApiError(400, 10004, "参数超出范围")
    return final_page, page_size


def page_payload(items: list[dict[str, Any]], total: int, page: int, page_size: int) -> dict:
    """统一分页响应 data。"""
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def image_thumbnail_url(image_id: int) -> str:
    return f"/api/v1/admin/content/images/{image_id}/thumbnail"


def image_preview_url(image_id: int) -> str:
    return f"/api/v1/admin/content/images/{image_id}/content"


def image_download_url(image_id: int) -> str:
    return f"/api/v1/admin/content/images/{image_id}/download"


def safe_filename_part(value: str) -> str:
    """把文件名非法字符替换为下划线；空值使用「未命名商品」。"""
    invalid = set('\\/:*?"<>|\r\n\t')
    cleaned = "".join("_" if ch in invalid else ch for ch in value).strip()
    return cleaned or "未命名商品"


def filename_timestamp(value: datetime | None) -> str:
    """文件名时间戳：东八区 yyyyMMddHHmmss。"""
    if value is None:
        value = now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(settings.TZ).strftime("%Y%m%d%H%M%S")


def media_type_for(path: Path | str) -> str:
    """按扩展名推断图片 MIME；未知按 PNG 处理。"""
    suffix = Path(str(path)).suffix.lower()
    return MEDIA_TYPES.get(suffix, "image/png")


def content_disposition(filename: str, *, inline: bool) -> str:
    """RFC 5987 编码的文件名响应头，兼容中文。"""
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename*=UTF-8''{quote(filename)}"


def archive_path_for(file_path: str) -> str:
    """归档对象路径：archive/{file_path}。"""
    return f"archive/{file_path}"


def read_storage_bytes(relative_path: str, *, archive_message: str | None = None) -> bytes:
    """读取存储文件；缺失返回 30014，读写异常返回 50003。

    归档路径按 ARCHIVE_READ_TIMEOUT_SECONDS 限制等待时间，超时按归档不可用处理。
    """
    path = storage.path(relative_path)
    if not path.is_file():
        raise ApiError(404, 30014, archive_message or "文件不存在")

    timeout = settings.ARCHIVE_READ_TIMEOUT_SECONDS
    if timeout <= 0:
        try:
            return path.read_bytes()
        except OSError as exc:
            raise ApiError(500, 50003, "存储服务错误") from exc

    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(path.read_bytes)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError as exc:
        raise ApiError(404, 30014, archive_message or "文件归档中，请稍后重试") from exc
    except OSError as exc:
        raise ApiError(500, 50003, "存储服务错误") from exc
    finally:
        # 不等待可能已卡住的读线程，避免请求被存储阻塞
        pool.shutdown(wait=False, cancel_futures=True)


def file_response(relative_path: str, *, headers: dict[str, str]) -> FileResponse:
    """返回热存储文件流；文件缺失或读取异常转为统一 JSON 错误。"""
    path = storage.path(relative_path)
    if not path.is_file():
        raise ApiError(404, 30014, "文件不存在")
    return FileResponse(path, media_type=media_type_for(path), headers=headers)


def bytes_response(data: bytes, *, media_type: str, headers: dict[str, str]) -> Response:
    """返回内存中的归档文件流。"""
    return Response(content=data, media_type=media_type, headers=headers)
