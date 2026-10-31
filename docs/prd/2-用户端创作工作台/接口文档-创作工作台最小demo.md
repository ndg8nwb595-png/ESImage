# 创作工作台最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `2-用户端创作工作台prd.md` §4~§10/§13；`../3-Agent会话交互/3-Agent会话交互prd.md` §5~§7；`9-后端服务与接口prd.md` §2/§3/§5/§7；`10-数据模型与存储prd.md` §4.6~§4.11 |
| 覆盖范围 | 用户端创作工作台最小 demo 的会话、上传、示例生成、确认全套、预览与下载接口 |
| 文档状态 | 最小 demo 约定；正式实现需与 9 号文档统一 |

> 本文档只描述最小 demo 需要落地的接口。未列出的接口（模板、尺寸、取消、单张重生成、整组 ZIP、历史作品、个人中心、管理后台等）不在本次范围内，见第 13 章。

---

## 1. 通用约定

### 1.1 地址与编码

| 项目 | 约定 |
| --- | --- |
| Base URL | `/api/v1` |
| 本地联调 | 前端通过 Vite 开发代理把 `/api` 转发到后端，避免额外 CORS 配置 |
| 请求/响应格式 | JSON：`application/json; charset=utf-8`；上传：`multipart/form-data` |
| 字段命名 | `snake_case` |
| ID | 整数，数据库 `BIGSERIAL` |
| 时间格式 | ISO 8601 带时区偏移，例如 `2026-10-31T10:00:00+08:00` |
| 空值 | `null`，不省略字段 |

### 1.2 统一响应

除 SSE 与文件流外，所有接口返回：

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
| 400 | 参数错误、上传不符合要求 | `1xxx` / `30006` / `30007` |
| 401 | 未登录、token 失效 | `2xxx` |
| 403 | 无权限、账号不可用 | `2xxx` |
| 404 | 会话、批次、上传图、图片不存在或不属于当前用户 | `30004` / `30013` / `30014` |
| 409 | 并发批次、批次状态不允许、幂等冲突 | `30003` / `30005` |
| 500 | 服务端异常 | `5xxx` |

### 1.4 鉴权

```http
Authorization: Bearer <jwt>
```

- 除登录接口外，所有接口必须携带 token；登录接口复用「1-登录界面」最小 demo。
- 后端每次请求校验：token 签名、过期时间、`token_version`、账号状态、接口权限。
- 工作台权限码：

| 权限码 | 用途 |
| --- | --- |
| `user.workspace` | 会话列表、消息读取、SSE 聊天 |
| `user.generate` | 上传商品图、创建批次、确认全套、读取预览图 |
| `user.history` | 下载正式图（与 9 号 §5.6 一致） |

- `demo_user` 需要同时具备三个权限；`demo_admin` 不具备，用于验证角色隔离。

### 1.5 分页

请求：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 1 | 从 1 开始；消息分页中 `page=1` 为最新一页 |
| `page_size` | int | 20 | 最大 100 |

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

### 1.6 幂等

| 场景 | 幂等键 | 规则 |
| --- | --- | --- |
| 发送聊天消息 | `client_message_id` | 同一会话内唯一；重复请求返回已保存消息，不重复调用模型 |
| 首条消息建会话 | `client_message_id` | 同一用户去重；重复请求返回同一会话 |
| 创建示例批次 | `client_request_id` | 全局唯一；重复请求返回已有批次 |
| 确认全套 | `client_request_id` | 全局唯一；重复请求返回已创建的全套批次 |

### 1.7 并发限制

- 同一用户同时只允许 1 个 `queued` / `running` 的生成批次；`sample_ready` 为等待用户操作，不计入并发。
- 确认全套时，被确认的 `sample_ready` 示例批次不参与并发校验。
- 超出限制返回 `30003`。

### 1.8 媒体文件访问

- 桶/目录不公开；所有图片经后端鉴权后流式返回。
- 响应中的 `file_url`、`thumbnail_url`、`content_url` 均为**相对路径**，前端拼接 Base URL 后使用 `fetch` + `Authorization` 读取，再转成 `blob:` URL 展示；不得把 token 写进 `<img src>` 或 URL 查询串。
- 上传图与生成图的预览接口是本 demo 的约定，正式实现需与 9 号 §8 统一。

---

## 2. 最小 demo 约定

### 2.1 运行形态

| 项目 | demo 处理 | 正式实现 |
| --- | --- | --- |
| 异步任务 | FastAPI `BackgroundTasks` + PostgreSQL 状态轮询 | Celery + Redis（11 号文档） |
| 对象存储 | 存储适配层 + 本地目录，接口不变 | MinIO `esimage` 桶（10 号 §6） |
| 权限缓存 | 每次请求查 PostgreSQL | Redis 缓存 ≤30 秒（9 号 §2.7） |
| 数据库迁移 | 建表脚本 + 幂等种子脚本 | Alembic（10 号 §10） |

### 2.2 生成管线

最小 demo 不调用真实 8 Agent 与豆包模型，使用「演示生成管线」：

- 按 `queued → running → sample_ready`（示例批次）或 `queued → running → completed`（全套批次）推进。
- 阶段依次写入 `product_understanding`、`copywriter`、`prompt_builder`、`image_generator`、`quality_reviewer`、`text_composition`、`done`。
- 每张图产出一张 1000×1000 的占位 PNG（可含商品名称与序号），状态置 `success`。
- 全套批次第 1 张直接复用被确认示例图的文件，不重复生成；第 2~6 张逐张生成，`completed_count` 从 1 递增到 6。
- 全套批次进入 `completed` 后，6 张 `final` 成功图的 `is_history_visible` 置为 `true`。
- 批次、图片、阶段、Token 字段与正式实现保持一致；PRD 4 替换管线内部时不改本文接口。

### 2.3 聊天桩

- 未配置启用的 `text_model` 时，SSE 只返回固定的演示回复与最小需求摘要。
- 已配置文本模型时，可替换为真实的规划 + 商品理解轻链路，SSE 事件与字段不变。
- 演示回复示例：
  - 未填写风格：`已了解商品「{商品名称}」。建议风格：简洁白底、高级质感、生活场景、国潮。你可以用自然语言选择或自行补充。`
  - 已填写风格：`已了解商品「{商品名称}」，风格按「{风格}」处理。可以继续补充卖点、目标人群或使用场景。`
- 最小需求摘要：

```json
{
  "product_name": "秋季通勤衬衫",
  "category": null,
  "selling_points": [],
  "target_audience": null,
  "scenes": [],
  "tone": null,
  "constraints": []
}
```

