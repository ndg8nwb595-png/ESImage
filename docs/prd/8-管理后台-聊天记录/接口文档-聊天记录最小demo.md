# 聊天记录最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `8-管理后台-聊天记录prd.md` §3~§10；`9-后端服务与接口prd.md` §2/§3/§4/§6.4/§6.5；`10-数据模型与存储prd.md` §4.6~§4.9、§4.14~§4.17 |
| 覆盖范围 | 聊天记录列表、会话详情与消息窗口、Agent 调用明细、消息搜索、模型配置、系统提示词与版本 |
| 文档状态 | 最小 demo 约定；正式实现需与 9 号文档统一 |

> 本文档只描述最小 demo 需要落地的接口。聊天导出、消息发送/编辑/删除、会话恢复、模型连通性测试、提示词 diff、A/B 测试、概览与 Token 统计、数据导出等不在本次范围内。

---

## 1. 通用约定

### 1.1 地址与编码

| 项目 | 约定 |
| --- | --- |
| Base URL | `/api/v1` |
| 本地联调 | 前端通过 Vite 开发代理把 `/api` 转发到后端，避免额外 CORS 配置 |
| 请求/响应格式 | JSON：`application/json; charset=utf-8` |
| 字段命名 | `snake_case` |
| ID | 整数，数据库 `BIGSERIAL` |
| 时间格式 | ISO 8601 带时区偏移，例如 `2026-10-31T10:00:00+08:00` |
| 日期筛选格式 | `YYYY-MM-DD`，按本地时区（+08:00）取当天 00:00:00 ~ 23:59:59.999 |
| 空值 | `null`，不省略字段 |

### 1.2 统一响应

除文件流外，所有接口返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | int | `0` 表示成功；非 0 为业务错误码 |
| `message` | string | 面向用户的提示文案 |
| `data` | object / null | 成功时的数据；业务错误时可为 `null` |

### 1.3 HTTP 状态码与业务码

| HTTP | 场景 | 业务码段 |
| --- | --- | --- |
| 200 | 成功 | `0` |
| 400 | 参数缺失、格式错误、超出范围、锚点参数冲突 | `1xxxx` |
| 401 | 未登录、登录过期、token 无效或版本不符 | `2xxxx` |
| 403 | 无权限、账号禁用/删除、管理员访问超管内容、管理员请求完整输入输出 | `2xxxx` |
| 404 | 会话、消息、Agent 调用、提示词、提示词版本不存在 | `30013` / `30020` / `30021` / `30022` / `30023` |
| 500 | 服务端异常、数据库错误、加密失败 | `5xxxx` |

### 1.4 鉴权与权限判定

```http
Authorization: Bearer <jwt>
```

除登录接口外，所有接口必须携带 token。每次请求按以下顺序校验：

1. 解析并校验 JWT 签名与过期时间：未携带或签名错误返回 401 `20003`，过期返回 401 `20002`。
2. 按 `sub` 读取用户；账号不存在、`status=disabled` 或 `status=deleted` 返回 403 `20004`。
3. 校验 token 中的 `token_version` 与该用户当前 `token_version` 一致；不一致返回 401 `20003`。
4. 读取用户角色与权限：`super_admin` 直接拥有全部权限码；其他角色取 `role_permissions` 并集。
5. 校验接口所需权限码；缺失返回 403 `20005`。

> 本 demo 不接 Redis，每次请求直查 PostgreSQL；权限变更在下一次请求立即生效。

### 1.5 分页

聊天会话列表与消息搜索使用页码分页：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 1 | 从 1 开始；小于 1 按 1 处理 |
| `page_size` | int | 20 | 会话列表仅接受 20/50/100；消息搜索固定 20，不开放该参数 |

响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20
  }
}
```

会话详情的消息流使用游标，不使用页码分页，见第 4 章。

### 1.6 字符串匹配

- 用户关键词、会话标题、消息搜索均为大小写不敏感的子串匹配。
- 使用 PostgreSQL `ILIKE`；对用户输入中的 `\`、`%`、`_` 做转义，并以 `ESCAPE '\'` 执行，避免用户输入被当作通配符。
- 去除首尾空格后为空的关键词按「未提供」处理；必填关键词为空返回参数错误。
- 本 demo 不建 `pg_trgm` / 全文索引；数据量大时按 10 号 §4.7 升级。

### 1.7 只读边界

聊天记录相关接口只提供读取。管理后台不提供以下能力：

- 发送消息、编辑消息、删除消息。
- 恢复已隐藏会话。
- 导出聊天记录。
- 以某个用户身份继续对话。
- 修改 `agent_runs` 的输入/输出、Token、状态。

---

## 2. 最小 demo 约定

### 2.1 运行形态

| 项目 | demo 处理 | 正式实现 |
| --- | --- | --- |
| 权限缓存 | 每次请求直查 PostgreSQL | Redis 缓存 ≤30 秒、变更主动失效（9 号 §2.7） |
| 数据库迁移 | 建表脚本 + 幂等种子脚本 | Alembic（10 号 §10） |
| 聊天数据 | 幂等种子夹具 | 用户真实聊天与生成数据 |
| 消息搜索 | `ILIKE`，不建索引 | 数据量大时启用 pg_trgm / 全文检索 |
| 模型配置缓存 | 每次读取直查数据库 | 保存后刷新缓存，下一次调用生效 |
| 提示词缓存 | 每次读取直查数据库 | 保存后立即刷新缓存 |
| 提示词并发 | 行锁 + 后保存者覆盖 | 与 6 号角色权限保存口径一致 |

### 2.2 演示账号与权限

