# 9-后端服务与接口 PRD

| 项目 | 内容 |
| --- | --- |
| 文档编号 | 9 |
| 文档名称 | 后端服务与接口 PRD |
| 版本 | v0.1 |
| 编写日期 | 2026-10-31 |
| 文档状态 | 待评审 |
| 上游文档 | `0-系统汇总prd.md` |
| 关联文档 | `1`~`8`、`10-数据模型与存储prd.md`、`11-部署与运维prd.md` |
| 术语依据 | `GLOSSARY.md` |

---

## 1. 文档目的与范围

### 1.1 目的

定义后端对前端提供的 REST 接口约定、鉴权、统一响应、分页、错误码、SSE、文件上传下载，以及用户端与管理端的主要接口清单。

### 1.2 本期范围

- 接口通用规范。
- 错误码表。
- 登录与账号接口。
- 用户端：配置读取、上传、会话、聊天、生成、历史、下载、个人中心。
- 管理端：概览、Token、用户、角色、内容追溯、聊天记录、Agent 配置、素材模板、日志、导出。
- SSE 协议。
- OpenAPI 文档。

### 1.3 不做

- 对外开放 API、API Key 管理。
- Webhook。
- GraphQL。
- 第三方登录。
- 接口级限流（仅做并发限制）。

---

## 2. 通用规范

### 2.1 基础约定

| 项目 | 约定 |
| --- | --- |
| 基础路径 | `/api/v1` |
| 协议 | HTTP/HTTPS |
| 请求/响应格式 | JSON，UTF-8 |
| 时间格式 | ISO 8601，带时区，如 `2026-10-31T10:00:00+08:00` |
| ID | 整数，数据库 `BIGSERIAL` |
| 字段命名 | `snake_case` |
| 空值 | `null`，不省略字段 |
| 布尔值 | `true` / `false` |
| ORM 会话 | SQLAlchemy 2.0 同步会话（FastAPI 线程池执行，Celery 任务共用同一会话模型） |

### 2.2 鉴权

```http
Authorization: Bearer <jwt>
```

- 除 `POST /auth/login` 外，所有接口必须携带 token。
- 后端每次请求校验：token 签名、过期时间、`token_version`、账号状态。
- 权限校验按 `permissions` 表中的权限码执行。
- 越权返回 `403`；未登录或 token 失效返回 `401`。

### 2.3 统一响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

- `code=0` 表示成功。
- 非 0 时 `data` 为 `null` 或包含补充信息。
- HTTP 状态码与业务码同时使用：
  - 参数错误：HTTP 400 + `1xxx`
  - 鉴权失败：HTTP 401 + `2xxx`
  - 无权限：HTTP 403 + `20005`
  - 业务错误：HTTP 400/409 + `3xxx`
  - 系统错误：HTTP 500 + `5xxx`

### 2.4 分页

请求：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 1 | 从 1 开始 |
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

### 2.5 幂等

| 场景 | 幂等键 | 规则 |
| --- | --- | --- |
| 发送聊天消息 | `client_message_id` | 同一会话内唯一；重复请求返回已保存消息 |
| 首条消息建会话 | `client_message_id` | 同一用户 + `client_message_id` 去重；重复请求返回同一会话，不重复创建 |
| 创建生成批次 | `client_request_id` | 全局唯一；重复请求返回已有批次 |
| 导出任务 | 同一超管同时只允许 1 个 | 重复提交返回已有任务 |

### 2.6 并发限制

- 同一用户同时只允许 1 个 `queued` / `running` 的生成批次；`sample_ready` 为等待用户操作，不计入并发。
- 确认全套时，被确认的 `sample_ready` 示例批次不参与该并发校验。
- 同一超管同时只允许 1 个导出任务。
- 超出限制返回 `30003` 或 `30008`。

### 2.7 缓存

