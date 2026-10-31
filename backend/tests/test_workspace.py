"""创作工作台最小 demo 后端接口测试。

每一步都打印中文日志，便于定位失败步骤。
"""

from __future__ import annotations

import json
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from urllib.parse import unquote

import pytest
from PIL import Image
from sqlalchemy import delete, func, select

LOGIN_URL = "/api/v1/auth/login"
SESSIONS_URL = "/api/v1/sessions"
UPLOADS_URL = "/api/v1/uploads"
SAMPLE_URL = "/api/v1/generations/sample"


def _login(client, username: str = "demo_user") -> str:
    print(f"[测试] 登录 {username}")
    response = client.post(
        LOGIN_URL,
        json={"username": username, "password": "Demo1234", "remember_me": False},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _uid() -> str:
    """幂等键按接口文档使用 UUID。"""
    return str(uuid.uuid4())


def _png(size: tuple[int, int] = (1200, 1200), color=(80, 120, 200)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(client, token: str, name: str = "shirt.png", data: bytes | None = None):
    return client.post(
        UPLOADS_URL,
        headers=_headers(token),
        files={"file": (name, data if data is not None else _png(), "image/png")},
    )


def _sse_events(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        event_name = ""
        data = ""
        for line in lines:
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        events.append((event_name, json.loads(data) if data else {}))
    return events


def _chat(
    client,
    token: str,
    *,
    client_message_id: str | None = None,
    content: str = "帮我做一套通勤风的图",
    product_name: str = "秋季通勤衬衫",
    style_text: str | None = "简洁白底",
    session_id: int | None = None,
):
    url = SESSIONS_URL + ("/messages" if session_id is None else f"/{session_id}/messages")
    payload = {
        "client_message_id": client_message_id or _uid(),
        "content": content,
        "params": {
            "product_name": product_name,
            "style_text": style_text,
            "width": 1000,
            "height": 1000,
            "template_id": None,
        },
    }
    if session_id is None:
        payload["session_id"] = None
    return client.post(url, headers=_headers(token), json=payload)


def _sample(
    client,
    token: str,
    *,
    client_request_id: str | None = None,
    session_id: int | None = None,
    product_name: str = "秋季通勤衬衫",
    style_text: str | None = "简洁白底",
    upload_ids: list[int] | None = None,
    template_id: int | None = None,
    width: int | None = 1000,
    height: int | None = 1000,
):
    return client.post(
        SAMPLE_URL,
        headers=_headers(token),
        json={
            "client_request_id": client_request_id or _uid(),
            "session_id": session_id,
            "product_name": product_name,
            "style_text": style_text,
            "width": width,
            "height": height,
            "template_id": template_id,
            "upload_ids": upload_ids,
            "requirement_summary": None,
        },
    )


@pytest.fixture(autouse=True)
def clean_workspace():
    """每个用例前清空工作台相关表与本地存储，保证用例互相独立。"""
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

    print("[测试] 清理工作台数据……")
    with SessionLocal() as db:
        db.execute(delete(AgentRun))
        db.execute(delete(GeneratedImage))
        db.execute(delete(GenerationBatch))
        db.execute(delete(ChatMessage))
        db.execute(delete(UploadedAsset))
        db.execute(delete(CreativeSession))
        db.commit()

    # 只清理用户产物，保留模板/素材种子文件，避免影响生成链路测试
    for subdir in ("uploads", "generated", "thumbnails"):
        shutil.rmtree(settings.STORAGE_ROOT / subdir, ignore_errors=True)
    settings.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    yield


def test_login_permissions_and_empty_sessions(client):
    print("[测试] 步骤 1：demo_user 登录并检查工作台权限")
    token = _login(client)
    me = client.get("/api/v1/auth/me", headers=_headers(token)).json()["data"]
    assert set(me["permissions"]) == {
        "user.workspace",
        "user.generate",
        "user.history",
        "user.profile",
    }

    print("[测试] 步骤 2：会话列表为空")
    response = client.get(SESSIONS_URL, headers=_headers(token))
    assert response.status_code == 200
    assert response.json()["data"] == {"items": [], "total": 0}


def test_first_message_creates_session_and_streams(client):
    token = _login(client)
    print("[测试] 步骤 1：首条消息无会话，SSE 返回 meta/session_id")
    response = _chat(client, token)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _sse_events(response.text)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names[-1] == "done"
    meta = events[0][1]
    assert isinstance(meta["session_id"], int)
    assert isinstance(meta["message_id"], int)
    agent_codes = [data["agent_code"] for name, data in events if name == "agent_status"]
    assert agent_codes[:3] == ["planner", "planner", "product_understanding"]
    missing = [data["content"] for name, data in events if name == "delta"]
    assert "".join(missing) == (
        "已了解商品「秋季通勤衬衫」，风格按「简洁白底」处理。可以继续补充卖点、目标人群或使用场景。"
    )
    done = events[-1][1]
    assert done["requirement_summary"]["product_name"] == "秋季通勤衬衫"
    assert done["token_in"] == 0 and done["token_out"] == 0

    print("[测试] 步骤 2：会话自动命名并出现在列表")
    sessions = client.get(SESSIONS_URL, headers=_headers(token)).json()["data"]["items"]
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == meta["session_id"]
    assert sessions[0]["title"] == "帮我做一套通勤风的图"
    assert sessions[0]["latest_batch_id"] is None

    print("[测试] 步骤 3：消息分页返回用户与 Agent 两条")
    messages = client.get(
        f"{SESSIONS_URL}/{meta['session_id']}/messages", headers=_headers(token)
    ).json()["data"]
    assert messages["total"] == 2
    assert [item["role"] for item in messages["items"]] == ["user", "assistant"]
    assert messages["items"][1]["agent_code"] == "product_understanding"

    print("[测试] 步骤 4：agent_runs 记录两个轻链路 Agent")
    from app.core.database import SessionLocal
    from app.models import AgentRun

    with SessionLocal() as db:
        codes = list(
            db.scalars(select(AgentRun.agent_code).where(AgentRun.session_id == meta["session_id"]))
        )
    assert sorted(codes) == ["planner", "product_understanding"]


def test_chat_idempotent_replay(client):
    token = _login(client)
    key = _uid()
    print("[测试] 步骤 1：相同 client_message_id 首次发送")
    first = _chat(client, token, client_message_id=key)
    first_events = _sse_events(first.text)
    first_session = first_events[0][1]["session_id"]

    print("[测试] 步骤 2：相同 client_message_id 再次发送，应重放而不新建")
    second = _chat(client, token, client_message_id=key)
    second_events = _sse_events(second.text)
    assert second_events[0][1]["session_id"] == first_session
    assert [name for name, _ in second_events] == ["meta", "delta", "done"]

    from app.core.database import SessionLocal
    from app.models import ChatMessage, CreativeSession

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CreativeSession)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.role == "user")
            )
            == 1
        )