### 2.4 参数与尺寸

- 尺寸固定 1000×1000；不提供 `GET /sizes`、尺寸预设下拉与自定义宽高。
- 不提供模板入口；`template_id` 必须为 `null`。
- 商品名称必填，1~60 字符；风格选填自由文本，1~50 字符；纯空格视为未填写。

### 2.5 会话创建

- 首条聊天消息与首次生成都可以在没有会话时由后端在事务内创建会话。
- 会话标题：
  - 首条用户消息存在：取消息前 20 个字符；
  - 首条动作是生成：取商品名称（超过 50 字符截断到 50）；
  - 都不可用：`未命名会话`。
- demo 使用进程内锁 + 数据库事务去重 `(user_id, client_message_id)`；单实例部署，不引入 Redis 幂等键。

### 2.6 前端 localStorage 键

| 键名 | 内容 | 说明 |
| --- | --- | --- |
| `esimage_token` | JWT | 复用 1 号 demo |
| `esimage_workspace_params_draft` | 参数 JSON | 尚未创建会话时使用 |
| `esimage_workspace_params_{session_id}` | 参数 JSON | 会话创建后迁移 |
| `esimage_workspace_upload_ids_draft` | `upload_id` 数组 | 尚未创建会话时使用 |
| `esimage_workspace_upload_ids_{session_id}` | `upload_id` 数组 | 会话创建后迁移 |
| `esimage_current_session_id` | 当前会话 ID | 刷新恢复用 |
| `esimage_latest_batch_id` | 最近批次 ID | 刷新恢复结果区用 |

参数 JSON 结构：

```json
{
  "product_name": "秋季通勤衬衫",
  "style_text": "简洁白底",
  "width": 1000,
  "height": 1000,
  "template_id": null
}
```

> 草稿键是在 PRD 只定义 `esimage_workspace_params_{session_id}` 的前提下，为「会话尚未创建但用户已填写参数」补充的 demo 约定，见第 12 章。

---