- 尺寸、模板、素材等配置可缓存 60 秒。
- 模型配置与系统提示词保存后立即刷新缓存。
- 用户权限在每次请求时读取，或缓存不超过 30 秒；权限变更后主动失效。

---

## 3. 错误码

### 3.1 通用

| code | HTTP | 含义 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 10001 | 400 | 参数错误 |
| 10002 | 400 | 缺少必填参数 |
| 10003 | 400 | 参数格式错误 |
| 10004 | 400 | 参数超出范围 |
| 20001 | 401 | 用户名或密码错误 |
| 20002 | 401 | 登录已过期 |
| 20003 | 401 | token 无效 |
| 20004 | 403 | 账号不可用（禁用/删除） |
| 20005 | 403 | 无权限 |
| 20006 | 403 | 无权操作超管账号 |
| 20007 | 403 | 不能操作自己 |
| 30001 | 400 | 模型调用失败 |
| 30002 | 400 | 模型未配置 |
| 30003 | 409 | 已有生成任务进行中 |
| 30004 | 404 | 批次不存在 |
| 30005 | 409 | 批次状态不允许该操作 |
| 30006 | 400 | 上传文件不符合要求 |
| 30007 | 400 | 内容未通过审核 |
| 30008 | 409 | 已有导出任务进行中 |
| 30009 | 409 | 角色组合不合法 |
| 30010 | 409 | 用户名已存在 |
| 30011 | 409 | 必须保留至少一个可用超管 |
| 30013 | 404 | 会话不存在 |
| 30014 | 404 | 文件不存在或归档不可用 |
| 30015 | 409 | 权限点不可授予该角色 |
| 30016 | 404 | 模板/素材/尺寸不存在 |
| 50001 | 500 | 系统内部错误 |
| 50002 | 500 | 数据库错误 |
| 50003 | 500 | 存储服务错误 |

> 30012 原用于「模板与图片角色不匹配」。模板改为整套模板后该错误废弃，编号保留不复用。

### 3.2 错误响应示例

```json
{
  "code": 30005,
  "message": "当前批次状态不允许确认",
  "data": {
    "batch_id": 12,
    "status": "running"
  }
}
```

---

## 4. 登录与账号接口

### 4.1 登录

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `POST /api/v1/auth/login` |
| 鉴权 | 不需要 |
| 请求 | `{ username, password, remember_me }` |
| 响应 | `{ token, expires_at, user }` |
| 权限 | — |

### 4.2 退出登录

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `POST /api/v1/auth/logout` |
| 鉴权 | 需要 |
| 请求 | 无 |
| 响应 | `null` |
| 说明 | 记录审计日志；服务端不维护黑名单 |

### 4.3 当前用户

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `GET /api/v1/auth/me` |
| 鉴权 | 需要 |
| 响应 | `{ user, roles, permissions }` |
| 说明 | 前端启动时调用，用于恢复登录态与渲染菜单 |

### 4.4 修改密码

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `PUT /api/v1/auth/password` |
| 鉴权 | 需要 |
| 请求 | `{ old_password, new_password }` |
| 响应 | `null` |
| 说明 | 校验旧密码；成功后 `token_version` 递增，当前 token 失效，需重新登录 |

---

## 5. 用户端接口