| 用户名 | 密码 | 角色 | 聊天记录 | Agent 完整输入输出 | 模型配置 | 系统提示词 |
| --- | --- | --- | --- | --- | --- | --- |
| `demo_super` | `Demo1234` | `super_admin` | 全部会话 | ✓ | ✓ | ✓ |
| `demo_admin` | `Demo1234` | `admin` | 非超管账号的会话 | ✗ | ✗ | ✓ |
| `demo_user` | `Demo1234` | `user` | ✗ | ✗ | ✗ | ✗ |
| `demo_dual` | `Demo1234` | `user` + `admin` | 同 `admin` | ✗ | ✗ | ✓ |

- 权限点沿用 6 号 demo 种子：`admin.content.view`、`admin.prompts.view`、`admin.prompts.edit` 授予 `admin`；`admin.model.view`、`admin.model.edit` 为超管专属。
- `super_admin` 不依赖 `role_permissions`，按角色即时授予全部权限码。
- 管理员访问超管账号的会话或该会话下的 Agent 调用，统一返回 403 `20005`；不返回 404，避免与本 demo 的「不存在」语义混淆。

### 2.3 幂等种子

种子脚本重复执行不覆盖已有数据。

| 归属 | 会话标题 | 状态 | 消息数 | Agent 调用 | 生成批次 |
| --- | --- | --- | --- | --- | --- |
| `demo_user` | 秋季通勤衬衫 | `active` | 12 | 6（`success` / `failed` / `skipped` 混合） | 2（`sample` + `full`） |
| `demo_user` | 夏季防晒外套 | `hidden` | 6 | 2 | 1（`sample`） |
| `demo_user` | 通勤鞋搭配建议 | `active` | 4 | 2 | 0 |
| `demo_super` | 超管测试会话 | `active` | 2 | 1 | 0 |

- 以 `(user_id, title)` 识别会话；会话已存在时跳过其消息、Agent 调用与批次。
- 累计 Token 由 `agent_runs.prompt_tokens + completion_tokens` 汇总，种子保证与列表一致。
- 至少 1 条 Agent 消息的 `agent_runs.batch_id` 非空，用于演示「查看批次」。
- 至少 1 条消息内容含「衬衫」，1 条含 `T-shirt`，1 条超管会话消息含「超管」。
- 所有 `input_full` / `output_full` 种子文本在写入前已脱敏，不含真实 API Key、密码或 JWT。

### 2.4 数据表最小字段

本 demo 使用以下表；建表脚本按 10 号字段创建，`CREATE TABLE IF NOT EXISTS`，已存在则跳过。

| 表 | 本 demo 使用字段 |
| --- | --- |
| `creative_sessions` | `id`、`user_id`、`title`、`status`、`requirement_summary`、`last_message_at`、`created_at`、`updated_at` |
| `chat_messages` | `id`、`session_id`、`role`、`agent_code`、`content`、`content_type`、`client_message_id`、`token_in`、`token_out`、`status`、`created_at` |
| `agent_runs` | `id`、`session_id`、`message_id`、`batch_id`、`image_id`、`agent_code`、`status`、`model_name`、`input_summary`、`output_summary`、`input_full`、`output_full`、`prompt_tokens`、`completion_tokens`、`latency_ms`、`error_message`、`created_at` |
| `generation_batches` | `id`、`user_id`、`session_id`、`batch_type`、`product_name`、`status`、`created_at` |
| `model_configs` | `id`、`provider`、`base_url`、`api_key_ciphertext`、`text_model`、`image_model`、`vision_model`、`temperature`、`timeout_seconds`、`concurrency`、`retry_count`、`max_context_tokens`、`is_active`、`updated_by`、`updated_at` |
| `system_prompts` | `id`、`agent_code`、`name`、`content`、`current_version`、`is_active`、`updated_by`、`created_at`、`updated_at` |
| `prompt_versions` | `id`、`prompt_id`、`agent_code`、`version`、`content`、`created_by`、`created_at` |
| `audit_logs` | `id`、`user_id`、`username_snapshot`、`action`、`target_type`、`target_id`、`result`、`ip`、`user_agent`、`detail`、`created_at` |

### 2.5 模型配置加密

| 项目 | 约定 |
| --- | --- |
| 算法 | AES-256-GCM |
| 密钥 | 环境变量 `MODEL_CONFIG_ENCRYPTION_KEY`，base64 编码的 32 字节密钥 |
| 随机数 | 每次加密生成 12 字节 nonce |
| 存储 | `base64(nonce + ciphertext + tag)` 写入 `model_configs.api_key_ciphertext` |
| 脱敏 | 明文长度 ≥ 8 时取前 3 位 + `****` + 后 4 位；长度 < 8 时统一 `****` |
| 明文边界 | 只在保存时加密、读取时解密后取后 4 位；不写日志、不写审计、不返回明文 |
| 启动校验 | 密钥缺失或不是 32 字节时应用启动失败，并输出明确错误 |

> 4 号 demo 使用环境变量 `DOUBAO_API_KEY` 直接调用豆包；本 demo 的模型配置写入数据库。正式实现需统一「数据库配置」与「环境变量」的优先级；本 demo 不发起真实模型调用。

### 2.6 Agent 字典与建议变量

| `agent_code` | 名称 | 建议变量 |
| --- | --- | --- |
| `planner` | 规划 Agent | `product_name`、`params`、`requirement_summary`、`chat_summary` |
| `product_understanding` | 商品理解 Agent | `product_name`、`params`、`requirement_summary`、`chat_summary` |
| `copywriter` | 文案 Agent | `product_name`、`params`、`requirement_summary`、`chat_summary`、`product_profile`、`plan`、`platform_rules` |
| `prompt_builder` | 提示词 Agent | `product_name`、`params`、`requirement_summary`、`product_profile`、`plan`、`copy_blocks` |
| `image_generator` | 生图执行 Agent | 无（系统级约束） |
| `quality_reviewer` | 质量审核 Agent | `product_profile` |
| `repairer` | 修复 Agent | `product_profile`、`review_issues` |
| `platform_rule` | 平台规范 Agent | `copy_blocks`、`platform_rules` |