## 3. 接口清单

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/v1/sessions` | `user.workspace` | 当前用户活跃会话列表 |
| GET | `/api/v1/sessions/{id}/messages` | `user.workspace` | 消息分页 |
| POST | `/api/v1/sessions/messages` | `user.workspace` | 首条消息（可无会话），SSE |
| POST | `/api/v1/sessions/{id}/messages` | `user.workspace` | 已有会话发消息，SSE |
| POST | `/api/v1/uploads` | `user.generate` | 上传商品图 |
| GET | `/api/v1/uploads/{upload_id}` | `user.generate` | 读取上传图元数据 |
| DELETE | `/api/v1/uploads/{upload_id}` | `user.generate` | 软删除上传图 |
| GET | `/api/v1/uploads/{upload_id}/content` | `user.generate` | 读取上传图原图（demo 约定） |
| GET | `/api/v1/uploads/{upload_id}/thumbnail` | `user.generate` | 读取上传图缩略图（demo 约定） |
| POST | `/api/v1/generations/sample` | `user.generate` | 创建示例批次 |
| GET | `/api/v1/generations/{batch_id}` | `user.generate` | 查询批次状态与进度 |
| POST | `/api/v1/generations/{batch_id}/confirm` | `user.generate` | 确认示例，创建全套批次 |
| GET | `/api/v1/images/{image_id}/content` | `user.generate` | 大图预览（demo 约定） |
| GET | `/api/v1/images/{image_id}/download` | `user.history` | 下载正式图 PNG |

---

## 4. 会话接口

### 4.1 会话列表

```http
GET /api/v1/sessions
Authorization: Bearer <jwt>
```

#### 请求参数

无。demo 返回当前用户全部 `status=active` 的会话，最多 50 条。

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
        "last_message_preview": "帮我做一套图",
        "latest_batch_id": 12,
        "created_at": "2026-10-31T09:50:00+08:00",
        "updated_at": "2026-10-31T10:00:00+08:00"
      }
    ],
    "total": 1
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | int | 会话 ID，对应 `creative_sessions.id` |
| `title` | string | 会话标题 |
| `status` | string | `active` / `hidden`；本接口只返回 `active` |
| `last_message_at` | string / null | 最后一条消息或首次生成时间 |
| `last_message_preview` | string / null | 最后一条消息摘要，最多 30 字 |
| `latest_batch_id` | int / null | 该会话最近一次生成批次，用于切换会话恢复结果区；demo 约定 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 更新时间 |

排序：`last_message_at DESC NULLS LAST`，其次 `created_at DESC`。

> `latest_batch_id` 与 `last_message_preview` 是 demo 为会话列表展示与结果恢复补充的字段，9 号未定义，见第 12 章。

### 4.2 会话消息分页

```http
GET /api/v1/sessions/{id}/messages?page=1&page_size=20
Authorization: Bearer <jwt>
```

#### 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | int | 否 | 1 | `page=1` 为最新一页 |
| `page_size` | int | 否 | 20 | 最大 100 |

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "message_id": 1001,
        "session_id": 12,
        "role": "user",
        "agent_code": null,
        "content": "帮我做一套图",
        "content_type": "text",
        "status": "done",
        "token_in": 0,
        "token_out": 0,
        "created_at": "2026-10-31T10:00:00+08:00"
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
| `message_id` | int | 对应 `chat_messages.id` |
| `session_id` | int | 所属会话 |
| `role` | string | `user` / `assistant` / `system` |
| `agent_code` | string / null | Agent 消息所属 Agent；轻链路为 `planner` 或 `product_understanding` |
| `content` | string | 消息正文 |
| `content_type` | string | `text` / `markdown` |
| `status` | string | `sending` / `done` / `failed` |
| `token_in` | int | 输入 Token |
| `token_out` | int | 输出 Token |
| `created_at` | string | 创建时间 |

分页顺序：先按 `created_at DESC` 取当前页，再在页内按 `created_at ASC` 返回，便于前端直接渲染。

#### 失败响应

| 场景 | HTTP | code |
| --- | --- | --- |
| 会话不存在或不属于当前用户 | 404 | 30013 |

### 4.3 发送消息（首条，可无会话）

```http
POST /api/v1/sessions/messages
Authorization: Bearer <jwt>
Content-Type: application/json
Accept: text/event-stream
```

#### 请求体

```json
{
  "client_message_id": "2f1c7c9e-9d1a-4b6e-8d0e-7a4c1f2b3a40",
  "content": "帮我做一套通勤风的图",
  "params": {
    "product_name": "秋季通勤衬衫",
    "style_text": "简洁白底",
    "width": 1000,
    "height": 1000,
    "template_id": null
  },
  "session_id": null
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `client_message_id` | string | 是 | UUID；同一会话内唯一，用于幂等 |
| `content` | string | 是 | 去除首尾空格后 1~2000 字符；空消息返回 10002 |
| `params` | object | 是 | 参数快照；`product_name` 必填 1~60 字符 |
| `params.style_text` | string / null | 否 | 1~50 字符；纯空格视为未填写 |
| `params.width` | int / null | 否 | 省略或 `null` 时默认 1000 |
| `params.height` | int / null | 否 | 省略或 `null` 时默认 1000 |
| `params.template_id` | int / null | 否 | 最小 demo 必须为 `null` |
| `session_id` | int / null | 否 | `null` 时后端事务内创建会话；非空时必须是当前用户的 `active` 会话 |

#### 成功响应

HTTP 200，`Content-Type: text/event-stream`：

```text
event: meta
data: {"message_id":1001,"session_id":12}

event: agent_status
data: {"agent_code":"planner","status":"started"}

event: agent_status
data: {"agent_code":"planner","status":"finished"}

event: agent_status
data: {"agent_code":"product_understanding","status":"started"}

event: delta
data: {"content":"已了解商品「秋季通勤衬衫」。"}

event: delta
data: {"content":"建议风格：简洁白底、高级质感、生活场景、国潮。"}

event: agent_status
data: {"agent_code":"product_understanding","status":"finished"}

event: done
data: {"message_id":1001,"token_in":0,"token_out":0,"requirement_summary":{"product_name":"秋季通勤衬衫","category":null,"selling_points":[],"target_audience":null,"scenes":[],"tone":null,"constraints":[]}}
```

> `meta.message_id` 与 `done.message_id` 为本次 Agent 回复的消息 ID。用户消息 ID 不通过 SSE 返回，前端可用 `client_message_id` 与本地临时 ID 对应。

#### 处理流程

1. 校验 token、权限、参数。
2. 若 `session_id` 为空：在事务内创建会话，标题按 §2.5 规则生成；写入用户消息；更新 `last_message_at`。
3. 若 `session_id` 非空：校验归属与状态；写入用户消息。
4. 以 `(session_id, client_message_id)` 去重；重复请求按 §7.4 处理。
5. 写入 Agent 回复消息，`status` 从 `sending` 到 `done`；更新会话 `requirement_summary`。
6. 通过 SSE 返回事件，`done` 或 `error` 后关闭连接。

#### 失败响应

参数、鉴权错误在建立事件流前返回普通 JSON：

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 商品名称未填 | 400 | 10002 | 请先填写商品名称 |
| 商品名称超过 60 字符 | 400 | 10004 | 商品名称不能超过 60 个字符 |
| 消息为空 | 400 | 10002 | 请输入内容 |
| 消息超过 2000 字符 | 400 | 10004 | 消息不能超过 2000 个字符 |
| 风格超过 50 字符 | 400 | 10004 | 风格不能超过 50 个字符 |
| 模板不支持 | 404 | 30016 | 模板/素材/尺寸不存在 |
| 会话不存在或不属于当前用户 | 404 | 30013 | 会话不存在 |
| 消息正在处理中 | 409 | 30005 | 消息正在处理中，请稍候 |
| 无 `user.workspace` | 403 | 20005 | 无权限 |

流建立后的模型失败通过 SSE `error` 事件返回，见 §7.5。

### 4.4 发送消息（已有会话）

```http
POST /api/v1/sessions/{id}/messages
Authorization: Bearer <jwt>
Content-Type: application/json
Accept: text/event-stream
```

请求体与 §4.3 相同，但不传 `session_id`（以路径参数为准）。路径中的会话必须是当前用户的 `active` 会话，否则返回 30013。

---

## 5. 上传接口

### 5.1 上传商品图

```http
POST /api/v1/uploads
Authorization: Bearer <jwt>
Content-Type: multipart/form-data
```

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 单张图片 |

#### 校验

1. 扩展名：`.jpg` / `.jpeg` / `.png` / `.webp`。
2. MIME：`image/jpeg` / `image/png` / `image/webp`。
3. 大小：≤10MB（`10 * 1024 * 1024` 字节）。
4. 可解码：能读取宽高；损坏图片拒绝。
5. 数量：当前用户「`session_id IS NULL` 且 `status='active'`」的上传总数不超过 5 张；新增后超过 5 张返回 30006。
6. 内容审核：最小 demo 跳过；正式实现返回 30007。

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "upload_id": 101,
    "file_url": "/api/v1/uploads/101/content",
    "thumbnail_url": "/api/v1/uploads/101/thumbnail",
    "width": 1200,
    "height": 1200,
    "size_bytes": 204800,
    "mime_type": "image/jpeg",
    "original_name": "shirt.jpg",
    "sort_order": 0,
    "status": "active",
    "created_at": "2026-10-31T10:00:00+08:00"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `upload_id` | int | 上传图 ID |
| `file_url` | string | 原图相对地址；需带 token 读取 |
| `thumbnail_url` | string | 缩略图相对地址；需带 token 读取 |
| `width` / `height` | int | 原图宽高 |
| `size_bytes` | int | 文件大小 |
| `mime_type` | string | MIME |
| `original_name` | string | 原始文件名 |
| `sort_order` | int | 当前排序，新上传追加到末尾 |
| `status` | string | `active` |
| `created_at` | string | 创建时间 |

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 缺少文件 | 400 | 10002 | 请选择要上传的图片 |
| 格式不支持 | 400 | 30006 | 仅支持 JPG、PNG、WEBP 格式 |
| 单张超过 10MB | 400 | 30006 | 单张图片不能超过 10MB |
| 图片损坏 | 400 | 30006 | 图片文件损坏，请重新上传 |
| 超过 5 张 | 400 | 30006 | 最多上传 5 张商品图 |
| 内容审核不通过 | 400 | 30007 | 内容未通过审核，请调整描述或更换商品图 |
| 无 `user.generate` | 403 | 20005 | 无权限 |

### 5.2 读取上传图元数据

```http
GET /api/v1/uploads/{upload_id}
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，`data` 与 §5.1 成功响应相同。

#### 失败响应

| 场景 | HTTP | code |
| --- | --- | --- |
| 不存在、已删除或不属于当前用户 | 404 | 30014 |

用途：刷新后按 localStorage 中的 `upload_id` 恢复缩略图与排序。

### 5.3 删除上传图

```http
DELETE /api/v1/uploads/{upload_id}
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": null
}
```

#### 说明

- 软删除：`uploaded_assets.status` 置为 `deleted`；原图与缩略图保留，供已生成记录追溯。
- 仅从当前创作中移除，不影响已生成批次中的引用。
- 不存在、已删除或不属于当前用户返回 404 `30014`。

### 5.4 读取上传图原图（demo 约定）

```http
GET /api/v1/uploads/{upload_id}/content
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，`Content-Type` 为原图 MIME，返回文件流：

