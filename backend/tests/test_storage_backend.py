"""存储后端切换单元测试（不依赖真实 MinIO / 数据库）。

覆盖：
- ``get_storage`` 按 ``STORAGE_BACKEND`` 选择适配器，且 MinIO 客户端惰性创建；
- MinIO 适配器的对象增删改查与错误码映射（30014 / 50003）；
- ``workspace.storage`` 门面对后端的选择与读写委托。
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET", "test-storage-backend-secret")

import pytest  # noqa: E402
from minio.error import S3Error  # noqa: E402

from app.modules.data import storage as data_storage  # noqa: E402
from app.modules.data.storage import (  # noqa: E402
    LocalStorageAdapter,
    MinioStorageAdapter,
    ObjectNotFound,
    StorageError,
    get_storage,
)


class FakeHttpResponse:
    """模拟 urllib3 的响应对象，供 MinIO 适配器读取。"""

    def __init__(self, content: bytes, mime: str) -> None:
        self._buffer = io.BytesIO(content)
        self.headers = {
            "Content-Type": mime,
            "Content-Length": str(len(content)),
            "ETag": '"fake-etag"',
            "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT",
        }
        self.closed = False

    def read(self, amt: int | None = None) -> bytes:
        return self._buffer.read(amt)

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        pass


class FakeMinioClient:
    """内存版 MinIO 客户端，只实现适配器用到的方法。"""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.error: Exception | None = None

    def _maybe_raise(self) -> None:
        if self.error is not None:
            raise self.error

    @staticmethod
    def _missing(bucket: str, key: str) -> S3Error:
        return S3Error(
            None,
            "NoSuchKey",
            "object not found",
            "resource",
            "request",
            "host",
            bucket_name=bucket,
            object_name=key,
        )

    def put_object(self, bucket, key, data, length, content_type=None):
        print(f"[测试] FakeMinio put bucket={bucket} key={key} length={length}")
        self._maybe_raise()
        payload = data.read(length) if hasattr(data, "read") else bytes(data)
        self.objects[(bucket, key)] = (payload, content_type or "application/octet-stream")
        return SimpleNamespace(etag='"fake-etag"')

    def get_object(self, bucket, key):
        print(f"[测试] FakeMinio get bucket={bucket} key={key}")
        self._maybe_raise()
        if (bucket, key) not in self.objects:
            raise self._missing(bucket, key)
        payload, mime = self.objects[(bucket, key)]
        return FakeHttpResponse(payload, mime)

    def stat_object(self, bucket, key):
        print(f"[测试] FakeMinio stat bucket={bucket} key={key}")
        self._maybe_raise()
        if (bucket, key) not in self.objects:
            raise self._missing(bucket, key)
        payload, mime = self.objects[(bucket, key)]
        return SimpleNamespace(
            size=len(payload),
            etag="fake-etag",
            content_type=mime,
            last_modified=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

    def copy_object(self, bucket, key, source):
        print(f"[测试] FakeMinio copy bucket={bucket} key={key}")
        self._maybe_raise()
        src_bucket = getattr(source, "bucket_name", bucket)
        src_key = getattr(source, "object_name", source)
        if (src_bucket, src_key) not in self.objects:
            raise self._missing(src_bucket, src_key)
        self.objects[(bucket, key)] = self.objects[(src_bucket, src_key)]
        return SimpleNamespace(etag='"fake-etag"')

    def remove_object(self, bucket, key):
        print(f"[测试] FakeMinio remove bucket={bucket} key={key}")
        self._maybe_raise()
        self.objects.pop((bucket, key), None)


def _minio_adapter(client: FakeMinioClient | None = None) -> MinioStorageAdapter:
    """构造不访问网络的 MinIO 适配器。"""
    return MinioStorageAdapter(client=client or FakeMinioClient(), bucket="esimage")


class TestGetStorage:
    def test_default_local(self, monkeypatch):
        print("[测试] STORAGE_BACKEND=local 时应返回本地适配器")
        monkeypatch.setattr(data_storage.config, "STORAGE_BACKEND", "local")
        assert isinstance(get_storage(), LocalStorageAdapter)

    def test_minio_is_lazy(self, monkeypatch):
        print("[测试] STORAGE_BACKEND=minio 时返回 MinIO 适配器且不建连")
        monkeypatch.setattr(data_storage.config, "STORAGE_BACKEND", "minio")
        adapter = get_storage()
        assert isinstance(adapter, MinioStorageAdapter)
        # 惰性创建：构造阶段不访问网络，客户端仍为空
        assert adapter._client is None

    def test_unknown_backend_rejected(self, monkeypatch):
        print("[测试] 未知存储后端应返回 50003")
        monkeypatch.setattr(data_storage.config, "STORAGE_BACKEND", "oss")
        with pytest.raises(StorageError) as excinfo:
            get_storage()
        assert excinfo.value.code == 50003


class TestMinioAdapter:
    def test_put_and_get_roundtrip(self):
        print("[测试] MinIO 适配器写入后应能读回相同内容")
        adapter = _minio_adapter()
        info = adapter.put_object("uploads/1/a.png", b"hello", "image/png")
        assert info.size == 5
        data, read_info = adapter.get_object("uploads/1/a.png")
        assert data == b"hello"
        assert read_info.size == 5
        assert read_info.mime == "image/png"

    def test_stat_exists_copy_delete(self):
        print("[测试] MinIO 适配器应支持 stat/exists/copy/delete")
        adapter = _minio_adapter()
        adapter.put_object("uploads/1/a.png", b"abc", "image/png")
        assert adapter.exists("uploads/1/a.png") is True
        assert adapter.exists("uploads/1/none.png") is False
        stat = adapter.stat_object("uploads/1/a.png")
        assert stat is not None and stat.size == 3

        adapter.copy_object("uploads/1/a.png", "archive/uploads/1/a.png")
        copied, _ = adapter.get_object("archive/uploads/1/a.png")
        assert copied == b"abc"

        adapter.delete_object("uploads/1/a.png")
        assert adapter.exists("uploads/1/a.png") is False
        # 删除不存在的对象应幂等成功
        adapter.delete_object("uploads/1/a.png")

    def test_missing_object_maps_to_30014(self):
        print("[测试] 读取缺失对象应映射为 30014")
        adapter = _minio_adapter()
        with pytest.raises(ObjectNotFound) as excinfo:
            adapter.get_object("uploads/1/missing.png")
        assert excinfo.value.code == 30014
        assert adapter.stat_object("uploads/1/missing.png") is None

    def test_copy_missing_source_maps_to_30014(self):
        print("[测试] 复制缺失源对象应映射为 30014")
        adapter = _minio_adapter()
        with pytest.raises(ObjectNotFound) as excinfo:
            adapter.copy_object("uploads/1/missing.png", "archive/x.png")
        assert excinfo.value.code == 30014

    def test_other_s3_error_maps_to_50003(self):
        print("[测试] 非缺失类 S3 错误应映射为 50003")
        client = FakeMinioClient()
        client.error = S3Error(
            None,
            "AccessDenied",
            "denied",
            "resource",
            "request",
            "host",
            bucket_name="esimage",
            object_name="uploads/1/a.png",
        )
        adapter = _minio_adapter(client)
        with pytest.raises(StorageError) as excinfo:
            adapter.get_object("uploads/1/a.png")
        assert excinfo.value.code == 50003

    def test_invalid_key_rejected_before_io(self):
        print("[测试] 非法对象键应在调用 MinIO 前拒绝")
        client = FakeMinioClient()
        adapter = _minio_adapter(client)
        with pytest.raises(StorageError) as excinfo:
            adapter.put_object("../escape.png", b"x")
        assert excinfo.value.code == 50003
        assert client.objects == {}

    def test_get_closes_response(self):
        print("[测试] MinIO 读取完成后必须关闭响应并归还连接")
        client = FakeMinioClient()
        adapter = _minio_adapter(client)
        adapter.put_object("uploads/1/a.png", b"hello", "image/png")

        captured = {}
        original_get = client.get_object

        def capture_get(bucket, key):
            response = original_get(bucket, key)
            captured["response"] = response
            return response

        client.get_object = capture_get
        adapter.get_object("uploads/1/a.png")
        assert captured["response"].closed is True

    def test_path_unsupported(self):
        print("[测试] MinIO 后端不应暴露本地路径")
        adapter = _minio_adapter()
        with pytest.raises(StorageError) as excinfo:
            adapter.path("uploads/1/a.png")
        assert excinfo.value.code == 50003


class TestWorkspaceFacade:
    def test_facade_delegates_to_minio(self, monkeypatch):
        print("[测试] workspace 门面应委托给 MinIO 适配器")
        from app.modules.workspace import storage as workspace_storage

        client = FakeMinioClient()
        backend = MinioStorageAdapter(client=client, bucket="esimage")
        monkeypatch.setattr(workspace_storage, "get_storage", lambda: backend)

        facade = workspace_storage.Storage()
        facade.save("uploads/1/a.png", b"payload")
        assert client.objects[("esimage", "uploads/1/a.png")][0] == b"payload"
        assert facade.read_bytes("uploads/1/a.png") == b"payload"
        assert facade.exists("uploads/1/a.png") is True
        facade.delete("uploads/1/a.png")
        assert facade.exists("uploads/1/a.png") is False

    def test_facade_local_path_and_stream(self, tmp_path, monkeypatch):
        print("[测试] workspace 门面在本地后端应保留 path 与流读取")
        from app.modules.workspace import storage as workspace_storage

        backend = LocalStorageAdapter(root=tmp_path)
        monkeypatch.setattr(workspace_storage, "get_storage", lambda: backend)

        facade = workspace_storage.Storage()
        facade.save("uploads/1/a.png", b"local")
        assert facade.read_bytes("uploads/1/a.png") == b"local"
        assert facade.path("uploads/1/a.png").is_file()
        with facade.open_stream("uploads/1/a.png") as stream:
            assert stream.read() == b"local"

    def test_facade_read_missing_maps_to_30014(self, tmp_path, monkeypatch):
        print("[测试] workspace 门面读取缺失文件应抛 30014")
        from app.modules.workspace import storage as workspace_storage

        backend = LocalStorageAdapter(root=tmp_path)
        monkeypatch.setattr(workspace_storage, "get_storage", lambda: backend)
        facade = workspace_storage.Storage()
        with pytest.raises(ObjectNotFound) as excinfo:
            facade.read_bytes("uploads/1/missing.png")
        assert excinfo.value.code == 30014
