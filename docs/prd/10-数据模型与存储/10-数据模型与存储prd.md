# 10-数据模型与存储 PRD

| 项目 | 内容 |
| --- | --- |
| 文档编号 | 10 |
| 文档名称 | 数据模型与存储 PRD |
| 版本 | v0.1 |
| 编写日期 | 2026-10-31 |
| 文档状态 | 待评审 |
| 上游文档 | `0-系统汇总prd.md` |
| 关联文档 | `4-生图任务与结果/4-生图任务与结果prd.md`、`6-管理后台-账号与权限/6-管理后台-账号与权限prd.md`、`7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md`、`9-后端服务与接口/9-后端服务与接口prd.md` |
| 术语依据 | `GLOSSARY.md` |

---

## 1. 文档目的与范围

### 1.1 目的

定义系统的数据库结构、字段约束、实体关系、图片文件存储路径、5 年热存与归档策略、备份与迁移规则。

### 1.2 本期范围

- PostgreSQL 16 的 18 张业务表。
- 字段类型、空值、默认值、约束、索引。
- 实体关系与外键策略。
- 枚举值字典。
- MinIO 单桶前缀存储结构。
- 5 年热存 + 归档任务。
- 备份与恢复。
- 迁移与种子数据。

### 1.3 不做

- 分库分表、读写分离。
- 多租户字段。
- 数据仓库、ETL。
- 物理删除业务数据。
- 冷存储到第三方云（归档仍在 MinIO）。

---

## 2. 数据库约定

| 项目 | 约定 |
| --- | --- |
| 数据库 | PostgreSQL 16 |
| 字符集 | UTF-8 |
| 时区 | Asia/Shanghai |
| 表名 | 小写、复数、`snake_case` |
| 字段名 | 小写、`snake_case` |
| 主键 | `BIGSERIAL`，字段名 `id` |
| 时间 | `TIMESTAMPTZ`，默认 `now()` |
| 布尔 | `BOOLEAN` |
| 结构化快照 | `JSONB` |
| 外键 | 默认 `ON DELETE RESTRICT`，不级联删除 |
| 软删除 | 使用 `status` 或 `deleted_at`，不物理删除 |
| 审计时间 | 业务表统一带 `created_at`、`updated_at` |
| 敏感字段 | 密码 bcrypt；API Key 对称加密后存储 |
| 迁移 | Alembic，版本化 |
| 命名索引 | `idx_<table>_<columns>`、`uq_<table>_<columns>` |

> 所有业务表不物理删除；外键不级联，避免误删历史数据。

---

## 3. 实体关系

```
users ──< user_roles >── roles ──< role_permissions >── permissions
  │
  ├──< creative_sessions ──< chat_messages ──< agent_runs
  │         │
  │         └──< generation_batches ──< generated_images
  │                   │
  │                   └──< agent_runs
  │
  ├──< uploaded_assets
  │
  └──< generation_batches ──< generated_images

system_prompts ──< prompt_versions
audit_logs（独立）
model_configs（单条启用配置）
templates / material_assets / size_presets（被批次快照引用或独立配置，不做外键）
```

### 3.1 关系说明

| 关系 | 说明 |
| --- | --- |
| 用户 ↔ 角色 | 多对多，账号最多 2 个角色；应用层校验组合 |
| 角色 ↔ 权限 | 多对多；超管逻辑上拥有全部权限 |
| 用户 → 会话 | 一对多 |
| 会话 → 消息 | 一对多 |
| 会话 → 生成批次 | 一对多 |
| 批次 → 图片 | 一对多 |
| 批次 → Agent 调用 | 一对多 |
| 提示词 → 版本 | 一对多 |
| 模板/素材 → 批次 | 无外键；批次快照保存名称与参数 |

---

## 4. 表结构

### 4.1 `users` 用户表

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `username` | VARCHAR(20) | 否 | — | 登录名，全局唯一，含已删除账号 |
| `display_name` | VARCHAR(30) | 否 | — | 显示名 |
| `password_hash` | VARCHAR(255) | 否 | — | bcrypt 哈希 |
| `avatar_path` | TEXT | 是 | NULL | MinIO 对象路径（预留字段，本期不做头像上传，恒为 NULL） |
| `email` | VARCHAR(255) | 是 | NULL | 选填 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `disabled` / `deleted` |
| `token_version` | INT | 否 | 0 | 改密/禁用/删除时递增，旧 token 失效 |
| `last_login_at` | TIMESTAMPTZ | 是 | NULL | 最后登录时间 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | 是 | NULL | 软删除时间 |

