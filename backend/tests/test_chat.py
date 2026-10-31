"""3 号 Agent 会话交互最小 demo 后端测试。

每一步都打印中文日志，便于定位失败步骤。
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select

LOGIN_URL = "/api/v1/auth/login"
SESSIONS_URL = "/api/v1/sessions"
UPLOADS_URL = "/api/v1/uploads"


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

    shutil.rmtree(settings.STORAGE_ROOT, ignore_errors=True)
    settings.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    yield


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
    return str(uuid.uuid4())


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
    width: int | None = 1000,
    height: int | None = 1000,
    upload_ids: list | None = None,
    session_id: int | None = None,
):
    url = SESSIONS_URL + ("/messages" if session_id is None else f"/{session_id}/messages")
    params = {
        "product_name": product_name,
        "style_text": style_text,
        "width": width,
        "height": height,
        "template_id": None,
    }
    if upload_ids is not None:
        params["upload_ids"] = upload_ids
    payload = {
        "client_message_id": client_message_id or _uid(),
        "content": content,
        "params": params,
    }
    if session_id is None:
        payload["session_id"] = None
    return client.post(url, headers=_headers(token), json=payload)


def _first_session(client, token: str, **kwargs) -> tuple[int, int, list[tuple[str, dict]]]:
    response = _chat(client, token, **kwargs)
    assert response.status_code == 200, response.text
    events = _sse_events(response.text)
    return events[0][1]["session_id"], events[0][1]["message_id"], events


def _user_id(db, username: str = "demo_user") -> int:
    from app.models import User

    return db.scalar(select(User.id).where(User.username == username))


def _confirmed_sample(
    db,
    *,
    user_id: int,
    session_id: int,
    style_text: str | None = "简洁白底",
    width: int = 1000,
    height: int = 1000,
    selling_points: list[str] | None = None,
    product_name: str = "秋季通勤衬衫",
):
    """直接写入一个已确认示例批次，供需求变化判定测试使用。"""
    from app.models import GenerationBatch

    summary = {
        "product_name": product_name,
        "category": None,
        "selling_points": selling_points or [],
        "target_audience": None,
        "scenes": [],
        "tone": None,
        "constraints": [],
    }
    batch = GenerationBatch(
        user_id=user_id,
        session_id=session_id,
        batch_type="sample",
        product_name=product_name,
        style_text=style_text,
        width=width,
        height=height,
        total_count=1,
        completed_count=1,
        status="confirmed",
        params_snapshot={},
        requirement_summary=summary,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def _messages(client, token: str, session_id: int) -> dict:
    response = client.get(f"{SESSIONS_URL}/{session_id}/messages", headers=_headers(token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ---------------------------------------------------------------------------
# 会话重命名
# ---------------------------------------------------------------------------


def test_rename_session_success_does_not_touch_last_message_at(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)

    from app.core.database import SessionLocal
    from app.models import CreativeSession

    with SessionLocal() as db:
        before = db.get(CreativeSession, session_id)
        before_last_message_at = before.last_message_at
        before_title = before.title

    print("[测试] 重命名会话：首尾空格应被去除")
    response = client.patch(
        f"{SESSIONS_URL}/{session_id}",
        headers=_headers(token),
        json={"title": "  秋季通勤衬衫  "},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["session_id"] == session_id
    assert data["title"] == "秋季通勤衬衫"
    assert data["status"] == "active"
    assert isinstance(data["updated_at"], str)

    print("[测试] 重命名不改消息、需求摘要与 last_message_at")
    with SessionLocal() as db:
        after = db.get(CreativeSession, session_id)
        assert after.title == "秋季通勤衬衫"
        assert after.title != before_title
        assert after.last_message_at == before_last_message_at


def test_rename_session_validation(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)
    url = f"{SESSIONS_URL}/{session_id}"

    cases = [
        ({}, 400, 10002, "请输入会话名称"),
        ({"title": None}, 400, 10002, "请输入会话名称"),
        ({"title": "   "}, 400, 10002, "请输入会话名称"),
        ({"title": "名" * 51}, 400, 10004, "会话名称不能超过 50 个字符"),
        ({"title": 123}, 400, 10003, "参数格式错误"),
        ({"title": "第一行\n第二行"}, 400, 10003, "参数格式错误"),
    ]
    for payload, status, code, message in cases:
        print(f"[测试] 重命名校验 {payload} -> {status}/{code}")
        response = client.patch(url, headers=_headers(token), json=payload)
        assert response.status_code == status, response.text
        assert response.json()["code"] == code
        assert response.json()["message"] == message

    print("[测试] 完全不传请求体 -> 10002")
    response = client.patch(url, headers=_headers(token))
    assert response.status_code == 400
    assert response.json()["code"] == 10002


def test_rename_session_permissions_and_ownership(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)
    url = f"{SESSIONS_URL}/{session_id}"

    print("[测试] 未登录 -> 401")
    assert client.patch(url, json={"title": "x"}).status_code == 401

    print("[测试] 管理员无 user.workspace -> 403/20005")
    admin_token = _login(client, "demo_admin")
    response = client.patch(url, headers=_headers(admin_token), json={"title": "x"})
    assert response.status_code == 403
    assert response.json()["code"] == 20005

    print("[测试] 他人会话 -> 404/30013")
    other_token = _login(client, "demo_dual")
    response = client.patch(url, headers=_headers(other_token), json={"title": "x"})
    assert response.status_code == 404
    assert response.json()["code"] == 30013

    print("[测试] 已隐藏会话 -> 404/30013")
    client.delete(url, headers=_headers(token))
    response = client.patch(url, headers=_headers(token), json={"title": "x"})
    assert response.status_code == 404
    assert response.json()["code"] == 30013


# ---------------------------------------------------------------------------
# 会话软删除
# ---------------------------------------------------------------------------


def test_delete_session_soft_hides_and_keeps_data(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)

    from app.core.database import SessionLocal
    from app.models import ChatMessage, CreativeSession

    with SessionLocal() as db:
        user_id = _user_id(db)
        _confirmed_sample(db, user_id=user_id, session_id=session_id)
        before = db.get(CreativeSession, session_id)
        before_last_message_at = before.last_message_at
        before_messages = db.scalar(
            select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session_id)
        )

    print("[测试] 软删除会话")
    response = client.delete(f"{SESSIONS_URL}/{session_id}", headers=_headers(token))
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"session_id": session_id, "status": "hidden"}

    print("[测试] 数据库中状态为 hidden，消息保留，last_message_at 不变")
    with SessionLocal() as db:
        session = db.get(CreativeSession, session_id)
        assert session.status == "hidden"
        assert session.last_message_at == before_last_message_at
        assert (
            db.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.session_id == session_id)
            )
            == before_messages
        )

    print("[测试] 会话列表不再展示该会话")
    items = client.get(SESSIONS_URL, headers=_headers(token)).json()["data"]["items"]
    assert all(item["session_id"] != session_id for item in items)

    print("[测试] 消息分页与继续聊天均返回 30013")
    assert client.get(
        f"{SESSIONS_URL}/{session_id}/messages", headers=_headers(token)
    ).json()["code"] == 30013
    assert _chat(client, token, session_id=session_id).status_code == 404

    print("[测试] 重复删除 -> 404/30013")
    again = client.delete(f"{SESSIONS_URL}/{session_id}", headers=_headers(token))
    assert again.status_code == 404
    assert again.json()["code"] == 30013


def test_delete_session_permissions(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)
    url = f"{SESSIONS_URL}/{session_id}"

    print("[测试] 未登录 -> 401")
    assert client.delete(url).status_code == 401

    print("[测试] 管理员 -> 403/20005")
    response = client.delete(url, headers=_headers(_login(client, "demo_admin")))
    assert response.status_code == 403
    assert response.json()["code"] == 20005

    print("[测试] 他人会话 -> 404/30013")
    response = client.delete(url, headers=_headers(_login(client, "demo_dual")))
    assert response.status_code == 404
    assert response.json()["code"] == 30013


def test_session_list_preview_strips_newlines_and_truncates(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)

    from app.core.database import SessionLocal
    from app.models import ChatMessage

    content = "  第一行\n第二行\r\n" + "长" * 40
    print("[测试] 写入带换行与首尾空格的最后一条消息")
    with SessionLocal() as db:
        db.add(
            ChatMessage(
                session_id=session_id,
                role="system",
                content=content,
                content_type="text",
                status="done",
            )
        )
        db.commit()

    items = client.get(SESSIONS_URL, headers=_headers(token)).json()["data"]["items"]
    item = next(item for item in items if item["session_id"] == session_id)
    preview = item["last_message_preview"]
    assert "\n" not in preview and "\r" not in preview
    assert preview == ("第一行第二行" + "长" * 40)[:30]


# ---------------------------------------------------------------------------
# 消息分页与惰性超时
# ---------------------------------------------------------------------------


def test_message_pagination_marks_stale_sending_assistant_failed(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)

    from app.core.database import SessionLocal
    from app.models import ChatMessage

    stale_at = datetime.now(timezone.utc) - timedelta(seconds=121)
    print("[测试] 直接写入超时的 sending Agent 消息与未超时的用户消息")
    with SessionLocal() as db:
        stale_assistant = ChatMessage(
            session_id=session_id,
            role="assistant",
            agent_code="product_understanding",
            content="未完成回复",
            content_type="text",
            status="sending",
            created_at=stale_at,
        )
        fresh_user = ChatMessage(
            session_id=session_id,
            role="user",
            content="未超时的用户消息",
            content_type="text",
            status="sending",
            created_at=datetime.now(timezone.utc),
        )
        db.add_all([stale_assistant, fresh_user])
        db.commit()
        stale_id = stale_assistant.id
        fresh_id = fresh_user.id

    data = _messages(client, token, session_id)
    statuses = {item["message_id"]: item["status"] for item in data["items"]}
    assert statuses[stale_id] == "failed", "超过 120 秒的 sending Agent 消息应被惰性标记为 failed"
    assert statuses[fresh_id] == "sending", "用户消息不参与超时标记"


def test_duplicate_request_with_stale_sending_reuses_assistant(client):
    token = _login(client)
    session_id, assistant_id, _ = _first_session(client, token)
    key = _uid()

    from app.core.database import SessionLocal
    from app.models import ChatMessage, CreativeSession

    print("[测试] 构造一条 121 秒前仍为 sending 的用户消息与 Agent 回复")
    stale_at = datetime.now(timezone.utc) - timedelta(seconds=121)
    with SessionLocal() as db:
        session = db.get(CreativeSession, session_id)
        user_message = ChatMessage(
            session_id=session_id,
            role="user",
            content="旧请求",
            content_type="text",
            client_message_id=key,
            status="done",
            created_at=stale_at,
        )
        db.add(user_message)
        db.flush()
        assistant = ChatMessage(
            session_id=session_id,
            role="assistant",
            agent_code="product_understanding",
            content="",
            content_type="text",
            status="sending",
            created_at=stale_at,
        )
        db.add(assistant)
        session.last_message_at = stale_at
        db.commit()
        user_id, assistant_id = user_message.id, assistant.id

    print("[测试] 相同 client_message_id 重试：超时应按失败处理并复用原回复消息")
    response = _chat(client, token, client_message_id=key, session_id=session_id)
    assert response.status_code == 200, response.text
    events = _sse_events(response.text)
    assert events[0][1]["message_id"] == assistant_id
    assert events[-1][0] == "done"

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.role == "user", ChatMessage.client_message_id == key)) == 1
        assert db.get(ChatMessage, assistant_id).status == "done"
        assert db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.role == "assistant", ChatMessage.session_id == session_id)) == 2


# ---------------------------------------------------------------------------
# SSE 幂等、重放与失败重试
# ---------------------------------------------------------------------------


def test_meta_duplicate_and_replay_requirement_changed(client):
    token = _login(client)
    key = _uid()
    session_id, assistant_id, first_events = _first_session(
        client, token, client_message_id=key
    )
    first_done = first_events[-1][1]
    assert first_events[0][1]["duplicate"] is False
    assert isinstance(first_done["requirement_changed"], bool)

    print("[测试] 相同幂等键重放：meta.duplicate=true，一条 delta + done")
    replay = _chat(client, token, client_message_id=key, session_id=session_id)
    assert replay.status_code == 200
    replay_events = _sse_events(replay.text)
    assert [name for name, _ in replay_events] == ["meta", "delta", "done"]
    assert replay_events[0][1]["duplicate"] is True
    assert replay_events[0][1]["message_id"] == assistant_id
    assert refresh_delta(replay_events) == refresh_delta(first_events)
    assert isinstance(replay_events[-1][1]["requirement_changed"], bool)


def refresh_delta(events: list[tuple[str, dict]]) -> str:
    return "".join(data["content"] for name, data in events if name == "delta")


def test_failed_assistant_is_reused_without_new_messages(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)
    key = _uid()

    from app.core.database import SessionLocal
    from app.models import ChatMessage

    print("[测试] 构造一条失败的用户消息 + Agent 回复")
    with SessionLocal() as db:
        user_message = ChatMessage(
            session_id=session_id,
            role="user",
            content="失败后重试",
            content_type="text",
            client_message_id=key,
            status="done",
        )
        db.add(user_message)
        db.flush()
        assistant = ChatMessage(
            session_id=session_id,
            role="assistant",
            agent_code="product_understanding",
            content="",
            content_type="text",
            status="failed",
        )
        db.add(assistant)
        db.commit()
        assistant_id = assistant.id

    print("[测试] 相同幂等键重试：复用原 Agent 回复消息，不新增用户/回复消息")
    response = _chat(client, token, client_message_id=key, session_id=session_id)
    assert response.status_code == 200, response.text
    events = _sse_events(response.text)
    assert events[0][1]["message_id"] == assistant_id
    assert events[0][1]["duplicate"] is False

    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.session_id == session_id, ChatMessage.role == "user")
            )
            == 2
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
            )
            == 2
        )
        reused = db.get(ChatMessage, assistant_id)
        assert reused.status == "done"
        assert reused.content != ""


def test_failed_retry_targets_its_own_reply_not_later_message(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)
    key_a = _uid()

    from app.core.database import SessionLocal
    from app.models import ChatMessage

    stale_at = datetime.now(timezone.utc) - timedelta(seconds=121)
    print("[测试] 构造：用户消息 A 失败，随后用户消息 B 成功")
    with SessionLocal() as db:
        user_a = ChatMessage(
            session_id=session_id,
            role="user",
            content="A 失败消息",
            content_type="text",
            client_message_id=key_a,
            status="done",
            created_at=stale_at,
        )
        db.add(user_a)
        db.flush()
        assistant_a = ChatMessage(
            session_id=session_id,
            role="assistant",
            agent_code="product_understanding",
            content="",
            content_type="text",
            status="failed",
            created_at=stale_at,
        )
        db.add(assistant_a)
        db.flush()
        user_b = ChatMessage(
            session_id=session_id,
            role="user",
            content="B 成功消息",
            content_type="text",
            client_message_id=_uid(),
            status="done",
        )
        db.add(user_b)
        db.flush()
        assistant_b = ChatMessage(
            session_id=session_id,
            role="assistant",
            agent_code="product_understanding",
            content="B 的回复",
            content_type="text",
            status="done",
        )
        db.add(assistant_b)
        db.commit()
        assistant_a_id = assistant_a.id
        assistant_b_id = assistant_b.id
        old_created_at = assistant_a.created_at

    print("[测试] 用 A 的幂等键重试，应只重试 A 的回复，不重放/覆盖 B")
    response = _chat(client, token, client_message_id=key_a, session_id=session_id)
    assert response.status_code == 200, response.text
    events = _sse_events(response.text)
    assert events[0][1]["message_id"] == assistant_a_id
    assert events[0][1]["duplicate"] is False

    with SessionLocal() as db:
        retried = db.get(ChatMessage, assistant_a_id)
        later = db.get(ChatMessage, assistant_b_id)
        assert retried.status == "done" and retried.content != ""
        assert retried.created_at > old_created_at, "重试应刷新处理时钟，避免被超时规则立即标记失败"
        assert later.status == "done" and later.content == "B 的回复"


def test_replay_returns_saved_summary_not_current_summary(client):
    token = _login(client)
    key = _uid()
    session_id, assistant_id, first_events = _first_session(
        client, token, client_message_id=key
    )
    saved_summary = first_events[-1][1]["requirement_summary"]

    from app.core.database import SessionLocal
    from app.models import CreativeSession

    print("[测试] 后续对话把会话摘要改掉，但不修改历史消息")
    with SessionLocal() as db:
        session = db.get(CreativeSession, session_id)
        changed = dict(session.requirement_summary or {})
        changed["selling_points"] = ["防水"]
        changed["tone"] = "专业"
        session.requirement_summary = changed
        db.commit()

    print("[测试] 重放应返回该条回复保存时的摘要，而不是当前会话摘要")
    replay = _chat(client, token, client_message_id=key, session_id=session_id)
    events = _sse_events(replay.text)
    assert events[0][1]["duplicate"] is True
    assert events[-1][1]["requirement_summary"] == saved_summary
    assert events[-1][1]["requirement_summary"]["selling_points"] == []


def test_first_message_same_key_returns_same_session(client):
    token = _login(client)
    key = _uid()
    print("[测试] 步骤 1：首条消息建会话")
    session_id, assistant_id, _ = _first_session(client, token, client_message_id=key)

    print("[测试] 步骤 2：相同 client_message_id 再次发送，应返回同一会话与回复")
    again = _chat(client, token, client_message_id=key)
    events = _sse_events(again.text)
    assert events[0][1]["session_id"] == session_id
    assert events[0][1]["message_id"] == assistant_id
    assert events[0][1]["duplicate"] is True


def test_hidden_session_first_message_key_creates_new_session(client):
    token = _login(client)
    key = _uid()
    print("[测试] 步骤 1：首条消息建会话并软删除")
    session_id, _, _ = _first_session(client, token, client_message_id=key)
    delete = client.delete(f"{SESSIONS_URL}/{session_id}", headers=_headers(token))
    assert delete.status_code == 200

    print("[测试] 步骤 2：相同 client_message_id 不带 session_id 重试，不应重放已隐藏会话")
    again = _chat(client, token, client_message_id=key)
    assert again.status_code == 200, again.text
    new_session_id = _sse_events(again.text)[0][1]["session_id"]
    assert new_session_id != session_id

    from app.core.database import SessionLocal
    from app.models import CreativeSession

    with SessionLocal() as db:
        assert db.get(CreativeSession, session_id).status == "hidden"
        assert db.get(CreativeSession, new_session_id).status == "active"


# ---------------------------------------------------------------------------
# 需求变化判定
# ---------------------------------------------------------------------------


def test_requirement_changed_by_style_size_and_selling_points(client):
    token = _login(client)
    session_id, _, first_events = _first_session(client, token)
    assert first_events[-1][1]["requirement_changed"] is False, "没有已确认示例批次时应为 false"

    from app.core.database import SessionLocal
    from app.models import CreativeSession

    print("[测试] 写入已确认示例批次与匹配的需求摘要")
    with SessionLocal() as db:
        user_id = _user_id(db)
        _confirmed_sample(
            db,
            user_id=user_id,
            session_id=session_id,
            style_text="简洁白底",
            width=1000,
            height=1000,
            selling_points=["轻便"],
        )
        session = db.get(CreativeSession, session_id)
        summary = dict(session.requirement_summary or {})
        summary.update({"product_name": "秋季通勤衬衫", "selling_points": ["轻便"]})
        session.requirement_summary = summary
        db.commit()

    print("[测试] 风格与尺寸都匹配 -> requirement_changed=false")
    same = _chat(client, token, session_id=session_id, style_text="简洁白底", width=1000, height=1000)
    same_done = _sse_events(same.text)[-1][1]
    assert same_done["requirement_changed"] is False

    print("[测试] 风格变化 -> requirement_changed=true")
    style_changed = _chat(
        client, token, session_id=session_id, style_text="生活场景", width=1000, height=1000
    )
    style_done = _sse_events(style_changed.text)[-1][1]
    assert style_done["requirement_changed"] is True
    assert style_done["requirement_summary"]["product_name"] == "秋季通勤衬衫"

    print("[测试] 尺寸变化 -> requirement_changed=true")
    size_changed = _chat(
        client, token, session_id=session_id, style_text="简洁白底", width=1200, height=1000
    )
    assert _sse_events(size_changed.text)[-1][1]["requirement_changed"] is True

    print("[测试] 卖点集合变化 -> requirement_changed=true（去空格、去重、忽略顺序）")
    with SessionLocal() as db:
        session = db.get(CreativeSession, session_id)
        summary = dict(session.requirement_summary or {})
        summary["selling_points"] = ["防水 ", "轻便", "防水"]
        session.requirement_summary = summary
        db.commit()
    points_changed = _chat(
        client, token, session_id=session_id, style_text="简洁白底", width=1000, height=1000
    )
    assert _sse_events(points_changed.text)[-1][1]["requirement_changed"] is True

    print("[测试] 重复请求重放时按当前状态重新计算 requirement_changed")
    replay_key = _uid()
    changed = _chat(
        client,
        token,
        client_message_id=replay_key,
        session_id=session_id,
        style_text="国潮",
        width=1000,
        height=1000,
    )
    replay = _chat(
        client,
        token,
        client_message_id=replay_key,
        session_id=session_id,
        style_text="国潮",
        width=1000,
        height=1000,
    )
    assert _sse_events(replay.text)[0][1]["duplicate"] is True
    assert _sse_events(replay.text)[-1][1]["requirement_changed"] is True


# ---------------------------------------------------------------------------
# 上下文窗口与需求摘要
# ---------------------------------------------------------------------------


def test_context_keeps_last_10_rounds_and_omission_note(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token, content="第 1 轮")
    for index in range(2, 13):
        response = _chat(
            client,
            token,
            session_id=session_id,
            content=f"第 {index} 轮",
            client_message_id=_uid(),
        )
        assert response.status_code == 200, response.text

    from app.core.database import SessionLocal
    from app.models import AgentRun, ChatMessage

    print("[测试] 第 12 轮上下文只保留最近 10 轮，并注入省略说明")
    with SessionLocal() as db:
        run = db.scalar(
            select(AgentRun)
            .where(AgentRun.session_id == session_id, AgentRun.agent_code == "planner")
            .order_by(AgentRun.id.desc())
            .limit(1)
        )
        context = json.loads(run.input_full)
        assert context["omitted"] is True
        assert context["system_note"] == "更早的对话已省略，需求摘要以当前 requirement_summary 为准"
        user_turns = [item["content"] for item in context["messages"] if item["role"] == "user"]
        assert len(user_turns) == 10
        assert "第 1 轮" not in user_turns
        assert user_turns[-1] == "第 12 轮"

        print("[测试] 省略说明只进入本次上下文，不写入 chat_messages")
        contents = list(db.scalars(select(ChatMessage.content).where(ChatMessage.session_id == session_id)))
        assert all("更早的对话已省略" not in (content or "") for content in contents)


def test_requirement_summary_preserves_existing_fields(client):
    token = _login(client)
    session_id, _, _ = _first_session(client, token)

    from app.core.database import SessionLocal
    from app.models import CreativeSession

    print("[测试] 步骤 1：预置已有需求摘要字段")
    with SessionLocal() as db:
        session = db.get(CreativeSession, session_id)
        session.requirement_summary = {
            "product_name": "旧名称",
            "category": "衬衫",
            "selling_points": ["轻便"],
            "target_audience": "通勤女性",
            "scenes": ["通勤"],
            "tone": "专业",
            "constraints": ["不要夸张"],
        }
        db.commit()

    print("[测试] 步骤 2：再聊一轮，未返回字段应保留")
    response = _chat(client, token, session_id=session_id, product_name="秋季通勤衬衫")
    done = _sse_events(response.text)[-1][1]
    summary = done["requirement_summary"]
    assert summary["product_name"] == "秋季通勤衬衫"
    assert summary["category"] == "衬衫"
    assert summary["selling_points"] == ["轻便"]
    assert summary["target_audience"] == "通勤女性"
    assert summary["scenes"] == ["通勤"]
    assert summary["tone"] == "专业"
    assert summary["constraints"] == ["不要夸张"]


def test_agent_runs_include_context_and_token_fields(client):
    token = _login(client)
    session_id, assistant_id, _ = _first_session(client, token)

    from app.core.database import SessionLocal
    from app.models import AgentRun

    print("[测试] 每次回复写入规划与商品理解两条调用明细")
    with SessionLocal() as db:
        runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.session_id == session_id, AgentRun.message_id == assistant_id)
                .order_by(AgentRun.id.asc())
            )
        )
    assert [run.agent_code for run in runs] == ["planner", "product_understanding"]
    for run in runs:
        assert run.status == "success"
        assert run.prompt_tokens == 0 and run.completion_tokens == 0
        assert run.latency_ms is not None
        assert run.input_full and run.output_full
        json.loads(run.input_full)


def test_chat_uses_real_model_when_configured(client, monkeypatch):
    from app.core.config import settings
    from app.modules.chat import model as chat_model
    from tests.chat_model_fakes import FakeClient

    print("[测试] 配置真实模型（假客户端），验证 SSE、Token 与 agent_runs")
    monkeypatch.setattr(settings, "ARK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ARK_TEXT_MODEL", "test-model")
    monkeypatch.setattr(settings, "CHAT_USE_STUB", False)
    fake = FakeClient()
    monkeypatch.setattr(chat_model, "_client", lambda: fake)

    token = _login(client)
    response = _chat(client, token, content="你好", client_message_id=_uid())
    assert response.status_code == 200, response.text
    events = _sse_events(response.text)
    assert "".join(data["content"] for name, data in events if name == "delta") == "已了解商品。"
    done = events[-1][1]
    assert done["token_in"] == 30 and done["token_out"] == 35
    assert done["requirement_summary"]["selling_points"] == ["轻便"]

    session_id = events[0][1]["session_id"]
    from app.core.database import SessionLocal
    from app.models import AgentRun, ChatMessage

    with SessionLocal() as db:
        runs = list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.session_id == session_id)
                .order_by(AgentRun.id.asc())
            )
        )
        assert [run.agent_code for run in runs] == ["planner", "product_understanding"]
        assert all(run.model_name == "test-model" for run in runs)
        assert (runs[0].prompt_tokens, runs[0].completion_tokens) == (10, 5)
        assert (runs[1].prompt_tokens, runs[1].completion_tokens) == (20, 30)
        assistant = db.get(ChatMessage, done["message_id"])
        assert assistant.content == "已了解商品。"
        assert assistant.token_in == 30 and assistant.token_out == 35


# ---------------------------------------------------------------------------
# 上传图参数校验
# ---------------------------------------------------------------------------


def test_chat_upload_ids_validation(client):
    from io import BytesIO

    from PIL import Image

    def png() -> bytes:
        buffer = BytesIO()
        Image.new("RGB", (120, 120), (80, 120, 200)).save(buffer, format="PNG")
        return buffer.getvalue()

    token = _login(client)
    upload = client.post(
        UPLOADS_URL,
        headers=_headers(token),
        files={"file": ("shirt.png", png(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    upload_id = upload.json()["data"]["upload_id"]

    print("[测试] 使用自己的 active 上传图 -> 成功")
    ok_response = _chat(client, token, upload_ids=[upload_id])
    assert ok_response.status_code == 200, ok_response.text

    print("[测试] 超过 5 张上传图 -> 30006")
    too_many = _chat(client, token, upload_ids=[1, 2, 3, 4, 5, 6])
    assert too_many.status_code == 400
    assert too_many.json()["code"] == 30006

    print("[测试] 使用他人上传图 -> 30006")
    other_token = _login(client, "demo_dual")
    other_upload = client.post(
        UPLOADS_URL,
        headers=_headers(other_token),
        files={"file": ("other.png", png(), "image/png")},
    ).json()["data"]["upload_id"]
    foreign = _chat(client, token, upload_ids=[other_upload])
    assert foreign.status_code == 400
    assert foreign.json()["code"] == 30006

    print("[测试] 已删除上传图 -> 30006")
    client.delete(f"{UPLOADS_URL}/{upload_id}", headers=_headers(token))
    deleted = _chat(client, token, upload_ids=[upload_id])
    assert deleted.status_code == 400
    assert deleted.json()["code"] == 30006

    print("[测试] upload_ids 类型错误 -> 10003")
    invalid = _chat(client, token, upload_ids=["abc"])
    assert invalid.status_code == 400
    assert invalid.json()["code"] == 10003


# ---------------------------------------------------------------------------
# 聊天不触发生成
# ---------------------------------------------------------------------------


def test_chat_does_not_create_generation_batch(client):
    token = _login(client)
    print("[测试] 步骤 1：发送一条聊天消息")
    _first_session(client, token)

    print("[测试] 步骤 2：确认聊天没有创建任何生成批次")
    from app.core.database import SessionLocal
    from app.models import GenerationBatch

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GenerationBatch)) == 0


# ---------------------------------------------------------------------------
# SSE 心跳
# ---------------------------------------------------------------------------


def test_heartbeat_wrapper_emits_ping_during_idle():
    from app.modules.chat.stream import with_heartbeat

    def slow_events():
        yield "event: meta\ndata: {}\n\n"
        time.sleep(0.06)
        yield "event: done\ndata: {}\n\n"

    print("[测试] 生成过程中空闲超过心跳间隔时输出 ping")
    output = "".join(with_heartbeat(slow_events(), interval=0.01))
    assert "event: ping" in output
    assert output.index("event: meta") < output.index("event: ping") < output.index("event: done")