- 变量名区分大小写。
- 全局可用变量为 9 个：`product_name`、`params`、`requirement_summary`、`chat_summary`、`product_profile`、`plan`、`copy_blocks`、`review_issues`、`platform_rules`。
- 不在全局清单中的变量为「未知变量」，原样保留并在保存时提示。
- 变量语法：`{{变量名}}`，允许花括号内两侧有空格；变量名匹配 `[A-Za-z_][A-Za-z0-9_]*`。

---

## 3. 聊天会话列表

### 3.1 请求

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `GET /api/v1/admin/chat/sessions` |
| 权限 | `admin.content.view` |
| 鉴权 | Bearer JWT |

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `user_keyword` | string | 否 | — | 匹配用户名或显示名，1~50 字符 |
| `title_keyword` | string | 否 | — | 匹配会话标题，1~50 字符 |
| `last_message_from` | date | 否 | — | 最后消息时间下限，`YYYY-MM-DD` |
| `last_message_to` | date | 否 | — | 最后消息时间上限，`YYYY-MM-DD` |
| `status` | string | 否 | `all` | `active` / `hidden` / `all` |
| `page` | int | 否 | 1 | 从 1 开始 |
| `page_size` | int | 否 | 20 | 仅接受 20/50/100 |

- `last_message_from` 晚于 `last_message_to` 返回 400 `10004`。
- 空字符串参数按未提供处理。
- 管理员可见范围排除拥有 `super_admin` 角色的账号的会话；超管可看全部。
- 已软删除账号的会话仍返回，保证内容可追溯；用户对象只返回 ID、用户名、显示名。

### 3.2 响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "session_id": 101,
        "user": {
          "user_id": 3,
          "username": "demo_user",
          "display_name": "演示用户"
        },
        "title": "秋季通勤衬衫",
        "status": "active",
        "message_count": 12,
        "last_message_at": "2026-10-30T18:20:00+08:00",
        "token_usage": {
          "prompt_tokens": 5200,
          "completion_tokens": 7140,
          "total_tokens": 12340
        },
        "batch_count": 2,
        "created_at": "2026-10-28T09:00:00+08:00",
        "updated_at": "2026-10-30T18:20:00+08:00"
      }
    ],
    "total": 3,
    "page": 1,
    "page_size": 20
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | int | 会话 ID |
| `user.user_id` | int | 用户 ID |
| `user.username` | string | 用户名 |
| `user.display_name` | string | 显示名 |
| `title` | string | 会话标题 |
| `status` | string | `active` / `hidden` |
| `message_count` | int | 用户 + Agent + 系统消息总数 |
| `last_message_at` | string / null | 最后消息时间；无消息时为 `null` |
| `token_usage.prompt_tokens` | int | 该会话全部 Agent 调用输入 Token |
| `token_usage.completion_tokens` | int | 该会话全部 Agent 调用输出 Token |
| `token_usage.total_tokens` | int | 输入 + 输出 |
| `batch_count` | int | 该会话的生成批次数 |
| `created_at` | string | 会话创建时间 |
| `updated_at` | string | 会话更新时间 |

### 3.3 排序与聚合口径

- 排序：`COALESCE(last_message_at, created_at) DESC, id DESC`。
- `message_count`：`chat_messages` 中该会话全部消息，不区分角色与状态。
- `token_usage`：`agent_runs` 中该会话全部调用的 `prompt_tokens` / `completion_tokens` 之和；`skipped` 调用通常为 0，仍按实际值计入。
- `batch_count`：`generation_batches` 中该会话的全部批次，不区分状态。
- `last_message_at`：取 `creative_sessions.last_message_at`，不实时扫描消息表。

### 3.4 错误

| 场景 | HTTP | 业务码 |
| --- | --- | --- |
| 未登录 / token 无效 / 过期 | 401 | `20002` / `20003` |
| 账号禁用或删除 | 403 | `20004` |
| 缺少 `admin.content.view` | 403 | `20005` |
| `status` 非枚举 | 400 | `10003` |
| `page_size` 非 20/50/100、日期范围倒置 | 400 | `10004` |

---

## 4. 会话详情与消息窗口

### 4.1 请求

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `GET /api/v1/admin/chat/sessions/{session_id}` |
| 权限 | `admin.content.view` |
| 鉴权 | Bearer JWT |

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `before_id` | int | 否 | — | 加载 ID 小于该值的更早消息 |
| `around_id` | int | 否 | — | 定位到该消息，返回其前后窗口 |
| `limit` | int | 否 | 20 | 本次返回消息数，1~50 |

- `before_id` 与 `around_id` 同时出现返回 400 `10001`。
- 两者都不传：返回最新 `limit` 条消息。
- `around_id` 不属于该会话：返回 404 `30023`。
- 会话不存在：返回 404 `30013`。
- 管理员访问超管账号的会话：返回 403 `20005`。
- 已隐藏会话对管理员/超管仍可访问。

### 4.2 消息窗口语义

| 场景 | 返回 |
| --- | --- |
| 默认 | 最新 `limit` 条，按 ID 正序 |
| `before_id=X` | ID < X 的最近 `limit` 条，按 ID 正序 |
| `around_id=X` | 锚点与前后消息，总数不超过 `limit`；锚点必含 |

`around_id` 的取数规则：

1. 取 ID < 锚点的最近 `floor((limit - 1) / 2)` 条，按正序。
2. 加入锚点。
3. 取 ID > 锚点的最早 `limit - 1 - 已取更早条数` 条，按正序。
4. 若一侧不足，不向另一侧无限扩张；仍以最多 `limit` 条为上限。