**约束与索引**

- `uq_users_username`：`UNIQUE (username)`。
- `ck_users_username_format`：`username ~ '^[A-Za-z0-9_]{4,20}$'`。
- `ck_users_status`：`status IN ('active','disabled','deleted')`。
- `idx_users_status`：`(status)`。
- `idx_users_created_at`：`(created_at DESC)`。

### 4.2 `roles` 角色表

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `code` | VARCHAR(20) | 否 | — | `user` / `admin` / `super_admin` |
| `name` | VARCHAR(50) | 否 | — | 角色名称 |
| `description` | TEXT | 是 | NULL | 描述 |
| `is_system` | BOOLEAN | 否 | `true` | 内置角色 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

**约束**

- `uq_roles_code`：`UNIQUE (code)`。
- `ck_roles_code`：`code IN ('user','admin','super_admin')`。

**种子数据**

| code | name |
| --- | --- |
| `user` | 普通用户 |
| `admin` | 管理员 |
| `super_admin` | 超管 |

### 4.3 `permissions` 权限点表

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `code` | VARCHAR(64) | 否 | — | 权限码，如 `admin.accounts.view` |
| `name` | VARCHAR(64) | 否 | — | 中文名称 |
| `type` | VARCHAR(16) | 否 | — | `menu` / `action` |
| `group_name` | VARCHAR(32) | 是 | NULL | 分组，如「账号与权限」 |
| `is_super_only` | BOOLEAN | 否 | `false` | 是否超管专属 |
| `description` | TEXT | 是 | NULL | 说明 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

**约束**

- `uq_permissions_code`：`UNIQUE (code)`。
- `ck_permissions_type`：`type IN ('menu','action')`。

### 4.4 `role_permissions` 角色权限关联

| 字段 | 类型 | 空 | 说明 |
| --- | --- | --- | --- |
| `role_id` | BIGINT | 否 | 外键 `roles.id` |
| `permission_id` | BIGINT | 否 | 外键 `permissions.id` |
| `created_at` | TIMESTAMPTZ | 否 | 创建时间 |

**约束**

- 主键 `(role_id, permission_id)`。
- 外键 `ON DELETE RESTRICT`。
- `is_super_only=true` 的权限点不得关联 `admin` / `user`，应用层校验。

### 4.5 `user_roles` 用户角色关联

| 字段 | 类型 | 空 | 说明 |
| --- | --- | --- | --- |
| `user_id` | BIGINT | 否 | 外键 `users.id` |
| `role_id` | BIGINT | 否 | 外键 `roles.id` |
| `created_at` | TIMESTAMPTZ | 否 | 创建时间 |

**约束**

- 主键 `(user_id, role_id)`。
- 应用层校验：1~2 个角色；禁止 `super_admin + admin`。
- `idx_user_roles_role_id`：`(role_id)`。

### 4.6 `creative_sessions` 创作会话

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `user_id` | BIGINT | 否 | — | 外键 `users.id` |
| `title` | VARCHAR(50) | 否 | — | 会话标题 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `hidden` |
| `requirement_summary` | JSONB | 是 | NULL | 需求摘要 |
| `last_message_at` | TIMESTAMPTZ | 是 | NULL | 最后消息时间 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

> 会话不持久化参数面板内容；参数由前端 localStorage 保存，生成批次快照存于 `generation_batches.params_snapshot`。

**约束与索引**

- `ck_sessions_status`：`status IN ('active','hidden')`。
- `idx_sessions_user_status_time`：`(user_id, status, last_message_at DESC)`。
- `idx_sessions_last_message_at`：`(last_message_at DESC)`。

