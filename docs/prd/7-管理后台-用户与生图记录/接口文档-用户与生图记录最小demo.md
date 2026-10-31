# 用户与生图记录最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `7-管理后台-用户与生图记录prd.md` §3~§7、§9、§10；`../9-后端服务与接口/9-后端服务与接口prd.md` §2/§3/§6.1/§6.3；`../10-数据模型与存储/10-数据模型与存储prd.md` §4.1/§4.6/§4.8~§4.10/§4.17 |
| 覆盖范围 | 概览四卡、Token 统计、内容追溯用户/会话/批次/图片、单图详情与媒体访问、用户详情真实统计与内容入口 |
| 文档状态 | 最小 demo 约定；正式实现需与 4/6/8/9/10 号文档统一 |

> 本文档只描述最小 demo 需要落地的接口。数据导出、聊天记录、Agent 调用明细、模型配置、系统提示词、素材模板、操作日志等接口不在本次范围内，见第 17 章。本 demo 的「做 / 不做」与最小化取舍见同目录 `README.md`。

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
| 日期筛选格式 | `YYYY-MM-DD`，按 Asia/Shanghai 解释为自然日 |
| 空值 | `null`，不省略字段 |
| 布尔值 | `true` / `false` |

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

文件流接口成功时直接返回二进制；失败时仍返回上述 JSON 结构。

### 1.3 HTTP 状态码与业务码

| HTTP | 场景 | 业务码段 |
| --- | --- | --- |
| 200 | 成功 | `0` |
| 400 | 参数错误、格式错误、超出范围 | `1xxx` |
| 401 | 未登录、登录过期、token 无效或版本不符 | `2xxx` |
| 403 | 无权限、账号禁用/删除、无权查看超管内容 | `2xxx` |
| 404 | 用户、会话、批次、图片不存在；文件/归档不可用 | `3xxx` |
| 409 | 状态不允许 | `3xxx` |
| 500 | 服务端异常、存储异常 | `5xxx` |

### 1.4 鉴权与权限判定

```http
Authorization: Bearer <jwt>
```

除登录接口外，所有接口必须携带 token。每次请求按以下顺序校验：

1. 解析并校验 JWT 签名与过期时间：未携带或签名错误返回 401 `20003`，过期返回 401 `20002`。
2. 按 `sub` 读取用户；账号不存在、`status=disabled` 或 `status=deleted` 返回 403 `20004`。
3. 校验 token 中的 `token_version` 与该用户当前 `token_version` 一致；不一致返回 401 `20003`。
4. 读取用户角色与权限：
   - 角色包含 `super_admin`：拥有全部权限码，不读取 `role_permissions`。
   - 其他角色：取所分配角色在 `role_permissions` 中的权限码并集。
5. 校验接口所需权限码；缺失返回 403 `20005`。

> 最小 demo 不接 Redis，每次请求直查 PostgreSQL，权限变更在下一次请求立即生效。权限模型与 6 号 demo 完全一致，本 demo 不新增权限点。

### 1.5 分页

请求：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 1 | 从 1 开始；小于 1 按 1 处理 |
| `page_size` | int | 20 | 最大 100；小于 1 或大于 100 返回 400 `10004` |

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

- Token 统计明细按 PRD §4.3 固定每页 20 条，不提供 `page_size` 参数。
- 内容追溯的用户、会话、批次、图片列表默认 20 条，允许 `page_size` 最大 100；前端默认使用 20。
- 页码超出范围时返回空 `items`，`total` 不变。

### 1.6 时间与时区

- 所有「当天」「最近 7 天」「日期分组」按 **Asia/Shanghai** 计算。
- `start_date` / `end_date` 为 `YYYY-MM-DD`，包含起止当天：实际查询区间为 `[start_date 00:00:00+08:00, end_date + 1 天 00:00:00+08:00)`。
- `start_date` 晚于 `end_date` 返回 400 `10003`。
- 响应中的时间字段统一输出 ISO 8601，带 `+08:00` 偏移。
- 数据库使用 `TIMESTAMPTZ`，聚合前转换为 Asia/Shanghai。

### 1.7 媒体访问

- 缩略图、大图预览、原图下载均需 `Authorization: Bearer <jwt>`。
- 前端不能把 token 拼进 `<img src>` 或 URL 查询参数；应使用 `fetch` 携带 Authorization 获取 Blob，再通过 `URL.createObjectURL` 展示。
- 成功时返回二进制，设置 `Content-Type`；失败时返回统一 JSON 错误结构。
- 缩略图响应设置 `Cache-Control: private, max-age=300`；大图与下载设置 `Cache-Control: private, no-store`。
- 本 demo 不提供预签名 URL；正式实现按 9 号 §8.3 改为预签名缩略图，并保持权限校验。

---

## 2. 最小 demo 约定

### 2.1 运行形态

| 项目 | demo 处理 | 正式实现 |
| --- | --- | --- |
| 概览缓存 | 进程内 TTL 缓存 60 秒，单实例 | Redis 缓存 60 秒（7 号 §3.1、9 号 §2.7） |
| 权限缓存 | 每次请求直查 PostgreSQL | Redis 缓存 ≤30 秒、变更主动失效 |
| 媒体访问 | 管理端鉴权接口 + 本地存储适配层 | MinIO 预签名缩略图 + 后端鉴权原件流 |
| 归档 | 种子写 `archived_at` 与 `archive/` 文件 | 每日归档任务与 5 年扫描（10 号 §7.2） |
| 数据导出 | 不做 | 异步任务、ZIP + CSV、24 小时下载（7 号 §8） |
| 数据库迁移 | 建表脚本 + 幂等种子脚本 | Alembic（10 号 §10） |

### 2.2 权限点与演示账号

本 demo 复用 6 号 demo 的 23 个权限点，不新增权限码。相关的权限点：

| 权限码 | 用途 |
| --- | --- |
| `admin.dashboard.view` | 概览四卡 |
| `admin.tokens.view` | Token 统计 |
| `admin.content.view` | 内容追溯、单图详情、媒体访问 |
| `admin.accounts.view` | 用户列表/详情（6 号 demo，本 demo 只改统计值） |

演示账号：

| 用户名 | 密码 | 角色 | 用途 |
| --- | --- | --- | --- |
| `demo_super` | `Demo1234` | `super_admin` | 可看全部内容 |
| `demo_admin` | `Demo1234` | `admin` | 看不到超管内容 |
| `demo_user` | `Demo1234` | `user` | 内容所有者；访问管理接口应 403 |
| `demo_user2` | `Demo1234` | `user` | 本 demo 新增，第二个内容所有者 |
| `demo_dual` | `Demo1234` | `user` + `admin` | 双角色切换 |

