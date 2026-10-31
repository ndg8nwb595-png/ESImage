"""历史作品最小 demo 后端接口测试。

每一步都打印中文日志，便于定位失败步骤。
"""

from __future__ import annotations

import csv
import io
import logging
import shutil
import zipfile
from urllib.parse import unquote

import pytest
from sqlalchemy import delete, select

LOGIN_URL = "/api/v1/auth/login"
HISTORY_URL = "/api/v1/history"


@pytest.fixture(scope="module", autouse=True)
def seeded_history():
    """模块级：清空历史数据并写入可重复夹具，供只读用例共享。"""
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import (
        AgentRun,
        ChatMessage,
        CreativeSession,
        GeneratedImage,
        GenerationBatch,
        UploadedAsset,
    )
    from app.modules.history.seed import seed_history

    print("[历史测试] 清理历史相关表与本地存储……")
    with SessionLocal() as db:
        db.execute(delete(AgentRun))
        db.execute(delete(GeneratedImage))
        db.execute(delete(GenerationBatch))
        db.execute(delete(ChatMessage))
        db.execute(delete(UploadedAsset))
        db.execute(delete(CreativeSession))
        db.commit()

    shutil.rmtree(settings.STORAGE_ROOT, ignore_errors=True)
    settings.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        seed_history(db)
    yield


