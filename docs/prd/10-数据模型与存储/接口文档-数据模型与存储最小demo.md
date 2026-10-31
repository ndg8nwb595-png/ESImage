# 数据模型与存储最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `10-数据模型与存储prd.md` §2~§10；`../6-管理后台-账号与权限/6-管理后台-账号与权限prd.md` §11；`../9-后端服务与接口/9-后端服务与接口prd.md` §2/§3/§6；`../11-部署与运维/11-部署与运维prd.md` §10 |
| 覆盖范围 | 数据库约定与 18 张表、迁移与 schema 校验、幂等种子与首个超管、对象存储路径与适配器、5 年归档与归档读取、验收回归命令 |
| 文档状态 | 最小 demo 约定；正式实现需与 6/7/9/11 号文档统一 |

> 10 号 PRD 不定义 HTTP 业务接口。本文的「接口」指**数据与存储契约**：数据库结构、迁移/种子命令、对象存储路径与适配器、归档任务、读取降级与验收命令。登录、会话、上传、生成、历史、管理后台等 HTTP 接口沿用 1~9 号 demo，本文不重复定义，也不新增业务接口。

---

## 1. 通用约定

### 1.1 数据库

| 项目 | 约定 |
| --- | --- |
| 数据库 | PostgreSQL 16（必须） |
| 字符集 | UTF-8 |
| 时区 | 会话时区 Asia/Shanghai；所有 `TIMESTAMPTZ` 按带时区时间存储与返回 |
| 表名 | 小写、复数、`snake_case` |
| 字段名 | 小写、`snake_case` |
| 主键 | `BIGSERIAL`，字段名 `id` |
| 时间 | `TIMESTAMPTZ`，默认 `now()` |
| 布尔 | `BOOLEAN`，不使用 `0`/`1` 或字符串 |
| 结构化快照 | `JSONB` |
| 外键 | 默认 `ON DELETE RESTRICT`，不级联删除 |
| 软删除 | 使用 `status` 或 `deleted_at`，不物理删除业务数据 |
| 审计时间 | 业务表统一带 `created_at`、`updated_at`；只读流水表可只有 `created_at` |
| 敏感字段 | 密码 bcrypt；API Key 对称加密后存储；日志/Agent 输入输出落库前脱敏 |
| 迁移 | Alembic，版本化，可正向与回滚 |
| 索引命名 | `idx_<table>_<columns>`、`uq_<table>_<columns>`、`ck_<table>_<...>` |

### 1.2 对象存储

| 项目 | 约定 |
| --- | --- |
| 桶 | 单桶 `esimage` |
| 对象键 | 桶内相对路径，不带前导 `/`，不包含 `..`、原始文件名或用户可控文本 |
| 对象名 | UUID；扩展名来自校验后的真实格式 |
| 访问 | 桶不公开；所有读取经后端鉴权后流式返回；不生成公开 URL |
| 归档 | `archive/{原相对路径}`，保持相对路径不变，便于恢复 |
| 缩略图 | 长期保留在 `thumbnails/`，不随原件归档 |

### 1.3 命令与错误

| 项目 | 约定 |
| --- | --- |
| 命令入口 | `esimage-data` |
| 成功退出码 | `0` |
| 失败退出码 | 非 `0`；输出中文原因，不打印堆栈、SQL、连接串或密钥 |
| 业务错误码 | 沿用 9 号 §3；本 demo 直接使用 `30006`（上传不符合要求）、`30014`（文件不存在或归档不可用）、`50002`（数据库错误）、`50003`（存储服务错误） |
| 日志 | 中文；包含操作、预期、实际、结论；归档任务额外包含扫描/成功/失败/跳过数与耗时 |

---

## 2. 数据库接口

### 2.1 连接与环境变量

| 变量 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `DATABASE_URL` | 是 | — | PostgreSQL 连接串，例如 `postgresql+psycopg://user:pass@localhost:5432/esimage` |
| `DATABASE_TIMEZONE` | 否 | `Asia/Shanghai` | 连接后设置的会话时区 |
| `STORAGE_BACKEND` | 否 | `local` | `local` 或 `minio`；本 demo 只验收 `local` |
| `STORAGE_ROOT` | 条件 | — | `local` 后端的桶根目录；必填且可写 |
| `MINIO_ENDPOINT` | 条件 | — | `minio` 后端必填；本 demo 不验收 |
| `MINIO_ACCESS_KEY` | 条件 | — | `minio` 后端必填 |
| `MINIO_SECRET_KEY` | 条件 | — | `minio` 后端必填 |
| `MINIO_BUCKET` | 否 | `esimage` | 固定为 `esimage`；修改视为偏离契约 |
| `MINIO_SECURE` | 否 | `false` | 是否使用 HTTPS |
| `ARCHIVE_RETENTION_DAYS` | 否 | `1825` | 归档保留期；仅 demo 可调小 |
| `INITIAL_SUPER_ADMIN_USERNAME` | 条件 | — | `init-super-admin` / `bootstrap` 必填 |
| `INITIAL_SUPER_ADMIN_PASSWORD` | 条件 | — | `init-super-admin` / `bootstrap` 必填 |

- 连接成功后校验 `server_version` 主版本为 16、`server_encoding` 为 UTF-8、`TimeZone` 为 `Asia/Shanghai`；不满足时命令失败。
- 不要求 Redis、Celery、Nginx。若连接串指向已有 1~9 号 demo 的数据库，必须使用独立库名，避免迁移版本冲突。

### 2.2 迁移命令

| 命令 | 行为 |
| --- | --- |
| `esimage-data db upgrade [revision]` | 升级到指定 revision；缺省 `head` |
| `esimage-data db downgrade <revision>` | 回滚到指定 revision；`base` 表示清空本 demo 创建的对象 |
| `esimage-data db current` | 输出当前 revision |
| `esimage-data db verify` | 校验 schema 与种子，输出中文报告 |

规则：