@pytest.mark.parametrize(
    ("content", "product_name", "style_text", "template_id", "expected"),
    [
        ("   ", "秋季通勤衬衫", None, None, (400, 10002)),
        ("x" * 2001, "秋季通勤衬衫", None, None, (400, 10004)),
        ("你好", "   ", None, None, (400, 10002)),
        ("你好", "秋季通勤衬衫", "风" * 51, None, (400, 10004)),
        ("你好", "秋季通勤衬衫", None, 9, (404, 30016)),
    ],
)
def test_chat_validation(client, content, product_name, style_text, template_id, expected):
    token = _login(client)
    print(f"[测试] 聊天参数校验 -> {expected}")
    response = _chat(
        client,
        token,
        content=content,
        product_name=product_name,
        style_text=style_text,
    )
    if template_id is not None:
        # 单独构造带模板的请求
        response = client.post(
            SESSIONS_URL + "/messages",
            headers=_headers(token),
            json={
                "client_message_id": _uid(),
                "content": content,
                "params": {
                    "product_name": product_name,
                    "style_text": style_text,
                    "width": 1000,
                    "height": 1000,
                    "template_id": template_id,
                },
                "session_id": None,
            },
        )
    assert response.status_code == expected[0], response.text
    assert response.json()["code"] == expected[1]


