"""登录链路接口测试。"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import jwt
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import AuditLog, User

LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
LOGOUT_URL = "/api/v1/auth/logout"


def _login(client, username: str = "demo_user", password: str = "Demo1234", remember_me: bool = False):
    print(f"[测试] 调用登录接口 username={username} remember_me={remember_me}")
    return client.post(
        LOGIN_URL,
        json={"username": username, "password": password, "remember_me": remember_me},
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_success_and_response_shape(client):
    print("[测试] 步骤 1：正确账号密码登录")
    response = _login(client)
    assert response.status_code == 200

    body = response.json()
    print("[测试] 步骤 2：校验统一响应结构与用户字段")
    assert body["code"] == 0
    assert body["message"] == "ok"
    data = body["data"]
    assert isinstance(data["token"], str) and data["token"]
    assert data["expires_at"].endswith("+08:00")
    assert data["user"]["username"] == "demo_user"
    assert data["user"]["display_name"] == "演示用户"
    assert data["user"]["avatar_url"] is None
    assert data["user"]["roles"] == ["user"]
    assert data["user"]["permissions"] == ["user.history", "user.profile", "user.workspace"]

    print("[测试] 步骤 3：校验 JWT 载荷")
    payload = jwt.decode(data["token"], settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert payload["sub"] == str(data["user"]["id"])
    assert payload["roles"] == ["user"]
    assert payload["token_version"] == 0


@pytest.mark.parametrize(
    ("remember_me", "expected_seconds"),
    [(False, 24 * 3600), (True, 7 * 24 * 3600)],
)
def test_remember_me_ttl(client, remember_me, expected_seconds):
    print(f"[测试] 验证 remember_me={remember_me} 的 token 有效期")
    response = _login(client, remember_me=remember_me)
    assert response.status_code == 200
    token = response.json()["data"]["token"]
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert abs((payload["exp"] - payload["iat"]) - expected_seconds) <= 2


def test_login_username_is_trimmed(client):
    print("[测试] 用户名首尾空格应被去除")
    response = _login(client, username="  demo_user  ")
    assert response.status_code == 200
    assert response.json()["data"]["user"]["username"] == "demo_user"


@pytest.mark.parametrize("username", ["demo_user", "demo_admin", "demo_dual"])
def test_login_three_demo_accounts(client, username):
    print(f"[测试] 演示账号 {username} 可登录")
    response = _login(client, username=username)
    assert response.status_code == 200
    assert response.json()["data"]["user"]["username"] == username


def test_dual_role_account_has_both_permission_groups(client):
    print("[测试] 双角色账号返回两组权限")
    response = _login(client, username="demo_dual")
    assert response.status_code == 200
    user = response.json()["data"]["user"]
    assert user["roles"] == ["admin", "user"]
    assert set(user["permissions"]) == {
        "user.workspace",
        "user.history",
        "user.profile",
        "admin.dashboard.view",
    }


def test_wrong_password_returns_unified_error(client):
    print("[测试] 密码错误返回 401/20001，且不泄露账号是否存在")
    response = _login(client, password="WrongPass1")
    assert response.status_code == 401
    assert response.json() == {"code": 20001, "message": "用户名或密码错误", "data": None}


def test_unknown_user_returns_same_error(client):
    print("[测试] 账号不存在返回与密码错误一致的提示")
    response = _login(client, username="nobody_here")
    assert response.status_code == 401
    assert response.json()["code"] == 20001
    assert response.json()["message"] == "用户名或密码错误"


def test_disabled_account_returns_unified_error(client, db_session):
    print("[测试] 禁用账号登录返回统一提示")
    user = db_session.scalar(select(User).where(User.username == "demo_user"))
    user.status = "disabled"
    db_session.commit()

    response = _login(client)
    assert response.status_code == 401
    assert response.json()["code"] == 20001
    assert response.json()["message"] == "用户名或密码错误"


@pytest.mark.parametrize(
    ("payload", "expected_code", "expected_message"),
    [
        ({"username": "", "password": "Demo1234"}, 10002, "请输入用户名"),
        ({"password": "Demo1234"}, 10002, "请输入用户名"),
        ({"username": "abc", "password": "Demo1234"}, 10003, "用户名需为 4~20 位字母、数字或下划线"),
        ({"username": "bad-name!", "password": "Demo1234"}, 10003, "用户名需为 4~20 位字母、数字或下划线"),
        ({"username": "demo_user"}, 10002, "请输入密码"),
        ({"username": "demo_user", "password": ""}, 10002, "请输入密码"),
        ({"username": "demo_user", "password": "short"}, 10003, "密码长度需为 8~32 位"),
        ({"username": "demo_user", "password": "x" * 33}, 10003, "密码长度需为 8~32 位"),
    ],
)
def test_login_validation(client, payload, expected_code, expected_message):
    print(f"[测试] 参数校验：{payload} -> {expected_code}")
    response = client.post(LOGIN_URL, json=payload)
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == expected_code
    assert body["message"] == expected_message
    assert body["data"] is None


def test_password_is_not_trimmed(client):
    print("[测试] 密码前后空格属于密码本身，不应被去除")
    response = _login(client, password=" Demo1234")
    assert response.status_code == 401
    assert response.json()["code"] == 20001


def test_me_returns_current_user(client):
    print("[测试] 登录后调用 /auth/me 恢复用户信息")
    token = _login(client).json()["data"]["token"]
    response = client.get(ME_URL, headers=_auth_headers(token))
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["user"]["username"] == "demo_user"
    assert data["user"]["display_name"] == "演示用户"
    assert data["user"]["avatar_url"] is None
    assert data["roles"] == ["user"]
    assert data["permissions"] == ["user.history", "user.profile", "user.workspace"]


def test_me_without_token_returns_20003(client):
    print("[测试] 未携带 token 访问 /auth/me")
    response = client.get(ME_URL)
    assert response.status_code == 401
    assert response.json()["code"] == 20003
    assert response.json()["message"] == "token 无效"


def test_me_with_invalid_token_returns_20003(client):
    print("[测试] 非法 token 访问 /auth/me")
    response = client.get(ME_URL, headers=_auth_headers("not-a-jwt"))
    assert response.status_code == 401
    assert response.json()["code"] == 20003


def test_me_with_expired_token_returns_20002(client):
    print("[测试] 过期 token 返回 20002")
    now = int(time.time())
    expired = jwt.encode(
        {
            "sub": "1",
            "iat": now - 100,
            "exp": now - 10,
            "token_version": 0,
            "roles": [],
            "permissions": [],
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = client.get(ME_URL, headers=_auth_headers(expired))
    assert response.status_code == 401
    assert response.json()["code"] == 20002
    assert response.json()["message"] == "登录已过期"


def test_token_version_bump_invalidates_token(client, db_session):
    print("[测试] token_version 递增后旧 token 失效")
    token = _login(client).json()["data"]["token"]
    user = db_session.scalar(select(User).where(User.username == "demo_user"))
    user.token_version = user.token_version + 1
    db_session.commit()

    response = client.get(ME_URL, headers=_auth_headers(token))
    assert response.status_code == 401
    assert response.json()["code"] == 20003


def test_disabled_after_login_returns_20004(client, db_session):
    print("[测试] 登录后账号被禁用，旧 token 返回 403/20004")
    token = _login(client).json()["data"]["token"]
    user = db_session.scalar(select(User).where(User.username == "demo_user"))
    user.status = "disabled"
    db_session.commit()

    response = client.get(ME_URL, headers=_auth_headers(token))
    assert response.status_code == 403
    assert response.json()["code"] == 20004
    assert response.json()["message"] == "账号不可用"


def test_logout_writes_audit(client, db_session):
    print("[测试] 退出登录写审计并返回 data=null")
    token = _login(client).json()["data"]["token"]
    response = client.post(
        LOGOUT_URL,
        headers={**_auth_headers(token), "User-Agent": "pytest-agent"},
    )
    assert response.status_code == 200
    assert response.json() == {"code": 0, "message": "ok", "data": None}

    log = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "auth.logout").order_by(AuditLog.id.desc())
    )
    assert log is not None
    assert log.result == "success"
    assert log.username_snapshot == "demo_user"
    assert log.user_agent == "pytest-agent"
    assert log.detail is None


def test_login_audit_success_and_failure_without_password(client, db_session):
    print("[测试] 登录成功与失败都写审计，失败日志不含密码")
    _login(client, username="demo_user", password="Demo1234")
    _login(client, username="demo_user", password="WrongPass1")

    logs = list(
        db_session.scalars(
            select(AuditLog).where(AuditLog.action == "auth.login").order_by(AuditLog.id)
        )
    )
    assert len(logs) == 2

    success, failed = logs
    assert success.result == "success"
    assert success.username_snapshot == "demo_user"
    assert success.detail is None

    assert failed.result == "failed"
    assert failed.username_snapshot == "demo_user"
    assert failed.detail == {"reason": "bad_credentials"}
    assert "password" not in failed.detail
    assert "Demo1234" not in str(failed.detail)

    print("[测试] 审计记录未包含密码与 token 字段")
    assert all("token" not in (log.detail or {}) for log in logs)


def test_login_updates_last_login_at(client, db_session):
    print("[测试] 登录成功更新 last_login_at")
    before = db_session.scalar(select(User).where(User.username == "demo_user")).last_login_at
    assert before is None

    _login(client)
    db_session.expire_all()
    after = db_session.scalar(select(User).where(User.username == "demo_user")).last_login_at
    assert after is not None
    assert after.tzinfo is not None


def test_expires_at_matches_jwt_exp(client):
    print("[测试] expires_at 与 JWT exp 表示同一时刻")
    data = _login(client, remember_me=True).json()["data"]
    payload = jwt.decode(data["token"], settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    expires_at = datetime.fromisoformat(data["expires_at"])
    assert int(expires_at.timestamp()) == payload["exp"]
    assert expires_at.utcoffset() is not None
    assert expires_at.utcoffset().total_seconds() == 8 * 3600


def test_login_body_missing_returns_400(client):
    print("[测试] 缺少请求体返回 400 统一结构")
    response = client.post(LOGIN_URL)
    assert response.status_code == 400
    body = response.json()
    assert body["code"] in (10002, 10003)
    assert body["data"] is None
    assert isinstance(body["message"], str)