- 只有一个 head；每次迁移可回滚。
- 迁移脚本不得删除已有业务数据；不得在迁移中写入业务种子。
- 从空库 `upgrade head` 必须成功；`downgrade base` 后再次 `upgrade head` 必须成功。
- 回滚只移除外键依赖顺序允许的对象，不误删其他 demo 的表。

### 2.3 Schema 校验输出

`esimage-data db verify` 逐项检查列、类型、空值、默认值、`CHECK`、唯一约束、部分唯一索引、普通索引与外键。示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "database": {"version": "16", "encoding": "UTF8", "timezone": "Asia/Shanghai"},
    "tables": {"expected": 18, "found": 18},
    "checks": [
      {"table": "users", "object": "uq_users_username", "status": "ok"},
      {"table": "chat_messages", "object": "uq_messages_session_client", "status": "ok"},
      {"table": "generation_batches", "object": "ck_batches_source", "status": "ok"}
    ],
    "failed": []
  }
}
```

- 任一项失败时 `code` 非 0、`data.failed` 列出表、对象、预期与实际，命令退出码非 0。
- 不输出密码、连接串、对象存储密钥。

### 2.4 表清单与关系

| 域 | 表 | 用途 | 关键关系 |
| --- | --- | --- | --- |
| 身份 | `users` | 账号 | 被会话、批次、图片、上传图、审计引用 |
| 身份 | `roles` | 内置角色 | 与用户、权限多对多 |
| 身份 | `permissions` | 权限点 | 与角色多对多 |
| 身份 | `role_permissions` | 角色权限关联 | `role_id` → `roles.id`；`permission_id` → `permissions.id` |
| 身份 | `user_roles` | 用户角色关联 | `user_id` → `users.id`；`role_id` → `roles.id` |
| 审计 | `audit_logs` | 操作日志 | 独立；`user_id` 可为空 |
| 内容 | `creative_sessions` | 创作会话 | `user_id` → `users.id` |
| 内容 | `chat_messages` | 聊天消息 | `session_id` → `creative_sessions.id` |
| 内容 | `agent_runs` | Agent 调用记录 | `session_id` / `message_id` / `batch_id` / `image_id` 均可空，均 `RESTRICT` |
| 内容 | `generation_batches` | 生成批次 | `user_id` → `users.id`；`session_id` → `creative_sessions.id`；`source_sample_batch_id` 指向示例批次（应用层校验） |
| 内容 | `generated_images` | 生成图片 | `batch_id` / `user_id` / `session_id` 均为外键；`source_image_id` 指向来源图（应用层校验） |
| 内容 | `uploaded_assets` | 上传商品图 | `user_id` → `users.id`；`session_id` 可空 |
| 配置 | `templates` | 模板 | 无外键；批次以名称快照引用 |
| 配置 | `material_assets` | 素材库 | 无外键；批次以快照引用 |
| 配置 | `model_configs` | 模型配置 | 单条启用；`updated_by` 记录修改人 |
| 配置 | `system_prompts` | 系统提示词 | `agent_code` 唯一 |
| 配置 | `prompt_versions` | 提示词版本 | `prompt_id` → `system_prompts.id` |
| 配置 | `size_presets` | 尺寸预设 | 独立配置 |

> `templates` / `material_assets` 与批次之间没有外键（10 号 §3.1）；`generation_batches.source_sample_batch_id` 与 `generated_images.source_image_id` 在 10 号 §4.9/§4.10 中为 BIGINT 字段，未声明外键，demo 由应用层校验引用存在性与类型，见 §8。

### 2.5 通用列

| 列 | 类型 | 约定 |
| --- | --- | --- |
| `id` | BIGSERIAL | 主键 |
| `created_at` | TIMESTAMPTZ | 非空，默认 `now()` |
| `updated_at` | TIMESTAMPTZ | 可更新表非空，默认 `now()`；由应用层在更新时写入 |
| `status` | VARCHAR | 枚举由各表 `CHECK` 约束；软删除通过 `status` 或 `deleted_at` |
| `deleted_at` | TIMESTAMPTZ | 可空；仅 `users` 使用 |

### 2.6 表结构

#### 2.6.1 `users` 用户表

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `username` | VARCHAR(20) | 否 | — | 登录名，全局唯一，含已删除账号 |
| `display_name` | VARCHAR(30) | 否 | — | 显示名 |
| `password_hash` | VARCHAR(255) | 否 | — | bcrypt 哈希 |
| `avatar_path` | TEXT | 是 | NULL | 预留；本 demo 恒为 NULL |
| `email` | VARCHAR(255) | 是 | NULL | 选填 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `disabled` / `deleted` |
| `token_version` | INT | 否 | 0 | 改密/禁用/删除时递增 |
| `last_login_at` | TIMESTAMPTZ | 是 | NULL | 最后登录时间 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是 | NULL | 软删除时间 |

约束与索引：`uq_users_username`；`ck_users_username_format`（`^[A-Za-z0-9_]{4,20}$`）；`ck_users_status`；`idx_users_status`；`idx_users_created_at`（`created_at DESC`）。

#### 2.6.2 `roles` 角色表

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `code` | VARCHAR(20) | 否 | — | `user` / `admin` / `super_admin` |
| `name` | VARCHAR(50) | 否 | — | 角色名称 |
| `description` | TEXT | 是 | NULL | 描述 |
| `is_system` | BOOLEAN | 否 | `true` | 内置角色 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

约束：`uq_roles_code`；`ck_roles_code`。

#### 2.6.3 `permissions` 权限点表

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `code` | VARCHAR(64) | 否 | — | 权限码 |
| `name` | VARCHAR(64) | 否 | — | 中文名称 |
| `type` | VARCHAR(16) | 否 | — | `menu` / `action` |
| `group_name` | VARCHAR(32) | 是 | NULL | 分组 |
| `is_super_only` | BOOLEAN | 否 | `false` | 超管专属 |
| `description` | TEXT | 是 | NULL | 说明 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

约束：`uq_permissions_code`；`ck_permissions_type`。

#### 2.6.4 `role_permissions` 角色权限关联

| 字段 | 类型 | 空 | 说明 |
| --- | --- | --- | --- |
| `role_id` | BIGINT | 否 | 外键 `roles.id`，`RESTRICT` |
| `permission_id` | BIGINT | 否 | 外键 `permissions.id`，`RESTRICT` |
| `created_at` | TIMESTAMPTZ | 否 | 创建时间 |

约束：主键 `(role_id, permission_id)`。

#### 2.6.5 `user_roles` 用户角色关联

| 字段 | 类型 | 空 | 说明 |
| --- | --- | --- | --- |
| `user_id` | BIGINT | 否 | 外键 `users.id`，`RESTRICT` |
| `role_id` | BIGINT | 否 | 外键 `roles.id`，`RESTRICT` |
| `created_at` | TIMESTAMPTZ | 否 | 创建时间 |

约束：主键 `(user_id, role_id)`；`idx_user_roles_role_id`。应用层角色组合规则不在本 demo，见 §8。

#### 2.6.6 `creative_sessions` 创作会话

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `user_id` | BIGINT | 否 | — | 外键 `users.id`，`RESTRICT` |
| `title` | VARCHAR(50) | 否 | — | 会话标题 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `hidden` |
| `requirement_summary` | JSONB | 是 | NULL | 需求摘要 |
| `last_message_at` | TIMESTAMPTZ | 是 | NULL | 最后消息时间 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

约束与索引：`ck_sessions_status`；`idx_sessions_user_status_time`（`user_id, status, last_message_at DESC`）；`idx_sessions_last_message_at`（`last_message_at DESC`）。

#### 2.6.7 `chat_messages` 聊天消息

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `session_id` | BIGINT | 否 | — | 外键 `creative_sessions.id`，`RESTRICT` |
| `role` | VARCHAR(16) | 否 | — | `user` / `assistant` / `system` |
| `agent_code` | VARCHAR(40) | 是 | NULL | Agent 消息所属 Agent |
| `content` | TEXT | 否 | — | 消息正文 |
| `content_type` | VARCHAR(16) | 否 | `text` | `text` / `markdown` |
| `client_message_id` | VARCHAR(64) | 是 | NULL | 前端幂等键 |
| `token_in` | INT | 否 | 0 | 输入 Token |
| `token_out` | INT | 否 | 0 | 输出 Token |
| `status` | VARCHAR(16) | 否 | `done` | `sending` / `done` / `failed` |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

约束与索引：`ck_messages_role`；`ck_messages_status`；`uq_messages_session_client` 为部分唯一索引，条件 `client_message_id IS NOT NULL`；`idx_messages_session_time`（`session_id, created_at`）；`idx_messages_created_at`（`created_at DESC`）。本期不建 `gin_trgm_ops` 索引。

#### 2.6.8 `agent_runs` Agent 调用记录

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `session_id` | BIGINT | 是 | NULL | 外键 `creative_sessions.id`，`RESTRICT` |
| `message_id` | BIGINT | 是 | NULL | 外键 `chat_messages.id`，`RESTRICT` |
| `batch_id` | BIGINT | 是 | NULL | 外键 `generation_batches.id`，`RESTRICT` |
| `image_id` | BIGINT | 是 | NULL | 外键 `generated_images.id`，`RESTRICT` |
| `agent_code` | VARCHAR(40) | 否 | — | Agent 标识 |
| `status` | VARCHAR(16) | 否 | — | `success` / `failed` / `skipped` |
| `model_name` | VARCHAR(100) | 是 | NULL | 模型名 |
| `input_summary` | TEXT | 是 | NULL | 输入摘要 |
| `output_summary` | TEXT | 是 | NULL | 输出摘要 |
| `input_full` | TEXT | 是 | NULL | 完整输入，存储前脱敏 |
| `output_full` | TEXT | 是 | NULL | 完整输出，存储前脱敏 |
| `prompt_tokens` | INT | 否 | 0 | 输入 Token |
| `completion_tokens` | INT | 否 | 0 | 输出 Token |
| `latency_ms` | INT | 是 | NULL | 耗时 |
| `error_message` | TEXT | 是 | NULL | 错误信息 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

约束与索引：`ck_agent_runs_status`；`idx_agent_runs_session`（`session_id, created_at`）；`idx_agent_runs_batch`（`batch_id, created_at`）；`idx_agent_runs_image`（`image_id`）；`idx_agent_runs_agent_time`（`agent_code, created_at DESC`）；`idx_agent_runs_created_at`（`created_at DESC`）。

#### 2.6.9 `generation_batches` 生成批次

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `user_id` | BIGINT | 否 | — | 外键 `users.id`，`RESTRICT` |
| `session_id` | BIGINT | 否 | — | 外键 `creative_sessions.id`，`RESTRICT` |
| `batch_type` | VARCHAR(16) | 否 | — | `sample` / `full` |
| `source_sample_batch_id` | BIGINT | 是 | NULL | `full` 引用的示例批次；应用层校验 |
| `product_name` | VARCHAR(60) | 否 | — | 商品名称快照 |
| `style_text` | VARCHAR(50) | 是 | NULL | 风格文本快照 |
| `width` | INT | 否 | — | 宽 |
| `height` | INT | 否 | — | 高 |
| `template_name` | VARCHAR(50) | 是 | NULL | 模板名称快照 |
| `total_count` | INT | 否 | — | 计划张数 |
| `completed_count` | INT | 否 | 0 | 已完成张数 |
| `status` | VARCHAR(20) | 否 | `queued` | 批次状态 |
| `stage` | VARCHAR(32) | 是 | NULL | Agent code / `text_composition` / `done`；`queued` 时为空 |
| `params_snapshot` | JSONB | 否 | — | 参数快照 |
| `requirement_summary` | JSONB | 是 | NULL | 生成时需求摘要 |
| `error_message` | TEXT | 是 | NULL | 失败原因 |
| `client_request_id` | VARCHAR(64) | 是 | NULL | 幂等键 |
| `started_at` | TIMESTAMPTZ | 是 | NULL | 开始时间 |
| `finished_at` | TIMESTAMPTZ | 是 | NULL | 结束时间 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

约束与索引：`ck_batches_type`；`ck_batches_status`；`ck_batches_stage`；`ck_batches_source`（`full` 非空、`sample` 为空）；`uq_batches_client_request` 为部分唯一索引，条件 `client_request_id IS NOT NULL`；`idx_batches_user_time`；`idx_batches_session_time`；`idx_batches_status`；`idx_batches_type`。

批次类型与状态的应用层约束：

- `sample` 允许：`queued`、`running`、`sample_ready`、`confirmed`、`failed`、`cancelled`。
- `full` 允许：`queued`、`running`、`completed`、`partially_failed`、`failed`、`cancelled`。
- 数据库只做全集校验，类型与状态的组合由应用层拒绝。

#### 2.6.10 `generated_images` 生成图片

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `batch_id` | BIGINT | 否 | — | 外键 `generation_batches.id`，`RESTRICT` |
| `user_id` | BIGINT | 否 | — | 外键 `users.id`，`RESTRICT` |
| `session_id` | BIGINT | 否 | — | 外键 `creative_sessions.id`，`RESTRICT` |
| `image_type` | VARCHAR(16) | 否 | — | `sample` / `final` |
| `image_role` | VARCHAR(16) | 否 | — | `main` / `detail`；示例图固定 `main` |
| `index_no` | INT | 否 | — | 组内序号 |
| `attempt_no` | INT | 否 | 1 | 第几次尝试 |
| `status` | VARCHAR(16) | 否 | `pending` | 图片状态 |
| `source_image_id` | BIGINT | 是 | NULL | 复用/替代来源；应用层校验 |
| `file_path` | TEXT | 是 | NULL | MinIO 对象路径 |
| `thumbnail_path` | TEXT | 是 | NULL | 缩略图路径 |
| `width` | INT | 是 | NULL | 宽 |
| `height` | INT | 是 | NULL | 高 |
| `prompt` | TEXT | 是 | NULL | 最终提示词 |
| `negative_prompt` | TEXT | 是 | NULL | 负面提示词 |
| `model_name` | VARCHAR(100) | 是 | NULL | 模型名 |
| `latency_ms` | INT | 是 | NULL | 耗时 |
| `prompt_tokens` | INT | 否 | 0 | 输入 Token |
| `completion_tokens` | INT | 否 | 0 | 输出 Token |
| `error_message` | TEXT | 是 | NULL | 失败原因 |
| `is_history_visible` | BOOLEAN | 否 | `false` | 是否进入历史作品 |
| `archived_at` | TIMESTAMPTZ | 是 | NULL | 归档时间 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

约束与索引：`ck_images_type`；`ck_images_role`；`ck_images_status`；`idx_images_batch_index`（`batch_id, index_no, attempt_no`）；`idx_images_user_history`（`user_id, is_history_visible, created_at DESC`）；`idx_images_status`；`idx_images_archived_at`。

图片状态流转（应用层）：

```text
pending → generating → success / failed / cancelled
success / failed → superseded
```

`success` 不回退；重试/重生成创建新记录并递增 `attempt_no`。

#### 2.6.11 `uploaded_assets` 用户上传商品图

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `user_id` | BIGINT | 否 | — | 外键 `users.id`，`RESTRICT` |
| `session_id` | BIGINT | 是 | NULL | 外键 `creative_sessions.id`，`RESTRICT`；首次用于生成时回填 |
| `file_path` | TEXT | 否 | — | MinIO 对象路径 |
| `thumbnail_path` | TEXT | 是 | NULL | 缩略图路径 |
| `original_name` | VARCHAR(255) | 否 | — | 原始文件名 |
| `mime_type` | VARCHAR(100) | 否 | — | MIME |
| `size_bytes` | BIGINT | 否 | — | 文件大小 |
| `width` | INT | 是 | NULL | 宽 |
| `height` | INT | 是 | NULL | 高 |
| `sort_order` | INT | 否 | 0 | 排序，首张为主参考图 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `deleted` |
| `archived_at` | TIMESTAMPTZ | 是 | NULL | 归档时间 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

约束与索引：`ck_uploads_status`；`idx_uploads_user_session`（`user_id, session_id, sort_order`）；`idx_uploads_status`；`idx_uploads_archived_at`。

#### 2.6.12 `templates` 模板

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `name` | VARCHAR(50) | 否 | — | 模板名称 |
| `style_text` | VARCHAR(50) | 是 | NULL | 默认风格文案 |
| `thumbnail_path` | TEXT | 否 | — | 缩略图 |
| `prompt_template` | TEXT | 是 | NULL | 提示词模板 |
| `layout_ref` | TEXT | 是 | NULL | 版式参考 |
| `sort_order` | INT | 否 | 0 | 排序 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `disabled` |
| `created_by` | BIGINT | 是 | NULL | 创建人 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

约束与索引：`ck_templates_status`；`idx_templates_status_sort`。

#### 2.6.13 `material_assets` 素材库

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `name` | VARCHAR(50) | 否 | — | 素材名称 |
| `file_path` | TEXT | 否 | — | 图片路径 |
| `thumbnail_path` | TEXT | 是 | NULL | 缩略图 |
| `tags` | JSONB | 是 | NULL | 标签数组 |
| `style_tags` | JSONB | 是 | NULL | 风格标签 |
| `sort_order` | INT | 否 | 0 | 排序 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `disabled` |
| `created_by` | BIGINT | 是 | NULL | 创建人 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

约束与索引：`ck_materials_status`；`idx_materials_status_sort`；`idx_materials_tags`（GIN）。

#### 2.6.14 `model_configs` 模型配置

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `provider` | VARCHAR(32) | 否 | `volcengine_ark` | 服务商 |
| `base_url` | TEXT | 否 | — | API 地址 |
| `api_key_ciphertext` | TEXT | 是 | NULL | 加密后的 API Key |
| `text_model` | VARCHAR(100) | 否 | — | 文本模型名 |
| `image_model` | VARCHAR(100) | 否 | — | 图像模型名 |
| `vision_model` | VARCHAR(100) | 是 | NULL | 视觉模型名 |
| `temperature` | NUMERIC(3,1) | 否 | 0.7 | 0.0~2.0 |
| `timeout_seconds` | INT | 否 | 120 | 30~300 |
| `concurrency` | INT | 否 | 4 | 1~16 |
| `retry_count` | INT | 否 | 1 | 0~3 |
| `max_context_tokens` | INT | 是 | NULL | 上下文上限 |
| `is_active` | BOOLEAN | 否 | `true` | 当前启用配置 |
| `updated_by` | BIGINT | 是 | NULL | 修改人 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

约束与索引：`ck_model_temperature`；`ck_model_timeout`；`ck_model_concurrency`；`ck_model_retry`；`uq_model_active` 为部分唯一索引，`is_active=true` 只允许一行。

#### 2.6.15 `system_prompts` 系统提示词

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `agent_code` | VARCHAR(40) | 否 | — | Agent 标识，唯一 |
| `name` | VARCHAR(50) | 否 | — | Agent 名称 |
| `content` | TEXT | 否 | — | 当前启用提示词 |
| `current_version` | INT | 否 | 1 | 当前版本号 |
| `is_active` | BOOLEAN | 否 | `true` | 是否启用 |
| `updated_by` | BIGINT | 是 | NULL | 修改人 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

约束：`uq_prompts_agent_code`。

#### 2.6.16 `prompt_versions` 提示词版本

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `prompt_id` | BIGINT | 否 | — | 外键 `system_prompts.id`，`RESTRICT` |
| `agent_code` | VARCHAR(40) | 否 | — | Agent 标识 |
| `version` | INT | 否 | — | 版本号 |
| `content` | TEXT | 否 | — | 版本内容 |
| `created_by` | BIGINT | 是 | NULL | 修改人 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

约束与索引：`uq_prompt_versions`（`prompt_id, version`）；`idx_prompt_versions_prompt`（`prompt_id, version DESC`）。

#### 2.6.17 `audit_logs` 操作日志

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `user_id` | BIGINT | 是 | NULL | 操作人；登录失败时可为空 |
| `username_snapshot` | VARCHAR(20) | 是 | NULL | 用户名快照 |
| `action` | VARCHAR(64) | 否 | — | 动作码 |
| `target_type` | VARCHAR(32) | 是 | NULL | 对象类型 |
| `target_id` | VARCHAR(64) | 是 | NULL | 对象标识 |
| `result` | VARCHAR(16) | 否 | — | `success` / `failed` |
| `ip` | VARCHAR(45) | 是 | NULL | IPv4/IPv6 |
| `user_agent` | TEXT | 是 | NULL | 浏览器标识 |
| `detail` | JSONB | 是 | NULL | 变更详情，敏感字段脱敏 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

约束与索引：`ck_audit_result`；`idx_audit_created_at`；`idx_audit_user`；`idx_audit_action`；`idx_audit_target`。

#### 2.6.18 `size_presets` 尺寸预设

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `platform_name` | VARCHAR(50) | 否 | — | 平台名称 |
| `width` | INT | 否 | — | 宽，正整数 |
| `height` | INT | 否 | — | 高，正整数 |
| `sort_order` | INT | 否 | 0 | 排序 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `disabled` |
| `created_by` | BIGINT | 是 | NULL | 创建人 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

约束与索引：`ck_sizes_positive`；`ck_sizes_status`；`uq_sizes_platform_size`；`idx_sizes_status_sort`。

### 2.7 枚举字典

| 枚举 | 取值 |
| --- | --- |
| 用户状态 | `active` / `disabled` / `deleted` |
| 角色 | `user` / `admin` / `super_admin` |
| 权限类型 | `menu` / `action` |
| 会话状态 | `active` / `hidden` |
| 消息角色 | `user` / `assistant` / `system` |
| 消息状态 | `sending` / `done` / `failed` |
| Agent 运行状态 | `success` / `failed` / `skipped` |
| 批次类型 | `sample` / `full` |
| 批次状态 | `queued` / `running` / `sample_ready` / `confirmed` / `completed` / `partially_failed` / `failed` / `cancelled` |
| 批次阶段 | 8 个 Agent code / `text_composition` / `done`；`queued` 时为空 |
| 图片类型 | `sample` / `final` |
| 图片角色 | `main` / `detail` |
| 图片状态 | `pending` / `generating` / `success` / `failed` / `cancelled` / `superseded` |
| 模板/素材/尺寸状态 | `active` / `disabled` |
| 上传图状态 | `active` / `deleted` |
| 审计结果 | `success` / `failed` |

### 2.8 完整性契约

- 所有外键 `ON DELETE RESTRICT`，不级联；业务数据不物理删除。
- `username` 唯一约束包含已删除账号；软删除后用户名不可复用。
- `chat_messages` 的 `(session_id, client_message_id)` 唯一仅在 `client_message_id` 非空时生效。
- `generation_batches` 的 `client_request_id` 唯一仅在非空时生效；`full` 必须有 `source_sample_batch_id`，`sample` 必须为空。
- `model_configs.is_active=true` 只允许一行。
- 应用层必须校验：`full` 引用的批次是 `sample`；批次类型与状态组合；图片状态流转；示例批次只有 1 张 `main`；全套批次 1 张 `main` + 5 张 `detail`；历史可见性四个条件（`full` 批次、`final`、`success`、批次 `completed`/`partially_failed`）。
- 应用层必须校验：`agent_runs.input_full` / `output_full` 与 `audit_logs.detail` 不含密码、API Key、JWT。
- 角色组合规则（1~2 个角色、禁止 `super_admin` + `admin`）由 6 号 demo 的应用层验收，数据库只保证关联表结构。

---

## 3. 对象存储接口

### 3.1 桶与前缀

| 前缀 | 用途 |
| --- | --- |
| `uploads/` | 用户上传商品图原件 |
| `generated/` | 生成图原件 |
| `thumbnails/` | 缩略图 |
| `archive/` | 满 5 年归档原件 |
| `exports/` | 数据导出 ZIP（本 demo 不写入） |
| `templates/` | 模板缩略图与参考图（本 demo 不写入） |
| `materials/` | 素材库文件（本 demo 不写入） |
| `avatars/` | 用户头像（预留，本 demo 恒为 NULL） |

### 3.2 路径规则

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| 上传图（已绑定会话） | `uploads/{user_id}/{session_id}/{uuid}.{ext}` | `session_id` 非空 |
| 上传图（未绑定会话） | `uploads/{user_id}/unbound/{uuid}.{ext}` | demo 约定；首次绑定只回填 `session_id`，不移动对象 |
| 上传图缩略图 | `thumbnails/{user_id}/{session_id}/{uuid}_thumb.webp` | 未绑定时为 `thumbnails/{user_id}/unbound/{uuid}_thumb.webp` |
| 生成图 | `generated/{user_id}/{session_id}/{batch_id}/{uuid}.png` | PNG |
| 生成图缩略图 | `thumbnails/{user_id}/{session_id}/{batch_id}/{uuid}_thumb.webp` | WebP |
| 归档 | `archive/{原相对路径}` | 例如 `archive/generated/12/34/56/abc.png` |
| 导出 | `exports/{admin_user_id}/{job_id}.zip` | 不在本 demo |
| 模板 | `templates/{template_id}/{uuid}.{ext}` | 不在本 demo |
| 素材 | `materials/{material_id}/{uuid}.{ext}` | 不在本 demo |
| 头像 | `avatars/{user_id}/{uuid}.{ext}` | 预留，不使用 |

> 10 号 §6.2 的缩略图模板包含 `batch_id`，但 `uploaded_assets` 没有批次概念；本 demo 约定上传图缩略图省略批次段，见 §8。

### 3.3 文件规则

- 对象名使用 UUID v4；原始文件名只存数据库。
- 上传允许 JPG、PNG、WEBP；MIME 与扩展名必须一致；单文件上限 10MB（10,485,760 字节）；文件必须可解码且可读取宽高。
- 生成图格式 PNG。
- 缩略图最大宽度 400px，高度等比缩放；输出 WebP、质量 80；原图宽度不超过 400px 时不放大。
- 桶不公开；不生成公开 URL；所有读取经后端鉴权。
- 归档保持相对路径不变，便于恢复。
- 对象键校验：非空、UTF-8、无前导 `/`、无 `..`、无控制字符。

### 3.4 存储适配器操作

| 操作 | 输入 | 输出 | 语义 |
| --- | --- | --- | --- |
| `put_object` | 对象键、内容、MIME | 对象键、大小、ETag | 写入或覆盖；UUID 键避免冲突 |
| `get_object` | 对象键 | 可读流、大小、MIME | 对象不存在返回“不存在”结果 |
| `stat_object` | 对象键 | 大小、ETag、MIME、更新时间 | 不存在返回“不存在”结果 |
| `exists` | 对象键 | 布尔 | 不抛裸异常 |
| `copy_object` | 源键、目标键 | 目标键、大小、ETag | 服务端复制；目标已存在时覆盖，用于归档幂等重试 |
| `delete_object` | 对象键 | 无 | 对象已不存在时视为成功，用于归档重试 |

- 适配器只接受桶内相对键，不接受完整 URL 或带桶名的键。
- `local` 后端把键映射为 `STORAGE_ROOT` 下的相对路径；目录穿越被拒绝。
- 存储不可用、权限错误映射为 `50003`；对象不存在在归档读取场景映射为 `30014`。
- 适配器不负责鉴权；鉴权由调用方在读取前完成。

### 3.5 访问控制

- 不提供公开读；`local` 后端不得把 `STORAGE_ROOT` 暴露为静态目录。
- 读取上传图、生成图、缩略图前必须确认当前用户是资源归属人，或当前账号具备对应管理端权限。
- 未登录返回 `401`，已登录无权限返回 `403 20005`，资源不存在或归档不可用返回 `404 30014`；具体 HTTP 语义沿用 9 号。
- 本 demo 的读取服务只返回流或“不存在/不可用”结果，不签发预签名 URL。

---

## 4. 种子与初始化接口

### 4.1 命令

| 命令 | 行为 |
| --- | --- |
| `esimage-data seed` | 幂等写入角色、权限、角色权限、尺寸预设、系统提示词与版本、默认模型配置 |
| `esimage-data init-super-admin` | 按显式环境变量创建首个超管并授予 `super_admin` |
| `esimage-data bootstrap` | 依次执行 `db upgrade head`、`seed`、`init-super-admin`；任一步失败即停止 |

### 4.2 种子清单

**角色（3 条）**

| code | name |
| --- | --- |
| `user` | 普通用户 |
| `admin` | 管理员 |
| `super_admin` | 超管 |

**权限点（23 条）**

| code | 名称 | 类型 | 默认角色 | 超管专属 |
| --- | --- | --- | --- | --- |
| `user.workspace` | 创作台 | menu | user | 否 |
| `user.generate` | 发起生成 | action | user | 否 |
| `user.history` | 历史作品 | menu | user | 否 |
| `user.profile` | 个人中心 | menu | user | 否 |
| `admin.dashboard.view` | 概览 | menu | admin | 否 |
| `admin.accounts.view` | 用户管理 | menu | admin | 否 |
| `admin.accounts.create` | 新建账号 | action | admin | 否 |
| `admin.accounts.edit` | 编辑账号 | action | admin | 否 |
| `admin.accounts.reset_password` | 重置密码 | action | admin | 否 |
| `admin.accounts.disable` | 禁用/启用 | action | admin | 否 |
| `admin.accounts.delete` | 删除/恢复 | action | admin | 否 |
| `admin.roles.view` | 角色管理 | menu | super_admin | 是 |
| `admin.roles.edit` | 编辑权限点 | action | super_admin | 是 |
| `admin.content.view` | 内容追溯 | menu | admin | 否 |
| `admin.assets.view` | 素材与模板 | menu | admin | 否 |
| `admin.assets.edit` | 编辑素材/模板/尺寸 | action | admin | 否 |
| `admin.prompts.view` | 系统提示词 | menu | admin | 否 |
| `admin.prompts.edit` | 编辑系统提示词 | action | admin | 否 |
| `admin.model.view` | 模型配置 | menu | super_admin | 是 |
| `admin.model.edit` | 编辑模型配置 | action | super_admin | 是 |
| `admin.tokens.view` | Token 统计 | menu | admin | 否 |
| `admin.audit.view` | 操作日志 | menu | super_admin | 是 |
| `admin.export` | 数据导出 | action | super_admin | 是 |

**角色权限矩阵**

| 角色 | 权限数 | 内容 |
| --- | --- | --- |
| `user` | 4 | 全部 `user.*` |
| `admin` | 13 | 全部非超管管理端权限：`admin.dashboard.view`、`admin.accounts.*`（5 个操作 + view）、`admin.content.view`、`admin.assets.view`、`admin.assets.edit`、`admin.prompts.view`、`admin.prompts.edit`、`admin.tokens.view` |
| `super_admin` | 23 | 全部权限点，用于展示；运行时仍按角色绕过 `role_permissions` |

**尺寸预设（4 条）**

| platform_name | width | height |
| --- | --- | --- |
| 淘宝/天猫 | 1000 | 1000 |
| 京东 | 1000 | 1000 |
| 拼多多 | 1000 | 1000 |
| 抖音 | 1000 | 1000 |

**系统提示词（8 条 + 8 条版本 1）**

`agent_code`：`planner`、`product_understanding`、`copywriter`、`prompt_builder`、`image_generator`、`quality_reviewer`、`repairer`、`platform_rule`。每条 `current_version=1`，同时写入 `prompt_versions` 的版本 1，内容与当前提示词一致。

**模型配置（1 条）**

| 字段 | 值 |
| --- | --- |
| `provider` | `volcengine_ark` |
| `base_url` | 演示占位地址 |
| `api_key_ciphertext` | 空 |
| `text_model` / `image_model` | 演示占位名 |
| `vision_model` | 空 |
| `temperature` | 0.7 |
| `timeout_seconds` | 120 |
| `concurrency` | 4 |
| `retry_count` | 1 |
| `max_context_tokens` | 32000 |
| `is_active` | true |

### 4.3 幂等规则

- 角色按 `code`、权限按 `code`、角色权限按 `(role_id, permission_id)`、尺寸按 `(platform_name, width, height)`、提示词按 `agent_code`、提示词版本按 `(prompt_id, version)` 判重。
- 已存在则跳过，不覆盖已修改的名称、内容、状态、角色权限。
- 提示词已存在但版本 1 缺失时，补写版本 1，内容取当前 `content`，不修改提示词本身。
- 已存在启用的模型配置时跳过；没有启用配置时插入默认配置。
- 超管权限矩阵只补缺失行，不删除已有行。
- 连续执行两次，第二次不新增任何行；用例输出「[种子] 第 2 次执行未新增数据」。
- 种子不创建模板、素材、普通用户或管理员账号。

### 4.4 首个超管

- `INITIAL_SUPER_ADMIN_USERNAME` 必须符合用户名格式 `^[A-Za-z0-9_]{4,20}$`。
- `INITIAL_SUPER_ADMIN_PASSWORD` 至少 8 位，同时包含字母与数字；禁止 `admin`、`password`、`12345678`、`qwerty123` 等常见弱口令。本地演示可使用 `Demo1234`，但部署到共享环境前必须改密。
- 缺失、空值、格式不符或弱口令时命令失败并输出中文原因，不创建账号。
- 密码以 bcrypt 哈希写入 `users.password_hash`；账号 `status=active`、`token_version=0`、`deleted_at` 为空。
- 授予 `super_admin` 角色；重复执行时若账号已存在，不重置密码、不重复授予角色。
- 不提供代码内默认密码；本地演示也必须显式传参。

### 4.5 脱敏契约

在写入 `audit_logs.detail`、`agent_runs.input_full`、`agent_runs.output_full`、`agent_runs.input_summary`、`agent_runs.output_summary` 之前，递归遍历字符串与 JSON 对象，对以下键名的值替换为 `[REDACTED]`：

`password`、`password_hash`、`api_key`、`api_key_ciphertext`、`authorization`、`access_token`、`refresh_token`、`jwt`、`secret`、`client_secret`、`cookie`、`set-cookie`。

- 匹配键名不区分大小写，支持下划线、连字符与驼峰写法。
- 不脱敏 `token_in`、`token_out`、`prompt_tokens`、`completion_tokens` 等计量字段。
- 不在日志中打印连接串、对象存储密钥、完整请求头。

---

## 5. 归档任务接口

### 5.1 命令

| 命令 | 行为 |
| --- | --- |
| `esimage-data archive run` | 按当前时间执行一次归档 |
| `esimage-data archive run --now 2026-10-31T03:00:00+08:00` | 注入当前时间，便于验证超期记录 |

保留期取 `ARCHIVE_RETENTION_DAYS`，默认 1825 天；截止时间 = `now - 保留期`，按 Asia/Shanghai 解释。

### 5.2 扫描规则

- `generated_images`：`created_at < 截止时间`、`archived_at IS NULL`、`file_path IS NOT NULL`。
- `uploaded_assets`：`created_at < 截止时间`、`archived_at IS NULL`、`file_path IS NOT NULL`。
- 不按图片状态、上传状态过滤；没有原件的记录跳过。
- 已归档记录不重复处理。

### 5.3 单条处理流程

```text
1. 读取原对象键 key = file_path
2. archive_key = "archive/" + key
3. copy_object(key, archive_key)
4. stat archive_key，校验存在且大小与原件一致
5. delete_object(key)
6. 回写 archived_at = now
```

- 任一步失败：记录失败原因，保持 `archived_at` 为空，不删除原件；继续处理下一条。
- 缩略图不处理；数据库记录不删除；`file_path` 不改写。
- 第 3 步成功、第 4/5 步失败时，下次执行按幂等规则继续：归档已存在且原件仍在 → 校验后删除原件并回写；归档已存在且原件已不存在 → 直接回写；归档不存在且原件不存在 → 记为失败，等待人工处理。

### 5.4 任务日志

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "scanned": 12,
    "succeeded": 10,
    "failed": 1,
    "skipped": 1,
    "duration_ms": 1830,
    "failures": [
      {
        "table": "generated_images",
        "record_id": 345,
        "object_key": "generated/12/34/56/abc.png",
        "reason": "归档对象校验失败：大小不一致"
      }
    ]
  }
}
```