```http
Content-Type: image/jpeg
Content-Disposition: inline
Cache-Control: private, max-age=300
```

#### 说明

- 仅当前用户可读；不存在或已删除返回 404 `30014`。
- 前端用 `fetch` + `Authorization` 读取后转 `blob:` URL，不直接把地址放进 `<img src>`。

### 5.5 读取上传图缩略图（demo 约定）

```http
GET /api/v1/uploads/{upload_id}/thumbnail
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，`Content-Type: image/webp`，最大宽度 400px：

```http
Content-Type: image/webp
Content-Disposition: inline
Cache-Control: private, max-age=3600
```

---

## 6. 生成接口

### 6.1 创建示例批次

```http
POST /api/v1/generations/sample
Authorization: Bearer <jwt>
Content-Type: application/json
```

#### 请求体

```json
{
  "client_request_id": "8b0f3f5a-2c4d-4f6e-9a1b-3c5d7e9f0a12",
  "session_id": 12,
  "product_name": "秋季通勤衬衫",
  "style_text": "简洁白底",
  "width": 1000,
  "height": 1000,
  "template_id": null,
  "upload_ids": [101, 102],
  "requirement_summary": null
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `client_request_id` | string | 是 | UUID；全局唯一，用于幂等 |
| `session_id` | int / null | 否 | `null` 时后端事务内创建会话；非空时必须是当前用户的 `active` 会话 |
| `product_name` | string | 是 | 去除首尾空格后 1~60 字符；不允许纯空格 |
| `style_text` | string / null | 否 | 1~50 字符；纯空格视为 `null` |
| `width` | int / null | 否 | 省略或 `null` 时默认 1000；正整数 |
| `height` | int / null | 否 | 省略或 `null` 时默认 1000；正整数 |
| `template_id` | int / null | 否 | 最小 demo 必须为 `null`；非空返回 30016 |
| `upload_ids` | int[] | 否 | 0~5 个；必须属于当前用户、`active`，且未绑定其他会话 |
| `requirement_summary` | object / null | 否 | 省略时使用会话的 `requirement_summary`；显式传入时以请求为准 |

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "batch_id": 12,
    "session_id": 12,
    "session_title": "秋季通勤衬衫",
    "batch_type": "sample",
    "status": "queued",
    "total_count": 1,
    "completed_count": 0
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | int | 示例批次 ID |
| `session_id` | int | 会话 ID；`session_id` 为空时为新创建的会话 |
| `session_title` | string | 会话标题 |
| `batch_type` | string | `sample` |
| `status` | string | `queued` |
| `total_count` | int | 固定 1 |
| `completed_count` | int | 初始 0 |

> 返回 `session_id` 与 `session_title` 是 demo 约定；9 号未定义创建响应，见第 12 章。

#### 处理流程

1. 校验 token、权限、参数。
2. 校验并发：当前用户无 `queued` / `running` 批次，否则 30003。
3. 校验上传图：归属、状态、数量；未绑定会话的上传图在本次生成时回填 `session_id`，并按 `upload_ids` 顺序写 `sort_order`。
4. `session_id` 为空时，在同一事务内创建会话；标题取商品名称（截断到 50）。
5. 创建 `sample` 批次：`total_count=1`、`completed_count=0`、`status=queued`、`stage=null`，写入 `params_snapshot`、`requirement_summary`、`client_request_id`。
6. 提交事务后投递演示生成管线。
7. 返回批次与会话信息。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 商品名称未填 | 400 | 10002 | 请先填写商品名称 |
| 商品名称超过 60 字符 | 400 | 10004 | 商品名称不能超过 60 个字符 |
| 风格超过 50 字符 | 400 | 10004 | 风格不能超过 50 个字符 |
| 宽高非正整数 | 400 | 10003 | 宽高需为正整数 |
| 模板非空 | 404 | 30016 | 模板/素材/尺寸不存在 |
| 上传图超过 5 张/不属于当前用户/已删除/已绑定其他会话 | 400 | 30006 | 上传文件不符合要求 |
| 会话不存在或不属于当前用户 | 404 | 30013 | 会话不存在 |
| 已有生成任务进行中 | 409 | 30003 | 已有生成任务进行中 |
| 无 `user.generate` | 403 | 20005 | 无权限 |

幂等：相同 `client_request_id` 重复提交返回已有批次，不重复创建、不重复投递任务，HTTP 200。

### 6.2 查询批次状态与进度

```http
GET /api/v1/generations/{batch_id}
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，示例批次：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "batch_id": 12,
    "batch_type": "sample",
    "status": "running",
    "stage": "image_generator",
    "total_count": 1,
    "completed_count": 0,
    "images": [
      {
        "image_id": 88,
        "index": 1,
        "image_role": "main",
        "status": "generating",
        "thumbnail_url": null,
        "content_url": "/api/v1/images/88/content",
        "error_message": null,
        "width": 1000,
        "height": 1000
      }
    ],
    "error_message": null,
    "created_at": "2026-10-31T10:00:00+08:00",
    "finished_at": null
  }
}
```

全套批次完成时：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "batch_id": 13,
    "batch_type": "full",
    "status": "completed",
    "stage": "done",
    "total_count": 6,
    "completed_count": 6,
    "images": [
      {
        "image_id": 88,
        "index": 1,
        "image_role": "main",
        "status": "success",
        "thumbnail_url": "/api/v1/images/88/thumbnail",
        "content_url": "/api/v1/images/88/content",
        "error_message": null,
        "width": 1000,
        "height": 1000
      },
      {
        "image_id": 89,
        "index": 2,
        "image_role": "detail",
        "status": "success",
        "thumbnail_url": "/api/v1/images/89/thumbnail",
        "content_url": "/api/v1/images/89/content",
        "error_message": null,
        "width": 1000,
        "height": 1000
      }
    ],
    "error_message": null,
    "created_at": "2026-10-31T10:05:00+08:00",
    "finished_at": "2026-10-31T10:05:12+08:00"
  }
}
```

> 为节省篇幅，示例中的 `images` 只展示前 2 张；实际 `full` 批次返回 6 张。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | int | 批次 ID |
| `batch_type` | string | `sample` / `full` |
| `status` | string | 批次状态，见 §9 |
| `stage` | string / null | 当前阶段；`queued` 时为 `null` |
| `total_count` | int | 计划张数：示例 1，全套 6 |
| `completed_count` | int | 已完成张数；全套批次初始为 1（复用示例图） |
| `images` | array | 图片列表，按 `index` 升序 |
| `images[].image_id` | int | 图片 ID |
| `images[].index` | int | 组内序号，从 1 开始 |
| `images[].image_role` | string | `main` / `detail` |
| `images[].status` | string | `pending` / `generating` / `success` / `failed` / `cancelled` / `superseded` |
| `images[].thumbnail_url` | string / null | 缩略图相对地址；未生成时为 `null` |
| `images[].content_url` | string / null | 原图相对地址；未生成时为 `null`；demo 约定 |
| `images[].error_message` | string / null | 失败原因 |
| `images[].width` / `height` | int / null | 图片尺寸 |
| `error_message` | string / null | 批次失败原因 |
| `created_at` | string | 创建时间 |
| `finished_at` | string / null | 结束时间 |

`stage` 取值与前端展示：

| `stage` | 前端展示 |
| --- | --- |
| `null` | 排队中 |
| `product_understanding` | 需求理解 |
| `copywriter` | 文案生成 |
| `prompt_builder` | 提示词构建 |
| `image_generator` | 图像绘制 |
| `quality_reviewer` | 质量审核 |
| `repairer` | 修复（demo 不进入） |
| `platform_rule` | 平台规范（demo 不进入） |
| `text_composition` | 文字合成 |
| `done` | 已完成 |

#### 失败响应

| 场景 | HTTP | code |
| --- | --- | --- |
| 批次不存在或不属于当前用户 | 404 | 30004 |

### 6.3 确认示例并生成全套

```http
POST /api/v1/generations/{batch_id}/confirm
Authorization: Bearer <jwt>
Content-Type: application/json
```

#### 请求体

```json
{
  "client_request_id": "c2d4e6f8-0a1b-2c3d-4e5f-6a7b8c9d0e1f"
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `client_request_id` | string | 是 | UUID；全局唯一，用于幂等 |

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "full_batch_id": 13,
    "total_count": 6,
    "status": "queued"
  }
}
```

#### 处理流程

1. 校验 token、权限、参数。
2. 在事务中对示例批次加行锁，校验：
   - 批次属于当前用户；
   - `batch_type=sample`；
   - 状态为 `sample_ready`；
   - 是该用户最近创建的、仍为 `sample_ready` 的示例批次（只有最新示例可确认）。
3. 校验并发：当前用户无 `queued` / `running` 批次；被确认的 `sample_ready` 不参与校验。
4. 创建 `full` 批次：`source_sample_batch_id` 指向示例批次，`total_count=6`、`completed_count=1`、`status=queued`。
5. 为示例图新建 `generated_images` 记录：`batch_id=full`、`image_type=final`、`image_role=main`、`index_no=1`、`status=success`、`source_image_id=示例图`、复用文件路径；`is_history_visible=false`，待全套批次完成后置 `true`。
6. 示例批次状态置 `confirmed`。
7. 复制示例批次的 `params_snapshot` 与 `requirement_summary` 到全套批次。
8. 提交事务后投递演示生成管线，生成第 2~6 张详情图。
9. 返回全套批次 ID。

#### 幂等

- 相同 `client_request_id` 重复提交返回已创建的全套批次及其当前状态。
- 示例批次已被确认、状态不是 `sample_ready`、或不是最新可确认示例时返回 30005。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 批次不存在或不属于当前用户 | 404 | 30004 | 批次不存在 |
| 示例批次状态不是 `sample_ready` | 409 | 30005 | 当前批次状态不允许确认 |
| 不是最新可确认示例 | 409 | 30005 | 该示例不是最新示例，请确认最新示例 |
| 已有生成任务进行中 | 409 | 30003 | 已有生成任务进行中 |
| 无 `user.generate` | 403 | 20005 | 无权限 |

### 6.4 大图预览（demo 约定）

```http
GET /api/v1/images/{image_id}/content
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，`Content-Type: image/png`，返回文件流：

