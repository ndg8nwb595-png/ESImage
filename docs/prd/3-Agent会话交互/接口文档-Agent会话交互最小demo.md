# Agent 会话交互最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `3-Agent会话交互prd.md` §2~§9/§12；`9-后端服务与接口prd.md` §3/§5.3/§5.4/§7；`10-数据模型与存储prd.md` §4.6~§4.8 |
| 覆盖范围 | 会话重命名、会话软删除、消息分页与聊天 SSE 的增量约定 |
| 文档状态 | 最小 demo 约定；正式实现需与 9 号文档统一 |

> 本文档只描述 3 号 PRD 最小 demo 相对 2 号 demo 的**增量**。会话列表、消息分页、首条消息建会话、SSE 基础事件、自动命名、幂等与断线重试的完整字段见 [`2 号接口文档`](../2-用户端创作工作台/接口文档-创作工作台最小demo.md)。本文档新增或变更的字段会显式标注「demo 约定」。

---

## 1. 通用约定

### 1.1 地址与编码

| 项目 | 约定 |
| --- | --- |
| Base URL | `/api/v1` |
| 本地联调 | 前端通过 Vite 开发代理把 `/api` 转发到后端 |
| 请求/响应格式 | JSON：`application/json; charset=utf-8`；聊天响应：`text/event-stream` |
| 字段命名 | `snake_case` |
| ID | 整数，数据库 `BIGSERIAL` |
| 时间格式 | ISO 8601 带时区偏移，例如 `2026-10-31T10:00:00+08:00` |
| 空值 | `null`，不省略字段 |

### 1.2 统一响应

除 SSE 外，所有接口返回：

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

### 1.3 鉴权与权限

```http
Authorization: Bearer <jwt>
```

- 除登录接口外，所有接口必须携带 token。
- 每次请求校验 token 签名、过期时间、`token_version`、账号状态与接口权限。
- 会话与聊天接口需要 `user.workspace`。
- 仅普通用户角色可调用；管理员账号调用用户端聊天接口返回 403 `20005`。
- 用户只能访问自己的会话与消息；他人会话与已隐藏会话统一返回 404 `30013`，不泄露存在性。

### 1.4 分页

沿用 2 号接口文档 §1.5：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 1 | 从 1 开始；`page=1` 为最新一页 |
| `page_size` | int | 20 | 最大 100 |

### 1.5 幂等

| 场景 | 幂等键 | 规则 |
| --- | --- | --- |
| 发送聊天消息 | `(session_id, client_message_id)` | 已完成则重放已保存回复；处理中返回 409；失败则复用原回复消息重试 |
| 首条消息建会话 | `(user_id, client_message_id)` | 重复请求返回同一会话与同一回复，不重复创建会话 |
| 重命名会话 | 无 | 同一标题重复提交结果一致；并发以最后一次写入为准 |
| 软删除会话 | 无 | 首次成功；重复删除返回 404 `30013`，前端按删除成功处理 |

> 最小 demo 用进程内锁 + 数据库唯一约束去重，单实例部署；正式实现按 10 号 §4.7 使用 Redis 短期幂等键（TTL 60 秒）。

---

## 2. 最小 demo 约定

### 2.1 与 2 号 demo 的关系

- 会话列表、消息分页、首条消息建会话、SSE 事件骨架、自动命名、断线重试、`agent_runs` 基础落库由 2 号 demo 04 交付。
- 本目录新增：`PATCH /sessions/{id}`、`DELETE /sessions/{id}`、`done.requirement_changed`、`meta.duplicate`、消息状态展示规则与 10 轮上下文截断。
- 2 号 demo 03（商品图上传）不是前置；`params.upload_ids` 存在时只校验归属与数量，不分析图片内容。

### 2.2 轻链路演示桩

- 未配置启用的 `text_model` 时，后端使用确定性演示桩：
  - 规划 Agent 固定输出「已了解商品「{商品名称}」」类确认语与可选建议；
  - 未填写风格时输出 3~5 个风格建议；
  - 商品理解 Agent 返回最小需求摘要。
- 演示桩仍按真实事件顺序推送 `agent_status`，仍写入两条 `agent_runs`，Token 写 0。
- 配置 `text_model` 后可切换真实模型；事件类型、字段与落库结构不变。
- 演示桩不调用内容审核，`30007` 仅保留。

### 2.3 上下文窗口

每次轻链路调用的上下文按以下顺序组装：