### 5.1 配置读取

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/sizes` | `user.workspace` | 启用中的尺寸预设；未选择时默认 1000×1000 |
| `GET /api/v1/templates` | `user.workspace` | 启用中的整套模板卡片 |
| `GET /api/v1/materials?tag=` | `user.workspace` | 内部使用；用户端不直接展示 |

> 风格为自由文本，不提供 `/styles` 配置接口，也不在后台维护风格列表。
> 模板为整套模板，不区分主图/详情图，不携带尺寸。

### 5.2 上传

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | `POST /api/v1/uploads` |
| 鉴权 | `user.generate` |
| 请求 | `multipart/form-data`，字段 `file` |
| 响应 | `{ upload_id, file_url, thumbnail_url, width, height, size_bytes }` |
| 限制 | JPG/PNG/WEBP；≤10MB；该用户「未绑定会话且 `active`」的上传总数 ≤5 张，绑定会话后释放名额 |
| 错误 | 30006 |

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `DELETE /api/v1/uploads/{upload_id}` | `user.generate` | 从当前会话移除上传图（软删除） |
| `GET /api/v1/uploads/{upload_id}` | `user.generate` | 读取当前用户上传图元数据与缩略图地址（localStorage 恢复用） |

> 上传图在首次用于生成时回填 `session_id`；未使用前可为空。

### 5.3 会话

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/sessions` | `user.workspace` | 当前用户活跃会话列表，按最后消息时间倒序 |
| `POST /api/v1/sessions` | `user.workspace` | 创建会话；返回 `session_id` |
| `PATCH /api/v1/sessions/{id}` | `user.workspace` | 重命名，`{ title }` |
| `DELETE /api/v1/sessions/{id}` | `user.workspace` | 软删除，状态置 `hidden` |
| `GET /api/v1/sessions/{id}/messages` | `user.workspace` | 分页获取消息 |

> `POST /sessions` 仅用于显式创建；首条消息与生成可在无会话时由后端原子创建。
> 参数面板内容不通过会话详情接口持久化；参数与上传图 ID 由前端 localStorage 保存。

**创建会话请求**

```json
{
  "title": null,
  "requirement_summary": null
}
```

- `title` 为空时按首条消息或商品名称自动命名。

### 5.4 聊天（SSE）

| 项目 | 内容 |
| --- | --- |
| 方法/路径 | 已有会话：`POST /api/v1/sessions/{id}/messages`；首条消息：`POST /api/v1/sessions/messages`（`session_id` 可为空） |
| 鉴权 | `user.workspace` |
| 请求头 | `Accept: text/event-stream` |
| 请求体 | `{ client_message_id, content, params, session_id? }`；首条消息可传 `session_id: null`；`params` 由前端 localStorage 读取，仅用于本轮上下文 |
| 响应 | SSE 事件流 |
| 说明 | 只调用规划 + 商品理解两个 Agent |

事件定义见第 7 章。

### 5.5 生成

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `POST /api/v1/generations/sample` | `user.generate` | 创建示例批次 |
| `GET /api/v1/generations/{batch_id}` | `user.generate` | 查询批次状态与进度 |
| `POST /api/v1/generations/{batch_id}/confirm` | `user.generate` | 确认示例，创建全套批次 |
| `POST /api/v1/generations/{batch_id}/cancel` | `user.generate` | 取消批次 |
| `GET /api/v1/generations/{batch_id}/images` | `user.generate` | 批次图片列表 |
| `POST /api/v1/images/{image_id}/regenerate` | `user.generate` | 重生成/重试单张 |

**创建示例批次请求**

```json
{
  "client_request_id": "uuid",
  "session_id": 12,
  "product_name": "秋季通勤衬衫",
  "style_text": "简洁白底",
  "width": 1000,
  "height": 1000,
  "template_id": 5,
  "upload_ids": [101, 102],
  "requirement_summary": {
    "selling_points": ["透气", "不易起球"],
    "target_audience": "通勤女性"
  }
}
```

- `style_text`、`width`、`height`、`template_id`、`upload_ids` 均为选填；`width`/`height` 省略时默认 1000×1000。
- `session_id` 可为空；为空时后端在同一事务内创建会话。
- 请求不再包含 `output_type`；每次固定生成 1 张主图 + 5 张详情图。