```http
Content-Type: image/png
Content-Disposition: inline
Cache-Control: private, max-age=300
```

#### 说明

- 仅当前用户可读。
- 示例图与正式图都可读取，用于结果区预览；是否允许下载由 §6.5 单独控制。
- 不存在或不属于当前用户返回 404 `30014`。

### 6.5 下载正式图

```http
GET /api/v1/images/{image_id}/download
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，返回 PNG 文件流：

```http
Content-Type: image/png
Content-Disposition: attachment; filename*=UTF-8''%E7%A7%8B%E5%AD%A3%E9%80%9A%E5%8B%A4%E8%A1%AC%E8%A1%AB_%E4%B8%BB%E5%9B%BE_1_20261031100512.png
```

#### 下载条件

只有同时满足以下条件的图片可下载：

1. 属于当前用户。
2. `image_type=final`。
3. `status=success`。
4. `is_history_visible=true`。
5. 所属批次状态为 `completed` 或 `partially_failed`。

示例图（`image_type=sample`）、确认前的示例图、失败图、取消任务半成品、`superseded` 旧图不可下载。

#### 文件命名

- `{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`
- 商品名称中的文件名非法字符替换为下划线。
- 示例图确认后作为正式图下载时，`image_role=main`，序号为 1。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 图片不存在或不属于当前用户 | 404 | 30014 | 文件不存在 |
| 示例图确认前下载 | 409 | 30005 | 示例图确认前不可下载 |
| 失败图/取消半成品/被替代旧图 | 409 | 30005 | 当前图片不可下载 |
| 归档文件暂不可用 | 404 | 30014 | 文件归档中，请稍后重试 |
| 无 `user.history` | 403 | 20005 | 无权限 |

---

## 7. SSE 协议

### 7.1 请求

```http
POST /api/v1/sessions/messages
Authorization: Bearer <jwt>
Accept: text/event-stream
Content-Type: application/json
```

或：

```http
POST /api/v1/sessions/{id}/messages
```

响应头：

```http
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

### 7.2 事件

| event | data | 说明 |
| --- | --- | --- |
| `meta` | `{ message_id, session_id }` | 连接建立，返回 Agent 回复消息 ID 与会话 ID |
| `agent_status` | `{ agent_code, status }` | `started` / `finished` / `skipped` |
| `delta` | `{ content }` | 增量文本 |
| `done` | `{ message_id, token_in, token_out, requirement_summary }` | 完成 |
| `error` | `{ code, message }` | 错误 |
| `ping` | `{}` | 心跳，每 15 秒 |

### 7.3 事件顺序

```text
meta
agent_status(planner, started)
agent_status(planner, finished)
agent_status(product_understanding, started)
delta...
agent_status(product_understanding, finished)
done
```

- 心跳可穿插在任意位置。
- `done` 或 `error` 之后服务端关闭连接。
- 每个事件以 `event:` 与 `data:` 两行输出，空行分隔。

### 7.4 幂等与重连

1. 前端每次发送生成 `client_message_id`。
2. 后端以 `(session_id, client_message_id)` 去重：
   - 已存在且已完成：返回 `meta`、一次 `delta`（完整回复）与 `done`，不重复调用模型。
   - 已存在且处理中：返回 HTTP 409 `30005`，前端提示「消息正在处理中，请稍候」。
3. 连接中断且未收到 `done`：
   - 前端提示「连接中断，正在重试」；
   - 自动重试最多 2 次，使用同一 `client_message_id`；
   - 仍失败则标记消息失败，提供「重新发送」。
4. 页面刷新后重新加载消息；处理中的消息若已超时，标记失败。

### 7.5 流内错误

模型调用失败、审核不通过等在流建立后通过 `error` 事件返回：

```text
event: error
data: {"code":30001,"message":"模型调用失败"}
```

| code | 含义 |
| --- | --- |
| 30001 | 模型调用失败 |
| 30007 | 内容未通过审核 |

前端收到 `error` 后把消息标记为失败，不自动重试审核失败。

### 7.6 Nginx

```nginx
location /api/v1/sessions/ {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 300s;
}
```

---

## 8. 数据结构

### 8.1 会话

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | int | 对应 `creative_sessions.id` |
| `title` | string | 标题，1~50 字符 |
| `status` | string | `active` / `hidden` |
| `last_message_at` | string / null | 最后消息或首次生成时间 |
| `last_message_preview` | string / null | 最后消息摘要，≤30 字 |
| `latest_batch_id` | int / null | 最近批次 ID；demo 约定 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 更新时间 |

### 8.2 消息

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message_id` | int | 对应 `chat_messages.id` |
| `session_id` | int | 所属会话 |
| `role` | string | `user` / `assistant` / `system` |
| `agent_code` | string / null | `planner` / `product_understanding` / `null` |
| `content` | string | 正文 |
| `content_type` | string | `text` / `markdown` |
| `status` | string | `sending` / `done` / `failed` |
| `token_in` / `token_out` | int | Token 消耗 |
| `created_at` | string | 创建时间 |

### 8.3 上传图

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `upload_id` | int | 对应 `uploaded_assets.id` |
| `file_url` | string | 原图相对地址 |
| `thumbnail_url` | string | 缩略图相对地址 |
| `width` / `height` | int | 宽高 |
| `size_bytes` | int | 大小 |
| `mime_type` | string | MIME |
| `original_name` | string | 原始文件名 |
| `sort_order` | int | 排序，首张为主参考图 |
| `status` | string | `active` / `deleted` |
| `created_at` | string | 创建时间 |

### 8.4 批次与图片

字段见 §6.2。批次状态与阶段枚举与 10 号 §5 一致。

### 8.5 参数快照

```json
{
  "product_name": "秋季通勤衬衫",
  "style_text": "简洁白底",
  "width": 1000,
  "height": 1000,
  "template_id": null,
  "upload_ids": [101, 102],
  "image_composition": "1 main + 5 detail",
  "requirement_summary": {
    "product_name": "秋季通勤衬衫",
    "category": null,
    "selling_points": [],
    "target_audience": null,
    "scenes": [],
    "tone": null,
    "constraints": []
  },
  "created_at": "2026-10-31T10:00:00+08:00"
}
```

写入 `generation_batches.params_snapshot`；生成过程中前端修改参数不影响已提交批次。

---

## 9. 状态机与并发

### 9.1 示例批次

```text
queued → running → sample_ready → confirmed
                 ↘ failed
queued / running / sample_ready → cancelled
```

最小 demo 只演示 `queued → running → sample_ready → confirmed`；`failed`、`cancelled` 保留枚举，不提供交互。

### 9.2 全套批次

```text
queued → running → completed / partially_failed / failed
queued / running → cancelled
```

最小 demo 只演示 `queued → running → completed`。

### 9.3 单图

```text
pending → generating → success / failed
                    ↘ cancelled
```

最小 demo 只演示 `pending → generating → success`。

### 9.4 并发与可确认规则

1. 同一用户同时只允许 1 个 `queued` / `running` 批次；`sample_ready` 不计入。
2. 重新生成示例创建新的 `sample` 批次，旧批次保留；结果区只展示最新示例。
3. 只有该用户最近创建的、仍为 `sample_ready` 的示例批次可以确认；旧示例返回 30005。
4. 确认在事务中对示例批次加行锁；重复确认或状态不符返回 30005。
5. `full` 批次必须引用一个 `confirmed` 的 `sample` 批次。
6. `cancelled` 是终态；最小 demo 不提供取消入口。

---

## 10. 错误码（最小集）

| code | HTTP | 含义 | 本 demo 使用场景 |
| --- | --- | --- | --- |
| 0 | 200 | 成功 | 全部 |
| 10001 | 400 | 参数错误 | 通用 |
| 10002 | 400 | 缺少必填参数 | 商品名称、消息、文件 |
| 10003 | 400 | 参数格式错误 | 宽高非正整数 |
| 10004 | 400 | 参数超出范围 | 商品名称/风格/消息超长 |
| 20002 | 401 | 登录已过期 | token 过期 |
| 20003 | 401 | token 无效 | 未携带/签名错误/版本不符 |
| 20004 | 403 | 账号不可用 | 账号禁用/删除 |
| 20005 | 403 | 无权限 | 缺少 `user.workspace` / `user.generate` / `user.history` |
| 30001 | 400/SSE | 模型调用失败 | 聊天流内错误 |
| 30003 | 409 | 已有生成任务进行中 | 创建示例/确认全套 |
| 30004 | 404 | 批次不存在 | 查询/确认批次 |
| 30005 | 409 | 批次状态不允许该操作 | 确认非 `sample_ready`、示例图下载、消息处理中 |
| 30006 | 400 | 上传文件不符合要求 | 格式、大小、数量、归属 |
| 30007 | 400/SSE | 内容未通过审核 | 上传/聊天（demo 跳过） |
| 30013 | 404 | 会话不存在 | 消息、生成 |
| 30014 | 404 | 文件不存在或归档不可用 | 上传图/图片/下载 |
| 30016 | 404 | 模板/素材/尺寸不存在 | 最小 demo 传 `template_id` 时 |
| 50001 | 500 | 系统内部错误 | 兜底 |
| 50002 | 500 | 数据库错误 | 兜底 |
| 50003 | 500 | 存储服务错误 | 兜底 |

错误响应统一为：

```json
{
  "code": 30005,
  "message": "示例图确认前不可下载",
  "data": null
}
```

---

## 11. 前端约定

### 11.1 请求注入

- 从 `localStorage` 读取 `esimage_token`，非空时注入 `Authorization: Bearer <token>`。
- token 不写入 URL、日志、错误上报。

### 11.2 参数与上传图恢复

1. 尚未创建会话时，参数写入 `esimage_workspace_params_draft`，上传图 ID 写入 `esimage_workspace_upload_ids_draft`。
2. 会话创建后（聊天 `meta.session_id` 或生成响应 `session_id`）：
   - 把草稿键内容写入 `esimage_workspace_params_{session_id}` 与 `esimage_workspace_upload_ids_{session_id}`；
   - 删除草稿键；
   - 写入 `esimage_current_session_id`。
3. 刷新时：
   - 读取 `esimage_current_session_id`；
   - 读取对应参数与上传图 ID；
   - 用 `GET /uploads/{upload_id}` 恢复上传图元数据与缩略图；
   - 用 `GET /sessions` 或 `esimage_latest_batch_id` 恢复最近批次结果。
4. 新建会话：清空参数与上传图，使用草稿键；不继承上一会话内容。

### 11.3 前端校验

| 字段 | 规则 | 处理 |
| --- | --- | --- |
| 商品名称 | 去除首尾空格后 1~60 字符；不允许纯空格 | 为空或超长时 `Modal.warning` 提示并聚焦输入框；不发请求；输入框 `maxLength=60`，粘贴超长截断并提示 |
| 风格 | 去除首尾空格后 1~50 字符；纯空格视为未填写 | 超长截断并提示；不阻塞生成 |
| 尺寸 | 最小 demo 固定 1000×1000 | 不提供编辑 |
| 商品图 | 0~5 张；JPG/PNG/WEBP；单张 ≤10MB | 不通过时 Toast 且不发请求 |
| 聊天消息 | 去除首尾空格后 1~2000 字符 | 空消息禁止发送；超长禁止发送 |

商品名称未填时：

- 聊天输入框禁用，占位文案「请先填写商品名称后再开始对话」。
- 「生成示例图」按钮不可用。
- 商品名称填写后两者同时可用。

### 11.4 生成按钮状态

| 条件 | 状态 |
| --- | --- |
| 商品名称为空 | 禁用 |
| 存在 `queued` / `running` 批次 | 禁用，显示「正在生成…」 |
| `sample_ready` | 可用（不阻塞重新生成或确认） |
| 其他 | 可用 |

### 11.5 轮询

- 每 2 秒调用 `GET /generations/{batch_id}`。
- 终态：`sample_ready`、`confirmed`、`completed`、`partially_failed`、`failed`、`cancelled`，停止轮询。
- 页面隐藏时降为 10 秒；恢复可见后立即刷新一次。
- 使用 `setTimeout` 串行调度，避免请求重叠。
- 网络异常时提示「网络异常，任务可能仍在后台执行」，继续以 2 秒（或降频 10 秒）轮询恢复状态。

### 11.6 媒体展示

- 通过 `fetch` + `Authorization` 读取 `thumbnail_url` / `content_url`。
- 转成 `URL.createObjectURL(blob)` 后放入 `<img>`；组件卸载或图片替换时 `URL.revokeObjectURL`。
- 预览大图使用 `GET /images/{image_id}/content`；不要复用下载接口。
- 缩略图加载失败显示占位图与「图片加载失败」。

### 11.7 下载

- 用 `fetch` + `Authorization` 获取文件流，从 `Content-Disposition` 解析文件名；解析失败时按 §6.5 规则在前端拼装。
- 用临时 `<a download>` 触发保存；保存后释放 blob URL。
- 示例图确认前不展示下载入口；即使调用接口也会被 30005 拦截。

### 11.8 错误处理

| 场景 | 前端行为 |
| --- | --- |
| 401（`20002` / `20003`） | 清除 token 与全局用户状态，跳 `/login?redirect=当前路径` |
| 403（`20004`） | 清除 token，跳 `/login` |
| 403（`20005`） | 跳 `/403` 或 Toast「无权限」 |
| 409（`30003`） | Toast「已有生成任务进行中」，刷新当前批次状态 |
| 404（`30004`） | Toast「批次不存在」，清除当前批次 |
| 409（`30005`） | Toast 返回的 `message`，刷新当前批次状态 |
| 400（`30006`） | 上传区 Toast 返回的 `message`，支持单张重试 |
| 400（`30007`） | Toast「内容未通过审核，请调整描述或更换商品图」，不自动重试 |
| 404（`30013`） | Toast「会话不存在或已删除」，回到会话列表/新建会话 |
| 404（`30014`） | Toast「文件不存在或归档中，请稍后重试」 |
| 5xx | Toast「系统繁忙，请稍后重试」，不自动登出 |
| 网络异常 | 生成中：「网络异常，任务可能仍在后台执行」；其他：「网络异常，请稍后重试」 |

---

## 12. 与 9 号文档的差异与待统一项

| 项目 | 本文 demo 口径 | 9 号 / 正式实现 | 处理建议 |
| --- | --- | --- | --- |
| 创建示例批次响应 | 返回 `batch_id`、`session_id`、`session_title`、`status`、`total_count`、`completed_count` | 9 号未定义创建响应，只定义批次状态响应 | 把 `session_id`、`session_title` 补进 9 号，或明确由会话列表关联 |
| 会话列表字段 | 增加 `last_message_preview`、`latest_batch_id` | 9 号只说明按最后消息时间倒序 | 正式实现确认由会话列表还是会话详情返回 |
| 大图预览接口 | `GET /images/{image_id}/content` | 9 号只定义下载；预览未定义 | 正式实现补预览接口，或约定预签名 URL（9 号 §8.3 仅备选） |
| 上传图读取接口 | `GET /uploads/{id}/content`、`/thumbnail` | 9 号只给 `file_url` / `thumbnail_url` | 正式实现明确 URL 形态与鉴权方式 |
| 预览接口权限 | `user.generate` | 9 号下载用 `user.history`；5 号历史作品也用 `user.history` | 正式实现统一为 `user.history` 或拆分预览/下载权限 |
| 示例图下载拦截 | 示例图下载返回 30005 | 9 号未定义该场景错误码 | 正式实现补充错误码或复用 30005 |
| 会话创建幂等 | 进程内锁 + 数据库事务，单实例 | 3 号要求 Redis 幂等键 TTL 60 秒 | 正式实现按 3 号接 Redis |
| 聊天请求是否必须带 `params` | 按 9 号 §7.1 要求必填 | 3 号 §7.1 的请求示例只有 `client_message_id` 与 `content` | 两处统一后再定 |
| 生成创建会话的 `last_message_at` | 取首次生成时间，便于会话列表排序 | 10 号只定义「最后消息时间」，未说明生成动作是否更新 | 正式实现确认写入口径 |
| 确认幂等的返回状态 | 返回已创建全套批次的当前状态 | 9 号只给确认成功响应示例 | 正式实现统一 |
| 生成管线 | 演示管线，占位 PNG，阶段推进 | 4 号要求 8 Agent 全链路、豆包 Seedream | PRD 4 实现后替换管线内部，接口不变 |
| 异步任务 | FastAPI `BackgroundTasks` | Celery + Redis | 正式实现换 Celery |
| 对象存储 | 本地目录适配层 | MinIO `esimage` 单桶 | 正式实现切 MinIO |
| 模板 | 不提供，`template_id` 必须为 `null` | 9 号 `GET /templates`；4 号模板管理 | 正式实现补模板 |
| 尺寸 | 固定 1000×1000 | 9 号 `GET /sizes`；4 号尺寸管理 | 正式实现补尺寸 |
| 聊天模型 | 未配置模型时固定回复 | 3 号要求规划 + 商品理解真实模型 | 正式实现按 3 号替换桩 |
| localStorage 草稿键 | 增加 `_draft` 键并在会话创建后迁移 | 2 号只定义 `esimage_workspace_params_{session_id}` | 正式实现确认草稿阶段键名 |
| 最新可确认示例 | 按用户维度「最近创建的 `sample_ready`」 | 4 号说「最新一次 `sample_ready`」，未明确用户/会话维度 | 正式实现确认维度 |
| 上传图数量口径 | 未绑定会话且 `active` 的总数 ≤5 | 9 号 / 2 号一致 | 保持 |

---

## 13. 未实现接口

以下接口明确不在最小 demo 内，调用方不得依赖：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/sizes` | 尺寸预设 |
| GET | `/api/v1/templates` | 模板卡片 |
| GET | `/api/v1/materials` | 素材库 |
| POST | `/api/v1/sessions` | 显式创建会话 |
| PATCH | `/api/v1/sessions/{id}` | 重命名会话 |
| DELETE | `/api/v1/sessions/{id}` | 软删除会话 |
| POST | `/api/v1/generations/{batch_id}/cancel` | 取消任务 |
| GET | `/api/v1/generations/{batch_id}/images` | 单独查询批次图片 |
| POST | `/api/v1/images/{image_id}/regenerate` | 单张重生成/重试 |
| GET | `/api/v1/batches/{batch_id}/download` | 整组 ZIP |
| GET | `/api/v1/history` | 历史作品列表 |
| GET | `/api/v1/history/{batch_id}` | 历史批次详情 |
| GET | `/api/v1/profile` | 个人中心 |
| PATCH | `/api/v1/profile` | 修改个人资料 |
| — | `/api/v1/admin/*` | 全部管理端接口 |

---

## 14. 验收调用序列

以下序列对应 README 第 5 章的演示脚本：

| 步骤 | 调用 | 期望 |
| --- | --- | --- |
| 1 | `POST /auth/login`（复用 1 号 demo） | 返回 token 与 `user.permissions` |
| 2 | `GET /auth/me` | 返回 `user.workspace`、`user.generate`、`user.history` |
| 3 | `GET /sessions` | 空列表或历史会话 |
| 4 | `POST /sessions/messages`（`session_id=null`） | SSE `meta` 返回新 `session_id`，`done` 返回需求摘要 |
| 5 | `GET /sessions` | 新会话出现，标题按首条消息自动生成 |
| 6 | `POST /uploads` ×2 | 返回两个 `upload_id` 与缩略图地址 |
| 7 | `POST /generations/sample` | 返回 `batch_id`、`session_id`、`status=queued` |
| 8 | `GET /generations/{batch_id}` 轮询 | `stage` 依次推进，最终 `sample_ready`，1 张示例图 |
| 9 | `GET /images/{sample_image_id}/content` | 可预览 |
| 10 | `GET /images/{sample_image_id}/download` | 409 `30005`，示例图确认前不可下载 |
| 11 | `POST /generations/sample`（`client_request_id` 不同） | 创建新的 `sample` 批次，旧批次保留 |
| 12 | `POST /generations/{latest_sample_batch_id}/confirm` | 返回 `full_batch_id`、`total_count=6`、`status=queued` |
| 13 | `GET /generations/{full_batch_id}` 轮询 | `completed_count` 从 1 到 6，`status=completed` |
| 14 | `GET /images/{full_image_id}/content` | 可预览 |
| 15 | `GET /images/{full_image_id}/download` | 200，PNG，文件名符合规则 |
| 16 | 刷新页面 | 从 localStorage 恢复参数、上传图、当前会话与最近批次 |
| 17 | `POST /generations/sample`（已有 `running` 批次） | 409 `30003` |
| 18 | `demo_admin` 的 token 调 `GET /sessions` | 403 `20005` |

### 14.1 示例：创建示例批次

```bash
curl -X POST http://localhost:8000/api/v1/generations/sample \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_request_id": "8b0f3f5a-2c4d-4f6e-9a1b-3c5d7e9f0a12",
    "session_id": 12,
    "product_name": "秋季通勤衬衫",
    "style_text": "简洁白底",
    "width": 1000,
    "height": 1000,
    "template_id": null,
    "upload_ids": [101, 102]
  }'
```

### 14.2 示例：确认全套

```bash
curl -X POST http://localhost:8000/api/v1/generations/12/confirm \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_request_id":"c2d4e6f8-0a1b-2c3d-4e5f-6a7b8c9d0e1f"}'
```

### 14.3 示例：SSE

```bash
curl -N -X POST http://localhost:8000/api/v1/sessions/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "client_message_id": "2f1c7c9e-9d1a-4b6e-8d0e-7a4c1f2b3a40",
    "content": "帮我做一套通勤风的图",
    "params": {
      "product_name": "秋季通勤衬衫",
      "style_text": "简洁白底",
      "width": 1000,
      "height": 1000,
      "template_id": null
    },
    "session_id": null
  }'
```