- `has_older`：存在 ID 小于本次返回第一条消息的消息。
- `has_newer`：存在 ID 大于本次返回最后一条消息的消息。
- 消息 ID 单调递增，作为游标；不按 `created_at` 做游标，避免同一时间戳顺序不稳定。

### 4.3 响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "session": {
      "session_id": 101,
      "user": {
        "user_id": 3,
        "username": "demo_user",
        "display_name": "演示用户"
      },
      "title": "秋季通勤衬衫",
      "status": "active",
      "message_count": 12,
      "token_usage": {
        "prompt_tokens": 5200,
        "completion_tokens": 7140,
        "total_tokens": 12340
      },
      "batch_count": 2,
      "last_message_at": "2026-10-30T18:20:00+08:00",
      "created_at": "2026-10-28T09:00:00+08:00",
      "updated_at": "2026-10-30T18:20:00+08:00"
    },
    "messages": [
      {
        "message_id": 1001,
        "role": "assistant",
        "agent_code": "planner",
        "agent_name": "规划 Agent",
        "content": "好的，我先确认几个信息……",
        "content_type": "markdown",
        "token_in": 120,
        "token_out": 300,
        "status": "done",
        "created_at": "2026-10-30T18:20:00+08:00",
        "agent_runs": [
          {
            "run_id": 2001,
            "agent_code": "planner",
            "agent_name": "规划 Agent",
            "status": "success",
            "latency_ms": 820,
            "prompt_tokens": 120,
            "completion_tokens": 300,
            "model_name": "doubao-demo-text"
          }
        ],
        "related_batches": [
          {
            "batch_id": 301,
            "batch_type": "sample",
            "status": "completed",
            "product_name": "秋季通勤衬衫",
            "created_at": "2026-10-30T18:21:00+08:00"
          }
        ]
      }
    ],
    "has_older": true,
    "has_newer": false,
    "anchor_message_id": null
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session` | object | 顶部摘要，字段同列表项 |
| `messages[].message_id` | int | 消息 ID |
| `messages[].role` | string | `user` / `assistant` / `system` |
| `messages[].agent_code` | string / null | Agent 消息所属 Agent；用户/系统消息为 `null` |
| `messages[].agent_name` | string / null | Agent 中文名 |
| `messages[].content` | string | 消息正文 |
| `messages[].content_type` | string | `text` / `markdown` |
| `messages[].token_in` | int | 消息输入 Token |
| `messages[].token_out` | int | 消息输出 Token |
| `messages[].status` | string | `sending` / `done` / `failed` |
| `messages[].created_at` | string | 消息时间 |
| `messages[].agent_runs` | array | 该消息关联的调用摘要，按调用顺序 |
| `messages[].related_batches` | array | 该消息关联的批次摘要 |
| `has_older` | bool | 是否还有更早消息 |
| `has_newer` | bool | 是否还有更新消息 |
| `anchor_message_id` | int / null | 本次定位的锚点消息 |

### 4.4 消息与批次关联

- `chat_messages` 没有 `batch_id` 字段；本 demo 通过 `agent_runs.message_id → agent_runs.batch_id` 推导消息关联的批次。
- `related_batches` 按 `batch_id` 去重，返回 `generation_batches` 的 ID、类型、状态、商品名称与创建时间。
- 用户消息与系统消息通常没有关联批次；若种子或真实数据通过 `agent_runs` 建立了关联，同样返回。
- 「查看批次」打开只读摘要抽屉；完整生图详情页由 7 号 PRD 提供，本 demo 不实现三层钻取。

### 4.5 渲染与只读

- 用户消息：保留换行，不解析 Markdown。
- Agent 消息：支持加粗、斜体、有序/无序列表、换行、行内代码；禁止原始 HTML；链接仅允许 `http/https`。
- 系统消息：纯文本，居中展示。
- 页面不提供发送、编辑、删除、恢复、导出入口。
- 超过 120 秒仍为 `sending` 的 Agent 消息，按 3 号 demo 约定惰性标记为 `failed` 后再返回。

### 4.6 错误

| 场景 | HTTP | 业务码 |
| --- | --- | --- |
| 会话不存在 | 404 | `30013` |
| 锚点消息不存在或不属于该会话 | 404 | `30023` |
| `limit` 超出 1~50 | 400 | `10004` |
| `before_id` / `around_id` 非正整数 | 400 | `10003` |
| `before_id` 与 `around_id` 同时出现 | 400 | `10001` |
| 管理员访问超管会话 | 403 | `20005` |
| 缺少 `admin.content.view` | 403 | `20005` |

---

## 5. Agent 调用明细

### 5.1 请求

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `GET /api/v1/admin/agent-runs/{run_id}` |
| 权限 | `admin.content.view` |
| 鉴权 | Bearer JWT |

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `full` | bool | 否 | `false` | 是否返回完整输入/输出；仅超管可传 `true` |

- 管理员传 `full=true` 返回 403 `20005`。
- 管理员不传或传 `false`，只返回摘要。
- 超管传 `false`，完整字段为 `null`，避免默认传输大文本。

### 5.2 响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "run_id": 2001,
    "session_id": 101,
    "message_id": 1001,
    "batch_id": 301,
    "image_id": null,
    "agent_code": "planner",
    "agent_name": "规划 Agent",
    "status": "success",
    "model_name": "doubao-demo-text",
    "created_at": "2026-10-30T18:20:01+08:00",
    "latency_ms": 820,
    "token_usage": {
      "prompt_tokens": 120,
      "completion_tokens": 300,
      "total_tokens": 420
    },
    "input_summary": "商品名称：秋季通勤衬衫；风格：简洁……",
    "output_summary": "任务计划：主图 1 张、详情图 5 张……",
    "input_full": null,
    "output_full": null,
    "full_available": true,
    "error_message": null
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | int | 调用记录 ID |
| `session_id` | int / null | 会话 ID |
| `message_id` | int / null | 关联消息 ID |
| `batch_id` | int / null | 关联批次 ID |
| `image_id` | int / null | 关联图片 ID |
| `agent_code` | string | Agent 标识 |
| `agent_name` | string | Agent 中文名 |
| `status` | string | `success` / `failed` / `skipped` |
| `model_name` | string / null | 使用的模型名 |
| `created_at` | string | 开始时间，取 `agent_runs.created_at` |
| `latency_ms` | int / null | 耗时毫秒 |
| `token_usage.prompt_tokens` | int | 输入 Token |
| `token_usage.completion_tokens` | int | 输出 Token |
| `token_usage.total_tokens` | int | 输入 + 输出 |
| `input_summary` | string / null | 输入摘要 |
| `output_summary` | string / null | 输出摘要 |
| `input_full` | string / null | 完整输入；仅超管且 `full=true` 时返回 |
| `output_full` | string / null | 完整输出；仅超管且 `full=true` 时返回 |
| `full_available` | bool | 当前角色是否可查看完整内容；超管 `true`，管理员 `false` |
| `error_message` | string / null | 失败原因 |

### 5.3 可见范围

- 管理员只能访问非超管账号会话下的调用。
- 调用记录通过 `session_id` 找到所属用户；`session_id` 为空时通过 `batch_id → generation_batches.session_id` 推导。
- 仍无法确定归属时，管理员访问返回 403 `20005`；超管可访问。
- 管理员访问超管会话下的调用返回 403 `20005`。
- 调用不存在返回 404 `30020`。

### 5.4 内容边界

- `input_full` / `output_full` 为写入时已脱敏的文本；后台不再拼接、不再调用模型。
- 不返回 API Key、密码、JWT、内部思维链、用户上传图二进制。
- 系统提示词全文不在明细中返回；如需查看，跳转「Agent 配置 → 系统提示词」。
- 输入/输出摘要由写入方截断到 2000 字符；后台按存储内容原样返回。

### 5.5 错误

| 场景 | HTTP | 业务码 |
| --- | --- | --- |
| 调用不存在 | 404 | `30020` |
| 管理员访问超管会话下的调用 | 403 | `20005` |
| 管理员传 `full=true` | 403 | `20005` |
| 缺少 `admin.content.view` | 403 | `20005` |

---

## 6. 消息关键词搜索

### 6.1 请求

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `GET /api/v1/admin/chat/messages/search` |
| 权限 | `admin.content.view` |
| 鉴权 | Bearer JWT |

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `keyword` | string | 是 | — | 关键词，去除首尾空格后 1~100 字符 |
| `page` | int | 否 | 1 | 从 1 开始 |

- 每页固定 20 条，不开放 `page_size`。
- 搜索范围：`chat_messages.content`；包含 `active` 与 `hidden` 会话；管理员排除超管账号的会话，超管包含全部。
- 大小写不敏感；对 `\`、`%`、`_` 转义。
- 不提供正则、布尔组合、字段限定、导出、按用户/Agent/时间二次筛选。

### 6.2 响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "message_id": 1003,
        "session_id": 101,
        "session_title": "秋季通勤衬衫",
        "session_status": "active",
        "user": {
          "user_id": 3,
          "username": "demo_user",
          "display_name": "演示用户"
        },
        "role": "user",
        "agent_code": null,
        "agent_name": null,
        "snippet": "帮我做一套秋季通勤衬衫的图，风格简洁一点……",
        "created_at": "2026-10-30T18:18:00+08:00"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message_id` | int | 消息 ID |