def test_upload_restore_thumbnail_and_delete(client):
    token = _login(client)
    print("[测试] 步骤 1：上传两张商品图")
    first = _upload(client, token, "shirt.png")
    second = _upload(client, token, "pants.png", _png(color=(200, 120, 60)))
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert first_data["sort_order"] == 0 and second_data["sort_order"] == 1
    assert first_data["width"] == 1200 and first_data["height"] == 1200
    assert first_data["file_url"] == f"/api/v1/uploads/{first_data['upload_id']}/content"

    print("[测试] 步骤 2：按 upload_id 恢复元数据与缩略图")
    restored = client.get(f"{UPLOADS_URL}/{first_data['upload_id']}", headers=_headers(token))
    assert restored.status_code == 200
    assert restored.json()["data"]["original_name"] == "shirt.png"
    content = client.get(first_data["file_url"], headers=_headers(token))
    assert content.status_code == 200 and content.headers["content-type"] == "image/png"
    thumbnail = client.get(first_data["thumbnail_url"], headers=_headers(token))
    assert thumbnail.status_code == 200 and thumbnail.headers["content-type"] == "image/webp"

    print("[测试] 步骤 3：软删除后元数据不可读")
    deleted = client.delete(f"{UPLOADS_URL}/{first_data['upload_id']}", headers=_headers(token))
    assert deleted.status_code == 200 and deleted.json() == {"code": 0, "message": "ok", "data": None}
    missing = client.get(f"{UPLOADS_URL}/{first_data['upload_id']}", headers=_headers(token))
    assert missing.status_code == 404 and missing.json()["code"] == 30014


@pytest.mark.parametrize(
    ("name", "data", "expected_message"),
    [
        ("shirt.gif", b"GIF89a", "仅支持 JPG、PNG、WEBP 格式"),
        ("broken.png", b"not-an-image", "图片文件损坏，请重新上传"),
    ],
)
def test_upload_validation(client, name, data, expected_message):
    token = _login(client)
    print(f"[测试] 上传校验 {name} -> {expected_message}")
    response = _upload(client, token, name, data)
    assert response.status_code == 400
    assert response.json()["code"] == 30006
    assert response.json()["message"] == expected_message


def test_upload_count_limit(client):
    token = _login(client)
    print("[测试] 连续上传 5 张")
    for index in range(5):
        response = _upload(client, token, f"p{index}.png")
        assert response.status_code == 200, response.text

    print("[测试] 第 6 张应返回 30006")
    sixth = _upload(client, token, "p6.png")
    assert sixth.status_code == 400
    assert sixth.json()["code"] == 30006
    assert sixth.json()["message"] == "最多上传 5 张商品图"


def test_sample_generation_progress_and_download_blocked(client):
    token = _login(client)
    upload_a = _upload(client, token, "a.png").json()["data"]["upload_id"]
    upload_b = _upload(client, token, "b.png").json()["data"]["upload_id"]

    print("[测试] 步骤 1：无会话创建示例批次")
    response = _sample(client, token, upload_ids=[upload_a, upload_b])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "queued"
    assert data["total_count"] == 1 and data["completed_count"] == 0
    assert data["session_id"] and data["session_title"] == "秋季通勤衬衫"
    batch_id = data["batch_id"]

    print("[测试] 步骤 2：轮询批次，示例图已完成")
    batch = client.get(f"/api/v1/generations/{batch_id}", headers=_headers(token)).json()["data"]
    assert batch["batch_type"] == "sample"
    assert batch["status"] == "sample_ready"
    assert batch["stage"] == "done"
    assert batch["completed_count"] == 1
    assert len(batch["images"]) == 1
    image = batch["images"][0]
    assert image["index"] == 1 and image["image_role"] == "main"
    assert image["status"] == "success"
    assert image["content_url"] and image["thumbnail_url"]
    assert image["width"] == 1000 and image["height"] == 1000

    print("[测试] 步骤 3：示例图可预览、不可下载")
    preview = client.get(image["content_url"], headers=_headers(token))
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    thumbnail = client.get(image["thumbnail_url"], headers=_headers(token))
    assert thumbnail.status_code == 200
    blocked = client.get(f"/api/v1/images/{image['image_id']}/download", headers=_headers(token))
    assert blocked.status_code == 409
    assert blocked.json()["code"] == 30005
    assert blocked.json()["message"] == "示例图确认前不可下载"

    print("[测试] 步骤 4：上传图已绑定会话并按顺序写入 sort_order")
    from app.core.database import SessionLocal
    from app.models import UploadedAsset

    with SessionLocal() as db:
        assets = list(
            db.scalars(
                select(UploadedAsset).where(UploadedAsset.id.in_([upload_a, upload_b]))
            )
        )
        by_id = {asset.id: asset for asset in assets}
        assert by_id[upload_a].session_id == data["session_id"]
        assert by_id[upload_b].session_id == data["session_id"]
        assert by_id[upload_a].sort_order == 0
        assert by_id[upload_b].sort_order == 1

    print("[测试] 步骤 5：会话列表恢复 latest_batch_id")
    sessions = client.get(SESSIONS_URL, headers=_headers(token)).json()["data"]["items"]
    assert sessions[0]["latest_batch_id"] == batch_id


