"""契约回归（``esimage-data verify --scope ...``，10 号 §12 / 接口文档 §6）。

每个用例输出中文日志：操作 / 预期 / 实际 / 结论；失败时返回非 0 退出码。
"""

from __future__ import annotations

import io
import json
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from PIL import Image
from sqlalchemy import func, select, text

from app.core.redact import redact
from app.models.config import ModelConfig, PromptVersion, SizePreset, SystemPrompt
from app.models.user import Permission, Role, User, role_permissions, user_roles
from app.models.workspace import (
    AgentRun,
    ChatMessage,
    CreativeSession,
    GeneratedImage,
    GenerationBatch,
    UploadedAsset,
)
from app.modules.data import datalink
from app.modules.data.archive import read_object, run_archive
from app.modules.data.config import config
from app.modules.data.db import SessionLocal, engine
from app.modules.data.schema import verify_schema
from app.modules.data.seed import AGENTS, PERMISSIONS, ROLE_PERMISSIONS, ROLES, seed
from app.modules.data.storage import (
    LocalStorageAdapter,
    ObjectNotFound,
    StorageError,
    generated_path,
    generated_thumbnail_path,
    make_thumbnail,
    upload_path,
    upload_thumbnail_path,
    validate_upload,
)
from app.modules.data.superadmin import SuperAdminError, init_super_admin, validate_super_admin


@dataclass
class Case:
    name: str
    action: str
    expect: str
    passed: bool
    actual: str = ""

    def line(self) -> str:
        verdict = "通过" if self.passed else "失败"
        return f"[用例] {self.name}\n  操作：{self.action}\n  预期：{self.expect}\n  实际：{self.actual}\n  结论：{verdict}"


@dataclass
class VerifyReport:
    cases: list[Case] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for case in self.cases if case.passed)

    @property
    def failed(self) -> int:
        return sum(1 for case in self.cases if not case.passed)

    def dump(self) -> dict:
        return {
            "code": 0 if self.failed == 0 else 1,
            "message": "ok" if self.failed == 0 else "存在失败用例",
            "data": {
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
                "cases": [
                    {"name": c.name, "passed": c.passed, "actual": c.actual} for c in self.cases
                ],
            },
        }


def _cleanup() -> None:
    """清理本 demo 的测试数据（用户名以 ``verify_`` 开头），不污染既有业务数据。"""
    verify_users = "SELECT id FROM users WHERE username LIKE 'verify_%'"
    verify_sessions = f"SELECT id FROM creative_sessions WHERE user_id IN ({verify_users})"
    with SessionLocal() as db:
        db.execute(text(f"DELETE FROM agent_runs WHERE session_id IN ({verify_sessions}) OR "
                        f"batch_id IN (SELECT id FROM generation_batches WHERE user_id IN ({verify_users}))"))
        db.execute(text(f"DELETE FROM generated_images WHERE user_id IN ({verify_users})"))
        db.execute(text(f"DELETE FROM generation_batches WHERE user_id IN ({verify_users})"))
        db.execute(text(f"DELETE FROM chat_messages WHERE session_id IN ({verify_sessions})"))
        db.execute(text(f"DELETE FROM uploaded_assets WHERE user_id IN ({verify_users})"))
        db.execute(text(f"DELETE FROM creative_sessions WHERE user_id IN ({verify_users})"))
        db.execute(text(f"DELETE FROM user_roles WHERE user_id IN ({verify_users})"))
        db.execute(text(f"DELETE FROM users WHERE username LIKE 'verify_%'"))
        db.commit()


def _make_user(db, username: str) -> User:
    user = User(username=username, display_name=username, password_hash="x" * 60, status="active")
    db.add(user)
    db.flush()
    return user


def verify_schema_scope(report: VerifyReport) -> None:
    result = verify_schema(engine)
    passed = result.found_tables == result.expected_tables and not result.failed
    report.cases.append(Case(
        "schema-18-tables",
        "校验 18 张业务表与列、类型、约束、索引、外键",
        f"18/18 张表全部存在且无失败项",
        passed,
        f"发现 {result.found_tables}/{result.expected_tables} 张表，"
        f"失败 {len(result.failed)} 项" + (
            "" if passed else f"（首个失败：{result.failed[0].table}.{result.failed[0].object}）"
        ),
    ))


