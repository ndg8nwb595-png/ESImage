"""8 号管理后台-聊天记录最小 demo 后端测试。

覆盖：会话列表与筛选、会话详情与消息窗口、Agent 调用明细、消息搜索、
模型配置读取/保存、系统提示词版本与回滚。每一步输出中文日志。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

LOGIN_URL = "/api/v1/auth/login"
SESSIONS_URL = "/api/v1/admin/chat/sessions"
SEARCH_URL = "/api/v1/admin/chat/messages/search"
MODEL_CONFIG_URL = "/api/v1/admin/model-config"
PROMPTS_URL = "/api/v1/admin/prompts"
DEMO_PASSWORD = "Demo1234"


def _login(client, username: str) -> str:
    print(f"[测试] 登录 {username}")
    response = client.post(
        LOGIN_URL,
        json={"username": username, "password": DEMO_PASSWORD, "remember_me": False},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sessions(client, token: str, **params) -> dict:
    response = client.get(SESSIONS_URL, headers=_headers(token), params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def _session_by_title(client, token: str, title: str) -> dict:
    data = _sessions(client, token, page_size=50)
    for item in data["items"]:
        if item["title"] == title:
            return item
    raise AssertionError(f"未找到会话：{title}")


def _detail(client, token: str, session_id: int, **params) -> dict:
    response = client.get(
        f"{SESSIONS_URL}/{session_id}", headers=_headers(token), params=params
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _error(response, status_code: int, code: int) -> None:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert body["code"] == code, body
    assert body["data"] is None, body


def test_session_list_visibility_and_aggregates(client):
    """管理员只看非超管会话；超管看全部；聚合字段与排序正确。"""
    print("[测试] 校验会话列表可见范围")
    admin = _login(client, "demo_admin")
    super_token = _login(client, "demo_super")

    admin_data = _sessions(client, admin, page_size=50)
    titles = [item["title"] for item in admin_data["items"]]
    assert admin_data["total"] == 3, titles
    assert set(titles) == {"秋季通勤衬衫", "夏季防晒外套", "通勤鞋搭配建议"}
    assert "超管测试会话" not in titles
    # 排序：最后消息时间倒序（秋季 120 分钟、通勤鞋 180 分钟、夏季 1 天）
    assert titles[0] == "秋季通勤衬衫"
    assert titles[-1] == "夏季防晒外套"

    autumn = _session_by_title(client, admin, "秋季通勤衬衫")
    assert autumn["user"]["username"] == "demo_user"
    assert autumn["message_count"] == 12
    assert autumn["batch_count"] == 2
    assert autumn["status"] == "active"
    assert autumn["token_usage"]["total_tokens"] == (
        autumn["token_usage"]["prompt_tokens"]
        + autumn["token_usage"]["completion_tokens"]
    )
    assert autumn["token_usage"]["total_tokens"] > 0

    super_data = _sessions(client, super_token, page_size=50)
    assert super_data["total"] == 4
    assert "超管测试会话" in [item["title"] for item in super_data["items"]]

    print("[测试] 普通用户访问会话列表应 403")
    user_token = _login(client, "demo_user")
    _error(
        client.get(SESSIONS_URL, headers=_headers(user_token)),
        403,
        20005,
    )


def test_session_list_filters_and_validation(client):
    """关键词、状态、日期与分页校验。"""
    print("[测试] 校验会话筛选与参数错误")
    token = _login(client, "demo_admin")

    assert _sessions(client, token, title_keyword="衬衫")["total"] == 1
    assert _sessions(client, token, user_keyword="demo_user")["total"] == 3
    assert _sessions(client, token, user_keyword="演示用户")["total"] == 3
    assert _sessions(client, token, status="hidden")["total"] == 1
    assert _sessions(client, token, status="active")["total"] == 2
    # 空字符串参数按未提供处理
    assert _sessions(client, token, status="")["total"] == 3
    assert _sessions(client, token, page_size=100)["page_size"] == 100
    # 通配符必须被转义，不能变成“匹配全部”
    assert _sessions(client, token, title_keyword="%")["total"] == 0

    # 日期范围：种子会话都在最近 2 天内；未来/过早区间应为空
    today = datetime.now(timezone.utc).astimezone().date()
    recent = _sessions(
        client,
        token,
        last_message_from=str(today - timedelta(days=2)),
        last_message_to=str(today + timedelta(days=1)),
    )
    assert recent["total"] == 3
    assert (
        _sessions(client, token, last_message_from=str(today + timedelta(days=1)))[
            "total"
        ]
        == 0
    )
    assert (
        _sessions(client, token, last_message_to=str(today - timedelta(days=3)))[
            "total"
        ]
        == 0
    )

    _error(
        client.get(SESSIONS_URL, headers=_headers(token), params={"status": "bad"}),
        400,
        10003,
    )
    _error(
        client.get(SESSIONS_URL, headers=_headers(token), params={"page_size": 30}),
        400,
        10004,
    )
    _error(
        client.get(
            SESSIONS_URL,
            headers=_headers(token),
            params={"last_message_from": "2026-12-01", "last_message_to": "2026-11-01"},
        ),
        400,
        10004,
    )
    _error(
        client.get(
            SESSIONS_URL,
            headers=_headers(token),
            params={"last_message_from": "bad-date"},
        ),
        400,
        10003,
    )


def test_session_detail_window_and_errors(client):
    """消息正序、Agent 名称、关联批次、游标与锚点。"""
    print("[测试] 校验会话详情消息窗口")
    token = _login(client, "demo_admin")
    autumn = _session_by_title(client, token, "秋季通勤衬衫")

    data = _detail(client, token, autumn["session_id"])
    messages = data["messages"]
    assert len(messages) == 12
    assert [message["message_id"] for message in messages] == sorted(
        message["message_id"] for message in messages
    )
    assert data["has_older"] is False
    assert data["has_newer"] is False
    assert data["anchor_message_id"] is None
    assert data["session"]["message_count"] == 12

    assistant_messages = [m for m in messages if m["role"] == "assistant"]
    assert assistant_messages and all(m["agent_name"] for m in assistant_messages)
    assert any(m["agent_runs"] for m in assistant_messages)
    assert any(m["related_batches"] for m in assistant_messages)
    run_statuses = {
        run["status"] for m in messages for run in m["agent_runs"]
    }
    assert {"success", "failed", "skipped"} <= run_statuses
    batch = next(
        batch
        for m in messages
        for batch in m["related_batches"]
        if batch["batch_type"] == "sample"
    )
    assert batch["product_name"] == "秋季通勤衬衫"

    print("[测试] 校验 before_id / around_id / 参数冲突")
    last_id = messages[-1]["message_id"]
    older = _detail(client, token, autumn["session_id"], before_id=last_id, limit=5)
    assert len(older["messages"]) == 5
    assert older["has_older"] is True
    assert older["has_newer"] is True

    anchor_id = messages[5]["message_id"]
    around = _detail(client, token, autumn["session_id"], around_id=anchor_id, limit=5)
    assert around["anchor_message_id"] == anchor_id
    assert len(around["messages"]) <= 5
    assert anchor_id in [m["message_id"] for m in around["messages"]]

    # 锚点靠前时，用实际取到的更早条数补齐更新消息，总数应达到 limit
    early_anchor = messages[2]["message_id"]
    near_start = _detail(
        client, token, autumn["session_id"], around_id=early_anchor, limit=10
    )
    assert near_start["anchor_message_id"] == early_anchor
    assert len(near_start["messages"]) == 10
    assert near_start["messages"][0]["message_id"] < early_anchor
    assert any(
        message["message_id"] > early_anchor for message in near_start["messages"]
    )

    _error(
        client.get(
            f"{SESSIONS_URL}/{autumn['session_id']}",
            headers=_headers(token),
            params={"before_id": last_id, "around_id": anchor_id},
        ),
        400,
        10001,
    )
    _error(
        client.get(
            f"{SESSIONS_URL}/{autumn['session_id']}",
            headers=_headers(token),
            params={"limit": 51},
        ),
        400,
        10004,
    )
    _error(
        client.get(
            f"{SESSIONS_URL}/{autumn['session_id']}",
            headers=_headers(token),
            params={"before_id": 0},
        ),
        400,
        10003,
    )
    _error(
        client.get(
            f"{SESSIONS_URL}/{autumn['session_id']}",
            headers=_headers(token),
            params={"around_id": 99999999},
        ),
        404,
        30023,
    )
    _error(
        client.get(f"{SESSIONS_URL}/99999999", headers=_headers(token)),
        404,
        30013,
    )

    print("[测试] 管理员访问超管会话应 403")
    super_token = _login(client, "demo_super")
    super_session = _session_by_title(client, super_token, "超管测试会话")
    _error(
        client.get(
            f"{SESSIONS_URL}/{super_session['session_id']}",
            headers=_headers(token),
        ),
        403,
        20005,
    )


def test_agent_run_detail_and_full_content(client):
    """Agent 调用摘要、完整输入输出权限与错误码。"""
    print("[测试] 校验 Agent 调用明细")
    admin = _login(client, "demo_admin")
    super_token = _login(client, "demo_super")
    autumn = _session_by_title(client, admin, "秋季通勤衬衫")
    detail = _detail(client, admin, autumn["session_id"])
    run = next(
        run for message in detail["messages"] for run in message["agent_runs"]
    )

    response = client.get(
        f"/api/v1/admin/agent-runs/{run['run_id']}", headers=_headers(admin)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["run_id"] == run["run_id"]
    assert data["agent_name"]
    assert data["token_usage"]["total_tokens"] == (
        data["token_usage"]["prompt_tokens"]
        + data["token_usage"]["completion_tokens"]
    )
    assert data["full_available"] is False
    assert data["input_full"] is None
    assert data["output_full"] is None
    assert "image_id" in data

    _error(
        client.get(
            f"/api/v1/admin/agent-runs/{run['run_id']}",
            headers=_headers(admin),
            params={"full": "true"},
        ),
        403,
        20005,
    )

    print("[测试] 超管可查看完整输入/输出，且不含明文 Key")
    super_response = client.get(
        f"/api/v1/admin/agent-runs/{run['run_id']}",
        headers=_headers(super_token),
        params={"full": "true"},
    )
    assert super_response.status_code == 200, super_response.text
    super_data = super_response.json()["data"]
    assert super_data["full_available"] is True
    assert super_data["input_full"] is not None
    assert super_data["output_full"] is not None
    assert "[REDACTED]" in super_data["input_full"]
    assert "sk-" not in super_data["input_full"]
    assert "sk-" not in json.dumps(super_data, ensure_ascii=False)

    no_full = client.get(
        f"/api/v1/admin/agent-runs/{run['run_id']}", headers=_headers(super_token)
    ).json()["data"]
    assert no_full["input_full"] is None
    assert no_full["output_full"] is None

    _error(
        client.get("/api/v1/admin/agent-runs/99999999", headers=_headers(super_token)),
        404,
        30020,
    )

    print("[测试] 管理员访问超管会话下的调用应 403")
    super_session = _session_by_title(client, super_token, "超管测试会话")
    super_detail = _detail(client, super_token, super_session["session_id"])
    super_run = next(
        run for message in super_detail["messages"] for run in message["agent_runs"]
    )
    _error(
        client.get(
            f"/api/v1/admin/agent-runs/{super_run['run_id']}",
            headers=_headers(admin),
        ),
        403,
        20005,
    )


def test_message_search_scope_and_snippet(client):
    """搜索大小写、可见范围、摘要与参数校验。"""
    print("[测试] 校验消息搜索")
    admin = _login(client, "demo_admin")
    super_token = _login(client, "demo_super")

    response = client.get(
        SEARCH_URL, headers=_headers(admin), params={"keyword": "衬衫"}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] >= 1
    assert data["page_size"] == 20
    assert all("衬衫" in item["snippet"] for item in data["items"])
    item = data["items"][0]
    for field in (
        "message_id",
        "session_id",
        "session_title",
        "session_status",
        "user",
        "role",
        "agent_code",
        "agent_name",
        "snippet",
        "created_at",
    ):
        assert field in item, field
    # 结果按消息时间倒序
    times = [item["created_at"] for item in data["items"]]
    assert times == sorted(times, reverse=True)

    # 大小写不敏感
    lower = client.get(
        SEARCH_URL, headers=_headers(admin), params={"keyword": "t-shirt"}
    ).json()["data"]
    assert lower["total"] >= 1

    # 超管可见超管会话，管理员不可见
    super_result = client.get(
        SEARCH_URL, headers=_headers(super_token), params={"keyword": "超管"}
    ).json()["data"]
    assert super_result["total"] >= 1
    admin_result = client.get(
        SEARCH_URL, headers=_headers(admin), params={"keyword": "超管"}
    ).json()["data"]
    assert admin_result["total"] == 0

    # 通配符转义
    assert (
        client.get(
            SEARCH_URL, headers=_headers(admin), params={"keyword": "%"}
        ).json()["data"]["total"]
        == 0
    )

    _error(client.get(SEARCH_URL, headers=_headers(admin)), 400, 10002)
    _error(
        client.get(SEARCH_URL, headers=_headers(admin), params={"keyword": "   "}),
        400,
        10002,
    )
    _error(
        client.get(
            SEARCH_URL, headers=_headers(admin), params={"keyword": "字" * 101}
        ),
        400,
        10004,
    )
    _error(
        client.get(
            SEARCH_URL, headers=_headers(admin), params={"keyword": "衬衫", "page": 0}
        ),
        400,
        10003,
    )


def test_model_config_permissions_validation_and_audit(client):
    """模型配置仅超管可读写；校验、脱敏与审计。"""
    print("[测试] 校验模型配置权限")
    admin = _login(client, "demo_admin")
    super_token = _login(client, "demo_super")
    _error(client.get(MODEL_CONFIG_URL, headers=_headers(admin)), 403, 20005)

    current = client.get(MODEL_CONFIG_URL, headers=_headers(super_token))
    assert current.status_code == 200, current.text
    current_data = current.json()["data"]
    assert current_data["provider"] == "volcengine_ark"
    assert current_data["provider_label"] == "豆包（火山方舟）"
    assert "api_key_masked" in current_data

    valid_payload = {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key": "sk-demo-12345678",
        "text_model": "doubao-demo-text",
        "image_model": "doubao-demo-image",
        "vision_model": None,
        "temperature": 0.8,
        "timeout_seconds": 90,
        "concurrency": 2,
        "retry_count": 2,
        "max_context_tokens": 4000,
    }

    print("[测试] 校验模型配置参数错误")
    for field, value, expected in (
        ("temperature", 2.5, 10004),
        ("temperature", 0.75, 10003),
        ("timeout_seconds", 10, 10004),
        ("concurrency", 0, 10004),
        ("retry_count", 4, 10004),
        ("max_context_tokens", 1000, 10004),
        ("text_model", "", 10002),
        ("base_url", "ftp://example.com", 10003),
        ("api_key", "k" * 513, 10003),
    ):
        payload = dict(valid_payload)
        payload[field] = value
        _error(
            client.put(MODEL_CONFIG_URL, headers=_headers(super_token), json=payload),
            400,
            expected,
        )
    missing = dict(valid_payload)
    missing.pop("text_model")
    _error(
        client.put(MODEL_CONFIG_URL, headers=_headers(super_token), json=missing),
        400,
        10002,
    )
    _error(
        client.put(
            MODEL_CONFIG_URL,
            headers=_headers(super_token),
            json={**valid_payload, "provider": "other"},
        ),
        400,
        10001,
    )

    print("[测试] 保存模型配置并校验脱敏")
    response = client.put(
        MODEL_CONFIG_URL, headers=_headers(super_token), json=valid_payload
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["api_key_configured"] is True
    assert data["api_key_masked"] == "sk-****5678"
    assert "sk-demo-12345678" not in response.text
    assert data["temperature"] == 0.8
    assert data["timeout_seconds"] == 90
    assert data["concurrency"] == 2
    assert data["retry_count"] == 2
    assert data["max_context_tokens"] == 4000
    assert data["updated_by"]["username"] == "demo_super"

    print("[测试] 校验模型配置审计日志")
    audit = client.get(
        "/api/v1/admin/audit-logs",
        headers=_headers(super_token),
        params={"action": "model_config.update"},
    )
    assert audit.status_code == 200, audit.text
    logs = audit.json()["data"]["items"]
    assert logs
    log = logs[0]
    assert log["target_type"] == "model_config"
    assert "changed_fields" in log["detail"]
    assert log["detail"]["api_key_changed"] is True
    assert "sk-demo-12345678" not in json.dumps(log, ensure_ascii=False)

    # 省略 api_key 时保持原值
    no_key = dict(valid_payload)
    no_key.pop("api_key")
    no_key["temperature"] = 0.9
    again = client.put(MODEL_CONFIG_URL, headers=_headers(super_token), json=no_key)
    assert again.status_code == 200, again.text
    assert again.json()["data"]["api_key_masked"] == "sk-****5678"


def test_prompt_list_detail_save_and_rollback(client):
    """提示词列表、保存新版本、变量告警、回滚与审计。"""
    print("[测试] 校验提示词列表")
    admin = _login(client, "demo_admin")
    super_token = _login(client, "demo_super")
    user_token = _login(client, "demo_user")

    _error(client.get(PROMPTS_URL, headers=_headers(user_token)), 403, 20005)

    response = client.get(PROMPTS_URL, headers=_headers(admin))
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert [item["agent_code"] for item in items] == [
        "planner",
        "product_understanding",
        "copywriter",
        "prompt_builder",
        "image_generator",
        "quality_reviewer",
        "repairer",
        "platform_rule",
    ]
    assert all("content_preview" in item for item in items)
    assert all("updated_by" in item for item in items)

    print("[测试] 校验提示词详情")
    detail_response = client.get(f"{PROMPTS_URL}/planner", headers=_headers(admin))
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()["data"]
    assert detail["agent_code"] == "planner"
    assert detail["suggested_variables"] == [
        "product_name",
        "params",
        "requirement_summary",
        "chat_summary",
    ]
    assert "variables_in_content" in detail
    assert detail["versions"]
    assert any(version["is_current"] for version in detail["versions"])
    base_version = detail["current_version"]
    version_one_content = next(
        version["content"] for version in detail["versions"] if version["version"] == 1
    )

    _error(client.get(f"{PROMPTS_URL}/unknown_agent", headers=_headers(admin)), 404, 30021)

    print("[测试] 保存提示词新版本并检查警告")
    content = "你是规划 Agent，请使用 {{product_name}} 与 {{foo}}。"
    save_response = client.put(
        f"{PROMPTS_URL}/planner",
        headers=_headers(admin),
        json={"content": content},
    )
    assert save_response.status_code == 200, save_response.text
    saved = save_response.json()["data"]
    assert saved["current_version"] == base_version + 1
    assert saved["content"] == content
    assert saved["variables_in_content"] == ["product_name", "foo"]
    assert saved["warnings"]["unknown_variables"] == ["foo"]
    assert set(saved["warnings"]["missing_suggested_variables"]) == {
        "params",
        "requirement_summary",
        "chat_summary",
    }
    assert len(saved["versions"]) >= base_version + 1

    _error(
        client.put(
            f"{PROMPTS_URL}/planner", headers=_headers(admin), json={"content": "   "}
        ),
        400,
        10002,
    )
    _error(
        client.put(
            f"{PROMPTS_URL}/planner",
            headers=_headers(admin),
            json={"content": "字" * 20001},
        ),
        400,
        10004,
    )
    _error(
        client.put(
            f"{PROMPTS_URL}/unknown_agent",
            headers=_headers(admin),
            json={"content": "x"},
        ),
        404,
        30021,
    )

    print("[测试] 校验提示词审计")
    audit = client.get(
        "/api/v1/admin/audit-logs",
        headers=_headers(super_token),
        params={"action": "prompt.update"},
    )
    logs = audit.json()["data"]["items"]
    assert logs
    assert logs[0]["target_type"] == "system_prompt"
    assert logs[0]["detail"]["version"] == base_version + 1
    assert logs[0]["detail"]["unknown_variables"] == ["foo"]

    print("[测试] 回滚到版本 1 生成新版本")
    rollback_response = client.post(
        f"{PROMPTS_URL}/planner/versions/1/activate", headers=_headers(admin)
    )
    assert rollback_response.status_code == 200, rollback_response.text
    rolled = rollback_response.json()["data"]
    assert rolled["current_version"] == base_version + 2
    assert rolled["content"] == version_one_content
    versions = {version["version"]: version for version in rolled["versions"]}
    assert rolled["current_version"] in versions
    assert 1 in versions
    assert base_version + 1 in versions
    assert versions[rolled["current_version"]]["content"] == version_one_content

    _error(
        client.post(
            f"{PROMPTS_URL}/planner/versions/9999/activate", headers=_headers(admin)
        ),
        404,
        30022,
    )

    rollback_audit = client.get(
        "/api/v1/admin/audit-logs",
        headers=_headers(super_token),
        params={"action": "prompt.rollback"},
    ).json()["data"]["items"]
    assert rollback_audit
    assert rollback_audit[0]["detail"]["source_version"] == 1
    assert rollback_audit[0]["detail"]["new_version"] == base_version + 2