def test_sample_idempotency_and_concurrency(client):
    token = _login(client)
    key = _uid()
    print("[测试] 步骤 1：相同 client_request_id 重复提交返回同一批次")
    first = _sample(client, token, client_request_id=key)
    second = _sample(client, token, client_request_id=key)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"]["batch_id"] == second.json()["data"]["batch_id"]

    from app.core.database import SessionLocal
    from app.models import CreativeSession, GenerationBatch, User

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GenerationBatch)) == 1
        session_id = db.scalar(select(CreativeSession.id))
        user_id = db.scalar(select(User.id).where(User.username == "demo_user"))
        print("[测试] 步骤 2：插入 running 批次后再次生成应返回 30003")
        db.add(
            GenerationBatch(
                user_id=user_id,
                session_id=session_id,
                batch_type="sample",
                source_sample_batch_id=None,
                product_name="占位商品",
                width=1000,
                height=1000,
                total_count=1,
                completed_count=0,
                status="running",
                params_snapshot={},
            )
        )
        db.commit()

    blocked = _sample(client, token, client_request_id=_uid())
    assert blocked.status_code == 409
    assert blocked.json()["code"] == 30003
    assert blocked.json()["message"] == "已有生成任务进行中"


def test_confirm_full_flow_and_download(client):
    token = _login(client)
    sample = _sample(client, token).json()["data"]
    sample_batch_id = sample["batch_id"]
    sample_image = client.get(
        f"/api/v1/generations/{sample_batch_id}", headers=_headers(token)
    ).json()["data"]["images"][0]

    print("[测试] 步骤 1：确认示例，创建全套批次")
    confirm = client.post(
        f"/api/v1/generations/{sample_batch_id}/confirm",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    assert confirm.status_code == 200, confirm.text
    full = confirm.json()["data"]
    assert full["total_count"] == 6 and full["status"] == "queued"

    print("[测试] 步骤 2：轮询全套批次，6 张全部成功")
    batch = client.get(
        f"/api/v1/generations/{full['full_batch_id']}", headers=_headers(token)
    ).json()["data"]
    assert batch["status"] == "completed"
    assert batch["stage"] == "done"
    assert batch["completed_count"] == 6 and batch["total_count"] == 6
    assert [image["index"] for image in batch["images"]] == [1, 2, 3, 4, 5, 6]
    assert batch["images"][0]["image_role"] == "main"
    assert all(image["image_role"] == "detail" for image in batch["images"][1:])
    assert all(image["status"] == "success" for image in batch["images"])

    print("[测试] 步骤 3：第 1 张主图复用示例图文件")
    from app.core.database import SessionLocal
    from app.models import GeneratedImage, GenerationBatch

    with SessionLocal() as db:
        main_image = db.scalar(
            select(GeneratedImage).where(
                GeneratedImage.batch_id == full["full_batch_id"],
                GeneratedImage.index_no == 1,
            )
        )
        source = db.get(GeneratedImage, sample_image["image_id"])
        assert main_image.source_image_id == sample_image["image_id"]
        assert main_image.file_path == source.file_path
        assert main_image.is_history_visible is True
        sample_row = db.get(GenerationBatch, sample_batch_id)
        assert sample_row.status == "confirmed"

    print("[测试] 步骤 4：下载主图与详情图，文件名符合规则")
    for image in (batch["images"][0], batch["images"][1]):
        download = client.get(
            f"/api/v1/images/{image['image_id']}/download", headers=_headers(token)
        )
        assert download.status_code == 200, download.text
        assert download.headers["content-type"] == "image/png"
        disposition = unquote(download.headers["content-disposition"])
        role_label = "主图" if image["image_role"] == "main" else "详情图"
        assert f"秋季通勤衬衫_{role_label}_{image['index']}_" in disposition
        assert disposition.endswith(".png")


def test_confirm_only_latest_and_idempotent(client):
    token = _login(client)
    first = _sample(client, token, client_request_id=_uid()).json()["data"]
    second = _sample(client, token, client_request_id=_uid()).json()["data"]

    print("[测试] 步骤 1：确认旧示例应返回 30005")
    old = client.post(
        f"/api/v1/generations/{first['batch_id']}/confirm",
        headers=_headers(token),
        json={"client_request_id": _uid()},
    )
    assert old.status_code == 409
    assert old.json()["code"] == 30005
    assert old.json()["message"] == "该示例不是最新示例，请确认最新示例"

    print("[测试] 步骤 2：确认最新示例成功，重复确认返回同一全套批次")
    confirm_key = _uid()
    ok_first = client.post(
        f"/api/v1/generations/{second['batch_id']}/confirm",
        headers=_headers(token),
        json={"client_request_id": confirm_key},
    )
    assert ok_first.status_code == 200, ok_first.text
    ok_second = client.post(
        f"/api/v1/generations/{second['batch_id']}/confirm",
        headers=_headers(token),
        json={"client_request_id": confirm_key},
    )
    assert ok_second.status_code == 200
    assert ok_first.json()["data"]["full_batch_id"] == ok_second.json()["data"]["full_batch_id"]


def test_permissions_and_data_isolation(client):
    user_token = _login(client, "demo_user")
    admin_token = _login(client, "demo_admin")
    dual_token = _login(client, "demo_dual")

    print("[测试] 步骤 1：管理员访问工作台接口返回 403/20005")
    admin_sessions = client.get(SESSIONS_URL, headers=_headers(admin_token))
    assert admin_sessions.status_code == 403
    assert admin_sessions.json()["code"] == 20005

    print("[测试] 步骤 2：demo_user 创建会话、上传图与批次")
    chat = _chat(client, user_token, client_message_id=_uid())
    session_id = _sse_events(chat.text)[0][1]["session_id"]
    upload_id = _upload(client, user_token, "mine.png").json()["data"]["upload_id"]
    batch_id = _sample(client, user_token, client_request_id=_uid()).json()["data"]["batch_id"]

    print("[测试] 步骤 3：另一个普通用户看不到他人数据")
    assert client.get(SESSIONS_URL, headers=_headers(dual_token)).json()["data"]["items"] == []
    other_batch = client.get(f"/api/v1/generations/{batch_id}", headers=_headers(dual_token))
    assert other_batch.status_code == 404 and other_batch.json()["code"] == 30004
    other_upload = client.get(f"{UPLOADS_URL}/{upload_id}", headers=_headers(dual_token))
    assert other_upload.status_code == 404 and other_upload.json()["code"] == 30014
    other_messages = client.get(
        f"{SESSIONS_URL}/{session_id}/messages", headers=_headers(dual_token)
    )
    assert other_messages.status_code == 404 and other_messages.json()["code"] == 30013

    print("[测试] 步骤 4：管理员不能下载正式图")
    sample_image_id = client.get(
        f"/api/v1/generations/{batch_id}", headers=_headers(user_token)
    ).json()["data"]["images"][0]["image_id"]
    admin_download = client.get(
        f"/api/v1/images/{sample_image_id}/download", headers=_headers(admin_token)
    )
    assert admin_download.status_code == 403
    assert admin_download.json()["code"] == 20005


def test_message_pagination(client):
    token = _login(client)
    print("[测试] 步骤 1：连续发送三条消息")
    session_id = _sse_events(
        _chat(client, token, client_message_id=_uid()).text
    )[0][1]["session_id"]
    for index in (2, 3):
        response = _chat(
            client,
            token,
            client_message_id=_uid(),
            content=f"第 {index} 条补充",
            session_id=session_id,
        )
        assert response.status_code == 200, response.text

    print("[测试] 步骤 2：每页 2 条，第一页为最新两对消息且页内升序")
    all_messages = client.get(
        f"{SESSIONS_URL}/{session_id}/messages?page=1&page_size=20", headers=_headers(token)
    ).json()["data"]["items"]
    all_ids = [item["message_id"] for item in all_messages]
    assert all_ids == sorted(all_ids)

    page_one = client.get(
        f"{SESSIONS_URL}/{session_id}/messages?page=1&page_size=2", headers=_headers(token)
    ).json()["data"]
    assert page_one["total"] == 6
    assert page_one["page"] == 1 and page_one["page_size"] == 2
    page_one_ids = [item["message_id"] for item in page_one["items"]]
    assert page_one_ids == all_ids[-2:]

    page_two = client.get(
        f"{SESSIONS_URL}/{session_id}/messages?page=2&page_size=2", headers=_headers(token)
    ).json()["data"]
    page_two_ids = [item["message_id"] for item in page_two["items"]]
    assert page_two_ids == all_ids[-4:-2]


def test_sample_validation(client):
    token = _login(client)
    cases = [
        ({}, 400, 10002),
        ({"product_name": "   "}, 400, 10002),
        ({"product_name": "商" * 61}, 400, 10004),
        ({"style_text": "风" * 51}, 400, 10004),
        ({"width": 0}, 400, 10003),
        ({"width": "abc"}, 400, 10003),
        ({"width": 5000}, 400, 10004),
        ({"height": 5000}, 400, 10004),
        ({"template_id": 3}, 404, 30016),
    ]
    for overrides, status, code in cases:
        print(f"[测试] 示例批次校验 {overrides} -> {status}/{code}")
        payload = {
            "client_request_id": _uid(),
            "session_id": None,
            "product_name": "秋季通勤衬衫",
            "style_text": None,
            "width": 1000,
            "height": 1000,
            "template_id": None,
            "upload_ids": [],
            "requirement_summary": None,
        }
        if overrides == {}:
            payload.pop("product_name")
        payload.update(overrides)
        response = client.post(SAMPLE_URL, headers=_headers(token), json=payload)
        assert response.status_code == status, response.text
        assert response.json()["code"] == code


def test_idempotency_key_requires_uuid(client):
    token = _login(client)
    print("[测试] 非 UUID 的聊天幂等键返回 10003")
    chat = _chat(client, token, client_message_id="not-a-uuid")
    assert chat.status_code == 400
    assert chat.json()["code"] == 10003

    print("[测试] 非 UUID 的批次幂等键返回 10003")
    sample = _sample(client, token, client_request_id="not-a-uuid")
    assert sample.status_code == 400
    assert sample.json()["code"] == 10003


def test_upload_missing_file_message(client):
    token = _login(client)
    print("[测试] 不传文件时返回「请选择要上传的图片」")
    response = client.post(UPLOADS_URL, headers=_headers(token))
    assert response.status_code == 400
    assert response.json()["code"] == 10002
    assert response.json()["message"] == "请选择要上传的图片"


def test_chat_concurrent_same_idempotency_key(client):
    token = _login(client)
    key = _uid()
    print("[测试] 两个线程并发发送同一 client_message_id")

    def send():
        return _chat(client, token, client_message_id=key)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: send(), range(2)))

    # 按接口文档 §7.4：处理中返回 409，已完成才重放；两种结果都不得产生重复数据
    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 409], [response.text for response in responses]
    waiting = next(response for response in responses if response.status_code == 409)
    assert waiting.json()["code"] == 30005
    assert waiting.json()["message"] == "消息正在处理中，请稍候"

    sessions = client.get(SESSIONS_URL, headers=_headers(token)).json()["data"]["items"]
    assert len(sessions) == 1

    from app.core.database import SessionLocal
    from app.models import ChatMessage, CreativeSession

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CreativeSession)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.role == "user")
            )
            == 1
        )