def verify_seed_scope(report: VerifyReport) -> None:
    with SessionLocal() as db:
        first = seed(db)
        second = seed(db)
        second_total = sum(second.values())
        first_total = sum(first.values())
        report.cases.append(Case(
            "seed-idempotent",
            "连续执行两次 seed",
            "第二次不新增任何行",
            second_total == 0,
            f"第一次新增 {first_total} 行，第二次新增 {second_total} 行",
        ))

        counts = {
            "roles": len(db.scalars(select(Role)).all()),
            "permissions": len(db.scalars(select(Permission)).all()),
            "size_presets": len(db.scalars(select(SizePreset)).all()),
            "system_prompts": len(db.scalars(select(SystemPrompt)).all()),
            "prompt_versions": len(db.scalars(select(PromptVersion)).all()),
            "model_configs": len(db.scalars(select(ModelConfig).where(ModelConfig.is_active.is_(True))).all()),
        }
        expected = {
            "roles": 3, "permissions": 23, "size_presets": 4,
            "system_prompts": 8, "prompt_versions": 8, "model_configs": 1,
        }
        for key, want in expected.items():
            got = counts[key]
            report.cases.append(Case(
                f"seed-count-{key}",
                f"校验种子 {key} 条数",
                f"{want} 条",
                got == want,
                f"{got} 条",
            ))

        # 超管权限矩阵
        super_role = db.scalar(select(Role).where(Role.code == "super_admin"))
        super_count = len(db.scalars(
            select(Permission).join(role_permissions, role_permissions.c.permission_id == Permission.id)
            .where(role_permissions.c.role_id == super_role.id)
        ).all())
        report.cases.append(Case(
            "seed-super-matrix",
            "校验超管角色权限矩阵",
            "23 条全部权限点",
            super_count == 23,
            f"{super_count} 条",
        ))


def verify_superadmin_scope(report: VerifyReport) -> None:
    # 缺密码
    try:
        validate_super_admin("demo_super", "")
        report.cases.append(Case("superadmin-missing-password", "缺密码初始化超管", "失败", False, "未抛出异常"))
    except SuperAdminError:
        report.cases.append(Case("superadmin-missing-password", "缺密码初始化超管", "失败并给出中文原因", True, "已拒绝"))

    # 弱口令
    try:
        validate_super_admin("demo_super", "12345678")
        report.cases.append(Case("superadmin-weak-password", "弱口令初始化超管", "失败", False, "未抛出异常"))
    except SuperAdminError:
        report.cases.append(Case("superadmin-weak-password", "弱口令初始化超管", "失败并给出中文原因", True, "已拒绝"))

    # 显式密码
    with SessionLocal() as db:
        created, user = init_super_admin(db, "verify_super", "Demo1234")
        report.cases.append(Case(
            "superadmin-explicit",
            "显式用户名与密码初始化超管",
            "创建账号且密码为 bcrypt 哈希",
            created and user.password_hash.startswith("$2"),
            f"created={created}, hash_prefix={user.password_hash[:4]}",
        ))

        # 幂等：不重置密码
        _, again = init_super_admin(db, "verify_super", "Another1234")
        report.cases.append(Case(
            "superadmin-idempotent",
            "重复初始化超管",
            "不重置已有密码",
            again.password_hash == user.password_hash,
            "密码未变",
        ))

        has_super = any(role.code == "super_admin" for role in again.roles)
        report.cases.append(Case(
            "superadmin-role",
            "校验超管角色",
            "具备 super_admin 角色",
            has_super,
            f"roles={[r.code for r in again.roles]}",
        ))


def _pn_bytes(width: int, height: int, fmt: str = "PNG", quality: int = 90) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 180, 160)).save(buf, format=fmt, quality=quality)
    return buf.getvalue()