### 4.7 `chat_messages` 聊天消息

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `session_id` | BIGINT | 否 | — | 外键 `creative_sessions.id` |
| `role` | VARCHAR(16) | 否 | — | `user` / `assistant` / `system` |
| `agent_code` | VARCHAR(40) | 是 | NULL | Agent 消息所属 Agent |
| `content` | TEXT | 否 | — | 消息正文 |
| `content_type` | VARCHAR(16) | 否 | `text` | `text` / `markdown` |
| `client_message_id` | VARCHAR(64) | 是 | NULL | 前端幂等键 |
| `token_in` | INT | 否 | 0 | 输入 Token |
| `token_out` | INT | 否 | 0 | 输出 Token |
| `status` | VARCHAR(16) | 否 | `done` | `sending` / `done` / `failed` |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

**约束与索引**

- `ck_messages_role`：`role IN ('user','assistant','system')`。
- `ck_messages_status`：`status IN ('sending','done','failed')`。
- `uq_messages_session_client`：`UNIQUE (session_id, client_message_id)`（部分索引，`client_message_id IS NOT NULL`）。
- 首条消息建会话使用 Redis 短期幂等键（TTL 60 秒）`(user_id, client_message_id)` 去重，避免并发创建两个会话。
- `idx_messages_session_time`：`(session_id, created_at)`。
- `idx_messages_created_at`：`(created_at DESC)`。
- 可选 `idx_messages_content_trgm`：`GIN (content gin_trgm_ops)`，用于关键词搜索。**本期不启用**（内网数据量小，`ILIKE` 全表扫描可接受）；数据量大时启用 pg_trgm 扩展与索引。

### 4.8 `agent_runs` Agent 调用记录

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `session_id` | BIGINT | 是 | NULL | 外键 `creative_sessions.id` |
| `message_id` | BIGINT | 是 | NULL | 外键 `chat_messages.id` |
| `batch_id` | BIGINT | 是 | NULL | 外键 `generation_batches.id` |
| `image_id` | BIGINT | 是 | NULL | 外键 `generated_images.id` |
| `agent_code` | VARCHAR(40) | 否 | — | Agent 标识 |
| `status` | VARCHAR(16) | 否 | — | `success` / `failed` / `skipped` |
| `model_name` | VARCHAR(100) | 是 | NULL | 模型名 |
| `input_summary` | TEXT | 是 | NULL | 输入摘要 |
| `output_summary` | TEXT | 是 | NULL | 输出摘要 |
| `input_full` | TEXT | 是 | NULL | 完整输入（超管可看；**存储前已脱敏** API Key 等敏感字段） |
| `output_full` | TEXT | 是 | NULL | 完整输出（超管可看；**存储前已脱敏** API Key 等敏感字段） |
| `prompt_tokens` | INT | 否 | 0 | 输入 Token |
| `completion_tokens` | INT | 否 | 0 | 输出 Token |
| `latency_ms` | INT | 是 | NULL | 耗时 |
| `error_message` | TEXT | 是 | NULL | 错误信息 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

**约束与索引**

- `ck_agent_runs_status`：`status IN ('success','failed','skipped')`。
- `idx_agent_runs_session`：`(session_id, created_at)`。
- `idx_agent_runs_batch`：`(batch_id, created_at)`。
- `idx_agent_runs_image`：`(image_id)`。
- `idx_agent_runs_agent_time`：`(agent_code, created_at DESC)`。
- `idx_agent_runs_created_at`：`(created_at DESC)`。

### 4.9 `generation_batches` 生成批次

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `user_id` | BIGINT | 否 | — | 外键 `users.id` |
| `session_id` | BIGINT | 否 | — | 外键 `creative_sessions.id` |
| `batch_type` | VARCHAR(16) | 否 | — | `sample` / `full` |
| `source_sample_batch_id` | BIGINT | 是 | NULL | `full` 引用的示例批次 |
| `product_name` | VARCHAR(60) | 否 | — | 商品名称快照 |
| `style_text` | VARCHAR(50) | 是 | NULL | 风格文本快照 |
| `width` | INT | 否 | — | 宽 |
| `height` | INT | 否 | — | 高 |
| `template_name` | VARCHAR(50) | 是 | NULL | 模板名称快照 |
| `total_count` | INT | 否 | — | 计划张数 |
| `completed_count` | INT | 否 | 0 | 已完成张数 |
| `status` | VARCHAR(20) | 否 | `queued` | 批次状态 |
| `stage` | VARCHAR(32) | 是 | NULL | 当前阶段：Agent code / `text_composition` / `done`；`queued` 时为空 |
| `params_snapshot` | JSONB | 否 | — | 参数快照 |
| `requirement_summary` | JSONB | 是 | NULL | 生成时需求摘要 |
| `error_message` | TEXT | 是 | NULL | 失败原因 |
| `client_request_id` | VARCHAR(64) | 是 | NULL | 幂等键 |
| `started_at` | TIMESTAMPTZ | 是 | NULL | 开始时间 |
| `finished_at` | TIMESTAMPTZ | 是 | NULL | 结束时间 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