**批次状态响应**

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
        "status": "generating",
        "thumbnail_url": null
      }
    ]
  }
}
```

- `stage` 取自 `generation_batches.stage`，取值见 `10-数据模型与存储prd.md` §5；`queued` 时为空。
- `images` 列表只返回每个序号最新一次尝试（`superseded` 旧图不返回）；旧图仅后台可见。

**确认请求**

```json
{
  "client_request_id": "uuid"
}
```

**确认响应**

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

### 5.6 历史与下载

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/history` | `user.history` | 当前用户历史批次分页 |
| `GET /api/v1/history/{batch_id}` | `user.history` | 批次详情与图片列表 |
| `GET /api/v1/images/{image_id}/download` | `user.history` | 下载单张 PNG |
| `GET /api/v1/batches/{batch_id}/download` | `user.history` | 下载整组 ZIP |

- 下载响应使用 `Content-Disposition: attachment; filename*=UTF-8''...`。
- 越权或不存在返回 403/404。

### 5.7 个人中心

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/profile` | `user.profile` | 当前用户资料 |
| `PATCH /api/v1/profile` | `user.profile` | 修改显示名、邮箱（头像本期不做） |
| `PUT /api/v1/auth/password` | 登录即可 | 修改密码 |

---

## 6. 管理端接口

### 6.1 概览与统计

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/admin/dashboard/summary` | `admin.dashboard.view` | 四张统计卡片 |
| `GET /api/v1/admin/tokens/stats` | `admin.tokens.view` | Token 统计，支持时间、用户、Agent、模型筛选 |

### 6.2 用户与角色

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/admin/users` | `admin.accounts.view` | 用户列表 |
| `POST /api/v1/admin/users` | `admin.accounts.create` | 新建账号 |
| `GET /api/v1/admin/users/{id}` | `admin.accounts.view` | 用户详情 |
| `PATCH /api/v1/admin/users/{id}` | `admin.accounts.edit` | 编辑显示名、角色、状态 |
| `POST /api/v1/admin/users/{id}/reset-password` | `admin.accounts.reset_password` | 重置密码 |
| `POST /api/v1/admin/users/{id}/disable` | `admin.accounts.disable` | 禁用 |
| `POST /api/v1/admin/users/{id}/enable` | `admin.accounts.disable` | 启用 |
| `DELETE /api/v1/admin/users/{id}` | `admin.accounts.delete` | 软删除 |
| `POST /api/v1/admin/users/{id}/restore` | `admin.accounts.delete` | 恢复 |
| `GET /api/v1/admin/roles` | `admin.roles.view` | 三个角色与权限点 |
| `PUT /api/v1/admin/roles/{code}/permissions` | `admin.roles.edit` | 保存角色权限点（仅超管） |

**新建账号请求**

```json
{
  "username": "zhangsan",
  "display_name": "张三",
  "password": "******",
  "roles": ["user"],
  "status": "active"
}
```

**编辑角色请求**

```json
{
  "display_name": "张三",
  "roles": ["admin", "user"],
  "status": "active"
}
```

**角色权限保存请求**

```json
{
  "permissions": ["admin.dashboard.view", "admin.accounts.view"]
}
```

### 6.3 内容追溯

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/admin/content/users` | `admin.content.view` | 有生成记录的用户 |
| `GET /api/v1/admin/content/users/{user_id}/sessions` | `admin.content.view` | 用户会话 |
| `GET /api/v1/admin/content/sessions/{session_id}/batches` | `admin.content.view` | 会话批次 |
| `GET /api/v1/admin/content/batches/{batch_id}/images` | `admin.content.view` | 批次图片 |
| `GET /api/v1/admin/content/images/{image_id}` | `admin.content.view` | 单图详情 |
| `GET /api/v1/admin/content/images/{image_id}/download` | `admin.content.view` | 下载单图 |