- 失败记录必须包含表名、记录 ID、对象键与中文原因。
- 单条失败不阻断其他记录；任务结束输出汇总，存在失败时退出码非 0。

### 5.5 归档读取

- `archived_at IS NULL`：读取原 `file_path`。
- `archived_at` 非空：读取 `archive/{file_path}`。
- 对象缺失、存储不可用或无法读取：返回 `404 30014`，`message` 为「文件归档中，请稍后重试」。
- 不得在归档对象缺失时回退读取已删除的原件路径。
- 缩略图始终读取 `thumbnail_path`，不受归档影响。

---

## 6. 验收回归接口

### 6.1 命令

| 命令 | 范围 |
| --- | --- |
| `esimage-data verify --scope schema` | 18 张表、列、默认值、约束、索引、外键 |
| `esimage-data verify --scope seed` | 种子条数、幂等、超管初始化、脱敏 |
| `esimage-data verify --scope storage` | 上传/生成路径、缩略图、10MB、鉴权读取 |
| `esimage-data verify --scope archive` | 归档、重试、缩略图保留、`30014` |
| `esimage-data verify --scope all` | 全部；默认 scope |

### 6.2 输出与退出码

- 每个用例输出中文日志：操作、预期、实际、结论。
- 成功时 `code=0`、`message="ok"`，`data` 含 `passed`、`failed`、`skipped` 与逐项结果。
- 失败时 `code` 非 0，`data.failed` 指出用例、断言、实际值与对应 Ticket；命令退出码非 0。
- 回归不依赖网络、豆包、Redis、Celery 或真实 MinIO。