**约束与索引**

- `ck_batches_type`：`batch_type IN ('sample','full')`。
- `ck_batches_status`：`status IN ('queued','running','sample_ready','confirmed','completed','partially_failed','failed','cancelled')`。
- `ck_batches_stage`：`stage IS NULL OR stage IN ('planner','product_understanding','copywriter','prompt_builder','image_generator','quality_reviewer','repairer','platform_rule','text_composition','done')`。
- `ck_batches_source`：`batch_type='full'` 时 `source_sample_batch_id IS NOT NULL`；`batch_type='sample'` 时为空。
- `uq_batches_client_request`：`UNIQUE (client_request_id)`（部分索引）。
- `idx_batches_user_time`：`(user_id, created_at DESC)`。
- `idx_batches_session_time`：`(session_id, created_at DESC)`。
- `idx_batches_status`：`(status)`。
- `idx_batches_type`：`(batch_type)`。

### 4.10 `generated_images` 生成图片

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `batch_id` | BIGINT | 否 | — | 外键 `generation_batches.id` |
| `user_id` | BIGINT | 否 | — | 外键 `users.id` |
| `session_id` | BIGINT | 否 | — | 外键 `creative_sessions.id` |
| `image_type` | VARCHAR(16) | 否 | — | `sample` / `final` |
| `image_role` | VARCHAR(16) | 否 | — | `main` 主图 / `detail` 详情图；示例图固定为 `main` |
| `index_no` | INT | 否 | — | 组内序号 |
| `attempt_no` | INT | 否 | 1 | 第几次尝试 |
| `status` | VARCHAR(16) | 否 | `pending` | 图片状态 |
| `source_image_id` | BIGINT | 是 | NULL | 复用/替代来源 |
| `file_path` | TEXT | 是 | NULL | MinIO 对象路径 |
| `thumbnail_path` | TEXT | 是 | NULL | 缩略图路径（生图成功、文字合成后由 Worker 同步生成） |
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

**约束与索引**

- `ck_images_type`：`image_type IN ('sample','final')`。
- `ck_images_role`：`image_role IN ('main','detail')`。
- `ck_images_status`：`status IN ('pending','generating','success','failed','cancelled','superseded')`。
- `idx_images_batch_index`：`(batch_id, index_no, attempt_no)`。
- `idx_images_user_history`：`(user_id, is_history_visible, created_at DESC)`。
- `idx_images_status`：`(status)`。
- `idx_images_archived_at`：`(archived_at)`。

### 4.11 `uploaded_assets` 用户上传商品图

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `user_id` | BIGINT | 否 | — | 外键 `users.id` |
| `session_id` | BIGINT | 是 | NULL | 外键 `creative_sessions.id`；首次用于生成时回填，未使用前为空 |
| `file_path` | TEXT | 否 | — | MinIO 对象路径 |
| `thumbnail_path` | TEXT | 是 | NULL | 缩略图路径（上传时生成） |
| `original_name` | VARCHAR(255) | 否 | — | 原始文件名 |
| `mime_type` | VARCHAR(100) | 否 | — | MIME |
| `size_bytes` | BIGINT | 否 | — | 文件大小 |
| `width` | INT | 是 | NULL | 宽 |
| `height` | INT | 是 | NULL | 高 |
| `sort_order` | INT | 否 | 0 | 排序，首张为主参考图 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `deleted` |
| `archived_at` | TIMESTAMPTZ | 是 | NULL | 归档时间 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

**约束与索引**

- `ck_uploads_status`：`status IN ('active','deleted')`。
- `idx_uploads_user_session`：`(user_id, session_id, sort_order)`。
- `idx_uploads_status`：`(status)`。
- `idx_uploads_archived_at`：`(archived_at)`。