### 6.4 聊天记录

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/admin/chat/sessions` | `admin.content.view` | 聊天会话列表 |
| `GET /api/v1/admin/chat/sessions/{session_id}` | `admin.content.view` | 会话详情与消息 |
| `GET /api/v1/admin/chat/messages/search` | `admin.content.view` | 消息关键词搜索 |
| `GET /api/v1/admin/agent-runs/{run_id}` | `admin.content.view` | Agent 调用明细 |

- 管理员看不到超管账号的会话；接口层过滤。
- 超管可通过 `?full=true` 获取完整输入/输出。

### 6.5 Agent 配置

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/admin/model-config` | `admin.model.view` | 读取模型配置（Key 脱敏） |
| `PUT /api/v1/admin/model-config` | `admin.model.edit` | 保存模型配置 |
| `GET /api/v1/admin/prompts` | `admin.prompts.view` | 8 个 Agent 提示词列表 |
| `GET /api/v1/admin/prompts/{agent_code}` | `admin.prompts.view` | 当前提示词与版本历史 |
| `PUT /api/v1/admin/prompts/{agent_code}` | `admin.prompts.edit` | 保存新版本 |
| `POST /api/v1/admin/prompts/{agent_code}/versions/{version}/activate` | `admin.prompts.edit` | 回滚 |

**模型配置请求**

```json
{
  "base_url": "https://ark.cn-beijing.volces.com/api/v3",
  "api_key": "******",
  "text_model": "doubao-xxx",
  "image_model": "doubao-seedream-xxx",
  "vision_model": "doubao-vision-xxx",
  "temperature": 0.7,
  "timeout_seconds": 120,
  "concurrency": 4,
  "retry_count": 1,
  "max_context_tokens": 32000
}
```

- `api_key` 为空表示不修改；非空则覆盖。
- 响应中的 `api_key` 始终脱敏。

### 6.6 素材与模板

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/admin/templates` | `admin.assets.view` | 模板列表 |
| `POST /api/v1/admin/templates` | `admin.assets.edit` | 新建模板 |
| `PATCH /api/v1/admin/templates/{id}` | `admin.assets.edit` | 编辑模板 |
| `POST /api/v1/admin/templates/{id}/status` | `admin.assets.edit` | 启用/停用 |
| `GET /api/v1/admin/materials` | `admin.assets.view` | 素材列表 |
| `POST /api/v1/admin/materials` | `admin.assets.edit` | 上传素材（multipart） |
| `PATCH /api/v1/admin/materials/{id}` | `admin.assets.edit` | 编辑素材 |
| `POST /api/v1/admin/materials/{id}/status` | `admin.assets.edit` | 启用/停用 |
| `GET /api/v1/admin/sizes` | `admin.assets.view` | 尺寸预设 |
| `POST /api/v1/admin/sizes` | `admin.assets.edit` | 新增尺寸 |
| `PATCH /api/v1/admin/sizes/{id}` | `admin.assets.edit` | 编辑尺寸 |

### 6.7 操作日志与导出

| 方法/路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/v1/admin/audit-logs` | `admin.audit.view` | 操作日志列表 |
| `GET /api/v1/admin/audit-logs/{id}` | `admin.audit.view` | 日志详情 |
| `POST /api/v1/admin/export` | `admin.export` | 创建导出任务 |
| `GET /api/v1/admin/export/{job_id}` | `admin.export` | 查询状态与下载链接 |

**导出请求**

```json
{
  "scope": "all",
  "user_ids": [],
  "start_time": "2026-01-01T00:00:00+08:00",
  "end_time": "2026-10-31T23:59:59+08:00",
  "include_audit_logs": false
}
```

**导出状态响应**

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "job_id": "exp_20261031_001",
    "status": "running",
    "progress": 0.4,
    "download_url": null,
    "expires_at": null
  }
}
```

---

## 7. SSE 协议

### 7.1 请求

```http
POST /api/v1/sessions/{id}/messages
Authorization: Bearer <token>
Accept: text/event-stream
Content-Type: application/json