1. 两个 Agent 各自的系统提示词。
2. 前端随聊天请求提交的当前参数（商品名称、风格、尺寸、模板）。
3. 会话最新的 `requirement_summary`。
4. 最近 10 轮对话（用户 + Agent 为一轮），按时间正序。
5. 已确认示例图描述（若有）：由已确认示例批次的商品名称、风格与需求摘要快照拼接。

截断规则：

- 超过 10 轮时从最早一轮开始丢弃。
- 丢弃后注入一条系统说明：「更早的对话已省略，需求摘要以当前 `requirement_summary` 为准」。
- 该说明只进入本次模型请求，不写入 `chat_messages`，不出现在消息分页。
- 最小 demo 不做 Token 上限的二次压缩；`max_context_tokens` 预留给正式实现。

### 2.4 需求变化判定

- 基准：当前会话最近一个 `batch_type='sample'` 且 `status='confirmed'` 的生成批次。
- 比对字段：
  - 风格：本次请求 `params.style_text` 与批次风格快照；
  - 卖点：会话最新 `requirement_summary.selling_points` 与批次 `requirement_summary.selling_points`；
  - 尺寸：本次请求 `params.width/height` 与批次宽高。
- 任一字段不同即 `requirement_changed=true`；没有已确认示例批次时始终为 `false`。
- 卖点按去空格、去重后的集合比较，忽略顺序；风格与尺寸按值比较。
- 判定只通过 `done` 事件返回，不新增查询接口，不阻断聊天。

### 2.5 消息超时处理

- 后端在消息分页时，将 `status='sending'` 且创建时间超过 120 秒的 Agent 消息惰性标记为 `failed`，再返回结果。
- 用户消息不参与超时标记。
- 超时只影响展示与重试，不删除已写入的内容。

---

## 3. 接口清单

