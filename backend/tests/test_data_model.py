"""10 号数据底座纯函数单元测试（不依赖数据库）。

覆盖：脱敏、对象键校验、路径规则、上传校验、缩略图、超管口令校验。
数据库相关的完整契约由 ``esimage-data verify --scope all`` 覆盖。
"""

from __future__ import annotations

import io
import os

os.environ.setdefault("JWT_SECRET", "test-data-model-secret")

from PIL import Image  # noqa: E402

from app.core.redact import redact  # noqa: E402
from app.modules.data.storage import (  # noqa: E402
    StorageError,
    generated_path,
    make_thumbnail,
    upload_path,
    validate_object_key,
    validate_upload,
)
from app.modules.data.superadmin import SuperAdminError, validate_super_admin  # noqa: E402


def _png(width: int = 100, height: int = 100, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (180, 160, 140)).save(buf, format=fmt)
    return buf.getvalue()


class TestRedact:
    def test_nested_json(self):
        value = {"api_key": "sk-123", "nested": {"Authorization": "Bearer x", "keep": "v"}}
        result = redact(value)
        assert result["api_key"] == "[REDACTED]"
        assert result["nested"]["Authorization"] == "[REDACTED]"
        assert result["nested"]["keep"] == "v"

    def test_case_and_separator_insensitive(self):
        assert redact({"apiKey": "x"})["apiKey"] == "[REDACTED]"
        assert redact({"API-KEY": "x"})["API-KEY"] == "[REDACTED]"
        assert redact({"password_hash": "x"})["password_hash"] == "[REDACTED]"
        assert redact({"client_secret": "x"})["client_secret"] == "[REDACTED]"

    def test_does_not_redact_tokens(self):
        assert redact({"token_in": 5, "prompt_tokens": 10}) == {"token_in": 5, "prompt_tokens": 10}

    def test_string_json_value(self):
        result = redact('{"api_key": "abc"}')
        assert '"api_key": "[REDACTED]"' in result


class TestObjectKey:
    def test_valid(self):
        assert validate_object_key("uploads/1/2/a.png") == "uploads/1/2/a.png"

    def test_reject_leading_slash(self):
        try:
            validate_object_key("/uploads/a.png")
            assert False
        except StorageError:
            pass

    def test_reject_dotdot(self):
        try:
            validate_object_key("uploads/../a.png")
            assert False
        except StorageError:
            pass


class TestPaths:
    def test_upload_bound(self):
        assert upload_path(7, 3, "png").startswith("uploads/7/3/")

    def test_upload_unbound(self):
        assert upload_path(7, None, "png").startswith("uploads/7/unbound/")

    def test_generated(self):
        assert generated_path(7, 3, 9).startswith("generated/7/3/9/")


class TestValidateUpload:
    def test_valid_png(self):
        assert validate_upload("a.png", "image/png", _png())["ext"] == "png"

    def test_reject_gif(self):
        try:
            validate_upload("a.gif", "image/gif", _png(fmt="GIF"))
            assert False
        except StorageError:
            pass

    def test_reject_mime_mismatch(self):
        try:
            validate_upload("a.png", "image/jpeg", _png())
            assert False
        except StorageError:
            pass

    def test_reject_corrupt(self):
        try:
            validate_upload("a.png", "image/png", b"not-an-image")
            assert False
        except StorageError:
            pass

    def test_reject_oversize(self):
        big = b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 1)
        try:
            validate_upload("a.png", "image/png", big)
            assert False
        except StorageError:
            pass


class TestThumbnail:
    def test_width_capped(self):
        thumb = make_thumbnail(_png(800, 600))
        with Image.open(io.BytesIO(thumb)) as img:
            assert img.format == "WEBP"
            assert img.width == 400


class TestSuperAdmin:
    def test_missing_password(self):
        try:
            validate_super_admin("demo", "")
            assert False
        except SuperAdminError:
            pass

    def test_weak_password(self):
        try:
            validate_super_admin("demo", "12345678")
            assert False
        except SuperAdminError:
            pass

    def test_short_password(self):
        try:
            validate_super_admin("demo", "Ab1")
            assert False
        except SuperAdminError:
            pass

    def test_valid(self):
        validate_super_admin("demo_super", "Demo1234")