### 4.12 `templates` 模板

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `name` | VARCHAR(50) | 否 | — | 模板名称 |
| `style_text` | VARCHAR(50) | 是 | NULL | 默认风格文案，自由文本 |
| `thumbnail_path` | TEXT | 否 | — | 缩略图 |
| `prompt_template` | TEXT | 是 | NULL | 提示词模板 |
| `layout_ref` | TEXT | 是 | NULL | 版式参考 |
| `sort_order` | INT | 否 | 0 | 排序 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `disabled` |
| `created_by` | BIGINT | 是 | NULL | 创建人 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

**约束与索引**

- `ck_templates_status`：`status IN ('active','disabled')`。
- `idx_templates_status_sort`：`(status, sort_order)`。

### 4.13 `material_assets` 素材库

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `name` | VARCHAR(50) | 否 | — | 素材名称 |
| `file_path` | TEXT | 否 | — | 图片路径 |
| `thumbnail_path` | TEXT | 是 | NULL | 缩略图 |
| `tags` | JSONB | 是 | NULL | 标签数组，如 `["服饰","室内"]` |
| `style_tags` | JSONB | 是 | NULL | 风格标签 |
| `sort_order` | INT | 否 | 0 | 排序 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `disabled` |
| `created_by` | BIGINT | 是 | NULL | 创建人 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

**约束与索引**

- `ck_materials_status`：`status IN ('active','disabled')`。
- `idx_materials_status_sort`：`(status, sort_order)`。
- `idx_materials_tags`：`GIN (tags)`。

### 4.14 `model_configs` 模型配置

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `provider` | VARCHAR(32) | 否 | `volcengine_ark` | 服务商 |
| `base_url` | TEXT | 否 | — | API 地址 |
| `api_key_ciphertext` | TEXT | 是 | NULL | 加密后的 API Key |
| `text_model` | VARCHAR(100) | 否 | — | 文本模型名 |
| `image_model` | VARCHAR(100) | 否 | — | 图像模型名 |
| `vision_model` | VARCHAR(100) | 是 | NULL | 视觉模型名；为空时质量审核跳过并标记 |
| `temperature` | NUMERIC(3,1) | 否 | 0.7 | 0.0~2.0 |
| `timeout_seconds` | INT | 否 | 120 | 30~300 |
| `concurrency` | INT | 否 | 4 | 1~16 |
| `retry_count` | INT | 否 | 1 | 0~3 |
| `max_context_tokens` | INT | 是 | NULL | 上下文上限 |
| `is_active` | BOOLEAN | 否 | `true` | 当前启用配置 |
| `updated_by` | BIGINT | 是 | NULL | 修改人 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

**约束与索引**

- `ck_model_temperature`：`temperature BETWEEN 0 AND 2`。
- `ck_model_timeout`：`timeout_seconds BETWEEN 30 AND 300`。
- `ck_model_concurrency`：`concurrency BETWEEN 1 AND 16`。
- `ck_model_retry`：`retry_count BETWEEN 0 AND 3`。
- `uq_model_active`：部分唯一索引，`is_active=true` 只允许一行。

### 4.15 `system_prompts` 系统提示词

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

**约束与索引**

- `uq_prompts_agent_code`：`UNIQUE (agent_code)`。

**种子数据**

8 条：`planner`、`product_understanding`、`copywriter`、`prompt_builder`、`image_generator`、`quality_reviewer`、`repairer`、`platform_rule`。

### 4.16 `prompt_versions` 提示词版本

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `prompt_id` | BIGINT | 否 | — | 外键 `system_prompts.id` |
| `agent_code` | VARCHAR(40) | 否 | — | Agent 标识 |
| `version` | INT | 否 | — | 版本号 |
| `content` | TEXT | 否 | — | 版本内容 |
| `created_by` | BIGINT | 是 | NULL | 修改人 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

**约束与索引**

- `uq_prompt_versions`：`UNIQUE (prompt_id, version)`。
- `idx_prompt_versions_prompt`：`(prompt_id, version DESC)`。