def test_confirm_concurrent_same_idempotency_key(client):
    token = _login(client)
    sample = _sample(client, token, client_request_id=_uid()).json()["data"]
    confirm_key = _uid()
    print("[测试] 两个线程并发确认同一示例，应返回同一全套批次")

    def confirm():
        return client.post(
            f"/api/v1/generations/{sample['batch_id']}/confirm",
            headers=_headers(token),
            json={"client_request_id": confirm_key},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: confirm(), range(2)))

    assert all(response.status_code == 200 for response in responses), [
        response.text for response in responses
    ]
    full_ids = {response.json()["data"]["full_batch_id"] for response in responses}
    assert len(full_ids) == 1

    from app.core.database import SessionLocal
    from app.models import GenerationBatch

    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(GenerationBatch)
                .where(GenerationBatch.batch_type == "full")
            )
            == 1
        )


def test_upload_from_other_session_is_rejected(client):
    token = _login(client)
    upload_id = _upload(client, token, "bound.png").json()["data"]["upload_id"]

    print("[测试] 步骤 1：上传图首次用于生成，绑定会话 A")
    _sample(client, token, client_request_id=_uid(), upload_ids=[upload_id])

    print("[测试] 步骤 2：在会话 B 中复用该上传图应返回 30006")
    session_id = _sse_events(
        _chat(client, token, client_message_id=_uid()).text
    )[0][1]["session_id"]
    response = _sample(
        client,
        token,
        client_request_id=_uid(),
        session_id=session_id,
        upload_ids=[upload_id],
    )
    assert response.status_code == 400
    assert response.json()["code"] == 30006