### 2.3 演示数据种子

种子脚本必须幂等：重复执行不重复创建、不重置已有密码与已修改权限。

| 对象 | 种子内容 |
| --- | --- |
| 用户 | 创建 `demo_user2`（普通用户）；`demo_user`、`demo_super`、`demo_admin` 复用 |
| 会话 | `demo_user` 2 个（1 个 `active`，1 个 `hidden`）；`demo_user2` 1 个；`demo_super` 1 个 |
| 批次 | `demo_user`：`sample_ready`、`completed`、`partially_failed`、`failed`、`cancelled`、归档 `completed`；`demo_user2`：`partially_failed`；`demo_super`：`completed` |
| 图片 | 覆盖 `main`/`detail`、`success`/`failed`/`cancelled`/`superseded`、`image_type=sample/final`；含 1 张 `archived_at` 非空的成功正式图 |
| Agent 调用 | 覆盖 8 个 Agent；跨 7 个自然日；2 个模型名；含 `success`、`failed`（有 Token 与 0 Token 各一条）、`skipped`（0 Token） |
| 文件 | 在 `STORAGE_DIR` 生成占位 PNG、`thumbnails/` 缩略图；归档图同时写入 `archive/`；不调用豆包 |

- 种子不修改 4 号 demo 真实生成的数据；两类数据可并存。
- 种子使用唯一键（用户名、`client_request_id`、固定业务标识）做幂等，不依赖固定自增 ID。
- 种子不写入导出任务、导出文件或 `export.*` 审计日志。

### 2.4 概览统计口径

| 卡片 | 字段 | 口径 |
| --- | --- | --- |
| 用户总数 | `user_total` | `users.status != 'deleted'` 的账号数 |
| 今日生成图片数 | `today_image_count` | 当天创建、`generated_images.image_type='final'`、`status='success'` 的图片数 |
| 累计图片数 | `total_image_count` | 全部 `image_type='final'`、`status='success'` 的图片数，含被重生成替代的旧图 |
| 今日 Token | `today_token_total` | 当天 `agent_runs` 的 `prompt_tokens + completion_tokens` 总和；`skipped` 的 0 Token 不影响结果 |

- 当天按 Asia/Shanghai 计算。
- 四张卡片分别聚合；允许在同一个数据库事务/会话内一次查询完成，但结果必须与独立查询一致。
- 缓存 60 秒，TTL 可由 `DASHBOARD_CACHE_TTL_SECONDS` 覆盖；缓存键包含当天日期，跨天自动失效。
- 缓存为进程内实现，提供测试可调用的清缓存函数；不提供 HTTP 清缓存接口。

### 2.5 Token 统计口径

- 计入：`agent_runs.status='success'` 的全部记录；`status='failed'` 且 `prompt_tokens + completion_tokens > 0` 的记录。
- 不计入：`status='skipped'`；`status='failed'` 且 Token 为 0 的记录。
- 调用次数 = 计入的 `agent_runs` 记录数。
- 用户归属：优先 `agent_runs.session_id` 对应 `creative_sessions.user_id`；否则 `agent_runs.batch_id` 对应 `generation_batches.user_id`；两者都为空的记录不计入按用户明细。
- 明细按「日期 + 用户 + Agent + 模型」聚合；汇总覆盖全部筛选结果。
- 日期按 `created_at` 转换为 Asia/Shanghai 后的自然日。
- 模型筛选为 `agent_runs.model_name` 精确匹配。

### 2.6 内容追溯口径

- 用户列表只包含至少存在 1 个 `generation_batches` 记录的用户；`last_generated_at = max(generation_batches.created_at)`。
- 用户列表包含 `active`、`disabled`、`deleted` 用户并返回状态；管理员过滤拥有 `super_admin` 角色的用户。
- 会话列表包含 `active` 与 `hidden`；`batch_count` 为该会话批次数；`latest_batch_at = max(batch.created_at)`。
- 批次图片构成按计划口径：`sample` = 1 主图 + 0 详情图；`full` = 1 主图 + (`total_count - 1`) 详情图。
- 图片列表默认每个 `index_no` 只返回最新一次尝试；`include_superseded=true` 返回全部尝试；`status=superseded` 时自动包含旧图。
- 归档图片：`archived_at` 非空时，缩略图仍从 `thumbnail_path`（热存储）读取；大图与下载从 `archive/{file_path}` 读取。

### 2.7 用户详情统计口径

| 字段 | 口径 |
| --- | --- |
| `image_count` | 该用户 `generated_images.image_type='final'` 且 `status='success'` 的图片数（含被替代的旧成功图） |
| `session_count` | 该用户全部会话数（`active` + `hidden`） |
| `token_total` | 该用户 `agent_runs` 输入 + 输出 Token 之和，归属规则同 §2.5 |
| `failed_task_count` | 该用户 `generation_batches.status IN ('failed','partially_failed')` 的批次数 |
| `stats_available` | 本 demo 固定为 `true` |

> 6 号 demo 的接口字段结构不变，只把占位 `0` / `false` 替换为真实值。用户列表与详情共用同一 `stats` 结构。

### 2.8 字典

**用户状态**

| 值 | 含义 |
| --- | --- |
| `active` | 启用 |
| `disabled` | 禁用 |
| `deleted` | 已删除 |

**批次类型**

| 值 | 含义 |
| --- | --- |
| `sample` | 示例批次 |
| `full` | 全套批次 |

**批次状态**

| 值 | 含义 |
| --- | --- |
| `queued` | 排队中 |
| `running` | 生成中 |
| `sample_ready` | 示例待确认 |
| `confirmed` | 已确认 |
| `completed` | 已完成 |
| `partially_failed` | 部分失败 |
| `failed` | 失败 |
| `cancelled` | 已取消 |

**图片类型 / 角色 / 状态**

| 字段 | 值 | 含义 |
| --- | --- | --- |
| `image_type` | `sample` / `final` | 示例图 / 正式图 |
| `image_role` | `main` / `detail` | 主图 / 详情图 |
| `status` | `pending` | 待生成 |
| `status` | `generating` | 生成中 |
| `status` | `success` | 成功 |
| `status` | `failed` | 失败 |
| `status` | `cancelled` | 已取消 |
| `status` | `superseded` | 已被替代 |

**Agent 字典**

| `agent_code` | `agent_name` |
| --- | --- |
| `planner` | 规划 |
| `product_understanding` | 商品理解 |
| `copywriter` | 文案 |
| `prompt_builder` | 提示词 |
| `image_generator` | 生图执行 |
| `quality_reviewer` | 质量审核 |
| `repairer` | 修复 |
| `platform_rule` | 平台规范 |

---

## 3. 接口清单