### 6.3 10 号 §12 覆盖

| 10 号 §12 | 覆盖 | 说明 |
| --- | --- | --- |
| 1 | 是 | `verify --scope schema` |
| 2 | 是 | 外键 `RESTRICT`、软删除用例 |
| 3 | 是 | `uq_users_username` |
| 4 | 部分 | 数据库结构与种子矩阵；角色组合由 6 号 demo 验收 |
| 5 | 是 | 批次类型/状态/来源用例 |
| 6 | 是 | 图片状态、1 主图 + 5 详情图、历史可见性 |
| 7 | 是 | Agent 调用字段与脱敏 |
| 8 | 是 | 审计与 Agent 输入输出脱敏 |
| 9 | 是 | 本地适配器等价验证单桶前缀 |
| 10 | 是 | 手动触发 + 可注入时钟 |
| 11 | 否 | 导出属 7 号 PRD |
| 12 | 否 | 备份恢复属 11 号 PRD |
| 13 | 是 | `db upgrade` / `db downgrade` |
| 14 | 是 | 种子幂等 + 超管显式密码 |

---

## 7. 不在本 demo 内

- 备份与恢复命令（`pg_dump`、`pg_restore`、`mc mirror`、7 天保留、恢复演练）。
- 数据导出、导出 ZIP、Redis 导出状态、24 小时清理。
- 孤儿上传清理。
- pg_trgm、消息全文索引、正则/布尔搜索。
- 模板、素材、尺寸的增删改查接口与页面。
- 用户头像上传。
- 真实 MinIO 部署、预签名 URL、Nginx。
- Redis 幂等键、Celery / Celery Beat 调度。
- 生成管线、Agent 编排、文字合成、失败重试、取消任务、ZIP 下载。
- 角色组合校验、账号管理接口、操作日志页面。

