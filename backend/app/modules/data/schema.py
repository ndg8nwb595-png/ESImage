"""数据库 schema 校验（``esimage-data db verify``）。

直接查询 PostgreSQL 系统目录，逐表校验 18 张表的列、类型、空值、CHECK 约束、
唯一约束、部分唯一索引、普通索引与外键，与 10 号 PRD §4 对齐。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass
class SchemaCheck:
    table: str
    object: str
    status: str  # ok / fail
    detail: str = ""


@dataclass
class SchemaReport:
    database: dict = field(default_factory=dict)
    expected_tables: int = 18
    found_tables: int = 0
    checks: list[SchemaCheck] = field(default_factory=list)

    @property
    def failed(self) -> list[SchemaCheck]:
        return [check for check in self.checks if check.status == "fail"]


# (column, normalized_type, nullable)
_C = tuple[str, str, bool]

# 每张表的列、CHECK、唯一约束、部分唯一索引、普通索引、外键
# 外键：{ column -> target_table }
TABLE_SPECS: dict[str, dict] = {
    "users": {
        "columns": [
            ("id", "BIGINT", False), ("username", "VARCHAR(20)", False),
            ("display_name", "VARCHAR(30)", False), ("password_hash", "VARCHAR(255)", False),
            ("avatar_path", "TEXT", True), ("email", "VARCHAR(255)", True),
            ("status", "VARCHAR(16)", False), ("token_version", "INTEGER", False),
            ("last_login_at", "TIMESTAMPTZ", True), ("created_at", "TIMESTAMPTZ", False),
            ("updated_at", "TIMESTAMPTZ", False), ("deleted_at", "TIMESTAMPTZ", True),
        ],
        "checks": ["ck_users_username_format", "ck_users_status"],
        "uniques": ["uq_users_username"],
        "partial_unique": [],
        "indexes": ["idx_users_status", "idx_users_created_at"],
        "fks": {},
    },
    "roles": {
        "columns": [
            ("id", "BIGINT", False), ("code", "VARCHAR(20)", False),
            ("name", "VARCHAR(50)", False), ("description", "TEXT", True),
            ("is_system", "BOOLEAN", False), ("created_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_roles_code"],
        "uniques": ["uq_roles_code"],
        "partial_unique": [],
        "indexes": [],
        "fks": {},
    },
    "permissions": {
        "columns": [
            ("id", "BIGINT", False), ("code", "VARCHAR(64)", False),
            ("name", "VARCHAR(64)", False), ("type", "VARCHAR(16)", False),
            ("group_name", "VARCHAR(32)", True), ("is_super_only", "BOOLEAN", False),
            ("description", "TEXT", True), ("created_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_permissions_type"],
        "uniques": ["uq_permissions_code"],
        "partial_unique": [],
        "indexes": [],
        "fks": {},
    },
    "role_permissions": {
        "columns": [
            ("role_id", "BIGINT", False), ("permission_id", "BIGINT", False),
            ("created_at", "TIMESTAMPTZ", False),
        ],
        "checks": [],
        "uniques": [],
        "partial_unique": [],
        "indexes": [],
        "fks": {"role_id": "roles", "permission_id": "permissions"},
    },
    "user_roles": {
        "columns": [
            ("user_id", "BIGINT", False), ("role_id", "BIGINT", False),
            ("created_at", "TIMESTAMPTZ", False),
        ],
        "checks": [],
        "uniques": [],
        "partial_unique": [],
        "indexes": ["idx_user_roles_role_id"],
        "fks": {"user_id": "users", "role_id": "roles"},
    },
    "creative_sessions": {
        "columns": [
            ("id", "BIGINT", False), ("user_id", "BIGINT", False),
            ("title", "VARCHAR(50)", False), ("status", "VARCHAR(16)", False),
            ("requirement_summary", "JSONB", True), ("last_message_at", "TIMESTAMPTZ", True),
            ("created_at", "TIMESTAMPTZ", False), ("updated_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_sessions_status"],
        "uniques": [],
        "partial_unique": [],
        "indexes": ["idx_sessions_user_status_time", "idx_sessions_last_message_at"],
        "fks": {"user_id": "users"},
    },
    "chat_messages": {
        "columns": [
            ("id", "BIGINT", False), ("session_id", "BIGINT", False),
            ("role", "VARCHAR(16)", False), ("agent_code", "VARCHAR(40)", True),
            ("content", "TEXT", False), ("content_type", "VARCHAR(16)", False),
            ("client_message_id", "VARCHAR(64)", True), ("token_in", "INTEGER", False),
            ("token_out", "INTEGER", False), ("status", "VARCHAR(16)", False),
            ("created_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_messages_role", "ck_messages_status"],
        "uniques": [],
        "partial_unique": ["uq_messages_session_client"],
        "indexes": ["idx_messages_session_time", "idx_messages_created_at"],
        "fks": {"session_id": "creative_sessions"},
    },
    "agent_runs": {
        "columns": [
            ("id", "BIGINT", False), ("session_id", "BIGINT", True),
            ("message_id", "BIGINT", True), ("batch_id", "BIGINT", True),
            ("image_id", "BIGINT", True), ("agent_code", "VARCHAR(40)", False),
            ("status", "VARCHAR(16)", False), ("model_name", "VARCHAR(100)", True),
            ("input_summary", "TEXT", True), ("output_summary", "TEXT", True),
            ("input_full", "TEXT", True), ("output_full", "TEXT", True),
            ("prompt_tokens", "INTEGER", False), ("completion_tokens", "INTEGER", False),
            ("latency_ms", "INTEGER", True), ("error_message", "TEXT", True),
            ("created_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_agent_runs_status"],
        "uniques": [],
        "partial_unique": [],
        "indexes": [
            "idx_agent_runs_session", "idx_agent_runs_batch", "idx_agent_runs_image",
            "idx_agent_runs_agent_time", "idx_agent_runs_created_at",
        ],
        "fks": {
            "session_id": "creative_sessions", "message_id": "chat_messages",
            "batch_id": "generation_batches", "image_id": "generated_images",
        },
    },
    "generation_batches": {
        "columns": [
            ("id", "BIGINT", False), ("user_id", "BIGINT", False),
            ("session_id", "BIGINT", False), ("batch_type", "VARCHAR(16)", False),
            ("source_sample_batch_id", "BIGINT", True), ("product_name", "VARCHAR(60)", False),
            ("style_text", "VARCHAR(50)", True), ("width", "INTEGER", False),
            ("height", "INTEGER", False), ("template_name", "VARCHAR(50)", True),
            ("total_count", "INTEGER", False), ("completed_count", "INTEGER", False),
            ("status", "VARCHAR(20)", False), ("stage", "VARCHAR(32)", True),
            ("params_snapshot", "JSONB", False), ("requirement_summary", "JSONB", True),
            ("error_message", "TEXT", True), ("client_request_id", "VARCHAR(64)", True),
            ("started_at", "TIMESTAMPTZ", True), ("finished_at", "TIMESTAMPTZ", True),
            ("created_at", "TIMESTAMPTZ", False), ("updated_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_batches_type", "ck_batches_status", "ck_batches_stage", "ck_batches_source"],
        "uniques": [],
        "partial_unique": ["uq_batches_client_request"],
        "indexes": [
            "idx_batches_user_time", "idx_batches_session_time",
            "idx_batches_status", "idx_batches_type",
        ],
        "fks": {"user_id": "users", "session_id": "creative_sessions"},
    },
    "generated_images": {
        "columns": [
            ("id", "BIGINT", False), ("batch_id", "BIGINT", False),
            ("user_id", "BIGINT", False), ("session_id", "BIGINT", False),
            ("image_type", "VARCHAR(16)", False), ("image_role", "VARCHAR(16)", False),
            ("index_no", "INTEGER", False), ("attempt_no", "INTEGER", False),
            ("status", "VARCHAR(16)", False), ("source_image_id", "BIGINT", True),
            ("file_path", "TEXT", True), ("thumbnail_path", "TEXT", True),
            ("width", "INTEGER", True), ("height", "INTEGER", True),
            ("prompt", "TEXT", True), ("negative_prompt", "TEXT", True),
            ("model_name", "VARCHAR(100)", True), ("latency_ms", "INTEGER", True),
            ("prompt_tokens", "INTEGER", False), ("completion_tokens", "INTEGER", False),
            ("error_message", "TEXT", True), ("is_history_visible", "BOOLEAN", False),
            ("archived_at", "TIMESTAMPTZ", True), ("created_at", "TIMESTAMPTZ", False),
            ("updated_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_images_type", "ck_images_role", "ck_images_status"],
        "uniques": [],
        "partial_unique": [],
        "indexes": [
            "idx_images_batch_index", "idx_images_user_history",
            "idx_images_status", "idx_images_archived_at",
        ],
        "fks": {
            "batch_id": "generation_batches", "user_id": "users",
            "session_id": "creative_sessions",
        },
    },
    "uploaded_assets": {
        "columns": [
            ("id", "BIGINT", False), ("user_id", "BIGINT", False),
            ("session_id", "BIGINT", True), ("file_path", "TEXT", False),
            ("thumbnail_path", "TEXT", True), ("original_name", "VARCHAR(255)", False),
            ("mime_type", "VARCHAR(100)", False), ("size_bytes", "BIGINT", False),
            ("width", "INTEGER", True), ("height", "INTEGER", True),
            ("sort_order", "INTEGER", False), ("status", "VARCHAR(16)", False),
            ("archived_at", "TIMESTAMPTZ", True), ("created_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_uploads_status"],
        "uniques": [],
        "partial_unique": [],
        "indexes": ["idx_uploads_user_session", "idx_uploads_status", "idx_uploads_archived_at"],
        "fks": {"user_id": "users", "session_id": "creative_sessions"},
    },
    "templates": {
        "columns": [
            ("id", "BIGINT", False), ("name", "VARCHAR(50)", False),
            ("style_text", "VARCHAR(50)", True), ("thumbnail_path", "TEXT", False),
            ("prompt_template", "TEXT", True), ("layout_ref", "TEXT", True),
            ("sort_order", "INTEGER", False), ("status", "VARCHAR(16)", False),
            ("created_by", "BIGINT", True), ("created_at", "TIMESTAMPTZ", False),
            ("updated_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_templates_status"],
        "uniques": [],
        "partial_unique": [],
        "indexes": ["idx_templates_status_sort"],
        "fks": {},
    },
    "material_assets": {
        "columns": [
            ("id", "BIGINT", False), ("name", "VARCHAR(50)", False),
            ("file_path", "TEXT", False), ("thumbnail_path", "TEXT", True),
            ("tags", "JSONB", True), ("style_tags", "JSONB", True),
            ("sort_order", "INTEGER", False), ("status", "VARCHAR(16)", False),
            ("created_by", "BIGINT", True), ("created_at", "TIMESTAMPTZ", False),
            ("updated_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_materials_status"],
        "uniques": [],
        "partial_unique": [],
        "indexes": ["idx_materials_status_sort", "idx_materials_tags"],
        "fks": {},
    },
    "model_configs": {
        "columns": [
            ("id", "BIGINT", False), ("provider", "VARCHAR(32)", False),
            ("base_url", "TEXT", False), ("api_key_ciphertext", "TEXT", True),
            ("text_model", "VARCHAR(100)", False), ("image_model", "VARCHAR(100)", False),
            ("vision_model", "VARCHAR(100)", True), ("temperature", "NUMERIC(3,1)", False),
            ("timeout_seconds", "INTEGER", False), ("concurrency", "INTEGER", False),
            ("retry_count", "INTEGER", False), ("max_context_tokens", "INTEGER", True),
            ("is_active", "BOOLEAN", False), ("updated_by", "BIGINT", True),
            ("updated_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_model_temperature", "ck_model_timeout", "ck_model_concurrency", "ck_model_retry"],
        "uniques": [],
        "partial_unique": ["uq_model_active"],
        "indexes": [],
        "fks": {},
    },
    "system_prompts": {
        "columns": [
            ("id", "BIGINT", False), ("agent_code", "VARCHAR(40)", False),
            ("name", "VARCHAR(50)", False), ("content", "TEXT", False),
            ("current_version", "INTEGER", False), ("is_active", "BOOLEAN", False),
            ("updated_by", "BIGINT", True), ("created_at", "TIMESTAMPTZ", False),
            ("updated_at", "TIMESTAMPTZ", False),
        ],
        "checks": [],
        "uniques": ["uq_prompts_agent_code"],
        "partial_unique": [],
        "indexes": [],
        "fks": {},
    },
    "prompt_versions": {
        "columns": [
            ("id", "BIGINT", False), ("prompt_id", "BIGINT", False),
            ("agent_code", "VARCHAR(40)", False), ("version", "INTEGER", False),
            ("content", "TEXT", False), ("created_by", "BIGINT", True),
            ("created_at", "TIMESTAMPTZ", False),
        ],
        "checks": [],
        "uniques": ["uq_prompt_versions"],
        "partial_unique": [],
        "indexes": ["idx_prompt_versions_prompt"],
        "fks": {"prompt_id": "system_prompts"},
    },
    "audit_logs": {
        "columns": [
            ("id", "BIGINT", False), ("user_id", "BIGINT", True),
            ("username_snapshot", "VARCHAR(20)", True), ("action", "VARCHAR(64)", False),
            ("target_type", "VARCHAR(32)", True), ("target_id", "VARCHAR(64)", True),
            ("result", "VARCHAR(16)", False), ("ip", "VARCHAR(45)", True),
            ("user_agent", "TEXT", True), ("detail", "JSONB", True),
            ("created_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_audit_result"],
        "uniques": [],
        "partial_unique": [],
        "indexes": ["idx_audit_created_at", "idx_audit_user", "idx_audit_action", "idx_audit_target"],
        "fks": {"user_id": "users"},
    },
    "size_presets": {
        "columns": [
            ("id", "BIGINT", False), ("platform_name", "VARCHAR(50)", False),
            ("width", "INTEGER", False), ("height", "INTEGER", False),
            ("sort_order", "INTEGER", False), ("status", "VARCHAR(16)", False),
            ("created_by", "BIGINT", True), ("created_at", "TIMESTAMPTZ", False),
            ("updated_at", "TIMESTAMPTZ", False),
        ],
        "checks": ["ck_sizes_positive", "ck_sizes_status"],
        "uniques": ["uq_sizes_platform_size"],
        "partial_unique": [],
        "indexes": ["idx_sizes_status_sort"],
        "fks": {},
    },
}


def _normalize_type(data_type: str, length: int | None, precision: int | None, scale: int | None) -> str:
    data_type = data_type.lower()
    if data_type == "character varying":
        return f"VARCHAR({length})"
    if data_type == "bigint":
        return "BIGINT"
    if data_type == "integer":
        return "INTEGER"
    if data_type == "text":
        return "TEXT"
    if data_type == "boolean":
        return "BOOLEAN"
    if data_type == "timestamp with time zone":
        return "TIMESTAMPTZ"
    if data_type == "jsonb":
        return "JSONB"
    if data_type == "numeric":
        return f"NUMERIC({precision},{scale})"
    return data_type.upper()


def verify_schema(engine: Engine) -> SchemaReport:
    """校验 18 张表，返回报告。"""
    report = SchemaReport()

    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_type='BASE TABLE'"
                )
            )
        }
        report.found_tables = len(TABLE_SPECS.keys() & tables)

        # 列、类型、空值
        columns = conn.execute(
            text(
                "SELECT table_name, column_name, data_type, character_maximum_length, "
                "numeric_precision, numeric_scale, is_nullable "
                "FROM information_schema.columns WHERE table_schema='public'"
            )
        ).all()
        columns_by_table: dict[str, dict[str, tuple[str, bool]]] = {}
        for row in columns:
            table, col, dtype, length, precision, scale, nullable = row
            norm = _normalize_type(dtype, length, precision, scale)
            columns_by_table.setdefault(table, {})[col] = (norm, nullable == "YES")

        # 约束（含外键引用列与删除策略）
        check_names: dict[str, set[str]] = {}
        unique_names: dict[str, set[str]] = {}
        fk_rows: dict[str, list[tuple[str, str, str]]] = {}
        fk_query = text(
            "SELECT c.conname, "
            "r.relname AS tbl, "
            "rf.relname AS reftbl, "
            "c.contype, c.confdeltype, "
            "(SELECT a.attname FROM pg_attribute a "
            " WHERE a.attrelid = c.conrelid AND a.attnum = c.conkey[1]) AS fk_col "
            "FROM pg_constraint c "
            "JOIN pg_class r ON r.oid = c.conrelid "
            "LEFT JOIN pg_class rf ON rf.oid = c.confrelid "
            "WHERE r.relnamespace = 'public'::regnamespace AND c.contype IN ('c','u','f')"
        )
        for conname, table, reftable, contype, confdeltype, fk_col in conn.execute(fk_query):
            if contype == "c":
                check_names.setdefault(table, set()).add(conname)
            elif contype == "u":
                unique_names.setdefault(table, set()).add(conname)
            elif contype == "f":
                fk_rows.setdefault(table, []).append(
                    (fk_col or "", reftable or "", confdeltype or "")
                )

        # 索引（含部分唯一索引）
        index_rows = conn.execute(
            text(
                "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname='public'"
            )
        ).all()
        index_by_table: dict[str, dict[str, str]] = {}
        for table, indexname, indexdef in index_rows:
            index_by_table.setdefault(table, {})[indexname] = indexdef

    # 逐表校验
    for table, spec in TABLE_SPECS.items():
        if table not in tables:
            report.checks.append(SchemaCheck(table, "table", "fail", "表不存在"))
            continue
        report.checks.append(SchemaCheck(table, "table", "ok"))

        # 列
        actual_cols = columns_by_table.get(table, {})
        for col, norm_type, nullable in spec["columns"]:
            if col not in actual_cols:
                report.checks.append(SchemaCheck(table, f"column.{col}", "fail", "列缺失"))
                continue
            act_type, act_nullable = actual_cols[col]
            if act_type != norm_type:
                report.checks.append(
                    SchemaCheck(table, f"column.{col}", "fail",
                                f"类型不一致：预期 {norm_type}，实际 {act_type}")
                )
            elif act_nullable != nullable:
                report.checks.append(
                    SchemaCheck(table, f"column.{col}", "fail",
                                f"空值不一致：预期 {'可空' if nullable else '非空'}，"
                                f"实际 {'可空' if act_nullable else '非空'}")
                )
            else:
                report.checks.append(SchemaCheck(table, f"column.{col}", "ok"))

        # CHECK
        for cname in spec["checks"]:
            ok = cname in check_names.get(table, set())
            report.checks.append(
                SchemaCheck(table, cname, "ok" if ok else "fail",
                            "" if ok else "CHECK 约束缺失")
            )

        # 唯一约束
        for uname in spec["uniques"]:
            ok = uname in unique_names.get(table, set())
            report.checks.append(
                SchemaCheck(table, uname, "ok" if ok else "fail",
                            "" if ok else "唯一约束缺失")
            )

        # 部分唯一索引
        idx_defs = index_by_table.get(table, {})
        for iname in spec["partial_unique"]:
            indexdef = idx_defs.get(iname, "")
            ok = "UNIQUE" in indexdef.upper() and "WHERE" in indexdef.upper()
            report.checks.append(
                SchemaCheck(table, iname, "ok" if ok else "fail",
                            "" if ok else "部分唯一索引缺失或不带 WHERE 条件")
            )

        # 普通索引
        for iname in spec["indexes"]:
            ok = iname in idx_defs
            report.checks.append(
                SchemaCheck(table, iname, "ok" if ok else "fail",
                            "" if ok else "索引缺失")
            )

        # 外键 RESTRICT
        actual_fks = {col: (ref, ondel) for col, ref, ondel in fk_rows.get(table, [])}
        for col, target in spec["fks"].items():
            if col not in actual_fks:
                report.checks.append(
                    SchemaCheck(table, f"fk.{col}", "fail",
                                f"外键缺失（应指向 {target}）")
                )
                continue
            ref, ondel = actual_fks[col]
            if ref != target:
                report.checks.append(
                    SchemaCheck(table, f"fk.{col}", "fail",
                                f"外键目标不一致：预期 {target}，实际 {ref}")
                )
            elif ondel != "r":
                report.checks.append(
                    SchemaCheck(table, f"fk.{col}", "fail",
                                f"外键未使用 ON DELETE RESTRICT（实际 confdeltype={ondel}）")
                )
            else:
                report.checks.append(SchemaCheck(table, f"fk.{col}", "ok"))

    return report