| 方法 | 路径 | 权限 | 用途 | 所在 Ticket |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/dashboard/summary` | `admin.dashboard.view` | 概览四张统计卡片 | 01 |
| GET | `/api/v1/admin/tokens/stats` | `admin.tokens.view` | Token 统计汇总与明细 | 02 |
| GET | `/api/v1/admin/content/users` | `admin.content.view` | 有生成记录的用户列表 | 03 |
| GET | `/api/v1/admin/content/users/{user_id}/sessions` | `admin.content.view` | 用户会话列表 | 03 |
| GET | `/api/v1/admin/content/sessions/{session_id}/batches` | `admin.content.view` | 会话批次列表 | 04 |
| GET | `/api/v1/admin/content/batches/{batch_id}/images` | `admin.content.view` | 批次图片列表 | 04 |
| GET | `/api/v1/admin/content/images/{image_id}` | `admin.content.view` | 单图详情 | 05 |
| GET | `/api/v1/admin/content/images/{image_id}/thumbnail` | `admin.content.view` | 缩略图 | 04 / 05 |
| GET | `/api/v1/admin/content/images/{image_id}/content` | `admin.content.view` | 大图预览 | 05 |
| GET | `/api/v1/admin/content/images/{image_id}/download` | `admin.content.view` | 下载原图 | 05 |
| GET | `/api/v1/admin/users` | `admin.accounts.view` | 用户列表；统计改为真实值（复用 6 号） | 06 |
| GET | `/api/v1/admin/users/{id}` | `admin.accounts.view` | 用户详情；统计改为真实值（复用 6 号） | 06 |

---

## 4. 概览

### 4.1 查询概览四卡

```http
GET /api/v1/admin/dashboard/summary
Authorization: Bearer <jwt>
```

#### 请求参数

无。

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "user_total": 128,
    "today_image_count": 12,
    "total_image_count": 3400,
    "today_token_total": 456789
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_total` | int | 未删除账号数 |
| `today_image_count` | int | 当天成功正式图数 |
| `total_image_count` | int | 累计成功正式图数（含被替代旧图） |
| `today_token_total` | int | 当天输入 + 输出 Token 总和 |

#### 计算规则

1. `user_total`：`SELECT count(*) FROM users WHERE status <> 'deleted'`。
2. `today_image_count`：`generated_images` 中 `image_type='final'`、`status='success'`、`created_at` 落在当天 Asia/Shanghai 区间的数量。
3. `total_image_count`：`generated_images` 中 `image_type='final'`、`status='success'` 的全部数量，不排除 `superseded`。
4. `today_token_total`：`agent_runs` 中 `created_at` 落在当天区间的 `prompt_tokens + completion_tokens` 总和；`skipped` 记录的 0 Token 不影响结果。
5. 四张卡片在同一请求内返回；任一聚合失败按整体失败处理，返回 500，不返回部分卡片。

#### 缓存

- 缓存 60 秒；`DASHBOARD_CACHE_TTL_SECONDS` 可覆盖。
- 缓存键为 `dashboard_summary:{YYYY-MM-DD}`；跨天自然失效。
- 60 秒内重复请求返回同一快照；过期后重新聚合。
- 测试可调用服务层清缓存函数；不提供 HTTP 清缓存接口。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 未登录/token 无效 | 401 | 20002 / 20003 | 登录已过期 / token 无效 |
| 账号禁用/删除 | 403 | 20004 | 账号不可用 |
| 无 `admin.dashboard.view` | 403 | 20005 | 无权限 |
| 数据库/系统异常 | 500 | 50001 / 50002 | 系统内部错误 / 数据库错误 |

#### 前端行为

- 四张卡片横向排列，数字超过 10000 使用千分位；无数据显示 `0`。
- 加载失败显示「加载失败，点击重试」，点击重新请求。
- 「今日生成图片数」「累计图片数」均可点击，跳转 `/admin/content?start_date={今天}&end_date={今天}`；日期按 Asia/Shanghai 生成。
- 快捷入口：「用户管理」→ `/admin/accounts`；「生图记录」→ `/admin/content`；「Token 统计」→ 当前页切换到 Token Tab。

---

## 5. Token 统计

### 5.1 查询 Token 统计

```http
GET /api/v1/admin/tokens/stats?start_date=2026-10-25&end_date=2026-10-31&user=demo&agent_codes=planner,copywriter&model=doubao-seed-1.6&page=1
Authorization: Bearer <jwt>
```

#### 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `start_date` | string | 否 | 今天 - 6 天 | `YYYY-MM-DD`，含当天 |
| `end_date` | string | 否 | 今天 | `YYYY-MM-DD`，含当天 |
| `user` | string | 否 | — | 用户名/显示名关键词，≤50 字符，模糊匹配；空字符串视为不筛选 |
| `agent_codes` | string | 否 | — | 逗号分隔的 Agent code，可多选；未知 code 返回 400 `10003` |
| `model` | string | 否 | — | 模型名精确匹配；空字符串视为不筛选 |
| `page` | int | 否 | 1 | 页码；小于 1 按 1 处理 |