| 方法 | 路径 | 权限 | 用途 | 相对 2 号 demo |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/sessions` | `user.workspace` | 当前用户活跃会话列表 | 沿用，无字段变更 |
| PATCH | `/api/v1/sessions/{id}` | `user.workspace` | 重命名会话 | 新增 |
| DELETE | `/api/v1/sessions/{id}` | `user.workspace` | 软删除会话 | 新增 |
| GET | `/api/v1/sessions/{id}/messages` | `user.workspace` | 消息分页 | 沿用，补充状态与超时约定 |
| POST | `/api/v1/sessions/messages` | `user.workspace` | 首条消息，SSE，可无会话 | 沿用，`done` 增加字段 |
| POST | `/api/v1/sessions/{id}/messages` | `user.workspace` | 已有会话发消息，SSE | 沿用，`done` 增加字段 |

不提供：`POST /sessions`、会话恢复、`POST /messages/{id}/cancel`、`GET /sessions/{id}/agent-runs`、消息搜索/导出、管理端聊天接口、聊天触发生图接口。

---

## 4. 会话重命名

```http
PATCH /api/v1/sessions/{id}
Authorization: Bearer <jwt>
Content-Type: application/json
```

### 4.1 请求体

```json
{
  "title": "秋季通勤衬衫"
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `title` | string | 是 | 去除首尾空格后 1~50 个字符；纯空格视为空；不允许换行控制字符 |

### 4.2 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "session_id": 12,
    "title": "秋季通勤衬衫",
    "status": "active",
    "updated_at": "2026-10-31T10:05:00+08:00"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | int | 会话 ID |
| `title` | string | 保存后的标题 |
| `status` | string | `active` |
| `updated_at` | string | 更新时间 |

### 4.3 处理规则

1. 校验 token、权限、路径参数与标题。
2. 查询当前用户、`status='active'` 的会话；不存在或不属于当前用户返回 `30013`。
3. 更新 `title` 与 `updated_at`；不修改消息、生成批次、需求摘要与 `last_message_at`。
4. 返回保存后的会话摘要。
5. 用户重命名后，后续消息或生成不再自动覆盖标题。

### 4.4 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 未传 `title` 或纯空格 | 400 | 10002 | 请输入会话名称 |
| `title` 超过 50 字符 | 400 | 10004 | 会话名称不能超过 50 个字符 |
| `title` 类型错误 | 400 | 10003 | 参数格式错误 |
| 会话不存在、已隐藏或不属于当前用户 | 404 | 30013 | 会话不存在 |
| 未登录或 token 失效 | 401 | 20002 / 20003 | 登录已过期，请重新登录 |
| 无 `user.workspace` | 403 | 20005 | 无权限 |

---

## 5. 会话软删除

```http
DELETE /api/v1/sessions/{id}
Authorization: Bearer <jwt>
```

### 5.1 请求参数

无请求体。路径参数 `id` 为会话 ID。

### 5.2 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "session_id": 12,
    "status": "hidden"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | int | 会话 ID |
| `status` | string | 固定为 `hidden` |

### 5.3 处理规则

1. 校验 token、权限与归属。
2. 将会话 `status` 置为 `hidden`，更新 `updated_at`。
3. 不删除、不隐藏消息、生成批次、生成图片与上传图；管理员后台仍可追溯。
4. 不更新 `last_message_at`。
5. 用户端会话列表与消息分页随即不可访问该会话。

### 5.4 前端行为

- 删除成功后重新拉取会话列表，移除该项。
- 若删除的是当前会话：切换到列表第一项（按 `last_message_at` 倒序）；列表为空时进入空会话草稿并清空聊天区与结果区。
- 用户端不提供恢复入口。
- 重复删除或已隐藏会话返回 `30013`，前端按删除成功处理，不重复提示。

### 5.5 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 会话不存在、已隐藏或不属于当前用户 | 404 | 30013 | 会话不存在 |
| 未登录或 token 失效 | 401 | 20002 / 20003 | 登录已过期，请重新登录 |
| 无 `user.workspace` | 403 | 20005 | 无权限 |

---

## 6. 会话列表与消息分页

### 6.1 会话列表

沿用 2 号接口文档 §4.1，无字段变更。补充约定：

- 只返回当前用户 `status='active'` 的会话，已隐藏会话不出现。
- 按 `last_message_at DESC NULLS LAST`、`created_at DESC` 排序。
- `last_message_preview` 取该会话最后一条消息（任意 `role`）的正文，去除换行与首尾空格后截取前 30 个字符；无消息时为 `null`。
- `latest_batch_id` 为该会话最近一次生成批次，没有时为 `null`。
- 不返回 `requirement_summary`；需求摘要由后端在聊天时读取。

### 6.2 消息分页

沿用 2 号接口文档 §4.2，补充约定：

- `page=1` 为最新一页；页内按 `created_at ASC` 返回。
- `status` 取值 `sending` / `done` / `failed`；`sending` 超过 120 秒的 Agent 消息在查询时被惰性标记为 `failed`（见 §2.5）。
- `agent_code` 对用户消息与系统消息为 `null`；Agent 消息为 `planner` 或 `product_understanding`。
- 系统消息 `role='system'`、`agent_code=null`、`token_in=0`、`token_out=0`。
- 已隐藏会话的消息分页返回 404 `30013`。

---

## 7. 聊天 SSE

### 7.1 请求

已有会话：

```http
POST /api/v1/sessions/{id}/messages
Authorization: Bearer <jwt>
Content-Type: application/json
Accept: text/event-stream
```

首条消息（可无会话）：

```http
POST /api/v1/sessions/messages
Authorization: Bearer <jwt>
Content-Type: application/json
Accept: text/event-stream
```

请求体：

```json
{
  "client_message_id": "2f1c7c9e-9d1a-4b6e-8d0e-7a4c1f2b3a40",
  "content": "帮我做一套通勤风的图",
  "params": {
    "product_name": "秋季通勤衬衫",
    "style_text": "简洁白底",
    "width": 1000,
    "height": 1000,
    "template_id": null,
    "upload_ids": [101, 102]
  },
  "session_id": null
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `client_message_id` | string | 是 | UUID；同一会话内唯一；首条消息按用户维度去重 |
| `content` | string | 是 | 去除首尾空格后 1~2000 字符 |
| `params` | object | 是 | 当前参数快照；只用于本轮上下文，不落库 |
| `params.product_name` | string | 是 | 去除首尾空格后 1~60 字符 |
| `params.style_text` | string / null | 否 | 去除首尾空格后 1~50 字符；纯空格视为未填写 |
| `params.width` | int / null | 否 | 省略或 `null` 时默认 1000；正整数 |
| `params.height` | int / null | 否 | 省略或 `null` 时默认 1000；正整数 |
| `params.template_id` | int / null | 否 | 最小 demo 必须为 `null` |
| `params.upload_ids` | int[] | 否 | 0~5 个；必须属于当前用户且 `status='active'` |
| `session_id` | int / null | 否 | 仅首条消息接口使用；`null` 时后端事务内创建会话 |

响应头：

```http
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

### 7.2 事件类型

| event | data | 说明 |
| --- | --- | --- |
| `meta` | `{"message_id":1001,"session_id":12,"duplicate":false}` | 连接建立；`message_id` 为 Agent 回复消息 ID |
| `agent_status` | `{"agent_code":"planner","status":"started"}` | `started` / `finished` / `skipped` |
| `delta` | `{"content":"好的，"}` | 增量文本 |
| `done` | `{"message_id":1001,"token_in":120,"token_out":300,"requirement_summary":{...},"requirement_changed":false}` | 完成 |
| `error` | `{"code":30001,"message":"模型调用失败"}` | 错误 |
| `ping` | `{}` | 心跳，每 15 秒 |

`meta.duplicate` 为 demo 约定：`false` 表示正常新请求；`true` 表示命中已完成消息的重放，见 §7.6。

`done.requirement_changed` 为 3 号 PRD 要求的字段；2 号接口文档未列出，属于兼容新增。

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

- `ping` 可穿插在任意位置，前端忽略。
- `delta` 只出现在 `product_understanding started` 之后、`finished` 之前。
- `done` 或 `error` 之后服务端关闭连接。
- 最小 demo 固定调用两个 Agent；`skipped` 为真实模型预留，演示桩不发送。

### 7.4 需求摘要结构

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

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `product_name` | string | 商品名称 |
| `category` | string / null | 推断类目 |
| `selling_points` | string[] | 卖点列表 |
| `target_audience` | string / null | 目标人群 |
| `scenes` | string[] | 场景偏好 |
| `tone` | string / null | 文案语气 |
| `constraints` | string[] | 用户明确提出的限制 |

更新规则（demo 约定）：

- 商品理解 Agent 每轮返回完整摘要；未返回的顶层字段保留上一轮值。
- 数组字段整体替换，不做追加。
- `done` 返回写入数据库后的最新摘要。

### 7.5 `requirement_changed`

- 按 §2.4 计算，只出现在 `done` 事件。
- `false` 时不展示提示；`true` 时前端展示「需求已变化，建议重新生成示例图」。
- 不阻断聊天、不自动生成、不修改批次。
- 重复请求重放时按当前状态重新计算，不缓存历史结果。

### 7.6 幂等与重复请求

后端以 `(session_id, client_message_id)` 定位用户消息：

1. **已完成**：不调用模型，返回重放流：
   - `meta` 的 `duplicate=true`；
   - 一条 `delta` 携带已保存的完整回复正文；
   - `done` 携带已保存的 `message_id`、Token、摘要与当前 `requirement_changed`。
   - 前端收到 `duplicate=true` 时清空本地未完成的流式内容，再按重放内容渲染。
2. **处理中且未超时**：建立事件流前返回 HTTP 409 `30005`「消息正在处理中，请稍候」。
3. **已失败**：复用原 Agent 回复消息，重置为 `sending` 后重新调用模型；不新增用户消息，不改变 `client_message_id`。
4. **不存在**：正常写入用户消息并调用模型。

首条消息接口以 `(user_id, client_message_id)` 去重：重复请求返回同一 `session_id` 与同一回复，不创建第二个会话。

### 7.7 断线与重连

1. 连接中断且未收到 `done`：前端显示「连接中断，正在重试」，自动重试最多 2 次，复用同一 `client_message_id`。
2. 重试命中已完成消息时按 §7.6 重放，不重复计费、不产生重复消息。
3. 两次重试仍失败：消息标记为失败，显示「发送失败，点击重试」；手动重试仍使用同一 `client_message_id`。
4. 页面刷新：重新加载消息分页；超过 120 秒仍为 `sending` 的 Agent 消息按 §2.5 标记为 `failed`。
5. 前端主动中止请求：本地展示「已停止生成」；后端按断开处理，停止生成并释放资源；已落库的 `sending` 消息由超时规则收敛为 `failed`。

### 7.8 失败响应

参数、鉴权、归属错误在建立事件流前返回普通 JSON：

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 商品名称未填 | 400 | 10002 | 请先填写商品名称 |
| 商品名称超过 60 字符 | 400 | 10004 | 商品名称不能超过 60 个字符 |
| 消息为空 | 400 | 10002 | 请输入内容 |
| 消息超过 2000 字符 | 400 | 10004 | 消息不能超过 2000 个字符 |
| 风格超过 50 字符 | 400 | 10004 | 风格不能超过 50 个字符 |
| 宽高不是正整数 | 400 | 10003 | 参数格式错误 |
| `template_id` 非空 | 400 | 30016 | 模板/素材/尺寸不存在 |
| 上传图不属于当前用户或已删除 | 400 | 30006 | 上传文件不符合要求 |
| 会话不存在、已隐藏或不属于当前用户 | 404 | 30013 | 会话不存在 |
| 消息正在处理中 | 409 | 30005 | 消息正在处理中，请稍候 |
| 未登录或 token 失效 | 401 | 20002 / 20003 | 登录已过期，请重新登录 |
| 无 `user.workspace` | 403 | 20005 | 无权限 |

流建立后的错误通过 SSE `error` 事件返回，随后关闭连接：

| 场景 | code | message |
| --- | --- | --- |
| 模型调用失败 | 30001 | 回复失败，请重试 |
| 模型未配置且未启用演示桩 | 30002 | 模型未配置 |
| 内容审核不通过（保留） | 30007 | 内容未通过审核，请调整后重试 |

---

## 8. 错误码汇总

| code | HTTP | 本 demo 使用场景 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 10002 | 400 | 会话标题为空、消息为空、商品名称未填 |
| 10003 | 400 | 字段类型错误、宽高格式错误 |
| 10004 | 400 | 标题、商品名称、风格或消息超长 |
| 20002 | 401 | 登录过期 |
| 20003 | 401 | token 无效 |
| 20005 | 403 | 无 `user.workspace`、管理员调用用户端接口 |
| 30001 | 400 | 模型调用失败（SSE `error`） |
| 30002 | 400 | 模型未配置（SSE `error`，演示桩启用时不出现） |
| 30005 | 409 | 消息正在处理中 |
| 30006 | 400 | 上传图不符合要求 |
| 30007 | 400 | 内容审核不通过（保留，不触发） |
| 30013 | 404 | 会话不存在、已隐藏或不属于当前用户 |
| 30016 | 404 | 最小 demo 传了非空 `template_id` |
| 50001 | 500 | 系统内部错误 |
| 50002 | 500 | 数据库错误 |

---

## 9. 与 2 号 / 9 号 / 10 号文档的差异

| 项目 | 差异 | 处理 |
| --- | --- | --- |
| `done.requirement_changed` | 3 号 PRD 要求，2 号接口文档未列出 | 兼容新增；实现 3 号功能时必须返回 |
| `meta.duplicate` | 9 号未定义重复请求在 SSE 下的返回形式 | demo 约定；正式实现需与 9 号统一 |
| 重放流中的完整 `delta` | 9 号只写「直接返回已保存消息」 | demo 约定用一条 `delta` 重放，前端按 `duplicate` 重置 |
| `PATCH /sessions/{id}` 响应 | 9 号只定义请求 `{ title }` | demo 返回会话摘要；正式实现可统一为完整会话对象 |
| `DELETE /sessions/{id}` 响应 | 9 号只定义软删除语义 | demo 返回 `{ session_id, status }` |
| 已隐藏会话的错误码 | 9 号未区分「不存在」与「已隐藏」 | demo 统一 404 `30013`，避免泄露存在性 |
| 消息超时标记 | 9 号未定义超时阈值与执行方 | demo 在消息分页时惰性标记 120 秒以上的 `sending` 消息 |
| `agent_runs` 查询 | 3 号验收要求后台可按消息查看调用明细 | 最小 demo 只落库，不提供查询接口；由 8 号 PRD 实现 |
| 上下文二次压缩 | 3 号 §8.2 要求 Token 超限时先丢历史再压缩摘要 | demo 只做 10 轮截断，预留 `max_context_tokens` |

---

## 10. 待确认项

1. **重复消息的返回形式**：`meta.duplicate=true` + 完整 `delta` 重放是本 demo 约定，需与 9 号 SSE 契约统一。
2. **已隐藏会话的 PATCH / DELETE 语义**：demo 统一返回 404；若产品要求幂等删除，需改为 200 并返回 `hidden`。
3. **需求变化比对字段**：demo 只比对风格、卖点、尺寸；是否纳入目标人群、场景、文案语气需产品确认。
4. **已确认示例图描述**：10 号没有对应字段；demo 用商品名称、风格与需求摘要快照拼接，正式实现需确认来源。
5. **消息超时阈值**：120 秒为 demo 约定；正式实现需结合模型超时配置。
6. **系统通知写入方**：本文档只定义渲染；「示例图已生成」「任务失败」等通知由 2 号/4 号生成流程写入。
7. **消息中止状态**：数据库没有 `cancelled`；demo 只在前端本地展示「已停止生成」，正式实现需确认是否新增状态或接口。
8. **`requirement_summary` 的合并规则**：demo 约定未返回字段保留旧值、数组整体替换；正式实现需与商品理解 Agent 的输出协议统一。
