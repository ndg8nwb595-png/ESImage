"""MinIO 真实后端集成测试（默认跳过，需本机 Docker MinIO）。

运行方式（PowerShell）：
    $env:MINIO_TEST_ENDPOINT="127.0.0.1:9002"
    $env:MINIO_TEST_ACCESS_KEY="esimage"
    $env:MINIO_TEST_SECRET_KEY="esimage123"
    python -m pytest tests/test_storage_minio_integration.py -q

未设置 ``MINIO_TEST_ENDPOINT`` 时整体跳过，保证 CI 与无 MinIO 环境不受影响。
"""

from __future__ import annotations

import os
import uuid

import pytest

MINIO_ENDPOINT = os.getenv("MINIO_TEST_ENDPOINT", "")
MINIO_ACCESS_KEY = os.getenv("MINIO_TEST_ACCESS_KEY", "esimage")
MINIO_SECRET_KEY = os.getenv("MINIO_TEST_SECRET_KEY", "esimage123")
MINIO_BUCKET = os.getenv("MINIO_TEST_BUCKET", "esimage")

pytestmark = pytest.mark.skipif(
    not MINIO_ENDPOINT,
    reason="未设置 MINIO_TEST_ENDPOINT，跳过真实 MinIO 集成测试",
)


def _adapter():
    from app.modules.data.storage import MinioStorageAdapter

    return MinioStorageAdapter(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        bucket=MINIO_BUCKET,
    )


def _key(name: str) -> str:
    """每次使用独立前缀，避免污染演示桶。"""
    return f"_pytest/{uuid.uuid4().hex}/{name}"


def test_minio_roundtrip_against_real_server():
    print("[测试] 连接真实 MinIO 并执行写入/读取/复制/删除")
    from app.modules.data.storage import ObjectNotFound

    adapter = _adapter()
    src = _key("a.bin")
    dst = _key("archive/a.bin")
    payload = b"esimage-minio-integration"

    try:
        print(f"[测试] 写入对象 {src}")
        info = adapter.put_object(src, payload, "application/octet-stream")
        assert info.size == len(payload)

        print("[测试] 读取并校验内容")
        content, read_info = adapter.get_object(src)
        assert content == payload
        assert read_info.size == len(payload)

        print("[测试] 校验 exists/stat")
        assert adapter.exists(src) is True
        assert adapter.stat_object(src) is not None

        print("[测试] 复制到归档前缀")
        adapter.copy_object(src, dst)
        assert adapter.get_object(dst)[0] == payload

        print("[测试] 删除后再次读取应返回 30014")
        adapter.delete_object(src)
        assert adapter.exists(src) is False
        with pytest.raises(ObjectNotFound) as excinfo:
            adapter.get_object(src)
        assert excinfo.value.code == 30014
    finally:
        print("[测试] 清理本次写入的对象")
        for key in (src, dst):
            try:
                adapter.delete_object(key)
            except Exception as exc:  # noqa: BLE001 - 清理失败不掩盖断言结果
                print(f"[测试] 清理失败 key={key} reason={exc}")


def test_facade_roundtrip_against_real_server():
    print("[测试] 统一存储门面对接真实 MinIO")
    from app.modules.workspace.storage import Storage

    backend = _adapter()
    facade = Storage(backend=backend)
    key = _key("facade.bin")
    try:
        facade.save(key, b"facade-through-minio")
        assert facade.read_bytes(key) == b"facade-through-minio"
        assert facade.exists(key) is True
    finally:
        facade.delete(key)
    print("[测试] 门面读写与删除完成")
