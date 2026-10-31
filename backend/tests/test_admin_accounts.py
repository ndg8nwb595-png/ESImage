"""管理后台「账号与权限」「操作日志」接口测试（6 号 PRD 最小 demo）。

每一步都输出中文日志，便于并行调试时定位问题。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models import AgentRun, AuditLog, CreativeSession, Permission, Role, User, user_roles
from app.modules.auth.seed import PERMISSIONS, ROLE_PERMISSIONS, seed

LOGIN_URL = "/api/v1/auth/login"
USERS_URL = "/api/v1/admin/users"
ROLES_URL = "/api/v1/admin/roles"
AUDIT_URL = "/api/v1/admin/audit-logs"

SEED_USERNAMES = {"demo_super", "demo_user", "demo_user2", "demo_admin", "demo_dual"}
ALL_PERMISSION_CODES = {item[0] for item in PERMISSIONS}


def _login(client, username: str, password: str = "Demo1234") -> str:
    print(f"[测试] 登录 {username}")
    response = client.post(LOGIN_URL, json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_user(client, token: str, username: str, roles: list[str], **overrides):
    payload = {
        "username": username,
        "display_name": f"测试{username}",
        "password": "Passw0rd!",
        "roles": roles,
        "status": "active",
    }
    payload.update(overrides)
    print(f"[测试] 新建账号 {username} roles={roles} payload={overrides}")
    return client.post(USERS_URL, json=payload, headers=_headers(token))


@pytest.fixture(autouse=True)
def restore_role_permissions():
    """每个用例前恢复种子默认角色权限，避免角色权限测试互相污染。"""
    with SessionLocal() as db:
        roles = {role.code: role for role in db.scalars(select(Role))}
        permissions = {permission.code: permission for permission in db.scalars(select(Permission))}
        for role_code, codes in ROLE_PERMISSIONS.items():
            roles[role_code].permissions = [permissions[code] for code in codes if code in permissions]
        # 超管不写 role_permissions，由鉴权层即时授予全部权限
        roles["super_admin"].permissions = []
        db.commit()
    yield


@pytest.fixture(autouse=True)
def cleanup_created_users():
    """每个用例后删除测试新建的账号，保持列表断言稳定。"""
    yield
    with SessionLocal() as db:
        ids = list(db.scalars(select(User.id).where(User.username.notin_(SEED_USERNAMES))))
        if ids:
            print(f"[测试] 清理测试账号 {len(ids)} 个")
            # 测试账号登录过会写审计日志（user_id 外键），先删日志再删账号
            db.execute(delete(AuditLog).where(AuditLog.user_id.in_(ids)))
            session_ids = select(CreativeSession.id).where(CreativeSession.user_id.in_(ids))
            db.execute(delete(AgentRun).where(AgentRun.session_id.in_(session_ids)))
            db.execute(delete(CreativeSession).where(CreativeSession.user_id.in_(ids)))
            db.execute(delete(user_roles).where(user_roles.c.user_id.in_(ids)))
            db.execute(delete(User).where(User.id.in_(ids)))
            db.commit()


def test_seed_catalog_and_super_permissions(client):
    print("[测试] 步骤 1：demo_super 登录，应拥有全部 23 个权限点")
    token = _login(client, "demo_super")
    me = client.get("/api/v1/auth/me", headers=_headers(token)).json()["data"]
    assert me["roles"] == ["super_admin"]
    assert set(me["permissions"]) == ALL_PERMISSION_CODES
    assert len(me["permissions"]) == 23

    print("[测试] 步骤 2：读取角色与权限点目录")
    data = client.get(ROLES_URL, headers=_headers(token)).json()["data"]
    assert [role["code"] for role in data["roles"]] == ["user", "admin", "super_admin"]
    assert [role["editable"] for role in data["roles"]] == [True, True, False]
    assert len(data["permissions"]) == 23
    assert {p["group_name"] for p in data["permissions"]} == {"用户端", "管理后台"}

    role_map = {role["code"]: set(role["permissions"]) for role in data["roles"]}
    assert role_map["user"] == set(ROLE_PERMISSIONS["user"])
    assert role_map["admin"] == set(ROLE_PERMISSIONS["admin"])
    assert role_map["super_admin"] == ALL_PERMISSION_CODES

    print("[测试] 步骤 3：管理员访问角色管理返回 403/20005")
    admin_token = _login(client, "demo_admin")
    response = client.get(ROLES_URL, headers=_headers(admin_token))
    assert response.status_code == 403
    assert response.json()["code"] == 20005


def test_user_list_filters_and_permissions(client):
    print("[测试] 步骤 1：普通用户访问用户列表返回 403/20005")
    user_token = _login(client, "demo_user")
    response = client.get(USERS_URL, headers=_headers(user_token))
    assert response.status_code == 403
    assert response.json()["code"] == 20005

    print("[测试] 步骤 2：超管访问用户列表")
    token = _login(client, "demo_super")
    data = client.get(USERS_URL, headers=_headers(token)).json()["data"]
    usernames = {item["username"] for item in data["items"]}
    assert SEED_USERNAMES <= usernames
    assert data["page"] == 1 and data["page_size"] == 20
    for item in data["items"]:
        assert set(item) == {
            "user_id",
            "username",
            "display_name",
            "roles",
            "status",
            "stats",
            "last_login_at",
            "created_at",
            "updated_at",
            "deleted_at",
        }
        assert item["stats"]["stats_available"] is True
        assert item["created_at"].endswith("+08:00")

    print("[测试] 步骤 3：关键词 + 角色过滤")
    data = client.get(
        USERS_URL, params={"keyword": "demo", "role": "admin", "status": "all"}, headers=_headers(token)
    ).json()["data"]
    assert {item["username"] for item in data["items"]} == {"demo_admin", "demo_dual"}

    print("[测试] 步骤 4：page=0 按 1 处理")
    data = client.get(USERS_URL, params={"page": 0}, headers=_headers(token)).json()["data"]
    assert data["page"] == 1

    print("[测试] 步骤 5：非法参数返回统一错误码")
    assert client.get(USERS_URL, params={"page_size": 30}, headers=_headers(token)).json()["code"] == 10003
    assert client.get(USERS_URL, params={"role": "root"}, headers=_headers(token)).json()["code"] == 10003
    assert client.get(USERS_URL, params={"status": "unknown"}, headers=_headers(token)).json()["code"] == 10003
    assert client.get(USERS_URL, params={"keyword": "长" * 51}, headers=_headers(token)).json()["code"] == 10004
    date_response = client.get(
        USERS_URL,
        params={"created_from": "2026-10-31", "created_to": "2026-10-01"},
        headers=_headers(token),
    )
    assert date_response.status_code == 400
    assert date_response.json()["code"] == 10003


def test_create_user_success_and_audit(client, db_session):
    token = _login(client, "demo_super")
    print("[测试] 步骤 1：超管新建普通用户")
    response = _create_user(client, token, "demo_editor", ["user"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["username"] == "demo_editor"
    assert data["roles"] == [{"code": "user", "name": "普通用户"}]
    assert data["status"] == "active"
    assert "password" not in data and "password_hash" not in data
    assert data["stats"]["stats_available"] is True

    print("[测试] 步骤 2：检查操作日志 account.create")
    db_session.expire_all()
    log = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "account.create").order_by(AuditLog.id.desc())
    )
    assert log is not None
    assert log.result == "success"
    assert log.target_type == "account"
    assert log.target_id == "demo_editor"
    assert "Passw0rd!" not in str(log.detail)

    print("[测试] 步骤 3：管理员可以创建普通用户与管理员")
    admin_token = _login(client, "demo_admin")
    assert _create_user(client, admin_token, "demo_mgr", ["admin"]).status_code == 200
    assert _create_user(client, admin_token, "demo_both", ["admin", "user"]).status_code == 200


def test_create_user_validation_and_boundaries(client):
    token = _login(client, "demo_super")
    admin_token = _login(client, "demo_admin")

    print("[测试] 步骤 1：缺少必填字段（含完全无请求体）")
    response = client.post(USERS_URL, json={"username": "abc123"}, headers=_headers(token))
    assert response.status_code == 400
    assert response.json()["code"] == 10002
    assert response.json()["message"] == "请填写完整账号信息"
    response = client.post(USERS_URL, headers=_headers(token))
    assert response.status_code == 400
    assert response.json()["code"] == 10002

    print("[测试] 步骤 2：用户名格式、显示名过长、密码长度、状态非法")
    response = _create_user(client, token, "ab", ["user"])
    assert response.json()["code"] == 10003
    assert response.json()["message"] == "用户名需为 4~20 位字母、数字或下划线"
    cases = [
        ({"display_name": "长" * 31}, 10004, "显示名不能超过 30 个字符"),
        ({"password": "short"}, 10004, "密码长度需为 8~32 位"),
        ({"status": "deleted"}, 10003, "状态参数不合法"),
    ]
    for overrides, expected_code, expected_message in cases:
        response = _create_user(client, token, "demo_bad1", ["user"], **overrides)
        assert response.json()["code"] == expected_code, overrides
        assert response.json()["message"] == expected_message

    print("[测试] 步骤 2.1：纯空格密码应被拒绝（接口文档 §5.1）")
    response = _create_user(client, token, "demo_bad1", ["user"], password=" " * 8)
    assert response.status_code == 400
    assert response.json()["code"] == 10002

    print("[测试] 步骤 3：角色组合不合法")
    response = _create_user(client, token, "demo_bad2", ["super_admin", "admin"])
    assert response.status_code == 409
    assert response.json()["code"] == 30009
    assert response.json()["message"] == "角色组合不合法"

    print("[测试] 步骤 4：用户名重复")
    assert _create_user(client, token, "demo_editor", ["user"]).status_code == 200
    response = _create_user(client, token, "demo_editor", ["user"])
    assert response.status_code == 409
    assert response.json()["code"] == 30010
    assert response.json()["message"] == "用户名已存在"

    print("[测试] 步骤 5：管理员不能分配超管")
    response = _create_user(client, admin_token, "demo_super2", ["super_admin"])
    assert response.status_code == 403
    assert response.json()["code"] == 20005
    assert response.json()["message"] == "无权分配超管角色"


def test_user_detail_and_admin_boundaries(client):
    super_token = _login(client, "demo_super")
    admin_token = _login(client, "demo_admin")
    super_id = client.get("/api/v1/auth/me", headers=_headers(super_token)).json()["data"]["user"]["id"]
    admin_id = client.get("/api/v1/auth/me", headers=_headers(admin_token)).json()["data"]["user"]["id"]

    print("[测试] 步骤 1：超管可查看超管详情")
    assert client.get(f"{USERS_URL}/{super_id}", headers=_headers(super_token)).status_code == 200

    print("[测试] 步骤 2：管理员查看超管返回 403/20006")
    response = client.get(f"{USERS_URL}/{super_id}", headers=_headers(admin_token))
    assert response.status_code == 403
    assert response.json()["code"] == 20006

    print("[测试] 步骤 3：管理员可查看自己")
    assert client.get(f"{USERS_URL}/{admin_id}", headers=_headers(admin_token)).status_code == 200

    print("[测试] 步骤 4：用户不存在返回 404/30017")
    response = client.get(f"{USERS_URL}/999999", headers=_headers(super_token))
    assert response.status_code == 404
    assert response.json()["code"] == 30017


def test_update_user_and_boundaries(client, db_session):
    super_token = _login(client, "demo_super")
    admin_token = _login(client, "demo_admin")
    super_id = client.get("/api/v1/auth/me", headers=_headers(super_token)).json()["data"]["user"]["id"]
    admin_id = client.get("/api/v1/auth/me", headers=_headers(admin_token)).json()["data"]["user"]["id"]

    print("[测试] 步骤 1：新建账号并修改显示名与角色")
    user_id = _create_user(client, super_token, "demo_editor", ["user"]).json()["data"]["user_id"]
    response = client.patch(
        f"{USERS_URL}/{user_id}",
        json={"display_name": "编辑小王", "roles": ["admin", "user"]},
        headers=_headers(super_token),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["display_name"] == "编辑小王"
    assert {role["code"] for role in data["roles"]} == {"admin", "user"}

    print("[测试] 步骤 2：account.update 日志包含 before/after")
    db_session.expire_all()
    log = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "account.update").order_by(AuditLog.id.desc())
    )
    assert log.target_id == "demo_editor"
    assert log.detail["before"]["roles"] == ["user"]
    assert log.detail["after"]["roles"] == ["admin", "user"]

    print("[测试] 步骤 3：管理员修改自己的角色返回 403/20007")
    response = client.patch(
        f"{USERS_URL}/{admin_id}", json={"roles": ["admin", "user"]}, headers=_headers(admin_token)
    )
    assert response.status_code == 403
    assert response.json()["code"] == 20007

    print("[测试] 步骤 4：管理员修改其他管理员的角色返回 403/20005")
    other_admin_id = _create_user(client, super_token, "demo_mgr", ["admin"]).json()["data"]["user_id"]
    response = client.patch(
        f"{USERS_URL}/{other_admin_id}", json={"roles": ["user"]}, headers=_headers(admin_token)
    )
    assert response.status_code == 403
    assert response.json()["code"] == 20005
    assert response.json()["message"] == "无权修改其他管理员的角色"

    print("[测试] 步骤 5：管理员操作超管返回 403/20006")
    response = client.patch(
        f"{USERS_URL}/{super_id}", json={"display_name": "改名"}, headers=_headers(admin_token)
    )
    assert response.status_code == 403
    assert response.json()["code"] == 20006

    print("[测试] 步骤 6：超管移除自己的超管角色返回 403/20007")
    response = client.patch(
        f"{USERS_URL}/{super_id}", json={"roles": ["admin"]}, headers=_headers(super_token)
    )
    assert response.status_code == 403
    assert response.json()["code"] == 20007

    print("[测试] 步骤 7：不能降级最后一个可用超管")
    response = client.patch(
        f"{USERS_URL}/{super_id}", json={"status": "disabled"}, headers=_headers(super_token)
    )
    assert response.status_code == 403
    assert response.json()["code"] == 20007

    print("[测试] 步骤 8：前端总是提交三个字段，未变化的角色/状态不应拦截改显示名")
    response = client.patch(
        f"{USERS_URL}/{admin_id}",
        json={"display_name": "管理员甲", "roles": ["admin"], "status": "active"},
        headers=_headers(admin_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["display_name"] == "管理员甲"

    print("[测试] 步骤 8.1：超管改自己显示名（角色/状态原样提交）")
    response = client.patch(
        f"{USERS_URL}/{super_id}",
        json={"display_name": "超管甲", "roles": ["super_admin"], "status": "active"},
        headers=_headers(super_token),
    )
    assert response.status_code == 200, response.text

    print("[测试] 步骤 8.2：管理员改其他管理员显示名（角色原样提交）")
    response = client.patch(
        f"{USERS_URL}/{other_admin_id}",
        json={"display_name": "管理员乙", "roles": ["admin"], "status": "active"},
        headers=_headers(admin_token),
    )
    assert response.status_code == 200, response.text

    print("[测试] 步骤 9：PATCH 无请求体返回 10002")
    response = client.patch(f"{USERS_URL}/{admin_id}", headers=_headers(admin_token))
    assert response.status_code == 400
    assert response.json()["code"] == 10002
    assert response.json()["message"] == "请至少修改一个字段"


def test_reset_password_and_token_invalidation(client, db_session):
    super_token = _login(client, "demo_super")
    admin_token = _login(client, "demo_admin")
    super_id = client.get("/api/v1/auth/me", headers=_headers(super_token)).json()["data"]["user"]["id"]

    print("[测试] 步骤 1：新建账号并登录，保存旧 token")
    created = _create_user(client, super_token, "demo_editor", ["user"]).json()["data"]
    user_id = created["user_id"]
    old_token = _login(client, "demo_editor", "Passw0rd!")

    print("[测试] 步骤 2：管理员不能重置超管密码")
    response = client.post(
        f"{USERS_URL}/{super_id}/reset-password", json={"new_password": "NewPass123"}, headers=_headers(admin_token)
    )
    assert response.status_code == 403
    assert response.json()["code"] == 20006

    print("[测试] 步骤 3：超管不能重置自己的密码")
    response = client.post(
        f"{USERS_URL}/{super_id}/reset-password", json={"new_password": "NewPass123"}, headers=_headers(super_token)
    )
    assert response.status_code == 403
    assert response.json()["code"] == 20007

    print("[测试] 步骤 4：无请求体返回 10002「请输入新密码」")
    response = client.post(f"{USERS_URL}/{user_id}/reset-password", headers=_headers(super_token))
    assert response.status_code == 400
    assert response.json()["code"] == 10002
    assert response.json()["message"] == "请输入新密码"

    print("[测试] 步骤 5：超管重置普通用户密码")
    response = client.post(
        f"{USERS_URL}/{user_id}/reset-password", json={"new_password": "NewPass123"}, headers=_headers(super_token)
    )
    assert response.status_code == 200
    assert response.json()["data"] is None

    print("[测试] 步骤 6：旧 token 返回 401/20003，新密码可登录")
    response = client.get("/api/v1/auth/me", headers=_headers(old_token))
    assert response.status_code == 401
    assert response.json()["code"] == 20003
    assert _login(client, "demo_editor", "NewPass123")

    print("[测试] 步骤 7：日志不含密码")
    db_session.expire_all()
    log = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "account.reset_password").order_by(AuditLog.id.desc())
    )
    assert log.target_id == "demo_editor"
    assert "NewPass123" not in str(log.detail)
    assert set(log.detail) == {"user_id", "username"}


def test_disable_enable_delete_restore(client, db_session):
    super_token = _login(client, "demo_super")
    admin_token = _login(client, "demo_admin")

    print("[测试] 步骤 1：新建账号并登录")
    user_id = _create_user(client, super_token, "demo_editor", ["user"]).json()["data"]["user_id"]
    user_token = _login(client, "demo_editor", "Passw0rd!")

    print("[测试] 步骤 2：禁用后旧 token 返回 403/20004")
    assert client.post(f"{USERS_URL}/{user_id}/disable", headers=_headers(admin_token)).status_code == 200
    response = client.get("/api/v1/auth/me", headers=_headers(user_token))
    assert response.status_code == 403
    assert response.json()["code"] == 20004

    print("[测试] 步骤 3：重复禁用返回 200 且不重复写日志")
    before = len(list(db_session.scalars(select(AuditLog).where(AuditLog.action == "account.disable"))))
    assert client.post(f"{USERS_URL}/{user_id}/disable", headers=_headers(admin_token)).status_code == 200
    db_session.expire_all()
    after = len(list(db_session.scalars(select(AuditLog).where(AuditLog.action == "account.disable"))))
    assert before == after

    print("[测试] 步骤 4：启用后可登录")
    assert client.post(f"{USERS_URL}/{user_id}/enable", headers=_headers(admin_token)).status_code == 200
    assert _login(client, "demo_editor", "Passw0rd!")

    print("[测试] 步骤 5：删除后状态为 deleted，用户名不能被复用")
    assert client.delete(f"{USERS_URL}/{user_id}", headers=_headers(admin_token)).status_code == 200
    data = client.get(USERS_URL, params={"status": "deleted", "keyword": "demo_editor"}, headers=_headers(super_token)).json()["data"]
    assert [item["username"] for item in data["items"]] == ["demo_editor"]
    response = _create_user(client, super_token, "demo_editor", ["user"])
    assert response.status_code == 409
    assert response.json()["code"] == 30010

    print("[测试] 步骤 6：已删除账号不能启用，重复删除返回 409/30018")
    assert client.post(f"{USERS_URL}/{user_id}/enable", headers=_headers(admin_token)).json()["code"] == 30018
    assert client.delete(f"{USERS_URL}/{user_id}", headers=_headers(admin_token)).json()["code"] == 30018

    print("[测试] 步骤 6.1：已删除账号不能通过 PATCH 绕过恢复接口")
    response = client.patch(
        f"{USERS_URL}/{user_id}", json={"status": "active"}, headers=_headers(super_token)
    )
    assert response.status_code == 409
    assert response.json()["code"] == 30018
    response = client.patch(
        f"{USERS_URL}/{user_id}", json={"display_name": "绕过恢复"}, headers=_headers(super_token)
    )
    assert response.status_code == 409
    assert response.json()["code"] == 30018

    print("[测试] 步骤 7：恢复后状态回到 active")
    response = client.post(f"{USERS_URL}/{user_id}/restore", headers=_headers(admin_token))
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "active"
    assert client.post(f"{USERS_URL}/{user_id}/restore", headers=_headers(admin_token)).json()["code"] == 30018

    print("[测试] 步骤 8：不能禁用/删除自己")
    admin_id = client.get("/api/v1/auth/me", headers=_headers(admin_token)).json()["data"]["user"]["id"]
    assert client.post(f"{USERS_URL}/{admin_id}/disable", headers=_headers(admin_token)).json()["code"] == 20007
    assert client.delete(f"{USERS_URL}/{admin_id}", headers=_headers(admin_token)).json()["code"] == 20007

    print("[测试] 步骤 9：不能禁用最后一个可用超管")
    super_id = client.get("/api/v1/auth/me", headers=_headers(super_token)).json()["data"]["user"]["id"]
    response = client.post(f"{USERS_URL}/{super_id}/disable", headers=_headers(super_token))
    assert response.status_code == 403
    assert response.json()["code"] == 20007


def test_role_permission_update(client, db_session):
    super_token = _login(client, "demo_super")
    admin_token = _login(client, "demo_admin")

    print("[测试] 步骤 1：保存管理员权限（移除用户管理）")
    permissions = [code for code in ROLE_PERMISSIONS["admin"] if code != "admin.accounts.view"]
    response = client.put(
        f"{ROLES_URL}/admin/permissions", json={"permissions": permissions}, headers=_headers(super_token)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["code"] == "admin" and data["editable"] is True
    assert "admin.accounts.view" not in data["permissions"]

    print("[测试] 步骤 2：管理员下一次请求访问用户列表返回 403/20005")
    assert client.get(USERS_URL, headers=_headers(admin_token)).json()["code"] == 20005

    print("[测试] 步骤 3：role.update 日志包含 before/after")
    db_session.expire_all()
    log = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "role.update").order_by(AuditLog.id.desc())
    )
    assert log.target_type == "role" and log.target_id == "admin"
    assert "admin.accounts.view" in log.detail["before"]
    assert "admin.accounts.view" not in log.detail["after"]

    print("[测试] 步骤 4：超管专属权限点不能授予管理员")
    response = client.put(
        f"{ROLES_URL}/admin/permissions",
        json={"permissions": ROLE_PERMISSIONS["admin"] + ["admin.audit.view"]},
        headers=_headers(super_token),
    )
    assert response.status_code == 409
    assert response.json()["code"] == 30015

    print("[测试] 步骤 5：最低权限校验")
    response = client.put(
        f"{ROLES_URL}/admin/permissions",
        json={"permissions": ["admin.accounts.view"]},
        headers=_headers(super_token),
    )
    assert response.status_code == 409
    assert response.json()["code"] == 30015
    response = client.put(
        f"{ROLES_URL}/user/permissions", json={"permissions": []}, headers=_headers(super_token)
    )
    assert response.status_code == 409
    assert response.json()["code"] == 30015

    print("[测试] 步骤 6：未知权限码、未知角色、超管角色")
    response = client.put(
        f"{ROLES_URL}/admin/permissions",
        json={"permissions": ROLE_PERMISSIONS["admin"] + ["admin.unknown"]},
        headers=_headers(super_token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == 10003
    assert client.put(
        f"{ROLES_URL}/root/permissions", json={"permissions": []}, headers=_headers(super_token)
    ).json()["code"] == 10003
    response = client.put(
        f"{ROLES_URL}/super_admin/permissions", json={"permissions": []}, headers=_headers(super_token)
    )
    assert response.status_code == 403
    assert response.json()["code"] == 20005

    print("[测试] 步骤 7：缺少 permissions 返回 10002")
    response = client.put(f"{ROLES_URL}/admin/permissions", json={}, headers=_headers(super_token))
    assert response.status_code == 400
    assert response.json()["code"] == 10002
    assert response.json()["message"] == "请选择权限点"

    print("[测试] 步骤 8：管理员不能编辑角色权限")
    response = client.put(
        f"{ROLES_URL}/user/permissions",
        json={"permissions": ROLE_PERMISSIONS["user"]},
        headers=_headers(admin_token),
    )
    assert response.status_code == 403
    assert response.json()["code"] == 20005


def test_audit_logs_dual_contract(client):
    super_token = _login(client, "demo_super")
    admin_token = _login(client, "demo_admin")

    print("[测试] 步骤 1：制造一条账号创建日志")
    _create_user(client, super_token, "demo_editor", ["user"])

    print("[测试] 步骤 2：按 6 号文档参数查询（operator/start_time/end_time/result=all）")
    now = datetime.now(timezone.utc)
    params = {
        "operator": "demo_super",
        "action": "account.create",
        "result": "all",
        "start_time": (now - timedelta(hours=1)).astimezone(timezone(timedelta(hours=8))).isoformat(),
        "end_time": (now + timedelta(hours=1)).astimezone(timezone(timedelta(hours=8))).isoformat(),
    }
    response = client.get(AUDIT_URL, params=params, headers=_headers(super_token))
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert items
    log = items[0]
    for field in (
        "log_id",
        "operator_user_id",
        "operator_username",
        "action",
        "target_type",
        "target_id",
        "result",
        "ip",
        "created_at",
    ):
        assert field in log
    assert log["log_id"] == log["id"]
    assert log["operator_username"] == log["username_snapshot"] == "demo_super"
    assert log["target_type"] == "account" and log["target_id"] == "demo_editor"

    print("[测试] 步骤 3：旧前端参数（keyword/created_from/created_to）仍然可用")
    legacy = client.get(
        AUDIT_URL,
        params={"keyword": "account.create", "created_from": "2026-01-01", "created_to": "2099-12-31"},
        headers=_headers(super_token),
    )
    assert legacy.status_code == 200
    assert legacy.json()["data"]["items"]

    print("[测试] 步骤 4：管理员和普通用户访问日志返回 403/20005")
    assert client.get(AUDIT_URL, headers=_headers(admin_token)).json()["code"] == 20005
    user_token = _login(client, "demo_user")
    assert client.get(AUDIT_URL, headers=_headers(user_token)).json()["code"] == 20005

    print("[测试] 步骤 5：结果参数与操作人长度校验")
    assert client.get(AUDIT_URL, params={"result": "unknown"}, headers=_headers(super_token)).json()["code"] == 10003
    assert client.get(AUDIT_URL, params={"operator": "x" * 21}, headers=_headers(super_token)).json()["code"] == 10004

    print("[测试] 步骤 6：日志详情与不存在错误码 30019")
    log_id = items[0]["log_id"]
    detail = client.get(f"{AUDIT_URL}/{log_id}", headers=_headers(super_token))
    assert detail.status_code == 200
    assert "user_agent" in detail.json()["data"]
    missing = client.get(f"{AUDIT_URL}/999999", headers=_headers(super_token))
    assert missing.status_code == 404
    assert missing.json()["code"] == 30019
    assert missing.json()["message"] == "操作日志不存在"


def test_not_found_writes_failed_audit(client, db_session):
    print("[测试] 步骤 1：编辑不存在的用户返回 404/30017")
    super_token = _login(client, "demo_super")
    response = client.patch(
        f"{USERS_URL}/999999", json={"display_name": "不存在"}, headers=_headers(super_token)
    )
    assert response.status_code == 404
    assert response.json()["code"] == 30017

    print("[测试] 步骤 2：业务失败写入 result=failed 审计")
    db_session.expire_all()
    log = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.action == "account.update", AuditLog.result == "failed")
        .order_by(AuditLog.id.desc())
    )
    assert log is not None
    assert log.target_type == "account"
    assert log.target_id == "999999"
    assert log.detail == {"reason": "用户不存在"}


def test_seed_converges_permission_catalog(db_session):
    print("[测试] 步骤 1：模拟旧库中权限点名称/分组与新目录不一致")
    permission = db_session.scalar(select(Permission).where(Permission.code == "admin.accounts.view"))
    permission.name = "旧名称"
    permission.group_name = "旧分组"
    permission.is_super_only = True
    db_session.commit()

    print("[测试] 步骤 2：重跑种子应收敛系统权限点目录")
    seed(db_session)
    db_session.expire_all()
    permission = db_session.scalar(select(Permission).where(Permission.code == "admin.accounts.view"))
    assert permission.name == "用户管理"
    assert permission.group_name == "管理后台"
    assert permission.is_super_only is False


def test_user_stats_batch_aggregation(client, db_session):
    print("[测试] 步骤 1：新建账号并写入一个会话与 Agent 调用")
    super_token = _login(client, "demo_super")
    user_id = _create_user(client, super_token, "demo_stats", ["user"]).json()["data"]["user_id"]
    session = CreativeSession(user_id=user_id, title="统计会话")
    db_session.add(session)
    db_session.flush()
    db_session.add(
        AgentRun(
            session_id=session.id,
            agent_code="planner",
            status="success",
            prompt_tokens=11,
            completion_tokens=7,
        )
    )
    db_session.commit()

    print("[测试] 步骤 2：详情统计应返回会话数与 Token 合计")
    detail = client.get(f"{USERS_URL}/{user_id}", headers=_headers(super_token)).json()["data"]
    assert detail["stats"]["session_count"] == 1
    assert detail["stats"]["token_total"] == 18

    print("[测试] 步骤 3：列表批量统计与详情一致")
    items = client.get(
        USERS_URL, params={"keyword": "demo_stats"}, headers=_headers(super_token)
    ).json()["data"]["items"]
    assert items[0]["stats"]["session_count"] == 1
    assert items[0]["stats"]["token_total"] == 18