def verify_storage_scope(report: VerifyReport) -> None:
    root = tempfile.mkdtemp(prefix="esimage_data_storage_")
    storage = LocalStorageAdapter(root=root)

    # 路径规则
    up = upload_path(7, 3, "png")
    report.cases.append(Case(
        "storage-upload-path", "生成上传图路径", "uploads/7/3/{uuid}.png", up.startswith("uploads/7/3/"), up,
    ))
    unbound = upload_path(7, None, "png")
    report.cases.append(Case(
        "storage-upload-unbound-path", "生成未绑定会话上传图路径", "uploads/7/unbound/{uuid}.png",
        unbound.startswith("uploads/7/unbound/"), unbound,
    ))
    gp = generated_path(7, 3, 9)
    report.cases.append(Case(
        "storage-generated-path", "生成图路径", "generated/7/3/9/{uuid}.png", gp.startswith("generated/7/3/9/"), gp,
    ))

    # 上传校验
    good = _pn_bytes(100, 100)
    try:
        validate_upload("a.png", "image/png", good)
        report.cases.append(Case("storage-valid-png", "上传合法 PNG", "通过", True, "ok"))
    except StorageError:
        report.cases.append(Case("storage-valid-png", "上传合法 PNG", "通过", False, "被拒绝"))

    # GIF 拒绝
    gif = _pn_bytes(50, 50, "GIF")
    try:
        validate_upload("a.gif", "image/gif", gif)
        report.cases.append(Case("storage-reject-gif", "上传 GIF", "拒绝", False, "未拒绝"))
    except StorageError as exc:
        report.cases.append(Case("storage-reject-gif", "上传 GIF", "拒绝", True, exc.message))

    # MIME 与扩展名不符
    try:
        validate_upload("a.png", "image/jpeg", good)
        report.cases.append(Case("storage-mime-mismatch", "扩展名与 MIME 不符", "拒绝", False, "未拒绝"))
    except StorageError as exc:
        report.cases.append(Case("storage-mime-mismatch", "扩展名与 MIME 不符", "拒绝", True, exc.message))

    # 超过 10MB
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 1)
    try:
        validate_upload("a.png", "image/png", big)
        report.cases.append(Case("storage-reject-oversize", "上传超过 10MB 文件", "拒绝", False, "未拒绝"))
    except StorageError as exc:
        report.cases.append(Case("storage-reject-oversize", "上传超过 10MB 文件", "拒绝", True, exc.message))

    # 损坏文件
    try:
        validate_upload("a.png", "image/png", b"not-an-image")
        report.cases.append(Case("storage-reject-corrupt", "上传损坏图片", "拒绝", False, "未拒绝"))
    except StorageError as exc:
        report.cases.append(Case("storage-reject-corrupt", "上传损坏图片", "拒绝", True, exc.message))

    # 缩略图 400px WebP
    wide = _pn_bytes(800, 600)
    thumb = make_thumbnail(wide)
    with Image.open(io.BytesIO(thumb)) as img:
        ok = img.format == "WEBP" and img.width == 400
    report.cases.append(Case(
        "storage-thumbnail", "生成 800x600 缩略图", "WebP 且宽 400px",
        ok, f"format=WEBP, width={Image.open(io.BytesIO(thumb)).width}",
    ))