| `session_id` | int | 会话 ID |
| `session_title` | string | 会话标题 |
| `session_status` | string | `active` / `hidden` |
| `user` | object | 用户 ID、用户名、显示名 |
| `role` | string | `user` / `assistant` / `system` |
| `agent_code` | string / null | Agent 消息所属 Agent |
| `agent_name` | string / null | Agent 中文名 |
| `snippet` | string | 命中位置附近的纯文本摘要 |
| `created_at` | string | 消息时间 |

### 6.3 摘要与高亮

- 找到第一个大小写不敏感的命中位置；向前后各取约 40 字符，总长度不超过约 120 字符。
- 将换行与连续空白折叠为单个空格；截断处加 `…`。
- 返回纯文本，不返回 HTML；前端用原始 `keyword` 对 `snippet` 做大小写不敏感高亮。
- 点击结果跳转 `/admin/chat-records/{session_id}?around_id={message_id}`；会话详情按第 4 章返回锚点窗口。

### 6.4 错误

| 场景 | HTTP | 业务码 |
| --- | --- | --- |
| 缺少 `keyword` 或全空格 | 400 | `10002` |
| `keyword` 超过 100 字符 | 400 | `10004` |
| `page` 非正整数 | 400 | `10003` |
| 缺少 `admin.content.view` | 403 | `20005` |

---

## 7. 模型配置

### 7.1 读取

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `GET /api/v1/admin/model-config` |
| 权限 | `admin.model.view`（超管专属） |
| 鉴权 | Bearer JWT |

响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "provider": "volcengine_ark",
    "provider_label": "豆包（火山方舟）",
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key_masked": null,
    "api_key_configured": false,
    "text_model": "doubao-demo-text",
    "image_model": "doubao-demo-image",
    "vision_model": null,
    "temperature": 0.7,
    "timeout_seconds": 120,
    "concurrency": 4,
    "retry_count": 1,
    "max_context_tokens": 32000,
    "updated_by": {
      "user_id": 1,
      "username": "demo_super",
      "display_name": "演示超管"
    },
    "updated_at": "2026-10-31T10:00:00+08:00"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `provider` | string | 固定 `volcengine_ark` |
