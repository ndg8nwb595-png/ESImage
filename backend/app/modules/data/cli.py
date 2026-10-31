"""``esimage-data`` 命令行入口（10 号数据底座）。

用法（在 backend/ 目录，或经 ``pip install -e .`` 安装后直接调用）：
    esimage-data db upgrade [revision]
    esimage-data db downgrade <revision>
    esimage-data db current
    esimage-data db verify
    esimage-data seed
    esimage-data init-super-admin
    esimage-data archive run [--now ISO8601]
    esimage-data verify [--scope schema|seed|storage|archive|all]
    esimage-data bootstrap
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# 数据底座命令不依赖业务 JWT；占位密钥仅供 app.core.config 加载，避免其抛错。
os.environ.setdefault("JWT_SECRET", "esimage-data-cli-placeholder-not-for-auth")

# Windows 控制台默认 GBK，统一改为 UTF-8，避免中文日志乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover - 非 Windows
    pass

from app.modules.data.archive import run_archive  # noqa: E402
from app.modules.data.config import config  # noqa: E402
from app.modules.data.db import SessionLocal, check_database, engine  # noqa: E402
from app.modules.data.migrations import current_revision, downgrade, upgrade  # noqa: E402
from app.modules.data.schema import verify_schema  # noqa: E402
from app.modules.data.seed import seed  # noqa: E402
from app.modules.data.superadmin import SuperAdminError, init_super_admin  # noqa: E402
from app.modules.data.verify import run_verify  # noqa: E402


def _fail(message: str, code: int = 1) -> int:
    print(f"[错误] {message}")
    return code


def cmd_db(args: argparse.Namespace) -> int:
    if args.action == "upgrade":
        upgrade(args.revision or "head")
        print(f"[迁移] 已升级到 {args.revision or 'head'}（当前 {current_revision()}）")
        return 0
    if args.action == "downgrade":
        downgrade(args.revision)
        print(f"[迁移] 已回滚到 {args.revision}（当前 {current_revision()}）")
        return 0
    if args.action == "current":
        print(current_revision() or "(base)")
        return 0
    if args.action == "verify":
        try:
            database = check_database()
        except RuntimeError as exc:
            return _fail(str(exc))
        report = verify_schema(engine)
        data = {
            "database": database,
            "tables": {"expected": report.expected_tables, "found": report.found_tables},
            "checks": [
                {"table": c.table, "object": c.object, "status": c.status, "detail": c.detail}
                for c in report.checks
            ],
            "failed": [
                {"table": c.table, "object": c.object, "detail": c.detail} for c in report.failed
            ],
        }
        code = 0 if report.found_tables == report.expected_tables and not report.failed else 1
        print(json.dumps({"code": code, "message": "ok" if code == 0 else "schema 校验失败",
                          "data": data}, ensure_ascii=False))
        return code
    return _fail(f"未知 db 子命令：{args.action}")


def cmd_seed(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        inserted = seed(db)
    total = sum(inserted.values())
    print(f"[种子] 完成。本次新增 {total} 行：{json.dumps(inserted, ensure_ascii=False)}")
    if total == 0:
        print("[种子] 第 2 次执行未新增数据")
    return 0


def cmd_init_super_admin(args: argparse.Namespace) -> int:
    if not config.INITIAL_SUPER_ADMIN_USERNAME or not config.INITIAL_SUPER_ADMIN_PASSWORD:
        return _fail("请设置环境变量 INITIAL_SUPER_ADMIN_USERNAME 与 INITIAL_SUPER_ADMIN_PASSWORD")
    with SessionLocal() as db:
        try:
            created, user = init_super_admin(
                db, config.INITIAL_SUPER_ADMIN_USERNAME, config.INITIAL_SUPER_ADMIN_PASSWORD
            )
        except SuperAdminError as exc:
            return _fail(str(exc))
    if created:
        print(f"[超管] 已创建账号 {user.username}")
    else:
        print(f"[超管] 账号 {user.username} 已存在，未重置密码、未重复授予角色")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    result = run_archive(now_value=args.now)
    print(json.dumps({
        "code": 0 if result.failed == 0 else 1,
        "message": "ok" if result.failed == 0 else "存在失败记录",
        "data": {
            "scanned": result.scanned,
            "succeeded": result.succeeded,
            "failed": result.failed,
            "skipped": result.skipped,
            "duration_ms": result.duration_ms,
            "failures": [
                {"table": f.table, "record_id": f.record_id, "object_key": f.object_key,
                 "reason": f.reason}
                for f in result.failures
            ],
        },
    }, ensure_ascii=False))
    return 0 if result.failed == 0 else 1


def cmd_verify(args: argparse.Namespace) -> int:
    report = run_verify(args.scope or "all")
    for case in report.cases:
        print(case.line())
    print(json.dumps(report.dump(), ensure_ascii=False))
    return 0 if report.failed == 0 else 1


def cmd_bootstrap(args: argparse.Namespace) -> int:
    try:
        upgrade("head")
        print("[初始化] 迁移完成")
    except Exception as exc:  # noqa: BLE001
        return _fail(f"迁移失败：{exc}")

    with SessionLocal() as db:
        seed(db)
    print("[初始化] 种子完成")

    if not config.INITIAL_SUPER_ADMIN_USERNAME or not config.INITIAL_SUPER_ADMIN_PASSWORD:
        return _fail("请设置环境变量 INITIAL_SUPER_ADMIN_USERNAME 与 INITIAL_SUPER_ADMIN_PASSWORD")
    code = cmd_init_super_admin(args)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="esimage-data", description="ESImage 数据模型与存储命令行")
    sub = parser.add_subparsers(dest="command", required=True)

    db = sub.add_parser("db", help="数据库迁移与 schema 校验")
    db.add_argument("action", choices=["upgrade", "downgrade", "current", "verify"])
    db.add_argument("revision", nargs="?")
    db.set_defaults(func=cmd_db)

    sub.add_parser("seed", help="幂等种子").set_defaults(func=cmd_seed)
    sub.add_parser("init-super-admin", help="初始化首个超管").set_defaults(func=cmd_init_super_admin)

    archive = sub.add_parser("archive", help="归档任务")
    archive_sub = archive.add_subparsers(dest="archive_action", required=True)
    archive_run = archive_sub.add_parser("run")
    archive_run.add_argument("--now")
    archive_run.set_defaults(func=cmd_archive)

    verify = sub.add_parser("verify", help="契约回归")
    verify.add_argument("--scope", choices=["schema", "seed", "storage", "archive", "all"], default="all")
    verify.set_defaults(func=cmd_verify)

    sub.add_parser("bootstrap", help="迁移 + 种子 + 首个超管").set_defaults(func=cmd_bootstrap)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:  # pragma: no cover
        return _fail("已取消")
    except Exception as exc:  # noqa: BLE001
        return _fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