### 4.17 `audit_logs` 操作日志

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `user_id` | BIGINT | 是 | NULL | 操作人 ID；登录失败时可能为空 |
| `username_snapshot` | VARCHAR(20) | 是 | NULL | 操作人用户名快照 |
| `action` | VARCHAR(64) | 否 | — | 动作码，如 `account.create` |
| `target_type` | VARCHAR(32) | 是 | NULL | 对象类型 |
| `target_id` | VARCHAR(64) | 是 | NULL | 对象标识 |
| `result` | VARCHAR(16) | 否 | — | `success` / `failed` |
| `ip` | VARCHAR(45) | 是 | NULL | IPv4/IPv6 |
| `user_agent` | TEXT | 是 | NULL | 浏览器标识 |
| `detail` | JSONB | 是 | NULL | 变更详情，敏感字段脱敏 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |

**约束与索引**

- `ck_audit_result`：`result IN ('success','failed')`。
- `idx_audit_created_at`：`(created_at DESC)`。
- `idx_audit_user`：`(user_id, created_at DESC)`。
- `idx_audit_action`：`(action, created_at DESC)`。
- `idx_audit_target`：`(target_type, target_id)`。

### 4.18 `size_presets` 尺寸预设

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | BIGSERIAL | 否 | — | 主键 |
| `platform_name` | VARCHAR(50) | 否 | — | 平台名称，如淘宝/天猫 |
| `width` | INT | 否 | — | 宽，正整数 |
| `height` | INT | 否 | — | 高，正整数 |
| `sort_order` | INT | 否 | 0 | 排序 |
| `status` | VARCHAR(16) | 否 | `active` | `active` / `disabled` |
| `created_by` | BIGINT | 是 | NULL | 创建人 |
| `created_at` | TIMESTAMPTZ | 否 | `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 否 | `now()` | 更新时间 |

**约束与索引**

- `ck_sizes_positive`：`width > 0 AND height > 0`。
- `ck_sizes_status`：`status IN ('active','disabled')`。
- `uq_sizes_platform_size`：`UNIQUE (platform_name, width, height)`。
- `idx_sizes_status_sort`：`(status, sort_order)`。

**种子数据**

| 平台名称 | 宽 | 高 |
| --- | --- | --- |
| 淘宝/天猫 | 1000 | 1000 |
| 京东 | 1000 | 1000 |
| 拼多多 | 1000 | 1000 |
| 抖音 | 1000 | 1000 |

---

## 5. 枚举字典

| 枚举 | 取值 |
| --- | --- |
| 用户状态 | `active` 启用 / `disabled` 禁用 / `deleted` 已删除 |
| 角色 | `user` 普通用户 / `admin` 管理员 / `super_admin` 超管 |
| 权限类型 | `menu` 菜单 / `action` 操作 |
| 会话状态 | `active` 活跃 / `hidden` 已隐藏 |
| 消息角色 | `user` / `assistant` / `system` |
| 消息状态 | `sending` / `done` / `failed` |
| Agent 运行状态 | `success` / `failed` / `skipped` |
| 批次类型 | `sample` 示例 / `full` 全套 |
| 图片角色 | `main` 主图 / `detail` 详情图（用于 `generated_images.image_role`） |
| 批次状态 | `queued` / `running` / `sample_ready` / `confirmed` / `completed` / `partially_failed` / `failed` / `cancelled` |
| 批次阶段 | `planner` / `product_understanding` / `copywriter` / `prompt_builder` / `image_generator` / `quality_reviewer` / `repairer` / `platform_rule` / `text_composition` / `done` |
| 图片类型 | `sample` 示例 / `final` 正式 |
| 图片状态 | `pending` / `generating` / `success` / `failed` / `cancelled` / `superseded` |
| 模板/素材/尺寸预设状态 | `active` 启用 / `disabled` 停用 |
| 审计结果 | `success` / `failed` |

**批次状态与类型约束**

- `sample` 批次允许：`queued`、`running`、`sample_ready`、`confirmed`、`failed`、`cancelled`。
- `full` 批次允许：`queued`、`running`、`completed`、`partially_failed`、`failed`、`cancelled`。
- 应用层校验，数据库只做全集校验。

---

## 6. 文件存储

### 6.1 桶与前缀

- MinIO 单桶：`esimage`。
- 前缀：

| 前缀 | 用途 |
| --- | --- |
| `uploads/` | 用户上传商品图 |
| `generated/` | 生成图原件 |
| `thumbnails/` | 缩略图 |
| `archive/` | 5 年后的归档原件 |
| `exports/` | 数据导出 ZIP |
| `templates/` | 模板缩略图与参考图 |
| `materials/` | 素材库文件 |
| `avatars/` | 用户头像（预留；本期不做头像上传） |

### 6.2 路径规则

| 类型 | 路径 |
| --- | --- |
| 上传图 | `uploads/{user_id}/{session_id}/{uuid}.{ext}` |
| 生成图 | `generated/{user_id}/{session_id}/{batch_id}/{uuid}.png` |
| 缩略图 | `thumbnails/{user_id}/{session_id}/{batch_id}/{uuid}_thumb.webp` |
| 归档 | `archive/{原相对路径}` |
| 导出 | `exports/{admin_user_id}/{job_id}.zip` |
| 模板 | `templates/{template_id}/{uuid}.{ext}` |
| 素材 | `materials/{material_id}/{uuid}.{ext}` |
| 头像（预留） | `avatars/{user_id}/{uuid}.{ext}`（本期不使用） |

### 6.3 文件规则

- 对象名使用 UUID，避免用户输入进入路径。
- 生成图格式：PNG。
- 缩略图：最大宽度 400px，WebP，质量 80。
- 原始文件名只存数据库，不用于对象名。
- 桶不公开；所有访问经后端鉴权后流式返回。
- 上传时校验 MIME、扩展名、大小、可解码性。
- 单文件上限 10MB。
- 归档时保持相对路径不变，便于恢复。

---

## 7. 保留与归档

### 7.1 热数据

- 业务数据（数据库记录）永久保留。
- 图片原件（`generated/`、`uploads/`）热存 5 年。
- 缩略图长期保留在 `thumbnails/`，用于列表展示。

### 7.2 归档任务

- 调度：每日 03:00（Asia/Shanghai）。
- 扫描 `generated_images` 与 `uploaded_assets` 中 `created_at < now() - 5 years` 且 `archived_at IS NULL` 的记录。
- 将原件从原前缀复制到 `archive/`，校验成功后删除原件。
- 更新 `archived_at`。
- 记录任务日志：扫描数、成功数、失败数、耗时。
- 失败记录重试，不阻塞其他记录。
- 归档不删除数据库记录。

### 7.3 读取归档

- 单图详情、历史作品仍展示缩略图。
- 下载或查看大图时，后端检测 `archived_at`，从 `archive/` 读取。
- 归档读取失败返回 `30014`，提示「文件归档中，请稍后重试」。

### 7.4 导出文件清理

- 导出 ZIP 存于 `exports/`，有效期 24 小时。
- 定时任务清理过期文件与 Redis 中的任务状态。
- 清理任务记录审计日志（可选）。

### 7.5 孤儿上传清理

- 调度：每日 04:00（Asia/Shanghai）。
- 扫描 `uploaded_assets` 中 `status='active'`、`session_id IS NULL`、`created_at < now() - 30 days` 且未被任何批次的 `params_snapshot` 引用的记录。
- 将该记录置为 `deleted`，并删除 MinIO 原件与缩略图对象。
- 记录任务日志：扫描数、清理数、失败数、耗时；失败记录重试。

---

## 8. 备份与恢复

### 8.1 备份

| 项目 | 规则 |
| --- | --- |
| 数据库 | 每日 02:00 `pg_dump`（custom format） |
| 对象存储 | 每日 `mc mirror` 到备份卷/远端 |
| 保留 | 7 天 |
| 位置 | 独立备份卷或远端对象存储，不与主数据同盘 |
| 校验 | 备份完成后校验文件大小与可读性 |

### 8.2 恢复

1. 停止 `backend`、`worker`。
2. 恢复 PostgreSQL：`pg_restore`。
3. 恢复 MinIO：`mc mirror` 备份到主桶。
4. 启动 `backend`、`worker`。
5. 校验：登录、读取会话、读取图片、触发生成。
6. 记录恢复操作与时间。

### 8.3 安全

- 备份文件不进入 Git。
- 备份卷权限仅服务账号可读。
- 如备份到远端，使用独立凭据与加密传输。

---

## 9. 数据导出

- 导出逻辑与文件结构见 `7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md` 第 8 章。
- 导出 ZIP 存于 `exports/`，状态存 Redis，TTL 24 小时。
- 不新增导出任务表。
- 导出内容不含密码哈希、API Key、JWT。
- 导出操作写入 `audit_logs`。

---

## 10. 迁移与种子数据

### 10.1 迁移

- 使用 Alembic 管理迁移。
- 每次迁移必须可回滚。
- 生产迁移前先备份。
- 迁移脚本不得删除业务数据。

### 10.2 种子数据

| 数据 | 内容 |
| --- | --- |
| 角色 | `user`、`admin`、`super_admin` |
| 权限点 | 第 11 章清单 |
| 超管角色权限 | 全部权限点（用于展示；逻辑上仍绕过） |
| 风格 | 不预置风格表；风格由用户填写或 Agent 推荐 |
| 尺寸预设 | `size_presets` 种子：淘宝/天猫、京东、拼多多、抖音，均 1000×1000 |
| 系统提示词 | 8 个 Agent 各一条初始提示词；`platform_rule` 含平台规范初始规则 |
| 模型配置 | 一条默认配置，`api_key` 为空，等待超管填写 |
| 超管账号 | 首次部署通过初始化脚本创建，密码由部署人设置 |

- 种子脚本必须幂等：存在则跳过，不覆盖已修改数据。
- 初始超管账号不得使用弱默认密码；未设置时拒绝启动或强制初始化。

---

## 11. 权限点清单

与 `6-管理后台-账号与权限/6-管理后台-账号与权限prd.md` 第 11 章一致，数据库种子需包含：

- 用户端：`user.workspace`、`user.generate`、`user.history`、`user.profile`
- 管理端菜单：`admin.dashboard.view`、`admin.accounts.view`、`admin.roles.view`、`admin.content.view`、`admin.assets.view`、`admin.prompts.view`、`admin.model.view`、`admin.tokens.view`、`admin.audit.view`
- 管理端操作：`admin.accounts.create`、`admin.accounts.edit`、`admin.accounts.reset_password`、`admin.accounts.disable`、`admin.accounts.delete`、`admin.roles.edit`、`admin.assets.edit`、`admin.prompts.edit`、`admin.model.edit`、`admin.export`
- 超管专属：`admin.roles.view`、`admin.roles.edit`、`admin.model.view`、`admin.model.edit`、`admin.audit.view`、`admin.export`

---

## 12. 验收标准

1. 18 张表按本文档创建，字段类型、空值、默认值、约束一致。
2. 外键不级联删除；删除账号为软删除，历史数据保留。
3. 用户名唯一约束包含已删除账号。
4. 角色组合规则在应用层生效，超管+管理员被拒绝。
5. 批次类型与状态符合枚举；`full` 批次必须引用 `sample` 批次。
6. 图片状态流转符合状态机；`generated_images.image_role` 为 1 个 `main` + 5 个 `detail`；历史可见性字段正确。
7. Agent 调用记录包含 Token、耗时、状态与输入输出摘要。
8. 审计日志不包含密码、API Key、JWT。
9. MinIO 使用单桶 `esimage` 与前缀分区，路径符合规则。
10. 5 年归档任务每日执行，原件迁入 `archive/`，缩略图保留热存。
11. 导出文件 24 小时过期清理。
12. 每日备份可执行、可恢复，保留 7 天。
13. Alembic 迁移可正向与回滚执行。
14. 种子数据幂等，初始超管账号必须显式设置密码。

---

## 13. 待确认项

> 以下事项已于 2026-10-31 细化评审中确定。

| 序号 | 事项 | 结论 |
| --- | --- | --- |
| 1 | `chat_messages.content` 是否启用 pg_trgm 全文索引 | 已确定：本期不启用，ILIKE 即可；数据量大时启用 |
| 2 | 归档后缩略图是否也归档 | 已确定：缩略图保持热存 |
| 3 | 备份是否复制到远端对象存储 | 已确定：先本地备份卷，远端可选 |
| 4 | 初始超管账号的创建方式 | 已确定：部署脚本初始化，禁止弱默认密码 |
| 5 | 是否需要数据保留期配置化 | 已确定：固定 5 年，配置化后续再做 |