def _login(client, username: str = "demo_user") -> str:
    print(f"[历史测试] 登录 {username}")
    response = client.post(
        LOGIN_URL,
        json={"username": username, "password": "Demo1234", "remember_me": False},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_batch(key: str):
    """按种子 key 读取批次。"""
    from app.core.database import SessionLocal
    from app.models import GenerationBatch
    from app.modules.history.seed import SEED_PREFIX

    with SessionLocal() as db:
        batch = db.scalar(
            select(GenerationBatch).where(
                GenerationBatch.client_request_id == f"{SEED_PREFIX}{key}"
            )
        )
        assert batch is not None, f"缺少种子批次 {key}"
        return batch


def _seed_image(key: str, index_no: int):
    """按种子 key 与序号读取图片。"""
    from app.core.database import SessionLocal
    from app.models import GeneratedImage

    batch = _seed_batch(key)
    with SessionLocal() as db:
        image = db.scalar(
            select(GeneratedImage).where(
                GeneratedImage.batch_id == batch.id,
                GeneratedImage.index_no == index_no,
                GeneratedImage.status != "superseded",
            )
        )
        assert image is not None, f"缺少种子图片 {key}#{index_no}"
        return image


def test_history_list_pagination_and_fields(client):
    token = _login(client)
    print("[历史测试] 步骤 1：第 1 页固定 20 条，按时间倒序")
    first = client.get(f"{HISTORY_URL}?page=1", headers=_headers(token))
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["page"] == 1 and data["page_size"] == 20
    assert data["total"] == 21, data
    assert len(data["items"]) == 20

    # 部分失败批次时间最新，排在第一位
    newest = data["items"][0]
    assert newest["product_name"] == "部分失败演示"
    assert newest["main_count"] == 1 and newest["detail_count"] == 5
    assert newest["success_count"] == 5 and newest["total_count"] == 6
    assert newest["cover_image_id"] is not None
    assert newest["cover_thumbnail_url"] == (
        f"/api/v1/images/{newest['cover_image_id']}/thumbnail"
    )
    assert newest["created_at"]

    created_at = [item["created_at"] for item in data["items"]]
    assert created_at == sorted(created_at, reverse=True), created_at

    print("[历史测试] 步骤 2：第 2 页只剩 1 条，越界页为空")
    second = client.get(f"{HISTORY_URL}?page=2", headers=_headers(token)).json()["data"]
    assert second["total"] == 21 and len(second["items"]) == 1
    beyond = client.get(f"{HISTORY_URL}?page=999", headers=_headers(token)).json()["data"]
    assert beyond["items"] == [] and beyond["total"] == 21

    print("[历史测试] 步骤 3：page 非正整数返回 400/10001")
    for value in ("0", "-1", "abc"):
        response = client.get(f"{HISTORY_URL}?page={value}", headers=_headers(token))
        assert response.status_code == 400, response.text
        assert response.json()["code"] == 10001
        assert response.json()["message"] == "页码参数错误"

    print("[历史测试] 步骤 4：超大 page 返回空列表而不是 500")
    huge = client.get(
        f"{HISTORY_URL}?page=99999999999999999999", headers=_headers(token)
    )
    assert huge.status_code == 200, huge.text
    assert huge.json()["data"]["items"] == []
    assert huge.json()["data"]["total"] == 21


def test_history_list_excludes_non_visible(client):
    token = _login(client)
    print("[历史测试] 示例批次、失败批次、superseded 旧图不进入历史")
    response = client.get(HISTORY_URL, headers=_headers(token))
    items = response.json()["data"]["items"]
    names = {item["product_name"] for item in items}
    assert "示例演示" not in names
    assert "失败批次演示" not in names

    print("[历史测试] 被替代旧图批次的封面取最新成功尝试")
    cover_item = next(item for item in items if item["product_name"] == "被替代旧图演示")
    from app.core.database import SessionLocal
    from app.models import GeneratedImage

    old = _seed_image("superseded", 1)
    with SessionLocal() as db:
        latest = db.scalar(
            select(GeneratedImage)
            .where(
                GeneratedImage.batch_id == old.batch_id,
                GeneratedImage.index_no == 1,
                GeneratedImage.status != "superseded",
            )
            .order_by(GeneratedImage.attempt_no.desc())
        )
        assert latest is not None
        assert cover_item["cover_image_id"] == latest.id


def test_history_detail_completed_partial_and_errors(client):
    token = _login(client)
    completed = _seed_batch("completed-01")
    partial = _seed_batch("partially-failed")
    sample = _seed_batch("sample")
    failed = _seed_batch("failed")

    print("[历史测试] 步骤 1：completed 批次返回 6 张成功图")
    response = client.get(f"{HISTORY_URL}/{completed.id}", headers=_headers(token))
    assert response.status_code == 200, response.text
    detail = response.json()["data"]
    assert detail["status"] == "completed"
    assert detail["success_count"] == 6 and detail["total_count"] == 6
    assert detail["main_count"] == 1 and detail["detail_count"] == 5
    assert [image["index"] for image in detail["images"]] == [1, 2, 3, 4, 5, 6]
    assert detail["images"][0]["image_role"] == "main"
    assert all(image["image_role"] == "detail" for image in detail["images"][1:])
    assert all(image["width"] == 1000 and image["height"] == 1000 for image in detail["images"])
    for image in detail["images"]:
        assert image["thumbnail_url"] == f"/api/v1/images/{image['image_id']}/thumbnail"
        assert image["content_url"] == f"/api/v1/images/{image['image_id']}/content"
    assert "prompt" not in detail and "params_snapshot" not in detail

    print("[历史测试] 步骤 2：partial 批次只返回 5 张成功图")
    partial_detail = client.get(
        f"{HISTORY_URL}/{partial.id}", headers=_headers(token)
    ).json()["data"]
    assert partial_detail["status"] == "partially_failed"
    assert partial_detail["success_count"] == 5
    assert [image["index"] for image in partial_detail["images"]] == [1, 2, 3, 4, 5]

    print("[历史测试] 步骤 3：示例/失败批次返回 404/30004")
    for batch_id in (sample.id, failed.id):
        response = client.get(f"{HISTORY_URL}/{batch_id}", headers=_headers(token))
        assert response.status_code == 404, response.text
        assert response.json()["code"] == 30004

    print("[历史测试] 步骤 4：双向越权均 403/20005，不存在 404/30004")
    dual_token = _login(client, "demo_dual")
    other = client.get(f"{HISTORY_URL}/{completed.id}", headers=_headers(dual_token))
    assert other.status_code == 403
    assert other.json()["code"] == 20005

    other_batch = _seed_batch("other-user")
    reverse = client.get(f"{HISTORY_URL}/{other_batch.id}", headers=_headers(token))
    assert reverse.status_code == 403
    assert reverse.json()["code"] == 20005

    missing = client.get(f"{HISTORY_URL}/99999999", headers=_headers(token))
    assert missing.status_code == 404 and missing.json()["code"] == 30004


def test_history_media_permissions_and_filename(client):
    token = _login(client)
    completed = _seed_batch("completed-01")
    detail = client.get(
        f"{HISTORY_URL}/{completed.id}", headers=_headers(token)
    ).json()["data"]
    image = detail["images"][0]

    print("[历史测试] 步骤 1：缩略图、原图、单张下载均可读")
    thumbnail = client.get(image["thumbnail_url"], headers=_headers(token))
    assert thumbnail.status_code == 200, thumbnail.text
    assert thumbnail.headers["content-type"] == "image/webp"
    content = client.get(image["content_url"], headers=_headers(token))
    assert content.status_code == 200, content.text
    assert content.headers["content-type"] == "image/png"
    download = client.get(
        f"/api/v1/images/{image['image_id']}/download", headers=_headers(token)
    )
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == "image/png"
    assert download.headers["cache-control"] == "no-store"
    disposition = unquote(download.headers["content-disposition"])
    assert "历史通勤衬衫 01_主图_1_" in disposition
    assert disposition.endswith(".png")

    print("[历史测试] 步骤 2：商品名称非法字符替换为下划线")
    illegal = _seed_image("completed-18", 1)
    illegal_download = client.get(
        f"/api/v1/images/{illegal.id}/download", headers=_headers(token)
    )
    illegal_disposition = unquote(illegal_download.headers["content-disposition"])
    assert "秋季_通勤_衬衫_主图_1_" in illegal_disposition
    assert "/" not in illegal_disposition and ":" not in illegal_disposition

    print("[历史测试] 步骤 3：示例图不可下载")
    sample_image = _seed_image("sample", 1)
    blocked = client.get(
        f"/api/v1/images/{sample_image.id}/download", headers=_headers(token)
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == 30005

    print("[历史测试] 步骤 4：管理员无权限，其他用户读不到他人图片")
    admin_token = _login(client, "demo_admin")
    for url in (image["thumbnail_url"], image["content_url"], "/api/v1/history"):
        response = client.get(url, headers=_headers(admin_token))
        assert response.status_code == 403, (url, response.text)
        assert response.json()["code"] == 20005

    dual_token = _login(client, "demo_dual")
    other = client.get(image["content_url"], headers=_headers(dual_token))
    assert other.status_code == 404 and other.json()["code"] == 30014

    print("[历史测试] 步骤 5：未登录返回 401/20003")
    anonymous = client.get("/api/v1/history")
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == 20003


def _read_manifest(archive: zipfile.ZipFile) -> list[list[str]]:
    raw = archive.read("manifest.csv")
    assert raw.startswith(b"\xef\xbb\xbf"), "manifest.csv 缺少 UTF-8 BOM"
    text = raw.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def test_history_zip_completed_and_partial(client):
    token = _login(client)
    completed = _seed_batch("completed-01")
    partial = _seed_batch("partially-failed")

    print("[历史测试] 步骤 1：completed 批次 ZIP 含 6 图与 manifest")
    response = client.get(
        f"/api/v1/batches/{completed.id}/download", headers=_headers(token)
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    disposition = unquote(response.headers["content-disposition"])
    assert "_全套_" in disposition and disposition.endswith(".zip")

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert len(names) == 7 and "manifest.csv" in names

    # ZIP 条目名必须与单张下载文件名完全一致
    first_image = _seed_image("completed-01", 1)
    single = client.get(
        f"/api/v1/images/{first_image.id}/download", headers=_headers(token)
    )
    single_name = unquote(
        single.headers["content-disposition"].split("filename*=UTF-8''", 1)[1]
    )
    assert single_name in names, (single_name, names)
    for name in names:
        if name.endswith(".png"):
            assert archive.read(name).startswith(b"\x89PNG")
    rows = _read_manifest(archive)
    assert rows[0] == ["序号", "文件名", "状态", "宽度", "高度", "生成时间", "失败原因"]
    assert len(rows) == 7
    assert all(row[2] == "success" for row in rows[1:])
    assert [row[0] for row in rows[1:]] == ["1", "2", "3", "4", "5", "6"]

    print("[历史测试] 步骤 2：partial 批次 ZIP 只含成功图，manifest 保留失败行")
    partial_response = client.get(
        f"/api/v1/batches/{partial.id}/download", headers=_headers(token)
    )
    assert partial_response.status_code == 200, partial_response.text
    partial_archive = zipfile.ZipFile(io.BytesIO(partial_response.content))
    partial_names = partial_archive.namelist()
    assert len([name for name in partial_names if name.endswith(".png")]) == 5
    partial_rows = _read_manifest(partial_archive)
    assert len(partial_rows) == 7
    assert partial_rows[6][0] == "6"
    assert partial_rows[6][1] == ""
    assert partial_rows[6][2] == "failed"
    assert partial_rows[6][6] == "生图执行失败"

    print("[历史测试] 步骤 3：示例批次 409，越权 403，不存在 404")
    sample = _seed_batch("sample")
    sample_response = client.get(
        f"/api/v1/batches/{sample.id}/download", headers=_headers(token)
    )
    assert sample_response.status_code == 409
    assert sample_response.json()["code"] == 30005

    dual_token = _login(client, "demo_dual")
    other = client.get(
        f"/api/v1/batches/{completed.id}/download", headers=_headers(dual_token)
    )
    assert other.status_code == 403 and other.json()["code"] == 20005

    missing = client.get(
        "/api/v1/batches/99999999/download", headers=_headers(token)
    )
    assert missing.status_code == 404 and missing.json()["code"] == 30004


def test_history_zip_superseded_uses_latest_attempt(client):
    token = _login(client)
    batch = _seed_batch("superseded")
    response = client.get(
        f"/api/v1/batches/{batch.id}/download", headers=_headers(token)
    )
    assert response.status_code == 200, response.text
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    rows = _read_manifest(archive)
    assert len(rows) == 7
    # 序号 1 只出现一次，且文件名来自最新成功尝试
    assert [row[0] for row in rows[1:]] == ["1", "2", "3", "4", "5", "6"]
    assert rows[1][2] == "success"
    assert rows[1][1].startswith("被替代旧图演示_主图_1_")


def test_history_archive_read_and_degradation(client, caplog):
    token = _login(client)
    batch = _seed_batch("archived")
    detail = client.get(
        f"{HISTORY_URL}/{batch.id}", headers=_headers(token)
    ).json()["data"]
    image = detail["images"][0]

    print("[历史测试] 步骤 1：归档批次详情、缩略图、原图、下载、ZIP 均可用")
    assert detail["success_count"] == 6
    thumbnail = client.get(image["thumbnail_url"], headers=_headers(token))
    assert thumbnail.status_code == 200
    content = client.get(image["content_url"], headers=_headers(token))
    assert content.status_code == 200 and content.headers["content-type"] == "image/png"
    download = client.get(
        f"/api/v1/images/{image['image_id']}/download", headers=_headers(token)
    )
    assert download.status_code == 200
    zip_response = client.get(
        f"/api/v1/batches/{batch.id}/download", headers=_headers(token)
    )
    assert zip_response.status_code == 200

    print("[历史测试] 步骤 2：归档文件移走后预览/下载/ZIP 返回 30014")
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import GeneratedImage

    with SessionLocal() as db:
        row = db.get(GeneratedImage, image["image_id"])
        assert row is not None and row.archived_at is not None
        archive_path = settings.STORAGE_ROOT / "archive" / (row.file_path or "")
    assert archive_path.is_file(), archive_path
    backup = archive_path.with_suffix(archive_path.suffix + ".bak")
    archive_path.rename(backup)
    try:
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger="esimage.storage"):
            content = client.get(image["content_url"], headers=_headers(token))
            assert content.status_code == 404
            assert content.json()["code"] == 30014
            assert content.json()["message"] == "文件归档中，请稍后重试"

            download = client.get(
                f"/api/v1/images/{image['image_id']}/download",
                headers=_headers(token),
            )
            assert download.status_code == 404
            assert download.json()["message"] == "文件归档中，请稍后重试"

            zip_response = client.get(
                f"/api/v1/batches/{batch.id}/download", headers=_headers(token)
            )
            assert zip_response.status_code == 404
            assert zip_response.json()["code"] == 30014

        assert "归档读取失败" in caplog.text
        assert str(row.batch_id) in caplog.text
    finally:
        backup.rename(archive_path)


def test_archive_timeout_returns_fast(monkeypatch):
    """归档读取超时必须尽快返回，不能等待慢存储读完。"""
    import threading
    import time
    from datetime import datetime, timezone
    from pathlib import Path
    from types import SimpleNamespace

    from app.core.config import settings
    from app.core.response import ApiError
    from app.modules.workspace.service import read_image_bytes

    image = _seed_image("archived", 1)
    archive_path = settings.STORAGE_ROOT / "archive" / (image.file_path or "")
    assert archive_path.is_file(), archive_path

    print("[历史测试] 模拟归档存储读取 2 秒，超时 0.1 秒")
    started = threading.Event()
    release = threading.Event()
    real_read_bytes = Path.read_bytes

    def slow_read_bytes(self):
        started.set()
        release.wait(2)
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", slow_read_bytes)
    monkeypatch.setattr(settings, "ARCHIVE_READ_TIMEOUT_SECONDS", 0.1)
    detached = SimpleNamespace(
        id=image.id,
        batch_id=image.batch_id,
        file_path=image.file_path,
        archived_at=datetime.now(timezone.utc),
    )

    begin = time.monotonic()
    try:
        with pytest.raises(ApiError) as exc:
            read_image_bytes(detached)
    finally:
        release.set()
    elapsed = time.monotonic() - begin

    assert started.is_set(), "读取线程未启动"
    assert exc.value.status_code == 404 and exc.value.code == 30014
    assert elapsed < 0.5, f"超时未生效，实际耗时 {elapsed:.2f}s"
    print(f"[历史测试] 归档超时在 {elapsed:.2f}s 内返回 30014")
