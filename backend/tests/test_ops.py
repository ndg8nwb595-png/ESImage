"""11 号部署与运维后端测试：健康检测、X-Request-ID、SSE 探针、初始超管、ops.selftest。"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from app.core.config import settings
from app.core.context import request_id_var, user_id_var
from app.core.request_id import _valid_request_id


# ---------------------------------------------------------------------------
# 健康检测逻辑（不依赖真实数据库/Redis/MinIO）
# ---------------------------------------------------------------------------
def test_run_health_checks_all_ok(monkeypatch):
    import app.modules.ops.health as health

    monkeypatch.setattr(health, "_check_database", lambda: "ok")
    monkeypatch.setattr(health, "_check_redis", lambda: "ok")
    monkeypatch.setattr(health, "_check_minio", lambda: "ok")
    assert health.run_health_checks() == {"database": "ok", "redis": "ok", "minio": "ok"}


def test_run_health_checks_single_error_no_short_circuit(monkeypatch):
    import app.modules.ops.health as health

    monkeypatch.setattr(health, "_check_database", lambda: "ok")
    monkeypatch.setattr(health, "_check_redis", lambda: "error")
    monkeypatch.setattr(health, "_check_minio", lambda: "ok")
    assert health.run_health_checks() == {"database": "ok", "redis": "error", "minio": "ok"}


def test_health_check_timeout_falls_back_to_error(monkeypatch):
    import app.modules.ops.health as health

    def _slow():
        raise Exception("unreachable")

    monkeypatch.setattr(health, "_check_database", _slow)
    monkeypatch.setattr(health, "_check_redis", lambda: "ok")
    monkeypatch.setattr(health, "_check_minio", lambda: "ok")
    assert health.run_health_checks()["database"] == "error"


# ---------------------------------------------------------------------------
# 双健康探针接口（monkeypatch 掉真实依赖检测）
# ---------------------------------------------------------------------------
def _patch_checks(monkeypatch, database="ok", redis="ok", minio="ok"):
    import app.modules.ops.router as router

    monkeypatch.setattr(
        router,
        "run_health_checks",
        lambda: {"database": database, "redis": redis, "minio": minio},
    )


def test_health_bare_ok(client, monkeypatch):
    _patch_checks(monkeypatch)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok", "minio": "ok"}}
    assert resp.headers["cache-control"] == "no-store"


def test_health_bare_degraded(client, monkeypatch):
    _patch_checks(monkeypatch, redis="error")
    resp = client.get("/api/health")
    assert resp.status_code == 503
    assert resp.json() == {
        "status": "degraded",
        "checks": {"database": "ok", "redis": "error", "minio": "ok"},
    }


def test_health_v1_ok(client, monkeypatch):
    _patch_checks(monkeypatch)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "ok"


def test_health_v1_degraded(client, monkeypatch):
    _patch_checks(monkeypatch, minio="error")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == 50001
    assert body["message"] == "服务依赖不可用"
    assert body["data"]["status"] == "degraded"
    assert body["data"]["checks"]["minio"] == "error"


# ---------------------------------------------------------------------------
# X-Request-ID 中间件
# ---------------------------------------------------------------------------
def test_request_id_reuse(client):
    resp = client.get("/api/health", headers={"X-Request-ID": "valid-id-1234"})
    assert resp.headers["x-request-id"] == "valid-id-1234"


def test_request_id_invalid_regenerated(client):
    # 非法值必须使用 ASCII：HTTP 头按 ascii 编码，中文会先触发 UnicodeEncodeError；
    # 空格与感叹号均不符合 ^[A-Za-z0-9_-]{8,64}$，仍能覆盖“非法则重新生成”的分支。
    invalid_id = "bad id!"
    resp = client.get("/api/health", headers={"X-Request-ID": invalid_id})
    rid = resp.headers["x-request-id"]
    assert rid != invalid_id
    assert _valid_request_id(rid)


def test_request_id_missing_generated(client):
    resp = client.get("/api/health")
    assert _valid_request_id(resp.headers["x-request-id"])


# ---------------------------------------------------------------------------
# SSE 演示探针
# ---------------------------------------------------------------------------
def test_sse_probe_stream_content(monkeypatch):
    monkeypatch.setenv("SSE_PROBE_INTERVAL", "0")
    from app.modules.ops.stream import sse_probe_stream

    async def collect():
        response = sse_probe_stream("rid-1234")
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return "".join(chunks)

    text = asyncio.run(collect())
    assert "event: meta" in text
    assert "event: delta" in text
    assert "event: done" in text
    assert '"request_id": "rid-1234"' in text


def test_sse_probe_route_headers(client, monkeypatch):
    monkeypatch.setenv("SSE_PROBE_INTERVAL", "0")
    resp = client.get("/api/v1/sessions/_probe/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"
    assert "event: meta" in resp.text
    assert "event: done" in resp.text


# ---------------------------------------------------------------------------
# 初始超管校验
# ---------------------------------------------------------------------------
def test_validate_initial_admin_ok(monkeypatch):
    from app.modules.ops.seed import validate_initial_admin

    monkeypatch.setattr(settings, "ADMIN_INITIAL_USERNAME", "esimage_admin")
    monkeypatch.setattr(settings, "ADMIN_INITIAL_PASSWORD", "Str0ng-P@ssword!")
    assert validate_initial_admin() == ("esimage_admin", "Str0ng-P@ssword!")


@pytest.mark.parametrize(
    "username,password",
    [
        ("ab", "Str0ng-P@ssword!"),  # 用户名过短
        ("bad name", "Str0ng-P@ssword!"),  # 用户名含非法字符
        ("esimage_admin", ""),  # 密码缺失
        ("esimage_admin", "short1"),  # 密码过短
        ("esimage_admin", "alllowercase123"),  # 少于 3 类字符
        ("esimage_admin", "esimage_admin"),  # 与用户名相同
    ],
)
def test_validate_initial_admin_rejects(monkeypatch, username, password):
    from app.modules.ops.seed import InitialAdminConfigError, validate_initial_admin

    monkeypatch.setattr(settings, "ADMIN_INITIAL_USERNAME", username)
    monkeypatch.setattr(settings, "ADMIN_INITIAL_PASSWORD", password)
    with pytest.raises(InitialAdminConfigError):
        validate_initial_admin()


# ---------------------------------------------------------------------------
# ops.selftest（纯函数，不依赖 Redis/Celery 运行时）
# ---------------------------------------------------------------------------
def test_selftest_pure():
    from app.tasks import ops as ops_tasks

    token = request_id_var.set("req-before")
    try:
        result = ops_tasks.selftest(request_id="rid-1", delay_ms=1)
    finally:
        request_id_var.reset(token)
    assert result["status"] == "ok"
    assert result["request_id"] == "rid-1"
    assert result["duration_ms"] >= 0


def test_selftest_generates_request_id_when_missing():
    from app.tasks import ops as ops_tasks

    result = ops_tasks.selftest()
    assert result["status"] == "ok"
    assert result["request_id"]


# ---------------------------------------------------------------------------
# JSON 结构化日志字段
# ---------------------------------------------------------------------------
def test_json_formatter_includes_required_fields(monkeypatch):
    import logging

    from app.core.logging import JsonFormatter

    formatter = JsonFormatter()
    token = request_id_var.set("rid-log")
    try:
        record = logging.LogRecord(
            name="esimage.ops", level=logging.INFO, pathname="x", lineno=1,
            msg="hello", args=(), exc_info=None,
        )
        payload = json.loads(formatter.format(record))
    finally:
        request_id_var.reset(token)
    assert payload["level"] == "INFO"
    assert payload["module"] == "esimage.ops"
    assert payload["request_id"] == "rid-log"
    assert payload["user_id"] is None
    assert payload["message"] == "hello"