| `provider_label` | string | 固定「豆包（火山方舟）」 |
| `base_url` | string | API 地址 |
| `api_key_masked` | string / null | 脱敏 Key；未配置为 `null` |
| `api_key_configured` | bool | 是否已配置 Key |
| `text_model` | string | 文本模型名 |
| `image_model` | string | 图像模型名 |
| `vision_model` | string / null | 视觉模型名；为空时质量审核跳过并标记「未校验」 |
| `temperature` | number | 0~2，步长 0.1 |
| `timeout_seconds` | int | 30~300 |
| `concurrency` | int | 1~16，豆包侧并发上限 |
| `retry_count` | int | 0~3，HTTP 瞬态重试次数 |
| `max_context_tokens` | int / null | 1024~128000 |
| `updated_by` | object / null | 最后修改人 |
| `updated_at` | string / null | 最后修改时间 |

- 无启用配置时返回默认骨架：`provider`、`provider_label` 固定，其余字段为 `null`，`api_key_configured=false`，`updated_by=null`，`updated_at=null`。
- 管理员与普通用户返回 403 `20005`。

### 7.2 保存

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `PUT /api/v1/admin/model-config` |
| 权限 | `admin.model.edit`（超管专属） |
| 鉴权 | Bearer JWT |

请求：

```json
{
  "base_url": "https://ark.cn-beijing.volces.com/api/v3",
  "api_key": "sk-demo-1234",
  "text_model": "doubao-demo-text",
  "image_model": "doubao-demo-image",
  "vision_model": null,
  "temperature": 0.7,
  "timeout_seconds": 120,
  "concurrency": 4,
  "retry_count": 1,
  "max_context_tokens": 32000
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `base_url` | string | 是 | 合法 `http/https` 地址，1~500 字符 |
| `api_key` | string / null | 否 | 省略、`null` 或空字符串表示不修改；非空最长 512 字符；保存时加密 |
| `text_model` | string | 是 | 非空，1~100 字符 |
| `image_model` | string | 是 | 非空，1~100 字符 |
| `vision_model` | string / null | 否 | 可为空；空字符串按 `null` 处理；最长 100 字符 |
| `temperature` | number | 是 | 0~2，步长 0.1 |
| `timeout_seconds` | int | 是 | 30~300 |
| `concurrency` | int | 是 | 1~16 |
| `retry_count` | int | 是 | 0~3 |
| `max_context_tokens` | int / null | 否 | 1024~128000；`null` 表示不限制 |
| `provider` | string | 否 | 只读；若传入必须为 `volcengine_ark` |

校验规则：

| 场景 | 业务码 |
| --- | --- |
| 缺少 `base_url` / `text_model` / `image_model` / 必填数值 | `10002` |
| `base_url` 非 http/https、模型名超长、Key 超长、`temperature` 非 0.1 步长 | `10003` |
| `temperature` 不在 0~2、`timeout_seconds` 不在 30~300、`concurrency` 不在 1~16、`retry_count` 不在 0~3、`max_context_tokens` 不在 1024~128000 | `10004` |
| `provider` 传入非 `volcengine_ark` | `10001` |

保存语义：

1. 校验通过后，在事务内读取 `is_active=true` 的配置行并加行锁；不存在则插入。
2. `api_key` 非空时使用 AES-256-GCM 加密后写入 `api_key_ciphertext`；省略/空字符串保持原值。
3. 更新 `updated_by`、`updated_at`；确保只有一行 `is_active=true`。
4. 提交后刷新配置读取；本 demo 每次直查数据库，下一次读取即生效。
5. 写操作日志 `model_config.update`，`detail` 记录 `changed_fields` 与 `api_key_changed`，不记录 Key 明文/密文。
6. 不做连通性测试；保存成功不代表 Key 可用。

响应：同 7.1 的 `data`，`api_key_masked` 为新的脱敏值。

### 7.3 错误

| 场景 | HTTP | 业务码 |
| --- | --- | --- |
| 管理员/普通用户访问 | 403 | `20005` |
| 参数校验失败 | 400 | `10001`~`10004` |
| 加密失败 | 500 | `50001` |
| 数据库写入失败 | 500 | `50002` |

---

## 8. 系统提示词

### 8.1 提示词列表

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `GET /api/v1/admin/prompts` |
| 权限 | `admin.prompts.view` |
| 鉴权 | Bearer JWT |

响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "agent_code": "planner",
        "name": "规划 Agent",
        "current_version": 2,
        "content_preview": "你是规划 Agent，负责判断用户意图……",
        "updated_by": {
          "user_id": 2,
          "username": "demo_admin",
          "display_name": "演示管理员"
        },
        "updated_at": "2026-10-31T11:00:00+08:00"
      }
    ]
  }
}
```

- 固定返回 8 个 Agent，顺序见第 2.6 节；不分页。
- `content_preview`：折叠空白后取前 60 字符，超出加 `…`。
- 种子保证 8 条都存在；若某条缺失，返回 500 `50002` 并记录日志，由种子脚本修复。

### 8.2 提示词详情

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `GET /api/v1/admin/prompts/{agent_code}` |
| 权限 | `admin.prompts.view` |
| 鉴权 | Bearer JWT |