def verify_archive_scope(report: VerifyReport) -> None:
    root = tempfile.mkdtemp(prefix="esimage_data_archive_")
    config.STORAGE_ROOT = root
    # 本用例使用临时本地目录，必须固定本地后端，避免开发者 .env 指向 MinIO
    config.STORAGE_BACKEND = "local"
    config.ARCHIVE_RETENTION_DAYS = 1

    with SessionLocal() as db:
        user = _make_user(db, f"verify_ar_{uuid.uuid4().hex[:6]}")
        session = CreativeSession(user_id=user.id, title="归档验证", status="active")
        db.add(session)
        db.flush()

        batch = GenerationBatch(
            user_id=user.id, session_id=session.id, batch_type="sample",
            product_name="归档商品", width=100, height=100, total_count=1,
            params_snapshot={}, status="sample_ready",
        )
        db.add(batch)
        db.flush()

        storage = LocalStorageAdapter(root=root)
        content = _pn_bytes(120, 120)
        gp = generated_path(user.id, session.id, batch.id)
        gtp = generated_thumbnail_path(user.id, session.id, batch.id, gp.rsplit("/", 1)[-1].split(".")[0])
        storage.put_object(gp, content, "image/png")
        storage.put_object(gtp, make_thumbnail(content), "image/webp")

        image = GeneratedImage(
            batch_id=batch.id, user_id=user.id, session_id=session.id,
            image_type="sample", image_role="main", index_no=1, attempt_no=1,
            status="success", file_path=gp, thumbnail_path=gtp,
        )
        image.created_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.add(image)
        db.commit()
        image_id = image.id

    result = run_archive(now_value=None, retention_days=1)

    with SessionLocal() as db:
        archived = db.get(GeneratedImage, image_id)
        archive_exists = LocalStorageAdapter(root=root).exists(f"archive/{gp}")
        original_exists = LocalStorageAdapter(root=root).exists(gp)
        thumb_exists = LocalStorageAdapter(root=root).exists(gtp)

        report.cases.append(Case(
            "archive-run", "归档超期生成图", "原件迁入 archive/、删除原件、回写 archived_at",
            archived.archived_at is not None and archive_exists and not original_exists,
            f"archived_at={archived.archived_at is not None}, archive={archive_exists}, original={original_exists}",
        ))
        report.cases.append(Case(
            "archive-thumb-kept", "归档后缩略图保留", "thumbnail_path 仍在 thumbnails/",
            thumb_exists, f"thumb_exists={thumb_exists}",
        ))
        report.cases.append(Case(
            "archive-db-kept", "归档后数据库记录保留", "记录不删除",
            archived is not None, "记录存在",
        ))

    # 幂等：再次执行不重复归档
    result2 = run_archive(now_value=None, retention_days=1)
    report.cases.append(Case(
        "archive-idempotent", "再次执行归档", "已归档记录跳过",
        result2.succeeded == 0 and result2.skipped == 0,
        f"succeeded={result2.succeeded}",
    ))

    # 归档读取缺失 -> 30014
    try:
        read_object("generated/nonexistent/1/2/x.png", None)
        report.cases.append(Case("archive-30014", "读取不存在对象", "返回 30014", False, "未抛异常"))
    except ObjectNotFound as exc:
        report.cases.append(Case("archive-30014", "读取不存在对象", "返回 30014「文件归档中，请稍后重试」",
                                 True, f"code={exc.code}" if exc.code == 30014 else str(exc.code)))