{
  "client_message_id": "uuid",
  "content": "帮我做一套图",
  "params": {
    "product_name": "秋季通勤衬衫",
    "style_text": "简洁白底",
    "width": 1000,
    "height": 1000,
    "template_id": 5
  }
}
```

- 首条消息可调用 `/api/v1/sessions/messages` 并传 `session_id: null`；`meta` 事件返回新建的 `session_id`。

### 7.2 事件

| event | data | 说明 |
| --- | --- | --- |
| `meta` | `{ message_id, session_id }` | 连接建立 |
| `agent_status` | `{ agent_code, status }` | `started` / `finished` / `skipped` |
| `delta` | `{ content }` | 增量文本 |
| `done` | `{ message_id, token_in, token_out, requirement_summary, requirement_changed }` | 完成 |
| `error` | `{ code, message }` | 错误 |
| `ping` | `{}` | 心跳，15 秒 |

### 7.3 服务端要求

- 响应头设置 `Cache-Control: no-cache`、`X-Accel-Buffering: no`。
- 每个事件以 `event:` 与 `data:` 两行输出，空行分隔。
- 客户端断开时停止生成并释放资源。
- `done` 或 `error` 后关闭连接。
- 聊天消息与 Agent 调用记录必须在生成过程中落库，断线后可查询。

### 7.4 Nginx

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

## 8. 文件上传与下载

### 8.1 上传

- `multipart/form-data`。
- 单文件字段名 `file`。
- 服务端校验：MIME、扩展名、大小、可解码、宽高。
- 存储路径见 `10-数据模型与存储prd.md`。
- 返回 `upload_id` 与访问地址。
- 图片访问默认需要鉴权；前端通过接口获取，不直接暴露 MinIO。

### 8.2 下载

- 单张：`GET /api/v1/images/{image_id}/download`。
- 整组：`GET /api/v1/batches/{batch_id}/download`。
- 后端校验权限后以流式返回。
- 文件名按业务规则生成，使用 RFC 5987 编码。
- 归档文件从 `archive/` 读取；不可用时返回 `30014`。

### 8.3 预签名 URL

- 缩略图访问使用预签名 URL：有效期不超过 5 分钟，签发前必须校验权限；原件下载仍走后端鉴权流式返回。
- 导出下载链接有效期 24 小时，仅超管可获取。

---

## 9. OpenAPI

- 使用 FastAPI 自动生成 OpenAPI 3.0 文档。
- 路径：`/api/docs`（Swagger UI）与 `/api/openapi.json`。
- 文档需包含：
  - 鉴权方式。
  - 统一响应与分页结构。
  - 错误码说明。
  - 每个接口的权限码。
- 生产环境可限制 `/api/docs` 仅内网访问。

---

## 10. 验收标准

1. 除登录外所有接口都校验 JWT；无 token 返回 401。
2. 越权接口返回 403，不泄露数据。
3. 统一响应结构与分页结构在所有接口一致。
4. 错误码与文档一致，前端可按 code 做提示。
5. 聊天 SSE 能流式输出，断线可重连，重试不重复消息。
6. 生成接口支持幂等，重复提交不创建重复批次。
7. 上传接口校验格式、大小、数量，非法文件被拒绝。
8. 下载接口校验权限，归档文件不可用时返回明确错误。
9. 管理员接口按权限点校验，管理员无法访问模型配置、日志、导出。
10. 管理员无法查看超管账号内容。
11. 导出接口仅超管可用，异步任务可查询状态与下载。
12. OpenAPI 文档可访问，包含鉴权、分页、错误码说明。

---

## 11. 待确认项

> 以下事项已于 2026-10-31 细化评审中确定。

| 序号 | 事项 | 结论 |
| --- | --- | --- |
| 1 | 是否引入接口级限流 | 已确定：只做并发限制，不做 QPS 限流 |
| 2 | 图片访问是否走预签名 URL | 已确定：原件走后端鉴权流式；缩略图走预签名 URL（≤5 分钟） |
| 3 | API 文档是否对外网开放 | 已确定：默认仅内网，部署时配置 |
| 4 | 批量上传是否合并为一个接口 | 已确定：单文件接口，前端循环上传 |
