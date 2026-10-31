"""9 号「后端服务与接口」契约回归套件。

覆盖 01~08 号切片的跨切面验收项：统一响应、错误码、参数校验、分页边界、
JWT 鉴权、权限点校验、OpenAPI 契约标注。业务接口本体（SSE、上传下载、
幂等并发等）已由 test_workspace / test_chat / test_history 覆盖，这里只验证
它们共同遵守的契约层。每个用例打印中文日志：请求、预期、实际、结论。
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import Role, User

LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
SESSIONS_URL = "/api/v1/sessions"
USERS_URL = "/api/v1/admin/users"
OPENAPI_URL = "/api/openapi.json"

# 6 号种子新增 demo_super（密码 Demo1234）；契约套件复用同一演示账号
SUPER_PASSWORD = "Demo1234"


def _login(client, username: str = "demo_user", password: str = "Demo1234"):
    return client.post(
        LOGIN_URL,
        json={"username": username, "password": password, "remember_me": False},
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(client, username: str = "demo_user", password: str = "Demo1234") -> str:
    response = _login(client, username, password)
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


@pytest.fixture(scope="session", autouse=True)
def super_admin(prepared_database):
    """确保存在一个超管账号，供「超管全量通过」契约用例使用。"""
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == "demo_super")) is None:
            role = db.scalar(select(Role).where(Role.code == "super_admin"))
            user = User(
                username="demo_super",
                display_name="超管",
                password_hash=hash_password(SUPER_PASSWORD),
                status="active",
                token_version=0,
            )
            user.roles.append(role)
            db.add(user)
            db.commit()
            print("[契约] 已创建超管账号 demo_super")
    yield


# ---------------------------------------------------------------------------
# 01：统一响应、错误码、参数校验与分页基线
# ---------------------------------------------------------------------------
def test_unified_response_shape(client):
    print("[契约] 用例：登录成功返回统一响应 { code=0, message=ok, data }")
    response = _login(client)
    body = response.json()
    assert response.status_code == 200
    assert set(body.keys()) == {"code", "message", "data"}
    assert body["code"] == 0 and body["message"] == "ok"
    assert set(body["data"].keys()) == {"token", "expires_at", "user"}
    print(f"[契约] 预期 200/code=0，实际 {response.status_code}/code={body['code']} -> 通过")


def test_login_error_codes(client):
    print("[契约] 用例：密码错误 -> 401/20001，data=null")
    response = _login(client, password="WrongPass1")
    body = response.json()
    assert response.status_code == 401 and body["code"] == 20001 and body["data"] is None
    print(f"[契约] 预期 401/20001，实际 {response.status_code}/{body['code']} -> 通过")

    print("[契约] 用例：缺少用户名 -> 400/10002")
    response = client.post(LOGIN_URL, json={"password": "Demo1234"})
    assert response.status_code == 400 and response.json()["code"] == 10002
    print("[契约] 预期 400/10002 -> 通过")

    print("[契约] 用例：用户名格式错误 -> 400/10003")
    response = client.post(LOGIN_URL, json={"username": "a", "password": "Demo1234"})
    assert response.status_code == 400 and response.json()["code"] == 10003
    print("[契约] 预期 400/10003 -> 通过")


def test_pagination_contract(client):
    token = _token(client)
    # 先造一个带消息的会话，保证分页载体可用
    chat = client.post(
        SESSIONS_URL + "/messages",
        headers=_headers(token),
        json={
            "client_message_id": str(uuid.uuid4()),
            "content": "帮我做一套图",
            "params": {"product_name": "秋季通勤衬衫", "width": 1000, "height": 1000},
            "session_id": None,
        },
    )
    # SSE 正文首事件 meta 带 session_id
    import json as _json

    session_id = None
    for line in chat.text.splitlines():
        if line.startswith("data:"):
            data = _json.loads(line[len("data:") :].strip())
            if isinstance(data, dict) and "session_id" in data:
                session_id = data["session_id"]
                break
    assert session_id is not None

    url = f"{SESSIONS_URL}/{session_id}/messages"

    print("[契约] 用例：正常分页返回 { items,total,page,page_size }")
    response = client.get(f"{url}?page=1&page_size=20", headers=_headers(token))
    body = response.json()
    assert response.status_code == 200
    assert set(body["data"].keys()) == {"items", "total", "page", "page_size"}
    assert isinstance(body["data"]["items"], list)
    print("[契约] 预期 200/统一分页结构，实际通过")

    print("[契约] 用例：page<1 -> 400/10001")
    response = client.get(f"{url}?page=0", headers=_headers(token))
    assert response.status_code == 400 and response.json()["code"] == 10001
    print("[契约] 预期 400/10001，实际通过")

    print("[契约] 用例：page_size>100 -> 400/10004")
    response = client.get(f"{url}?page_size=101", headers=_headers(token))
    assert response.status_code == 400 and response.json()["code"] == 10004
    print("[契约] 预期 400/10004，实际通过")

    print("[契约] 用例：page_size 非整数 -> 400/10003")
    response = client.get(f"{url}?page_size=abc", headers=_headers(token))
    assert response.status_code == 400 and response.json()["code"] == 10003
    print("[契约] 预期 400/10003，实际通过")


# ---------------------------------------------------------------------------
# 02：JWT 鉴权与账号状态校验
# ---------------------------------------------------------------------------
def test_jwt_failure_modes(client):
    print("[契约] 用例：无 token -> 401/20003")
    response = client.get(ME_URL)
    assert response.status_code == 401 and response.json()["code"] == 20003
    print("[契约] 预期 401/20003，实际通过")

    print("[契约] 用例：坏签名 -> 401/20003")
    response = client.get(ME_URL, headers=_headers("not-a-valid-jwt"))
    assert response.status_code == 401 and response.json()["code"] == 20003
    print("[契约] 预期 401/20003，实际通过")

    print("[契约] 用例：过期 token -> 401/20002")
    from app.core.config import settings

    expired = jwt.encode(
        {
            "sub": "1",
            "iat": int(time.time()) - 1000,
            "exp": int(time.time()) - 100,
            "token_version": 0,
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = client.get(ME_URL, headers=_headers(expired))
    assert response.status_code == 401 and response.json()["code"] == 20002
    print("[契约] 预期 401/20002，实际通过")


def test_token_version_mismatch(client):
    token = _token(client)
    print("[契约] 用例：修改密码后旧 token（token_version 不符）-> 401/20003")
    change = client.put(
        "/api/v1/auth/password",
        headers=_headers(token),
        json={"old_password": "Demo1234", "new_password": "Demo12345"},
    )
    assert change.status_code == 200, change.text
    response = client.get(ME_URL, headers=_headers(token))
    assert response.status_code == 401 and response.json()["code"] == 20003
    print("[契约] 预期 401/20003，实际通过")

    # 恢复密码，避免影响其他用例（reset_state 只重置 token_version 与状态，不重置密码）
    restore = client.put(
        "/api/v1/auth/password",
        headers=_headers(_token(client, "demo_user", "Demo12345")),
        json={"old_password": "Demo12345", "new_password": "Demo1234"},
    )
    assert restore.status_code == 200, restore.text


def test_disabled_account(client, db_session):
    fresh = _token(client)
    print("[契约] 用例：禁用账号 -> 403/20004")
    user = db_session.scalar(select(User).where(User.username == "demo_user"))
    user.status = "disabled"
    db_session.commit()
    response = client.get(ME_URL, headers=_headers(fresh))
    assert response.status_code == 403 and response.json()["code"] == 20004
    print("[契约] 预期 403/20004，实际通过")


# ---------------------------------------------------------------------------
# 03：权限点校验与越权语义
# ---------------------------------------------------------------------------
def test_permission_contract(client):
    user_token = _token(client, "demo_user")
    admin_token = _token(client, "demo_admin")
    super_token = _token(client, "demo_super", SUPER_PASSWORD)

    print("[契约] 用例：demo_user 访问管理端 -> 403/20005")
    response = client.get(USERS_URL, headers=_headers(user_token))
    assert response.status_code == 403 and response.json()["code"] == 20005
    assert response.json()["message"] == "无权限"
    print("[契约] 预期 403/20005，实际通过")

    print("[契约] 用例：demo_admin 访问用户端 -> 403/20005")
    response = client.get(SESSIONS_URL, headers=_headers(admin_token))
    assert response.status_code == 403 and response.json()["code"] == 20005
    print("[契约] 预期 403/20005，实际通过")

    print("[契约] 用例：demo_super 两类接口均通过")
    assert client.get(USERS_URL, headers=_headers(super_token)).status_code == 200
    assert client.get(SESSIONS_URL, headers=_headers(super_token)).status_code == 200
    print("[契约] 预期超管全量通过，实际通过")

    print("[契约] 用例：demo_dual 拥有 user+admin 权限并集")
    dual_token = _token(client, "demo_dual")
    assert client.get(SESSIONS_URL, headers=_headers(dual_token)).status_code == 200
    assert client.get(USERS_URL, headers=_headers(dual_token)).status_code == 200
    print("[契约] 预期并集通过，实际通过")


# ---------------------------------------------------------------------------
# 08：OpenAPI 契约标注
# ---------------------------------------------------------------------------
def test_openapi_contract(client):
    print("[契约] 用例：/api/openapi.json 包含契约标注")
    schema = client.get(OPENAPI_URL).json()

    schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "BearerAuth" in schemes, "缺少 Bearer 鉴权方案"

    schemas = schema.get("components", {}).get("schemas", {})
    assert "UnifiedResponse" in schemas, "缺少统一响应结构"
    assert "PaginatedResponse" in schemas, "缺少分页结构"

    error_codes = schema.get("x-error-codes", [])
    assert error_codes, "缺少错误码表"
    codes = {entry["code"] for entry in error_codes}
    for code in (0, 10002, 20005, 30006, 50001):
        assert code in codes, f"错误码表缺少 {code}"

    # 至少抽查 3 个接口的权限码标注
    checks = [
        ("/api/v1/auth/login", "post", "none"),
        ("/api/v1/admin/users", "get", "admin.accounts.view"),
        ("/api/v1/sessions/{session_id}/messages", "get", "user.workspace"),
    ]
    for path, method, expected in checks:
        op = schema["paths"][path][method]
        perm = op.get("x-permission")
        assert perm == expected or perm == [expected], (
            f"{method.upper()} {path} 权限码标注 {perm!r} != {expected!r}"
        )
    print("[契约] 预期 Bearer/统一响应/分页/错误码/权限码均存在，实际通过")