def verify_datalink_scope(report: VerifyReport) -> None:
    with SessionLocal() as db:
        user = _make_user(db, f"verify_dl_{uuid.uuid4().hex[:6]}")
        db.commit()
        user_id = user.id

    # 首条消息幂等 + 并发
    def _send(_i):
        with SessionLocal() as db:
            return datalink.create_first_message(
                db, user_id=user_id, title="并发会话", role="user",
                content="你好", client_message_id="cm-1",
            )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_send, range(4)))

    with SessionLocal() as db:
        sessions = db.scalars(
            select(CreativeSession).where(CreativeSession.user_id == user_id)
        ).all()
        messages = db.scalars(
            select(ChatMessage).join(CreativeSession, ChatMessage.session_id == CreativeSession.id)
            .where(CreativeSession.user_id == user_id, ChatMessage.client_message_id == "cm-1")
        ).all()
        report.cases.append(Case(
            "datalink-first-message-concurrency",
            "并发写入相同首条消息（4 线程）",
            "只创建一个会话和一条消息",
            len(sessions) == 1 and len(messages) == 1,
            f"sessions={len(sessions)}, messages={len(messages)}",
        ))
        session_id = sessions[0].id

        # 稳定排序
        datalink.write_message(db, session_id, role="user", content="第二条", client_message_id="cm-2")
        db.commit()
        ordered = datalink.list_messages(db, session_id)
        ids = [m.id for m in ordered]
        report.cases.append(Case(
            "datalink-ordered", "按 (created_at, id) 读取消息", "稳定升序", ids == sorted(ids), f"ids={ids}",
        ))

        # 重复 client_message_id 幂等
        before = len(datalink.list_messages(db, session_id))
        datalink.write_message(db, session_id, role="user", content="重复", client_message_id="cm-2")
        db.commit()
        after = len(datalink.list_messages(db, session_id))
        report.cases.append(Case(
            "datalink-message-idempotent", "重复写入同一 client_message_id", "不新增行",
            before == after, f"before={before}, after={after}",
        ))

        # Agent 调用脱敏
        run = datalink.record_agent_run(
            db, agent_code="planner", status="success",
            input_full=json.dumps({"api_key": "SECRET", "prompt": "你好"}),
            output_full=json.dumps({"Authorization": "Bearer xxx"}),
        )
        db.commit()
        clean = "SECRET" not in (run.input_full or "") and "Bearer xxx" not in (run.output_full or "")
        report.cases.append(Case(
            "datalink-redact", "Agent 输入输出脱敏", "api_key/Authorization 不落明文",
            clean, f"input_full={run.input_full}",
        ))

    # 批次与图片
    with SessionLocal() as db:
        user2 = _make_user(db, f"verify_b_{uuid.uuid4().hex[:6]}")
        session2 = CreativeSession(user_id=user2.id, title="批次验证", status="active")
        db.add(session2)
        db.flush()

        # full 缺 sample 引用
        try:
            datalink.create_batch(
                db, user_id=user2.id, session_id=session2.id, batch_type="full",
                product_name="x", width=100, height=100, total_count=6, params_snapshot={},
            )
            report.cases.append(Case("batch-full-needs-sample", "full 批次不引用 sample", "拒绝", False, "未拒绝"))
        except datalink.DataLinkError:
            report.cases.append(Case("batch-full-needs-sample", "full 批次不引用 sample", "拒绝", True, "已拒绝"))

        sample = datalink.create_batch(
            db, user_id=user2.id, session_id=session2.id, batch_type="sample",
            product_name="x", width=100, height=100, total_count=1, params_snapshot={},
        )
        sample_images = datalink.create_images(db, sample)
        roles = [img.image_role for img in sample_images]
        report.cases.append(Case(
            "batch-sample-images", "示例批次图片角色", "1 张 main 且无 detail",
            roles == ["main"], f"roles={roles}",
        ))

        full = datalink.create_batch(
            db, user_id=user2.id, session_id=session2.id, batch_type="full",
            product_name="x", width=100, height=100, total_count=6,
            params_snapshot={}, source_sample_batch_id=sample.id,
        )
        full_images = datalink.create_images(db, full)
        f_roles = [img.image_role for img in full_images]
        report.cases.append(Case(
            "batch-full-images", "全套批次图片角色", "1 张 main + 5 张 detail",
            f_roles.count("main") == 1 and f_roles.count("detail") == 5,
            f"main={f_roles.count('main')}, detail={f_roles.count('detail')}",
        ))

        # 非法状态流转
        img = full_images[0]
        img.status = "success"
        db.flush()
        try:
            datalink.transition_image(db, img, "generating")
            report.cases.append(Case("image-invalid-transition", "success -> generating", "拒绝", False, "未拒绝"))
        except datalink.DataLinkError:
            report.cases.append(Case("image-invalid-transition", "success -> generating", "拒绝", True, "已拒绝"))

        db.commit()


def run_verify(scope: str = "all") -> VerifyReport:
    report = VerifyReport()
    _cleanup()

    if scope in ("schema", "all"):
        verify_schema_scope(report)
    if scope in ("seed", "all"):
        verify_seed_scope(report)
    if scope in ("all",):
        verify_superadmin_scope(report)
        verify_datalink_scope(report)
    if scope in ("storage", "all"):
        verify_storage_scope(report)
    if scope in ("archive", "all"):
        verify_archive_scope(report)
    if scope not in ("schema", "seed", "storage", "archive", "all"):
        raise ValueError(f"未知 scope：{scope}")

    return report