---

## 8. 待确认项

1. **超管权限是否落 `role_permissions`**：本 demo 按 10 号 §10.2 写 23 行；6 号 demo 不写行、运行时按角色授予全部权限。需统一。
2. **上传图缩略图路径**：10 号 §6.2 模板含 `batch_id`，上传图无批次；demo 约定省略批次段。需确认正式路径。
3. **未绑定会话的上传图路径**：10 号路径模板要求 `session_id`；demo 用 `unbound/` 段，首次绑定不移动对象。需确认是否需要移动对象以严格匹配模板。
4. **`source_sample_batch_id` 与 `source_image_id` 是否加外键**：10 号只声明为 BIGINT 字段；demo 由应用层校验。需确认是否改为自引用外键。
5. **`client_request_id` 跨用户重复**：数据库唯一约束是全局的；同一用户重复返回原批次，不同用户提交相同值应返回冲突还是忽略，10 号未定义。
6. **归档保留期配置化**：10 号 §13 确定固定 5 年；demo 用环境变量缩短。正式实现是否保留配置入口待定。
7. **归档调度归属**：10 号写每日 03:00，11 号写 Celery Beat；demo 只提供手动命令。
8. **归档中间态**：复制成功、删除失败时的幂等规则由 demo 约定，10 号未定义。
9. **缩略图生成失败**：demo 保持图片 `success`、`thumbnail_path` 为空并记日志；是否应视为图片失败待定。
10. **初始超管密码策略**：10 号只要求禁止弱默认密码；demo 约定 8 位以上且含字母与数字，并禁用常见弱口令。
11. **`updated_at` 维护方式**：demo 由应用层写入；是否统一改为数据库触发器待定。
12. **审计动作码**：10 号未给清单；6/8 号 demo 各自使用不同动作码。本 demo 不新增动作码。
13. **模板与素材种子**：10 号 §10.2 不含模板/素材；4 号 demo 自行种入。本 demo 只建表。
14. **管理员默认权限矩阵**：demo 按 6 号 §11 默认角色列授予 13 个非超管权限；需确认正式种子是否一致。
15. **已归档上传图的业务可用性**：10 号对所有超期上传图归档；历史批次读取时走 `archive/`。是否符合业务预期待确认。
16. **导出与孤儿清理**：分别属 7 号与 10 号完整实现，本 demo 不提供。