响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "agent_code": "planner",
    "name": "规划 Agent",
    "content": "你是规划 Agent，负责判断用户意图……",
    "current_version": 2,
    "updated_by": {
      "user_id": 2,
      "username": "demo_admin",
      "display_name": "演示管理员"
    },
    "updated_at": "2026-10-31T11:00:00+08:00",
    "suggested_variables": [
      "product_name",
      "params",
      "requirement_summary",
      "chat_summary"
    ],
    "variables_in_content": [
      "product_name",
      "chat_summary"
    ],
    "versions": [
      {
        "version": 2,
        "content": "你是规划 Agent……",
        "created_by": {
          "user_id": 2,
          "username": "demo_admin",
          "display_name": "演示管理员"
        },
        "created_at": "2026-10-31T11:00:00+08:00",
        "is_current": true
      },
      {
        "version": 1,
        "content": "你是规划 Agent……",
        "created_by": {
          "user_id": 1,
          "username": "demo_super",
          "display_name": "演示超管"
        },
        "created_at": "2026-10-31T10:00:00+08:00",
        "is_current": false
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `agent_code` | string | Agent 标识 |
| `name` | string | Agent 中文名 |
| `content` | string | 当前启用提示词全文 |
| `current_version` | int | 当前版本号 |
| `updated_by` | object / null | 最后修改人 |
| `updated_at` | string | 最后修改时间 |
| `suggested_variables` | array | 该 Agent 的建议变量 |
| `variables_in_content` | array | 正文实际引用的变量，按首次出现顺序去重 |
| `versions` | array | 版本历史，按版本号倒序；含全文 |
| `versions[].is_current` | bool | 是否为当前版本 |

- `agent_code` 不在 8 个 Agent 中：返回 404 `30021`。

### 8.3 保存新版本

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `PUT /api/v1/admin/prompts/{agent_code}` |
| 权限 | `admin.prompts.edit` |
| 鉴权 | Bearer JWT |

请求：

```json
{
  "content": "你是规划 Agent……使用 {{product_name}} 与 {{chat_summary}}。"
}
```

- `content` 必填；去除首尾空格后为空返回 400 `10002`；超过 20000 字符返回 400 `10004`。
- 变量识别区分大小写；未知变量原样保留；建议变量未引用只警告，不阻止保存。
- 保存使用行锁；`new_version = current_version + 1`；写入 `prompt_versions` 并更新 `system_prompts`。
- 写操作日志 `prompt.update`，`detail` 记录 `agent_code`、`version`、`unknown_variables`、`missing_suggested_variables`。
- 不提供版本号参数，不做乐观锁；并发保存按后保存者覆盖。

响应：在 8.2 的 `data` 基础上增加 `warnings`：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "agent_code": "planner",
    "name": "规划 Agent",
    "content": "你是规划 Agent……",
    "current_version": 3,
    "updated_by": { "user_id": 2, "username": "demo_admin", "display_name": "演示管理员" },
    "updated_at": "2026-10-31T11:30:00+08:00",
    "suggested_variables": ["product_name", "params", "requirement_summary", "chat_summary"],
    "variables_in_content": ["product_name", "foo"],
    "versions": [],
    "warnings": {
      "unknown_variables": ["foo"],
      "missing_suggested_variables": ["params", "requirement_summary", "chat_summary"]
    }
  }
}
```

- `warnings.unknown_variables`：正文引用但不在全局 9 个变量中的变量。
- `warnings.missing_suggested_variables`：该 Agent 的建议变量中未被正文引用的变量。
- 两个数组无内容时返回空数组，不省略。
- 响应中的 `versions` 按 8.2 规则返回完整历史；示例为节省篇幅置空，实际不省略。

### 8.4 回滚到指定版本

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `POST /api/v1/admin/prompts/{agent_code}/versions/{version}/activate` |
| 权限 | `admin.prompts.edit` |
| 鉴权 | Bearer JWT |

- 请求体为空。
- `agent_code` 不存在返回 404 `30021`；`version` 不属于该 Agent 返回 404 `30022`。
- 回滚不删除、不改写任何历史版本；复制目标版本内容生成 `current_version + 1` 的新版本，并设为当前。
- 目标版本等于当前版本时，仍生成一个内容相同的新版本；本 demo 不做空操作优化。
- 写操作日志 `prompt.rollback`，`detail` 记录 `agent_code`、`source_version`、`new_version`、`unknown_variables`、`missing_suggested_variables`。
- 响应：同 8.3，包含新版本详情与 `warnings`。

### 8.5 错误

| 场景 | HTTP | 业务码 |
| --- | --- | --- |
| Agent 不存在 | 404 | `30021` |
| 提示词版本不存在 | 404 | `30022` |
| 内容为空 | 400 | `10002` |
| 内容超过 20000 字符 | 400 | `10004` |
| 缺少 `admin.prompts.view` / `admin.prompts.edit` | 403 | `20005` |

---

## 9. 前端路由与权限

| 路由 | 页面 | 权限 | 说明 |
| --- | --- | --- | --- |
| `/admin/chat-records` | 聊天记录列表 | `admin.content.view` | 筛选、分页、搜索入口 |
| `/admin/chat-records/:sessionId` | 会话详情 | `admin.content.view` | 支持 `?around_id=` 定位 |
| `/admin/model-config` | 模型配置 | `admin.model.view` | 仅超管；管理员跳 `/403` |
| `/admin/prompts` | 系统提示词 | `admin.prompts.view` | 8 个 Agent 列表、详情、历史、保存、回滚 |
| `/admin/prompts/:agentCode` | 系统提示词详情 | `admin.prompts.view` | 可选；也可在同一页面右侧展示 |

- 菜单可见性由 `GET /auth/me` 返回的权限码决定；后端仍需逐接口校验，不能只靠前端隐藏。
- 403 统一跳 `/403`；本 demo 不区分 `20004` / `20005`，均按 6 号 demo 约定处理。
- 管理后台桌面优先；本 demo 不做手机端适配。

---

## 10. 错误码汇总

| code | HTTP | 含义 | 本 demo 场景 |
| --- | --- | --- | --- |
| 0 | 200 | 成功 | — |
| 10001 | 400 | 参数错误 | `before_id` 与 `around_id` 同时出现；`provider` 非法 |
| 10002 | 400 | 缺少必填参数 | 搜索关键词为空；提示词内容为空；模型必填字段缺失 |
| 10003 | 400 | 参数格式错误 | 枚举值非法；URL 格式非法；`temperature` 非 0.1 步长；游标非正整数 |
| 10004 | 400 | 参数超出范围 | 页码/页大小非法；关键词超长；模型数值越界；提示词超长 |
| 20002 | 401 | 登录已过期 | token 过期 |
| 20003 | 401 | token 无效 | 未携带、签名错误、版本不符 |
| 20004 | 403 | 账号不可用 | 账号禁用/删除 |
| 20005 | 403 | 无权限 | 缺权限码；管理员访问超管会话/调用；管理员传 `full=true`；管理员访问模型配置 |
| 30013 | 404 | 会话不存在 | 会话 ID 不存在 |
| 30020 | 404 | Agent 调用不存在 | `run_id` 不存在 |
| 30021 | 404 | 系统提示词不存在 | `agent_code` 不在 8 个 Agent 中 |
| 30022 | 404 | 提示词版本不存在 | 回滚目标版本不存在 |
| 30023 | 404 | 消息不存在 | `around_id` 不存在或不属于该会话 |
| 50001 | 500 | 系统内部错误 | 加密失败、未预期异常 |
| 50002 | 500 | 数据库错误 | 查询/写入失败；种子缺失导致提示词不完整 |

> `30002`（模型未配置）用于生成/聊天接口，本 demo 的后台配置读取不返回该码；`20006`（无权操作超管账号）本 demo 不使用，管理员访问超管内容统一 `20005`。

---

## 11. 审计动作

| 动作 | 触发 | `target_type` | `target_id` | `detail` 字段 |
| --- | --- | --- | --- | --- |
| `model_config.update` | 模型配置保存成功 | `model_config` | 配置行 ID | `changed_fields`、`api_key_changed` |
| `prompt.update` | 提示词保存新版本 | `system_prompt` | `agent_code` | `agent_code`、`version`、`unknown_variables`、`missing_suggested_variables` |
| `prompt.rollback` | 提示词回滚 | `system_prompt` | `agent_code` | `agent_code`、`source_version`、`new_version`、`unknown_variables`、`missing_suggested_variables` |

- `result` 成功写 `success`；本 demo 的参数校验失败不写审计（避免噪声）。
- 审计不记录 API Key 明文/密文、密码、JWT。
- 操作日志页面由 6 号 demo 提供；本 demo 只负责写入。若 6 号日志页的动作筛选为固定枚举，需补充上述三个动作。
- 登录、账号、角色等动作沿用 6 号 demo 的动作码。

---

## 12. 权限矩阵

| 功能 | 管理员 `admin` | 超管 `super_admin` | 普通用户 `user` |
| --- | --- | --- | --- |
| 聊天记录列表 | ✓（不含超管账号） | ✓ | ✗ |
| 会话详情与消息 | ✓（不含超管账号） | ✓ | ✗ |
| Agent 调用摘要 | ✓（不含超管账号） | ✓ | ✗ |
| Agent 完整输入/输出 | ✗ | ✓ | ✗ |
| 消息搜索 | ✓（可见范围） | ✓ | ✗ |
| 模型配置读取/保存 | ✗ | ✓ | ✗ |
| 系统提示词查看 | ✓ | ✓ | ✗ |
| 系统提示词编辑/回滚 | ✓ | ✓ | ✗ |
| 聊天记录导出/编辑/删除 | ✗ | ✗ | ✗ |

- 权限码：`admin.content.view`（聊天记录）、`admin.model.view` / `admin.model.edit`（模型配置，超管专属）、`admin.prompts.view` / `admin.prompts.edit`（提示词）。
- 管理员对超管内容与模型配置的拒绝均为 403 `20005`；前端不展示对应菜单或按钮。
- 聊天记录只读，任何角色都不能修改或删除。

---

## 13. 待确认项

1. **新增错误码**：`30020`、`30021`、`30022`、`30023` 为 demo 约定，需写入 9 号错误码表。
2. **管理员访问超管内容的错误码**：demo 统一 `20005`；是否改用 `20006`（无权操作超管账号）或 404 隐藏存在性待定。
3. **管理员传 `full=true`**：demo 返回 403 `20005`；是否改为忽略 `full` 只返回摘要待定。
4. **消息与批次关联**：`chat_messages` 无 `batch_id`，demo 通过 `agent_runs` 推导；是否新增消息级批次字段待定。
5. **「查看批次」的最终形态**：demo 用只读摘要抽屉；7 号 PRD 实现后改为跳转生图详情。
6. **消息游标**：`before_id` / `around_id` 与默认/最大 `limit` 为 demo 约定，9 号未定义。
7. **搜索分页与摘要长度**：固定每页 20、摘要约 120 字符；需与 8 号 §6.2 及 9 号统一。
8. **模型配置密钥**：`MODEL_CONFIG_ENCRYPTION_KEY` 的命名、编码格式、轮换流程需与 11 号部署文档统一；与 4 号 demo 的 `DOUBAO_API_KEY` 优先级待定。
9. **提示词并发与回滚当前版本**：行锁 + last-write-wins；回滚当前版本仍生成新版本；是否改为冲突检测/空操作待定。
10. **提示词「查看其他超管内容」**：提示词为全局配置，8 号 §8.6 该行在本 demo 不适用，需确认正式口径。
11. **已删除用户的会话**：demo 仍展示；是否在列表标记「已删除用户」待定。
12. **审计动作码**：`model_config.update` / `prompt.update` / `prompt.rollback` 需与 9/10 号统一；6 号日志页动作筛选需同步。
13. **种子表与真实表**：demo 建表脚本按 10 号最小字段集；若 2/3/4 号 demo 已建表则复用，字段差异需在正式实现前对齐。
14. **Token 口径**：`token_usage` 汇总全部 `agent_runs`，包含 `failed` 但有 Token 的调用；`skipped` 通常为 0，仍需确认是否参与合计。