- 不提供 `page_size`；明细固定每页 20 条。
- 默认时间范围为最近 7 天（含今天），按 Asia/Shanghai。
- `start_date` 晚于 `end_date` 返回 400 `10003`。

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "summary": {
      "prompt_tokens": 12000,
      "completion_tokens": 18000,
      "total_tokens": 30000,
      "call_count": 240
    },
    "items": [
      {
        "date": "2026-10-31",
        "user_id": 2,
        "username": "demo_user",
        "display_name": "演示用户",
        "agent_code": "copywriter",
        "agent_name": "文案",
        "model_name": "doubao-seed-1.6",
        "call_count": 5,
        "prompt_tokens": 100,
        "completion_tokens": 200,
        "total_tokens": 300
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
| `summary.prompt_tokens` | int | 筛选范围内输入 Token 合计 |
| `summary.completion_tokens` | int | 筛选范围内输出 Token 合计 |
| `summary.total_tokens` | int | 输入 + 输出 |
| `summary.call_count` | int | 计入的 `agent_runs` 记录数 |
| `items[].date` | string | `YYYY-MM-DD`，Asia/Shanghai 自然日 |
| `items[].user_id` | int | 用户 ID |
| `items[].username` | string | 用户名 |
| `items[].display_name` | string | 显示名 |
| `items[].agent_code` | string | Agent code |
| `items[].agent_name` | string | Agent 中文名 |
| `items[].model_name` | string / null | 模型名 |
| `items[].call_count` | int | 该组合的调用次数 |
| `items[].prompt_tokens` | int | 该组合输入 Token |
| `items[].completion_tokens` | int | 该组合输出 Token |
| `items[].total_tokens` | int | 该组合输入 + 输出 |
| `total` | int | 聚合组数，不是记录数 |
| `page` / `page_size` | int | 分页信息；`page_size` 固定 20 |

#### 聚合与排序规则

1. 计入规则见 §2.5。
2. 用户归属：`session.user_id` 优先，其次 `batch.user_id`；两者都为空的记录不计入按用户明细。
3. 分组键：`(date, user_id, agent_code, model_name)`；`model_name` 为 `null` 时归入 `null` 组。
4. 汇总在全部筛选结果上计算，不受分页影响；`summary` 与 `items` 合计一致。
5. 排序：`date DESC, total_tokens DESC, user_id ASC, agent_code ASC, model_name ASC`。
6. 分页：`page` 从 1 开始；每页 20 条。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 日期格式错误 / 起止倒置 | 400 | 10003 | 参数格式错误 |
| Agent code 未知 | 400 | 10003 | Agent 参数不合法 |
| 页码非法 | 400 | 10004 | 参数超出范围 |
| 无 `admin.tokens.view` | 403 | 20005 | 无权限 |
| 数据库异常 | 500 | 50002 | 数据库错误 |

#### 前端行为

- Tab 切换后默认最近 7 天；筛选条件可组合，重置恢复默认。
- 汇总区展示四个数字；明细表格按列展示，日期倒序、合计 Token 倒序。
- 无数据时显示「暂无 Token 数据」；加载失败显示「加载失败，点击重试」。
- 不提供图表、导出、金额换算。

---

## 6. 内容追溯：用户列表

### 6.1 查询有生成记录的用户

```http
GET /api/v1/admin/content/users?keyword=demo&page=1&page_size=20
Authorization: Bearer <jwt>
```

#### 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `keyword` | string | 否 | — | 用户名/显示名关键词，≤50 字符，模糊匹配；空字符串视为不筛选 |
| `page` | int | 否 | 1 | 页码 |
| `page_size` | int | 否 | 20 | 每页条数，最大 100 |

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "user_id": 2,
        "username": "demo_user",
        "display_name": "演示用户",
        "status": "active",
        "last_generated_at": "2026-10-31T10:00:00+08:00",
        "batch_count": 6
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
| `user_id` | int | 用户 ID |
| `username` | string | 用户名 |
| `display_name` | string | 显示名 |
| `status` | string | `active` / `disabled` / `deleted` |
| `last_generated_at` | string | 该用户最近一个批次的创建时间 |
| `batch_count` | int | 该用户批次数 |

#### 规则

1. 只返回至少存在 1 个 `generation_batches` 记录的用户。
2. `last_generated_at` 取该用户所有批次 `created_at` 的最大值。
3. 排序：`last_generated_at DESC, user_id DESC`。
4. 包含 `active`、`disabled`、`deleted` 用户，并返回状态；管理员（`admin`）过滤拥有 `super_admin` 角色的用户，超管（`super_admin`）不过滤。
5. 关键词同时匹配 `username` 与 `display_name`，使用 `ILIKE` 模糊匹配。
6. 每页默认 20，最大 100。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 关键词超长 / 参数格式错误 | 400 | 10003 | 参数格式错误 |
| 分页参数越界 | 400 | 10004 | 参数超出范围 |
| 无 `admin.content.view` | 403 | 20005 | 无权限 |
| 数据库异常 | 500 | 50002 | 数据库错误 |

---

## 7. 内容追溯：会话列表

### 7.1 查询用户会话

```http
GET /api/v1/admin/content/users/2/sessions?page=1&page_size=20
Authorization: Bearer <jwt>
```

#### 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `user_id` | int | 是 | — | 路径参数，用户 ID |
| `page` | int | 否 | 1 | 页码 |
| `page_size` | int | 否 | 20 | 每页条数，最大 100 |

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "session_id": 12,
        "title": "秋季通勤衬衫",
        "status": "active",
        "last_message_at": "2026-10-31T10:00:00+08:00",
        "batch_count": 2,
        "latest_batch_at": "2026-10-31T10:00:00+08:00",
        "created_at": "2026-10-29T09:00:00+08:00"
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
| `session_id` | int | 会话 ID |
| `title` | string | 会话标题 |
| `status` | string | `active` / `hidden` |
| `last_message_at` | string / null | 最后消息时间 |
| `batch_count` | int | 会话批次数 |
| `latest_batch_at` | string / null | 最近批次创建时间；无批次为 `null` |
| `created_at` | string | 会话创建时间 |

#### 规则

1. 返回该用户的全部会话，包含 `active` 与 `hidden`。
2. `batch_count` 为该会话的批次数；`latest_batch_at` 为 `max(generation_batches.created_at)`。
3. 排序：`COALESCE(last_message_at, created_at) DESC, session_id DESC`；前端默认展开第一个会话。
4. 用户不存在返回 404 `30017`。
5. 目标用户拥有 `super_admin` 角色且当前登录用户为 `admin` 时，返回 403 `20006`；`super_admin` 可查看。
6. 无会话返回空 `items`。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 用户不存在 | 404 | 30017 | 用户不存在 |
| 管理员查看超管用户会话 | 403 | 20006 | 无权查看超管账号内容 |
| 无 `admin.content.view` | 403 | 20005 | 无权限 |
| 分页参数越界 | 400 | 10004 | 参数超出范围 |

---

## 8. 内容追溯：批次列表

### 8.1 查询会话批次

```http
GET /api/v1/admin/content/sessions/12/batches?product_name=衬衫&batch_type=full&status=completed&start_date=2026-10-01&end_date=2026-10-31&page=1&page_size=20
Authorization: Bearer <jwt>
```

#### 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | int | 是 | — | 路径参数，会话 ID |
| `product_name` | string | 否 | — | 批次快照商品名称模糊匹配，≤60 字符 |
| `batch_type` | string | 否 | `all` | `sample` / `full` / `all` |
| `status` | string | 否 | `all` | 8 种批次状态或 `all` |
| `start_date` | string | 否 | — | 批次创建时间起，`YYYY-MM-DD`，含当天 |
| `end_date` | string | 否 | — | 批次创建时间止，`YYYY-MM-DD`，含当天 |
| `page` | int | 否 | 1 | 页码 |
| `page_size` | int | 否 | 20 | 每页条数，最大 100 |

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "batch_id": 13,
        "batch_type": "full",
        "status": "completed",
        "product_name": "秋季通勤衬衫",
        "style_text": "简洁白底",
        "width": 1000,
        "height": 1000,
        "template_name": "简约白底",
        "total_count": 6,
        "completed_count": 6,
        "composition": {
          "main": 1,
          "detail": 5
        },
        "created_at": "2026-10-29T10:00:00+08:00",
        "finished_at": "2026-10-29T10:05:00+08:00"
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
| `batch_id` | int | 批次 ID |
| `batch_type` | string | `sample` / `full` |
| `status` | string | 批次状态 |
| `product_name` | string | 商品名称快照 |
| `style_text` | string / null | 风格文本快照 |
| `width` / `height` | int | 尺寸 |
| `template_name` | string / null | 模板名称快照 |
| `total_count` | int | 计划张数 |
| `completed_count` | int | 已完成张数 |
| `composition.main` | int | 计划主图数 |
| `composition.detail` | int | 计划详情图数 |
| `created_at` | string | 创建时间 |
| `finished_at` | string / null | 结束时间 |

#### 规则

1. `composition` 按计划口径：`sample` 为 `{main: 1, detail: 0}`；`full` 为 `{main: 1, detail: total_count - 1}`。
2. 筛选条件可组合；`product_name` 只用批次快照，不关联商品表。
3. 时间筛选按 `generation_batches.created_at`，Asia/Shanghai 自然日，含边界。
4. 排序：`created_at DESC, batch_id DESC`。
5. 会话不存在返回 404 `30013`；会话所属用户为超管且当前为管理员返回 403 `20006`。
6. 无结果显示空 `items`；前端展示「没有符合条件的记录」。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 会话不存在 | 404 | 30013 | 会话不存在 |
| 管理员查看超管会话 | 403 | 20006 | 无权查看超管账号内容 |
| 批次类型/状态非法 | 400 | 10003 | 参数格式错误 |
| 日期格式错误 / 起止倒置 | 400 | 10003 | 参数格式错误 |
| 无 `admin.content.view` | 403 | 20005 | 无权限 |

---

## 9. 内容追溯：图片列表

### 9.1 查询批次图片

```http
GET /api/v1/admin/content/batches/13/images?image_role=detail&status=success&include_superseded=false&page=1&page_size=20
Authorization: Bearer <jwt>
```

#### 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `batch_id` | int | 是 | — | 路径参数，批次 ID |
| `image_role` | string | 否 | `all` | `main` / `detail` / `all` |
| `status` | string | 否 | `all` | `pending` / `generating` / `success` / `failed` / `cancelled` / `superseded` / `all` |
| `include_superseded` | bool | 否 | `false` | 是否返回全部尝试；`status=superseded` 时自动按 `true` 处理 |
| `page` | int | 否 | 1 | 页码 |
| `page_size` | int | 否 | 20 | 每页条数，最大 100 |

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "image_id": 88,
        "index_no": 2,
        "attempt_no": 1,
        "image_role": "detail",
        "status": "success",
        "width": 1000,
        "height": 1000,
        "thumbnail_url": "/api/v1/admin/content/images/88/thumbnail",
        "archived_at": null,
        "is_history_visible": true,
        "created_at": "2026-10-29T10:02:00+08:00"
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
| `image_id` | int | 图片 ID |
| `index_no` | int | 组内序号 |
| `attempt_no` | int | 第几次尝试 |
| `image_role` | string | `main` / `detail` |
| `status` | string | 图片状态 |
| `width` / `height` | int / null | 宽高 |
| `thumbnail_url` | string / null | 缩略图接口相对路径；无缩略图为 `null` |
| `archived_at` | string / null | 归档时间 |
| `is_history_visible` | bool | 是否历史可见 |
| `created_at` | string | 创建时间 |

#### 规则

1. 批次不存在返回 404 `30004`；批次所属用户为超管且当前为管理员返回 403 `20006`。
2. `include_superseded=false` 且 `status=all`：每个 `index_no` 只返回 `attempt_no` 最大（同值取 `id` 最大）的记录。
3. `include_superseded=true`：返回全部尝试。
4. `status` 为具体值（非 `all`）时，返回所有匹配该状态的记录；若状态为 `superseded`，自动包含旧图。
5. 排序：`index_no ASC, attempt_no DESC, image_id DESC`。
6. 缩略图路径只返回相对接口路径，不返回存储路径或预签名 URL；前端带 token 取 Blob。
7. 无图片返回空 `items`；缩略图缺失时前端显示占位。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 批次不存在 | 404 | 30004 | 批次不存在 |
| 管理员查看超管批次 | 403 | 20006 | 无权查看超管账号内容 |
| 图片角色/状态非法 | 400 | 10003 | 参数格式错误 |
| 分页参数越界 | 400 | 10004 | 参数超出范围 |
| 无 `admin.content.view` | 403 | 20005 | 无权限 |

---

## 10. 单图详情

### 10.1 查询单图详情

```http
GET /api/v1/admin/content/images/88
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "image_id": 88,
    "batch_id": 13,
    "batch_type": "full",
    "batch_status": "completed",
    "session_id": 12,
    "session_title": "秋季通勤衬衫",
    "user_id": 2,
    "username": "demo_user",
    "display_name": "演示用户",
    "index_no": 2,
    "attempt_no": 1,
    "image_type": "final",
    "image_role": "detail",
    "status": "success",
    "product_name": "秋季通勤衬衫",
    "style_text": "简洁白底",
    "width": 1000,
    "height": 1000,
    "template_name": "简约白底",
    "prompt": "白底商品详情图，展示面料细节……",
    "negative_prompt": null,
    "model_name": "doubao-seedream-4.0",
    "latency_ms": 12000,
    "prompt_tokens": 100,
    "completion_tokens": 0,
    "error_message": null,
    "created_at": "2026-10-29T10:02:00+08:00",
    "file_path": "generated/2/12/13/2_88.png",
    "is_history_visible": true,
    "archived_at": null,
    "thumbnail_url": "/api/v1/admin/content/images/88/thumbnail",
    "preview_url": "/api/v1/admin/content/images/88/content",
    "download_url": "/api/v1/admin/content/images/88/download"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `image_id` | int | 图片 ID |
| `batch_id` | int | 批次 ID |
| `batch_type` | string | `sample` / `full` |
| `batch_status` | string | 批次状态 |
| `session_id` | int | 会话 ID |
| `session_title` | string | 会话标题 |
| `user_id` | int | 用户 ID |
| `username` | string | 用户名 |
| `display_name` | string | 显示名 |
| `index_no` | int | 组内序号 |
| `attempt_no` | int | 第几次尝试 |
| `image_type` | string | `sample` / `final` |
| `image_role` | string | `main` / `detail` |
| `status` | string | 图片状态 |
| `product_name` | string | 批次商品名称快照 |
| `style_text` | string / null | 批次风格快照 |
| `width` / `height` | int / null | 尺寸 |
| `template_name` | string / null | 批次模板快照 |
| `prompt` | string / null | 最终提示词 |
| `negative_prompt` | string / null | 负面提示词 |
| `model_name` | string / null | 模型名 |
| `latency_ms` | int / null | 耗时（毫秒） |
| `prompt_tokens` | int | 输入 Token |
| `completion_tokens` | int | 输出 Token |
| `error_message` | string / null | 失败原因 |
| `created_at` | string | 创建时间 |
| `file_path` | string / null | 存储对象路径 |
| `is_history_visible` | bool | 是否历史可见 |
| `archived_at` | string / null | 归档时间 |
| `thumbnail_url` | string / null | 缩略图接口；无缩略图为 `null` |
| `preview_url` | string / null | 大图预览接口；无文件为 `null` |
| `download_url` | string / null | 下载接口；无文件为 `null` |

#### 规则

1. 图片不存在返回 404 `30024`。
2. 图片所属用户为超管且当前为管理员返回 403 `20006`。
3. `file_path` 为存储对象路径（MinIO 路径），用于后台追溯展示；不返回存储密钥。
4. `archived_at` 非空表示原件在 `archive/` 前缀；缩略图仍在热存储。
5. `prompt`、`negative_prompt`、`error_message` 按原值返回，不做截断；前端负责折叠展示。
6. `thumbnail_url` / `preview_url` / `download_url` 为相对路径，前端需带 token 取 Blob。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 图片不存在 | 404 | 30024 | 图片不存在 |
| 管理员查看超管图片 | 403 | 20006 | 无权查看超管账号内容 |
| 无 `admin.content.view` | 403 | 20005 | 无权限 |
| 数据库异常 | 500 | 50002 | 数据库错误 |

#### 前端行为

- 点击图片网格项打开右侧抽屉；抽屉内展示大图、字段表与操作按钮。
- 大图支持缩放；加载失败显示占位与重试。
- 「下载原图」触发下载；「跳转会话」→ `/admin/chat?session_id={session_id}`；「跳转用户详情」→ `/admin/accounts/{user_id}`。
- 不提供删除、重新生成、修改提示词、修改状态入口。

---

## 11. 媒体访问

### 11.1 获取缩略图

```http
GET /api/v1/admin/content/images/{image_id}/thumbnail
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，`Content-Type` 为图片 MIME（如 `image/png`），响应体为二进制。

| 响应头 | 值 |
| --- | --- |
| `Content-Type` | `image/png` / `image/jpeg` / `image/webp` |
| `Cache-Control` | `private, max-age=300` |

#### 规则

- 读取 `generated_images.thumbnail_path`；缩略图始终从热存储读取，不因 `archived_at` 非空切换路径。
- 缩略图不存在、文件缺失或存储异常返回 404 `30014`。
- 图片记录不存在返回 404 `30024`；超管内容且当前为管理员返回 403 `20006`；无权限返回 403 `20005`。

### 11.2 获取大图预览

```http
GET /api/v1/admin/content/images/{image_id}/content
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，`Content-Type` 为图片 MIME，响应体为二进制。

| 响应头 | 值 |
| --- | --- |
| `Content-Type` | `image/png` / `image/jpeg` / `image/webp` |
| `Content-Disposition` | `inline; filename*=UTF-8''<encoded>` |
| `Cache-Control` | `private, no-store` |

#### 规则

- `archived_at` 为空：读取 `file_path`；`archived_at` 非空：读取 `archive/{file_path}`。
- 归档读取超过 `ARCHIVE_READ_TIMEOUT_SECONDS`（默认 60 秒）、文件缺失或存储异常返回 404 `30014`，`message` 为「文件归档中，请稍后重试」。
- 图片记录不存在返回 404 `30024`；`file_path` 为空返回 404 `30014`。
- 超管内容且当前为管理员返回 403 `20006`；无权限返回 403 `20005`。

### 11.3 下载原图

```http
GET /api/v1/admin/content/images/{image_id}/download
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，响应体为二进制。

| 响应头 | 值 |
| --- | --- |
| `Content-Type` | 图片 MIME |
| `Content-Disposition` | `attachment; filename*=UTF-8''<encoded>` |
| `Cache-Control` | `private, no-store` |

#### 文件名规则

- `{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`。
- 非法字符（`/ \ : * ? " < > |` 与控制字符）替换为下划线；商品名称为空时用「未命名商品」。
- 时间戳取图片 `created_at`，按 Asia/Shanghai 格式化。
- 使用 RFC 5987 编码，兼容中文文件名。

#### 规则

- 只有 `file_path` 非空且文件可读的图片可下载；`failed`/`pending`/无文件返回 404 `30014`。
- 归档图片从 `archive/{file_path}` 读取，超时或缺失返回 404 `30014`。
- 图片记录不存在返回 404 `30024`；超管内容且当前为管理员返回 403 `20006`；无权限返回 403 `20005`。
- 不提供整包下载；整组 ZIP 属 4/5 号 demo。

---

## 12. 用户详情统计与内容入口

### 12.1 用户列表统计变更

复用 6 号 demo 的：

```http
GET /api/v1/admin/users
Authorization: Bearer <jwt>
```

本 demo 只改变 `stats` 的取值，不改变字段结构：

```json
{
  "stats": {
    "image_count": 23,
    "session_count": 2,
    "token_total": 34567,
    "failed_task_count": 2,
    "stats_available": true
  }
}
```

- 列表与详情共用同一 `stats` 结构。
- 列表页展示前三项；详情页展示四项。
- 统计口径见 §2.7。
- 管理员查看超管账号详情仍返回 403 `20006`；普通用户 403 `20005`；用户不存在 404 `30017`。

### 12.2 用户详情统计变更

```http
GET /api/v1/admin/users/2
Authorization: Bearer <jwt>
```

响应中的 `stats` 与 §12.1 相同；其余账号字段与 6 号 demo 一致。

#### 内容入口

| 按钮 | 跳转 | 说明 |
| --- | --- | --- |
| 查看生图记录 | `/admin/content?user_id={id}` | 内容页定位并选中该用户，加载其会话 |
| 查看会话 | `/admin/chat?user_id={id}` | 8 号 demo 页面；未实现时按钮置灰并提示 |

- 内容页收到 `user_id` 后：若用户存在且有生成记录，左侧列表定位并选中；若用户存在但无生成记录，展示空状态「该用户暂无生成记录」；若用户不存在，展示「用户不存在」。
- 管理员对超管用户不展示内容入口（详情本身 403）。

#### 统计一致性

- 同一用户的 `image_count`、`session_count`、`token_total`、`failed_task_count` 与种子数据一致。
- `token_total` 与 Token 统计中该用户、该时间范围的输入 + 输出合计可交叉核对。
- 列表统计使用批量聚合查询，避免逐用户 N+1；详情与列表同一用户数值一致。

---

## 13. 数据结构汇总

### 13.1 概览

```json
{
  "user_total": 128,
  "today_image_count": 12,
  "total_image_count": 3400,
  "today_token_total": 456789
}
```

### 13.2 Token 统计

```json
{
  "summary": {
    "prompt_tokens": 12000,
    "completion_tokens": 18000,
    "total_tokens": 30000,
    "call_count": 240
  },
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

### 13.3 内容用户

```json
{
  "user_id": 2,
  "username": "demo_user",
  "display_name": "演示用户",
  "status": "active",
  "last_generated_at": "2026-10-31T10:00:00+08:00",
  "batch_count": 6
}
```

### 13.4 会话

```json
{
  "session_id": 12,
  "title": "秋季通勤衬衫",
  "status": "active",
  "last_message_at": "2026-10-31T10:00:00+08:00",
  "batch_count": 2,
  "latest_batch_at": "2026-10-31T10:00:00+08:00",
  "created_at": "2026-10-29T09:00:00+08:00"
}
```

### 13.5 批次

```json
{
  "batch_id": 13,
  "batch_type": "full",
  "status": "completed",
  "product_name": "秋季通勤衬衫",
  "style_text": "简洁白底",
  "width": 1000,
  "height": 1000,
  "template_name": "简约白底",
  "total_count": 6,
  "completed_count": 6,
  "composition": {"main": 1, "detail": 5},
  "created_at": "2026-10-29T10:00:00+08:00",
  "finished_at": "2026-10-29T10:05:00+08:00"
}
```

### 13.6 图片

```json
{
  "image_id": 88,
  "index_no": 2,
  "attempt_no": 1,
  "image_role": "detail",
  "status": "success",
  "width": 1000,
  "height": 1000,
  "thumbnail_url": "/api/v1/admin/content/images/88/thumbnail",
  "archived_at": null,
  "is_history_visible": true,
  "created_at": "2026-10-29T10:02:00+08:00"
}
```

### 13.7 单图详情

见 §10.1。

### 13.8 用户统计

```json
{
  "image_count": 23,
  "session_count": 2,
  "token_total": 34567,
  "failed_task_count": 2,
  "stats_available": true
}
```

---

## 14. 权限与数据边界

### 14.1 接口权限矩阵

| 接口 | `admin` | `super_admin` | 普通用户 |
| --- | --- | --- | --- |
| 概览 `GET /admin/dashboard/summary` | ✓ | ✓ | 403 `20005` |
| Token `GET /admin/tokens/stats` | ✓ | ✓ | 403 `20005` |
| 内容用户/会话/批次/图片/详情/媒体 | ✓（非超管内容） | ✓（全部） | 403 `20005` |
| 用户列表/详情 | 6 号 demo 规则 | 6 号 demo 规则 | 403 `20005` |
| 数据导出 | 未实现 | 未实现 | 未实现 |

### 14.2 超管内容边界

- 管理员的 `/admin/content/users` 列表过滤拥有 `super_admin` 角色的用户。
- 管理员直接请求超管用户的会话、批次、图片、媒体，统一返回 403 `20006`，`message` 为「无权查看超管账号内容」。
- 超管可查看全部用户内容，包括其他超管。
- 普通用户访问任意管理接口返回 403 `20005`；未登录 401；账号禁用/删除 403 `20004`。

### 14.3 数据可见性

| 数据 | demo 处理 |
| --- | --- |
| 已删除/禁用用户的内容 | 可见，列表与详情显示账号状态；用于历史追溯 |
| `hidden` 会话 | 可见，显示「已隐藏」状态 |
| `superseded` 旧图 | 默认不在网格展示；`include_superseded=true` 或 `status=superseded` 可查看；详情可按 ID 查看 |
| `failed`/`pending` 图片 | 网格可见；无文件时下载/预览返回 30014 |
| 归档图片 | 元数据与缩略图可见；大图/下载从 `archive/` 读取 |
| 超管内容 | 管理员不可见；超管可见 |

### 14.4 不提供的入口

- 删除生图记录、删除图片、重新生成、修改提示词、修改状态。
- 导出数据、直连数据库、SQL 查询。
- 后台替用户创建会话或生成图片。

---

## 15. 错误码（最小集）

| code | HTTP | 含义 | 典型场景 |
| --- | --- | --- | --- |
| 0 | 200 | 成功 | — |
| 10001 | 400 | 参数错误 | 缺少必填参数 |
| 10003 | 400 | 参数格式错误 | 日期格式错误、起止倒置、枚举非法、Agent code 未知 |
| 10004 | 400 | 参数超出范围 | `page_size` 超出 1~100、页码非法 |
| 20002 | 401 | 登录已过期 | token 过期 |
| 20003 | 401 | token 无效 | 签名错误、`token_version` 不符 |
| 20004 | 403 | 账号不可用 | 禁用/删除账号 |
| 20005 | 403 | 无权限 | 缺失权限码、普通用户访问管理接口 |
| 20006 | 403 | 无权查看超管账号内容 | 管理员访问超管用户/会话/批次/图片/媒体 |
| 30004 | 404 | 批次不存在 | 批次 ID 无效 |
| 30013 | 404 | 会话不存在 | 会话 ID 无效 |
| 30014 | 404 | 文件不存在或归档不可用 | 文件缺失、归档超时/不可用 |
| 30017 | 404 | 用户不存在 | 用户 ID 无效 |
| 30024 | 404 | 图片不存在 | 图片 ID 无效（本 demo 新增） |
| 50001 | 500 | 系统内部错误 | 未预期异常 |
| 50002 | 500 | 数据库错误 | 查询/聚合失败 |
| 50003 | 500 | 存储服务错误 | 本地存储读写失败 |

错误响应示例：

```json
{
  "code": 30024,
  "message": "图片不存在",
  "data": null
}
```

归档不可用示例：

```json
{
  "code": 30014,
  "message": "文件归档中，请稍后重试",
  "data": {
    "image_id": 88,
    "archived_at": "2021-10-31T10:00:00+08:00"
  }
}
```

---

## 16. 与 9 / 10 号文档的差异与待统一项

1. **新增管理端媒体接口**：本 demo 新增 `/thumbnail` 与 `/content`；9 号 §6.3 只定义 `/download`。正式实现需把两个接口写入 9 号，或改为预签名 URL。
2. **新增错误码 `30024`（图片不存在）**：9 号未定义；本 demo 暂用 `30024`，避开 6 号 demo 的 `30017`~`30019` 与 8 号 demo 的 `30020`~`30023`。
3. **内容接口响应字段**：9 号只列路径与用途，未定义字段；本 demo 的字段以本文档为准，正式实现前回写 9 号。
4. **日期参数命名**：本 demo 用 `start_date` / `end_date`（`YYYY-MM-DD`）；9 号导出用 `start_time` / `end_time`（ISO 8601）。正式实现需统一。
5. **概览缓存**：PRD §3.1 要求 Redis 60 秒；本 demo 用进程内 TTL 60 秒，单实例。正式实现按 9 号 §2.7 换 Redis。
6. **媒体访问方式**：9 号 §8.3 要求缩略图预签名 URL；本 demo 用鉴权接口 + 前端 Blob。正式实现可保留接口，内部改为预签名。
7. **用户详情统计**：6 号 demo 返回 `0` 且 `stats_available=false`；本 demo 改为真实值且 `true`，字段结构不变。需在 6 号 demo 的接口文档中标注升级。
8. **内容追溯范围**：本 demo 包含已删除/禁用用户与 `hidden` 会话；9/10 号未明确。正式实现需确认是否保留历史内容可见。
9. **`superseded` 图片**：本 demo 默认每个序号只展示最新尝试，提供 `include_superseded`；9 号未定义该参数。正式实现需确认网格默认口径。
10. **归档读取**：本 demo 复用 5 号 demo 05 的 `archived_at` + `archive/` 规则与 `30014`；正式实现需统一超时阈值与错误文案。
11. **`agent_runs` 用户归属**：本 demo 优先 `session.user_id`，其次 `batch.user_id`；需 4 号运行时保证每次调用至少关联会话或批次。
12. **Token 统计失败调用**：本 demo 只计入 `success` 与有 Token 的 `failed`；`failed` 且 0 Token 不计入。PRD §4.4 未细化 0 Token 情况。
13. **数据导出未实现**：PRD §8 与验收项 9/10/12/13 延期；本 demo 不提供导出接口、按钮与 `export.*` 审计动作。
14. **「查看会话」依赖 8 号聊天页**：本 demo 只提供 `/admin/chat?user_id=...` 链接；8 号未实现时置灰。
15. **`failed_task_count` 口径**：本 demo 按批次 `failed` 或 `partially_failed` 计数；是否计入 `cancelled` 待确认。
16. **超管内容越权错误码**：本 demo 用 `20006` 并返回「无权查看超管账号内容」；9 号未区分查看与操作。

---

## 17. 未实现接口

以下接口不在本 demo 范围：

- `POST /api/v1/admin/export`、`GET /api/v1/admin/export/{job_id}`、导出文件下载接口。
- `GET /api/v1/admin/chat/sessions`、`GET /api/v1/admin/chat/sessions/{session_id}`、`GET /api/v1/admin/chat/messages/search`、`GET /api/v1/admin/agent-runs/{run_id}`（8 号 demo）。
- `GET/PUT /api/v1/admin/model-config`、`GET/PUT /api/v1/admin/prompts/*`（8 号 demo）。
- `GET/POST/PATCH /api/v1/admin/templates/*`、`/api/v1/admin/materials/*`、`/api/v1/admin/sizes/*`（其他 demo）。
- `GET /api/v1/admin/audit-logs`、`GET /api/v1/admin/audit-logs/{id}`（6 号 demo）。
- 批次/图片删除、重新生成、修改提示词、修改状态接口。
- 直连数据库或 SQL 查询接口。

---

## 18. 验收调用序列

以下示例使用 `BASE=http://localhost:8000/api/v1`、`TOKEN` 为对应账号登录后的 JWT；示例 ID 来自种子，实际以查询结果为准。

### 18.1 概览

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/admin/dashboard/summary"
```

预期：`code=0`，四个数字与种子一致；60 秒内重复调用数字不变。

### 18.2 Token 统计

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/admin/tokens/stats?start_date=2026-10-25&end_date=2026-10-31&agent_codes=copywriter,prompt_builder&model=doubao-seed-1.6&page=1"
```

预期：`summary` 与 `items` 合计一致；`skipped` 不计 Token；`failed` 且 0 Token 的记录不出现。

### 18.3 内容用户

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/admin/content/users?keyword=demo&page=1&page_size=20"
```

预期：`demo_admin` 看不到 `demo_super`；`demo_super` 能看到全部。

### 18.4 用户会话

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/admin/content/users/2/sessions?page=1&page_size=20"
```

预期：包含 `active` 与 `hidden` 会话；默认第一条为最近会话。

### 18.5 会话批次

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/admin/content/sessions/12/batches?product_name=衬衫&batch_type=full&status=completed&start_date=2026-10-01&end_date=2026-10-31&page=1&page_size=20"
```

预期：命中全套批次；`composition` 为 `{main:1, detail:5}`。

### 18.6 批次图片

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/admin/content/batches/13/images?image_role=detail&status=success&include_superseded=false&page=1&page_size=20"
```

预期：只返回成功详情图；默认每个序号最新尝试；`thumbnail_url` 非空。

### 18.7 单图详情

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/admin/content/images/88"
```

预期：返回完整字段；`file_path`、`is_history_visible`、`archived_at` 与种子一致。

### 18.8 媒体访问

```bash
curl -s -H "Authorization: Bearer $TOKEN" -o thumb.png \
  "$BASE/admin/content/images/88/thumbnail"

curl -s -H "Authorization: Bearer $TOKEN" -o preview.png \
  "$BASE/admin/content/images/88/content"

curl -s -H "Authorization: Bearer $TOKEN" -OJ \
  "$BASE/admin/content/images/88/download"
```

预期：成功返回二进制；归档图片下载显示「正在从归档读取…」；归档不可用返回 404 `30014`。

### 18.9 用户详情统计

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/admin/users/2"
```

预期：`stats_available=true`；四项统计与种子一致；「查看生图记录」跳转 `/admin/content?user_id=2`。

### 18.10 越权验证

```bash
# demo_admin 的 token 访问超管用户会话
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$BASE/admin/content/users/{super_admin_user_id}/sessions"
# 预期：403 20006

# demo_user 的 token 访问管理接口
curl -s -H "Authorization: Bearer $USER_TOKEN" \
  "$BASE/admin/content/users"
# 预期：403 20005
```

### 18.11 测试日志要求

前后端冒烟测试按步骤输出中文日志，例如：

```text
步骤 1：使用 demo_admin 登录并读取概览四卡
步骤 2：断言今日生成图片数与种子一致
步骤 3：等待缓存过期后重新请求，断言数字更新
步骤 4：使用 demo_admin 请求 demo_super 会话，断言 403/20006
```

日志不得输出 JWT、密码、API Key 或完整提示词。
