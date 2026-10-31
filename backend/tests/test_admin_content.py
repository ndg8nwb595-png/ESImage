"""7 号管理后台-用户与生图记录接口测试。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.user import User
from app.models.workspace import AgentRun, CreativeSession, GeneratedImage, GenerationBatch
from app.modules.workspace.storage import storage

BASE = "/api/v1"
PASSWORD = "Demo1234"
SEED_PREFIX = "seed7"


# ---------------------------------------------------------------------------
# 夹具：模块级写入 7 号演示数据，结束后清理，避免影响其他模块用例
# ---------------------------------------------------------------------------


def _seed_paths(db) -> tuple[list[int], list[int], list[str]]:
    batch_ids = list(
        db.scalars(
            select(GenerationBatch.id).where(
                GenerationBatch.client_request_id.like(f"{SEED_PREFIX}:%")
            )
        )
    )
    session_ids = list(
        db.scalars(
            select(GenerationBatch.session_id)
            .where(GenerationBatch.id.in_(batch_ids))
            .distinct()
        )
    ) if batch_ids else []
    file_paths: list[str] = []
    if batch_ids:
        for image in db.scalars(
            select(GeneratedImage).where(GeneratedImage.batch_id.in_(batch_ids))
        ):
            if image.file_path:
                file_paths.append(image.file_path)
            if image.thumbnail_path:
                file_paths.append(image.thumbnail_path)
            if image.archived_at is not None and image.file_path:
                file_paths.append(f"archive/{image.file_path}")
    return batch_ids, session_ids, file_paths


@pytest.fixture(scope="module", autouse=True)
def admin_demo_data(prepared_database):
    """写入 7 号种子；测试结束后清理内容与生成文件。"""
    from sqlalchemy import delete

    from app.core.database import SessionLocal
    from app.modules.admin.dashboard.service import clear_dashboard_cache
    from app.modules.admin.seed_content import seed_admin_content

    with SessionLocal() as db:
        seed_admin_content(db)
    clear_dashboard_cache()
    print("[测试] 已写入 7 号管理后台演示数据")
    yield

    with SessionLocal() as db:
        batch_ids, session_ids, file_paths = _seed_paths(db)
        if batch_ids:
            db.execute(
                delete(AgentRun).where(
                    AgentRun.input_summary.like(f"{SEED_PREFIX}:%")
                )
            )
            db.execute(delete(AgentRun).where(AgentRun.batch_id.in_(batch_ids)))
            db.execute(
                delete(GeneratedImage).where(GeneratedImage.batch_id.in_(batch_ids))
            )
            db.execute(
                delete(GenerationBatch).where(GenerationBatch.id.in_(batch_ids))
            )
        if session_ids:
            db.execute(
                delete(CreativeSession).where(CreativeSession.id.in_(session_ids))
            )
        db.commit()
    for relative_path in file_paths:
        storage.delete(relative_path)
    clear_dashboard_cache()
    print("[测试] 已清理 7 号管理后台演示数据")


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def login(client, username: str) -> str:
    response = client.post(
        f"{BASE}/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def user_id(db, username: str) -> int:
    return db.scalar(select(User.id).where(User.username == username))


def batch_id(db, marker: str) -> int:
    return db.scalar(
        select(GenerationBatch.id).where(
            GenerationBatch.client_request_id == f"{SEED_PREFIX}:batch:{marker}"
        )
    )


def session_id(db, title: str) -> int:
    return db.scalar(select(CreativeSession.id).where(CreativeSession.title == title))


def archived_image_id(db) -> int:
    return db.scalar(
        select(GeneratedImage.id).where(GeneratedImage.archived_at.is_not(None))
    )


# ---------------------------------------------------------------------------
# 概览
# ---------------------------------------------------------------------------


def test_dashboard_summary_matches_database(client, db_session):
    print("[测试] 步骤 1：超管读取概览四卡")
    token = login(client, "demo_super")
    response = client.get(f"{BASE}/admin/dashboard/summary", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    print("[测试] 步骤 2：用数据库独立聚合核对四卡口径")
    today = datetime.now(settings.TZ).date()
    start = datetime.combine(today, datetime.min.time(), tzinfo=settings.TZ)
    end = start + timedelta(days=1)
    expected_user_total = db_session.scalar(
        select(func.count()).select_from(User).where(User.status != "deleted")
    )
    expected_today_images = db_session.scalar(
        select(func.count())
        .select_from(GeneratedImage)
        .where(
            GeneratedImage.image_type == "final",
            GeneratedImage.status == "success",
            GeneratedImage.created_at >= start,
            GeneratedImage.created_at < end,
        )
    )
    expected_total_images = db_session.scalar(
        select(func.count())
        .select_from(GeneratedImage)
        .where(
            GeneratedImage.image_type == "final",
            GeneratedImage.status == "success",
        )
    )
    expected_today_tokens = db_session.scalar(
        select(
            func.coalesce(
                func.sum(AgentRun.prompt_tokens + AgentRun.completion_tokens), 0
            )
        ).where(AgentRun.created_at >= start, AgentRun.created_at < end)
    )
    assert data == {
        "user_total": int(expected_user_total),
        "today_image_count": int(expected_today_images),
        "total_image_count": int(expected_total_images),
        "today_token_total": int(expected_today_tokens),
    }
    print(f"[测试] 概览四卡一致：{data}")

    print("[测试] 步骤 3：60 秒内重复请求返回同一快照")
    again = client.get(
        f"{BASE}/admin/dashboard/summary", headers=auth_headers(token)
    )
    assert again.json()["data"] == data


def test_dashboard_cache_expires_and_can_be_cleared(db_session, monkeypatch):
    print("[测试] 验证概览缓存命中与清缓存后重算")
    import app.modules.admin.dashboard.service as dashboard_service

    first = dashboard_service.get_summary(db_session)
    fake = {
        "user_total": 1,
        "today_image_count": 2,
        "total_image_count": 3,
        "today_token_total": 4,
    }
    monkeypatch.setattr(dashboard_service, "_aggregate", lambda db: dict(fake))
    assert dashboard_service.get_summary(db_session) == first

    dashboard_service.clear_dashboard_cache()
    assert dashboard_service.get_summary(db_session) == fake
    print("[测试] 缓存命中与清缓存行为符合预期")


def test_dashboard_permissions(client):
    print("[测试] 概览权限：管理员可看，普通用户 403，未登录 401")
    admin_token = login(client, "demo_admin")
    user_token = login(client, "demo_user")
    assert (
        client.get(
            f"{BASE}/admin/dashboard/summary", headers=auth_headers(admin_token)
        ).status_code
        == 200
    )
    denied = client.get(
        f"{BASE}/admin/dashboard/summary", headers=auth_headers(user_token)
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == 20005
    unauthorized = client.get(f"{BASE}/admin/dashboard/summary")
    assert unauthorized.status_code == 401


# ---------------------------------------------------------------------------
# Token 统计
# ---------------------------------------------------------------------------


def _all_token_items(client, token: str, params: dict | None = None) -> dict:
    items = []
    page = 1
    total = None
    summary = None
    while True:
        query = dict(params or {})
        query["page"] = page
        response = client.get(
            f"{BASE}/admin/tokens/stats", params=query, headers=auth_headers(token)
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        summary = data["summary"]
        total = data["total"]
        items.extend(data["items"])
        if len(items) >= total or not data["items"]:
            break
        page += 1
    assert total == len(items)
    return {"summary": summary, "items": items, "total": total}


def test_token_stats_summary_matches_detail(client, db_session):
    print("[测试] 步骤 1：默认最近 7 天 Token 统计")
    token = login(client, "demo_admin")
    data = _all_token_items(client, token)
    assert data["total"] > 0
    assert data["summary"]["prompt_tokens"] == sum(
        item["prompt_tokens"] for item in data["items"]
    )
    assert data["summary"]["completion_tokens"] == sum(
        item["completion_tokens"] for item in data["items"]
    )
    assert data["summary"]["total_tokens"] == sum(
        item["total_tokens"] for item in data["items"]
    )
    assert data["summary"]["call_count"] == sum(
        item["call_count"] for item in data["items"]
    )

    print("[测试] 步骤 2：数据库核对计入与排除口径")
    today = datetime.now(settings.TZ).date()
    start = datetime.combine(today - timedelta(days=6), datetime.min.time(), tzinfo=settings.TZ)
    end = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=settings.TZ)
    runs = list(
        db_session.scalars(
            select(AgentRun).where(
                AgentRun.created_at >= start, AgentRun.created_at < end
            )
        )
    )
    counted = [
        run
        for run in runs
        if run.status == "success"
        or (
            run.status == "failed"
            and run.prompt_tokens + run.completion_tokens > 0
        )
    ]
    assert data["summary"]["call_count"] == len(counted)
    print(f"[测试] 计入调用 {len(counted)} 次，明细与汇总一致")


def test_token_stats_filters(client):
    print("[测试] 用户、Agent、模型筛选可组合")
    token = login(client, "demo_admin")

    data = _all_token_items(client, token, {"user": "demo_user2"})
    assert data["total"] >= 1
    assert {item["username"] for item in data["items"]} == {"demo_user2"}

    data = _all_token_items(
        client,
        token,
        {"agent_codes": "planner,platform_rule", "model": "doubao-seed-1.6"},
    )
    assert data["total"] >= 1
    assert {item["agent_code"] for item in data["items"]} == {
        "planner",
        "platform_rule",
    }
    assert {item["model_name"] for item in data["items"]} == {"doubao-seed-1.6"}


def test_token_stats_validation(client):
    print("[测试] 未知 Agent、起止倒置、越界页码")
    token = login(client, "demo_admin")
    headers = auth_headers(token)

    unknown = client.get(
        f"{BASE}/admin/tokens/stats",
        params={"agent_codes": "unknown_agent"},
        headers=headers,
    )
    assert unknown.status_code == 400
    assert unknown.json()["code"] == 10003
    assert unknown.json()["message"] == "Agent 参数不合法"

    reversed_range = client.get(
        f"{BASE}/admin/tokens/stats",
        params={"start_date": "2026-10-31", "end_date": "2026-10-01"},
        headers=headers,
    )
    assert reversed_range.status_code == 400
    assert reversed_range.json()["code"] == 10003

    print("[测试] 仅传早于默认起始日的 end_date，也应按起止倒置拒绝")
    early_end = client.get(
        f"{BASE}/admin/tokens/stats",
        params={"end_date": "2020-01-01"},
        headers=headers,
    )
    assert early_end.status_code == 400
    assert early_end.json()["code"] == 10003

    empty_page = client.get(
        f"{BASE}/admin/tokens/stats", params={"page": 99}, headers=headers
    )
    assert empty_page.status_code == 200
    assert empty_page.json()["data"]["items"] == []
    assert empty_page.json()["data"]["page"] == 99

    no_permission = client.get(
        f"{BASE}/admin/tokens/stats", headers=auth_headers(login(client, "demo_user"))
    )
    assert no_permission.status_code == 403
    assert no_permission.json()["code"] == 20005


# ---------------------------------------------------------------------------
# 内容追溯：用户 / 会话 / 批次 / 图片
# ---------------------------------------------------------------------------


def test_content_users_admin_filters_super_admin(client):
    print("[测试] 管理员看不到超管用户，超管能看到全部")
    admin_token = login(client, "demo_admin")
    super_token = login(client, "demo_super")

    admin_data = client.get(
        f"{BASE}/admin/content/users", headers=auth_headers(admin_token)
    ).json()["data"]
    admin_names = {item["username"] for item in admin_data["items"]}
    assert "demo_super" not in admin_names
    assert {"demo_user", "demo_user2"} <= admin_names

    super_data = client.get(
        f"{BASE}/admin/content/users", headers=auth_headers(super_token)
    ).json()["data"]
    assert "demo_super" in {item["username"] for item in super_data["items"]}

    keyword = client.get(
        f"{BASE}/admin/content/users",
        params={"keyword": "用户二"},
        headers=auth_headers(super_token),
    ).json()["data"]
    assert [item["username"] for item in keyword["items"]] == ["demo_user2"]
    print("[测试] 管理员过滤超管用户与关键词查询均正确")


def test_content_sessions_include_hidden_and_boundary(client, db_session):
    print("[测试] 会话列表包含隐藏会话，按最近消息倒序")
    token = login(client, "demo_super")
    uid = user_id(db_session, "demo_user")
    response = client.get(
        f"{BASE}/admin/content/users/{uid}/sessions", headers=auth_headers(token)
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert {item["status"] for item in items} == {"active", "hidden"}
    assert items[0]["status"] == "hidden"
    assert all(item["batch_count"] >= 1 for item in items)

    print("[测试] 管理员访问超管会话返回 403/20006")
    admin_token = login(client, "demo_admin")
    super_id = user_id(db_session, "demo_super")
    denied = client.get(
        f"{BASE}/admin/content/users/{super_id}/sessions",
        headers=auth_headers(admin_token),
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == 20006

    missing = client.get(
        f"{BASE}/admin/content/users/999999/sessions", headers=auth_headers(token)
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 30017


def test_batches_filters_and_composition(client, db_session):
    print("[测试] 会话批次构成、筛选与错误码")
    token = login(client, "demo_super")
    sid = session_id(db_session, "秋季通勤衬衫")
    headers = auth_headers(token)

    response = client.get(
        f"{BASE}/admin/content/sessions/{sid}/batches", headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 5
    statuses = {item["status"] for item in data["items"]}
    assert {"sample_ready", "completed", "partially_failed", "cancelled", "failed"} <= statuses
    for item in data["items"]:
        if item["batch_type"] == "sample":
            assert item["composition"] == {"main": 1, "detail": 0}
        else:
            assert item["composition"] == {
                "main": 1,
                "detail": item["total_count"] - 1,
            }

    partial = client.get(
        f"{BASE}/admin/content/sessions/{sid}/batches",
        params={"status": "partially_failed"},
        headers=headers,
    ).json()["data"]
    assert partial["total"] == 1
    assert partial["items"][0]["batch_type"] == "full"

    by_product = client.get(
        f"{BASE}/admin/content/sessions/{sid}/batches",
        params={"product_name": "衬衫", "batch_type": "full"},
        headers=headers,
    ).json()["data"]
    assert by_product["total"] >= 1
    assert all("衬衫" in item["product_name"] for item in by_product["items"])

    invalid = client.get(
        f"{BASE}/admin/content/sessions/{sid}/batches",
        params={"status": "bad_status"},
        headers=headers,
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == 10003

    empty = client.get(
        f"{BASE}/admin/content/sessions/{sid}/batches",
        params={"start_date": "2020-01-01", "end_date": "2020-01-02"},
        headers=headers,
    ).json()["data"]
    assert empty["total"] == 0

    print("[测试] 管理员访问超管批次返回 403/20006")
    admin_token = login(client, "demo_admin")
    super_session = session_id(db_session, "超管测试商品")
    denied = client.get(
        f"{BASE}/admin/content/sessions/{super_session}/batches",
        headers=auth_headers(admin_token),
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == 20006

    missing = client.get(
        f"{BASE}/admin/content/sessions/999999/batches", headers=headers
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 30013


def test_image_grid_latest_attempt_and_filters(client, db_session):
    print("[测试] 图片网格默认每个序号只展示最新尝试")
    token = login(client, "demo_super")
    bid = batch_id(db_session, "partially-failed")
    headers = auth_headers(token)

    latest = client.get(
        f"{BASE}/admin/content/batches/{bid}/images", headers=headers
    ).json()["data"]
    assert latest["total"] == 6
    index_three = [item for item in latest["items"] if item["index_no"] == 3]
    assert len(index_three) == 1
    assert index_three[0]["attempt_no"] == 2
    assert all(item["thumbnail_url"] for item in latest["items"] if item["status"] == "success")

    all_attempts = client.get(
        f"{BASE}/admin/content/batches/{bid}/images",
        params={"include_superseded": "true"},
        headers=headers,
    ).json()["data"]
    assert all_attempts["total"] == 7

    superseded = client.get(
        f"{BASE}/admin/content/batches/{bid}/images",
        params={"status": "superseded"},
        headers=headers,
    ).json()["data"]
    assert superseded["total"] == 1
    assert superseded["items"][0]["attempt_no"] == 1

    details = client.get(
        f"{BASE}/admin/content/batches/{bid}/images",
        params={"image_role": "detail", "status": "success"},
        headers=headers,
    ).json()["data"]
    assert details["total"] == 3
    assert {item["image_role"] for item in details["items"]} == {"detail"}

    invalid = client.get(
        f"{BASE}/admin/content/batches/{bid}/images",
        params={"image_role": "bad"},
        headers=headers,
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == 10003

    print("[测试] 管理员访问超管批次图片返回 403/20006")
    admin_token = login(client, "demo_admin")
    super_batch = batch_id(db_session, "super-completed")
    denied = client.get(
        f"{BASE}/admin/content/batches/{super_batch}/images",
        headers=auth_headers(admin_token),
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == 20006

    missing = client.get(
        f"{BASE}/admin/content/batches/999999/images", headers=headers
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 30004


def test_image_detail_fields_and_boundaries(client, db_session):
    print("[测试] 单图详情返回归档与失败字段")
    token = login(client, "demo_super")
    headers = auth_headers(token)

    archived_id = archived_image_id(db_session)
    detail = client.get(
        f"{BASE}/admin/content/images/{archived_id}", headers=headers
    )
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["archived_at"] is not None
    assert data["file_path"]
    assert data["thumbnail_url"].endswith(f"/{archived_id}/thumbnail")
    assert data["preview_url"].endswith(f"/{archived_id}/content")
    assert data["download_url"].endswith(f"/{archived_id}/download")
    assert data["product_name"] == "夏季连衣裙"
    assert data["prompt"]

    failed_image = db_session.scalar(
        select(GeneratedImage).where(
            GeneratedImage.batch_id == batch_id(db_session, "partially-failed"),
            GeneratedImage.index_no == 5,
            GeneratedImage.attempt_no == 1,
        )
    )
    failed_detail = client.get(
        f"{BASE}/admin/content/images/{failed_image.id}", headers=headers
    ).json()["data"]
    assert failed_detail["status"] == "failed"
    assert failed_detail["preview_url"] is None
    assert failed_detail["download_url"] is None
    assert failed_detail["thumbnail_url"] is None
    assert failed_detail["error_message"]

    missing = client.get(
        f"{BASE}/admin/content/images/999999", headers=headers
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 30024

    print("[测试] 管理员访问超管图片返回 403/20006")
    admin_token = login(client, "demo_admin")
    super_image = db_session.scalar(
        select(GeneratedImage.id).where(
            GeneratedImage.batch_id == batch_id(db_session, "super-completed")
        )
    )
    denied = client.get(
        f"{BASE}/admin/content/images/{super_image}", headers=auth_headers(admin_token)
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == 20006


# ---------------------------------------------------------------------------
# 媒体访问
# ---------------------------------------------------------------------------


def test_media_thumbnail_preview_download_and_archive(client, db_session):
    print("[测试] 归档图片的缩略图走热存储，大图与下载走 archive/")
    token = login(client, "demo_super")
    headers = auth_headers(token)
    image_id = archived_image_id(db_session)
    image = db_session.get(GeneratedImage, image_id)

    thumbnail = client.get(
        f"{BASE}/admin/content/images/{image_id}/thumbnail", headers=headers
    )
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"
    assert "max-age=300" in thumbnail.headers["cache-control"]

    hot_path = storage.path(image.file_path)
    archive_path = storage.path(f"archive/{image.file_path}")
    hot_backup = hot_path.with_suffix(hot_path.suffix + ".bak")
    archive_backup = archive_path.with_suffix(archive_path.suffix + ".bak")

    print("[测试] 临时移走热存储原件，确认大图仍从归档读取")
    hot_path.rename(hot_backup)
    try:
        content = client.get(
            f"{BASE}/admin/content/images/{image_id}/content", headers=headers
        )
        assert content.status_code == 200
        assert content.headers["content-type"] == "image/png"
        assert "no-store" in content.headers["cache-control"]

        download = client.get(
            f"{BASE}/admin/content/images/{image_id}/download", headers=headers
        )
        assert download.status_code == 200
        disposition = download.headers["content-disposition"]
        assert disposition.startswith("attachment; filename*=UTF-8''")
        assert "%E5%A4%8F%E5%AD%A3%E8%BF%9E%E8%A1%A3%E8%A3%99" in disposition
        print("[测试] 归档读取成功，下载文件名编码正确")
    finally:
        hot_backup.rename(hot_path)

    print("[测试] 临时移走归档文件，确认降级为 404/30014")
    archive_path.rename(archive_backup)
    hot_path.rename(hot_backup)
    try:
        unavailable = client.get(
            f"{BASE}/admin/content/images/{image_id}/content", headers=headers
        )
        assert unavailable.status_code == 404
        assert unavailable.json() == {
            "code": 30014,
            "message": "文件归档中，请稍后重试",
            "data": None,
        }
    finally:
        hot_backup.rename(hot_path)
        archive_backup.rename(archive_path)

    print("[测试] 失败图片下载返回 404/30014")
    failed_image = db_session.scalar(
        select(GeneratedImage).where(
            GeneratedImage.batch_id == batch_id(db_session, "partially-failed"),
            GeneratedImage.index_no == 5,
        )
    )
    failed_download = client.get(
        f"{BASE}/admin/content/images/{failed_image.id}/download", headers=headers
    )
    assert failed_download.status_code == 404
    assert failed_download.json()["code"] == 30014

    print("[测试] 普通用户访问媒体接口返回 403/20005，未登录 401")
    user_token = login(client, "demo_user")
    denied = client.get(
        f"{BASE}/admin/content/images/{image_id}/thumbnail",
        headers=auth_headers(user_token),
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == 20005
    assert (
        client.get(f"{BASE}/admin/content/images/{image_id}/thumbnail").status_code
        == 401
    )


# ---------------------------------------------------------------------------
# 用户列表 / 详情统计
# ---------------------------------------------------------------------------


def test_user_list_and_detail_stats(client, db_session):
    print("[测试] 用户列表与详情统计值为真实聚合")
    token = login(client, "demo_super")
    headers = auth_headers(token)
    uid = user_id(db_session, "demo_user")

    listing = client.get(
        f"{BASE}/admin/users", params={"page_size": 50}, headers=headers
    )
    assert listing.status_code == 200, listing.text
    users = {item["username"]: item for item in listing.json()["data"]["items"]}
    assert "demo_user2" in users
    assert users["demo_user"]["stats"]["stats_available"] is True

    detail = client.get(f"{BASE}/admin/users/{uid}", headers=headers).json()["data"]
    assert detail["stats"] == users["demo_user"]["stats"]

    stats = detail["stats"]
    expected_images = db_session.scalar(
        select(func.count())
        .select_from(GeneratedImage)
        .where(
            GeneratedImage.user_id == uid,
            GeneratedImage.image_type == "final",
            GeneratedImage.status == "success",
        )
    )
    expected_sessions = db_session.scalar(
        select(func.count())
        .select_from(CreativeSession)
        .where(CreativeSession.user_id == uid)
    )
    expected_failed = db_session.scalar(
        select(func.count())
        .select_from(GenerationBatch)
        .where(
            GenerationBatch.user_id == uid,
            GenerationBatch.status.in_(("failed", "partially_failed")),
        )
    )
    assert stats["image_count"] == int(expected_images)
    assert stats["session_count"] == int(expected_sessions)
    assert stats["failed_task_count"] == int(expected_failed)
    assert stats["token_total"] > 0
    print(f"[测试] demo_user 统计与数据库一致：{stats}")


def test_user_list_filters_and_boundaries(client, db_session):
    print("[测试] 用户列表筛选、分页与超管边界")
    token = login(client, "demo_super")
    headers = auth_headers(token)

    filtered = client.get(
        f"{BASE}/admin/users",
        params={"keyword": "demo", "role": "admin", "status": "all"},
        headers=headers,
    ).json()["data"]
    assert filtered["total"] >= 2
    assert all(
        "admin" in {role["code"] for role in item["roles"]}
        for item in filtered["items"]
    )

    invalid_page_size = client.get(
        f"{BASE}/admin/users", params={"page_size": 10}, headers=headers
    )
    assert invalid_page_size.status_code == 400
    assert invalid_page_size.json()["code"] == 10003
    assert invalid_page_size.json()["message"] == "每页条数不合法"

    invalid_range = client.get(
        f"{BASE}/admin/users",
        params={"created_from": "2026-10-31", "created_to": "2026-10-01"},
        headers=headers,
    )
    assert invalid_range.status_code == 400
    assert invalid_range.json()["code"] == 10003

    admin_token = login(client, "demo_admin")
    super_uid = user_id(db_session, "demo_super")
    denied = client.get(
        f"{BASE}/admin/users/{super_uid}", headers=auth_headers(admin_token)
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == 20006

    missing = client.get(f"{BASE}/admin/users/999999", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == 30017

    user_token = login(client, "demo_user")
    no_permission = client.get(
        f"{BASE}/admin/users", headers=auth_headers(user_token)
    )
    assert no_permission.status_code == 403
    assert no_permission.json()["code"] == 20005


def test_content_endpoints_reject_ordinary_user(client):
    print("[测试] 普通用户访问全部内容追溯接口返回 403/20005")
    token = login(client, "demo_user")
    headers = auth_headers(token)
    paths = [
        f"{BASE}/admin/content/users",
        f"{BASE}/admin/content/users/1/sessions",
        f"{BASE}/admin/content/sessions/1/batches",
        f"{BASE}/admin/content/batches/1/images",
        f"{BASE}/admin/content/images/1",
    ]
    for path in paths:
        response = client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert response.json()["code"] == 20005, path
    print("[测试] 普通用户内容接口全部拒绝")
