# 9-后端服务与接口：最小实现 demo

| 项目 | 内容 |
| --- | --- |
| 上游 PRD | [`9-后端服务与接口prd.md`](./9-后端服务与接口prd.md) |
| 目标 | 用最小范围固化「统一响应 → 错误码 → 鉴权 → 权限 → 分页 → 上传/下载 → SSE → OpenAPI」这套跨切面接口契约，并用 1~6 号 demo 的既有接口做端到端验证 |
| 任务形式 | 8 个垂直切片，按依赖顺序编号，存放在 `issues/` |
| 接口文档 | [`接口文档-后端服务与接口最小demo.md`](./接口文档-后端服务与接口最小demo.md) |

> 本目录只覆盖 9 号 PRD 中与「接口契约基线」直接相关的最小集合，不代表 9 号 PRD 的全部验收项。本 demo **不新增业务接口**：登录、会话、上传、生成、历史、管理后台等业务接口沿用 1~6 号 demo，本文只固化它们共同遵守的跨切面规则，并用这些接口验证契约。概览统计、Token 统计、内容追溯、聊天记录后台、模型配置、系统提示词、素材模板尺寸管理、数据导出均不在本 demo 内。

---

## 1. 最小 demo 范围

### 1.1 做

- 统一响应：除文件流与 SSE 外，所有接口返回 `{ code, message, data }`；成功 `code=0`，失败 `data` 为 `null` 或补充信息。
- 错误码与 HTTP 状态：`400 + 1xxx`、`401 + 2xxx`、`403 + 2xxx`、`404/409 + 3xxx`、`500 + 5xxx`；参数缺失、格式错误、超出范围分别映射 `10002` / `10003` / `10004`。
- 字段约定：`snake_case`、`null` 不省略、布尔值 `true` / `false`、时间 ISO 8601 带时区、ID 为整数。
- 分页约定：`page` / `page_size`、默认 20、最大 100、`{ items, total, page, page_size }`、稳定排序、空页处理。
- JWT 鉴权：`Authorization: Bearer <jwt>`；校验签名、过期时间、`token_version`、账号状态；区分 `401` 与 `403`；每次请求直查 PostgreSQL。
- 权限校验：按 `permissions` 表权限码判定；`super_admin` 恒有全部权限；缺失权限返回 `403 20005`；越权不泄露资源存在性。
- 上传契约：`multipart/form-data`、字段名 `file`、MIME/扩展名/大小/可解码/宽高校验、单用户未绑定上传 ≤5 张、`30006`、上传图元数据与访问方式。
- 下载契约：单张与整组流式下载、权限校验、RFC 5987 文件名、归档不可用返回 `30014`、缩略图预签名 URL 的有效期与权限要求。
- SSE 协议：事件 `meta` / `agent_status` / `delta` / `done` / `error` / `ping`、15 秒心跳、帧格式、响应头、`done` / `error` 后关闭、断线停止生成并落库可查。
- 幂等与并发：`client_message_id`、首条消息建会话去重、`client_request_id`、单用户 1 个 `queued` / `running` 生成批次、`sample_ready` 不占名额、`30003`。
- OpenAPI：`/api/docs` 与 `/api/openapi.json`，包含 Bearer 安全方案、统一响应与分页结构、错误码说明、每个接口的权限码。
- 契约回归套件：用 1~6 号 demo 的载体接口覆盖上述规则，失败时输出可定位的中文日志。

### 1.2 不做

- 不新增任何业务接口；不重写 1~6 号 demo 已经定义的业务字段与业务语义。
- 不做登录页、创作工作台、聊天页、生图结果区、历史作品页、个人中心、管理后台页面。
- 不实现生成管线、8 Agent 全链路、文字合成、内容审核、失败重试、取消任务等业务能力。
- 不接 Redis（权限与账号状态每次请求直查 PostgreSQL）。
- 不接 Alembic（沿用建表脚本 + 幂等种子脚本）。
- 不接 Celery / Redis 异步队列（沿用 2 号 demo 的 `BackgroundTasks`）。
- 不接 MinIO；预签名 URL 用本地签名适配器模拟，原件仍走鉴权流式。
- 不写 Nginx 配置、不做生产环境 `/api/docs` 内网限制（属 11 号部署文档）。
- 不做导出接口、导出任务并发限制、24 小时下载链接。
- 不做 5 年归档任务；只在文件缺失或归档不可用时返回 `30014`。
- 不做接口级 QPS 限流、Webhook、GraphQL、第三方登录、API Key 管理。
- 不裁决 6 号 demo README 第 6 章的 8 个待确认项；本 demo 只原样记录，见第 6 章。

### 1.3 相对 PRD 的最小化取舍

| PRD 要求 | 最小 demo 处理 | 原因 / 影响 |
| --- | --- | --- |
| 权限与账号状态走 Redis 缓存 ≤30 秒 | 每次请求直查 PostgreSQL | 不引入 Redis；行为更严格（即时生效），不影响契约验证 |
| 尺寸、模板、素材等配置缓存 60 秒 | 不做缓存，直接读数据库 | 契约层不验证缓存命中；正式实现按 9 号 §2.7 接入 |
| Alembic 迁移 | 建表脚本 + 幂等种子脚本 | 降低本地启动成本；正式实现再换 Alembic |
| Celery + Redis 异步任务 | 沿用 2 号 demo 的 `BackgroundTasks` + 数据库状态轮询 | 契约层不依赖具体队列；正式实现替换执行器，接口不变 |
| MinIO 单桶与预签名 URL | 存储适配层 + 本地目录；预签名用本地 HMAC 签名适配器模拟 | 保留「签发前校验权限、有效期 ≤5 分钟」的契约；正式实现切 MinIO |
| Nginx SSE 代理配置 | 只实现响应头与帧格式，不写 Nginx 配置 | 部署配置属 11 号文档；契约验证不依赖反向代理 |
| 生产环境 `/api/docs` 仅内网 | demo 本地始终可访问 | 访问控制属部署配置，不影响文档内容完整性 |
| 导出任务并发与 24 小时下载链接 | 不做 | 导出属 7 号 PRD 范围；本 demo 只保留 `30008` 错误码 |
| 5 年归档与 `archive/` 冷数据 | 不做归档任务；保留 `30014` 降级契约 | 归档任务属 10/11 号文档；下载契约可先用「文件缺失」模拟 |
| 接口级限流 | 不做 | 9 号 §1.3 已明确本期只做并发限制 |
| 业务接口字段定义 | 不重复定义，链接到 1~6 号 demo 接口文档 | 避免同一字段出现两个来源；9 号只做跨切面规则 |
| 6 号 demo 的 8 个待确认项 | 原样记录，不裁决 | 按用户确认：本 demo 只记录，留待正式评审统一 |

---

## 2. 前置与演示配置

### 2.1 前置

本目录假定以下 demo 已完成；本 demo 只在这些接口上补契约与回归，不改业务语义。

| 前置 | 提供的载体 |
| --- | --- |
| 1 号 demo 01~03 | 工程骨架、`POST /auth/login`、`GET /auth/me`、登录态与路由守卫 |
| 2 号 demo 03 | `POST /uploads`、`GET/DELETE /uploads/{upload_id}`、`/content` 与 `/thumbnail` 读取 |
| 2 号 demo 04 | `GET /sessions/{id}/messages`、`POST /sessions/messages`、`POST /sessions/{id}/messages`（SSE） |
| 2 号 demo 05 | `POST /generations/sample`、并发限制与 `client_request_id` |
| 2 号 demo 07 | `GET /images/{image_id}/download` |
| 3 号 demo 03 | SSE 事件顺序、`done.requirement_changed`、重复消息重放约定 |
| 5 号 demo 03~04 | `GET /images/{image_id}/download`、`GET /batches/{batch_id}/download`、归档降级 |
| 6 号 demo 01 / 07 | `GET /admin/users`、`super_admin` 全量权限、权限点种子 |

> 若某个载体尚未完成，本 demo 的对应切片保持阻塞，不用自造接口替代。

### 2.2 演示账号

沿用 1 号与 6 号 demo，不新增账号。

| 用户名 | 密码 | 角色 | 用途 |
| --- | --- | --- | --- |
| `demo_user` | `Demo1234` | `user` | 验证用户端权限、上传/下载/SSE 归属 |
| `demo_admin` | `Demo1234` | `admin` | 验证管理端权限与越权 |
| `demo_dual` | `Demo1234` | `user` + `admin` | 验证多角色权限并集 |
| `demo_super` | `Demo1234` | `super_admin` | 验证超管恒有全部权限（6 号 demo 01 新增） |

> 仅用于本地 demo，部署到任何共享环境前必须删除或改密。

### 2.3 契约验证方式

- Swagger UI：`/api/docs`，用于人工检查统一响应、分页、错误码、权限码标注与 SSE 说明。
- `curl`：用于演示 401 / 403 / 400 / 404 / 409 的 HTTP 状态与业务码。
- 契约回归套件：按 `issues/` 的验收项逐条断言，每个用例输出中文日志（请求、预期、实际、结论）。
- 不要求改前端；前端只需按既有 demo 的调用方式工作。

---

## 3. 接口总览

### 3.1 本 demo 不新增业务接口

本 demo 的所有验收都落在 1~6 号 demo 的既有接口上。9 号 PRD 第 4~6 章已定义、但本 demo 不作为载体的接口，见 §3.3。

### 3.2 契约载体接口

字段、业务状态与权限语义以「来源」列的接口文档为准；本 demo 只补跨切面规则。

| 方法 | 路径 | 验证的契约 | 来源 | Ticket |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | 无鉴权接口、统一响应、参数校验、`20001` | 1 号 demo 02 | 01 |
| GET | `/api/v1/auth/me` | JWT 签名、过期、`token_version`、账号状态、权限回显 | 1 号 demo 03 | 02 |
| GET | `/api/v1/sessions/{id}/messages` | 分页结构、页码范围、稳定排序、归属隔离 | 2 号 demo 04 | 01 / 03 |
| POST | `/api/v1/sessions/messages` | 首条消息建会话幂等、SSE 事件 | 2 号 demo 04 / 3 号 demo 03 | 06 / 07 |
| POST | `/api/v1/sessions/{id}/messages` | SSE 事件、心跳、断线、重复消息 | 2 号 demo 04 / 3 号 demo 03 | 06 / 07 |
| POST | `/api/v1/uploads` | multipart 校验、数量限制、`30006`、元数据响应 | 2 号 demo 03 | 04 |
| GET | `/api/v1/uploads/{upload_id}` | 上传图元数据、归属隔离 | 2 号 demo 03 | 04 |
| DELETE | `/api/v1/uploads/{upload_id}` | 软删除、归属隔离 | 2 号 demo 03 | 04 |
| GET | `/api/v1/uploads/{upload_id}/content` | 原件鉴权流式读取 | 2 号 demo 03 | 04 |
| GET | `/api/v1/uploads/{upload_id}/thumbnail` | 缩略图鉴权读取 / 预签名适配 | 2 号 demo 03 | 04 |
| POST | `/api/v1/generations/sample` | `client_request_id` 幂等、并发 `30003` | 2 号 demo 05 | 07 |
| GET | `/api/v1/images/{image_id}/download` | 流式下载、RFC 5987、越权、`30014` | 2 号 demo 07 / 5 号 demo 03 | 05 |
| GET | `/api/v1/batches/{batch_id}/download` | ZIP 流式下载、归档降级、`30014` | 5 号 demo 04 | 05 |
| GET | `/api/v1/admin/users` | 权限点校验、`20005`、分页、超管全量 | 6 号 demo 01 / 07 | 03 |

### 3.3 明确不提供的接口

本 demo 不实现、也不新增以下接口；它们属于其他 PRD 或部署文档：

`GET /api/v1/sizes`、`GET /api/v1/templates`、`GET /api/v1/materials`、`POST /api/v1/sessions`、`PATCH/DELETE /api/v1/sessions/{id}`、`GET /api/v1/generations/{batch_id}`、`POST /api/v1/generations/{batch_id}/confirm`、`POST /api/v1/generations/{batch_id}/cancel`、`GET /api/v1/generations/{batch_id}/images`、`POST /api/v1/images/{image_id}/regenerate`、`GET /api/v1/history`、`GET/PATCH /api/v1/profile`、`PUT /api/v1/auth/password`、`GET /api/v1/admin/dashboard/summary`、`GET /api/v1/admin/tokens/stats`、`GET /api/v1/admin/content/*`、`GET /api/v1/admin/chat/*`、`GET /api/v1/admin/agent-runs/{run_id}`、`/api/v1/admin/model-config`、`/api/v1/admin/prompts/*`、`/api/v1/admin/templates/*`、`/api/v1/admin/materials/*`、`/api/v1/admin/sizes/*`、`POST /api/v1/admin/export`、`GET /api/v1/admin/export/{job_id}`。

> 其中生成、下载、管理后台接口已在 2/4/5/6 号 demo 内实现；本 demo 只借用其中列出的载体，不重复实现其余接口。

---

## 4. 任务依赖

```text
1 号 demo 01~03（工程骨架、登录闭环、登录态与路由守卫）
        ↓
01 统一响应、错误码、参数校验与分页基线
        ↓
02 JWT 鉴权与账号状态校验
        ↓
03 权限点校验与越权语义
        ├──────────────┬──────────────┬──────────────┐
        ↓              ↓              ↓              ↓
04 文件上传契约   05 文件下载契约   06 SSE 协议基线   07 幂等与并发契约
        └──────────────┴──────────────┴──────────────┘
                              ↓
08 OpenAPI 文档与契约回归
```

> 04 额外依赖 2 号 demo 03；05 额外依赖 5 号 demo 03~04；06 额外依赖 2 号 demo 04 与 3 号 demo 03；07 额外依赖 2 号 demo 04~05。04~07 互不阻塞，可并行。
>
> 预重构：01 先把 1 号 demo 中分散的响应包装、异常处理、错误码映射与分页拼装抽取为共享层，抽取过程不改变既有接口的返回内容；02 再在该共享层上补鉴权与权限判定。这样后续 04~07 只需接入共享层，不重复实现。

| # | Ticket | 阻塞于 | 交付的可演示行为 |
| --- | --- | --- | --- |
| 01 | [统一响应、错误码、参数校验与分页基线](./issues/01-统一响应错误码与分页基线.md) | 1 号 demo 01~03 | 成功与失败都返回统一结构；缺参/格式/越界分别返回 `10002`/`10003`/`10004`；分页结构与页码行为一致 |
| 02 | [JWT 鉴权与账号状态校验](./issues/02-JWT鉴权与账号状态校验.md) | 01 | 无 token、过期、版本不符、禁用/删除分别返回 `20003`/`20002`/`20003`/`20004` |
| 03 | [权限点校验与越权语义](./issues/03-权限点校验与越权语义.md) | 02 | 普通用户访问管理接口返回 `403 20005`；超管全量通过；他人资源不泄露 |
| 04 | [文件上传契约](./issues/04-文件上传契约.md) | 03；2 号 demo 03 | 非法格式/超限/损坏/第 6 张返回 `30006`；合法上传返回完整元数据 |
| 05 | [文件下载契约](./issues/05-文件下载契约.md) | 03；5 号 demo 03~04 | 单张/ZIP 流式下载、中文文件名正确；归档不可用返回 `30014` |
| 06 | [SSE 协议基线](./issues/06-SSE协议基线.md) | 03；2 号 demo 04、3 号 demo 03 | 事件顺序、15 秒心跳、断开停止、断线后可查消息 |
| 07 | [幂等与并发契约](./issues/07-幂等与并发契约.md) | 03；2 号 demo 04~05 | 重复消息/重复批次不重复落库；并发第二次返回 `30003` |
| 08 | [OpenAPI 文档与契约回归](./issues/08-OpenAPI文档与契约回归.md) | 01~07 | Swagger 展示鉴权、统一响应、分页、错误码与权限码；契约回归全绿 |

---

## 5. 验收总口径（演示脚本）

最小 demo 完成时，至少能完整演示以下路径：

1. 打开 `/api/docs`，能看到 Bearer 鉴权、统一响应、分页结构、错误码说明，以及每个接口的权限码。
2. `POST /auth/login` 密码错误 → HTTP 401，响应体 `code=20001`，`data=null`。
3. 缺少必填参数 → HTTP 400，`code=10002`；参数格式错误 → `code=10003`；参数超出范围 → `code=10004`。
4. 不携带 token 请求 `/auth/me` → HTTP 401，`code=20003`；携带过期 token → HTTP 401，`code=20002`。
5. 重置密码或账号被禁用后，旧 token 请求 → 分别返回 401 `20003`、403 `20004`。
6. `demo_user` 请求 `/admin/users` → HTTP 403，`code=20005`；`demo_admin` 请求用户端接口 → 403 `20005`；`demo_super` 全部通过。
7. 用 `demo_user` 请求他人会话消息或上传图 → 404 / 403，响应体不含他人数据。
8. `GET /sessions/{id}/messages?page=1&page_size=20` → 返回 `{items,total,page,page_size}`；页码超出范围时 `items=[]` 且 `total` 正确；`page_size>100` → 400 `10004`。
9. 上传 JPG/PNG/WEBP 合法图 → 200，返回 `upload_id`、`file_url`、`thumbnail_url`、`width`、`height`、`size_bytes`。
10. 上传 GIF、超过 10MB、损坏图片、第 6 张未绑定图 → 400 `30006`，提示可读。
11. 下载单张 PNG / 整组 ZIP → `Content-Disposition` 含 RFC 5987 中文文件名；文件流可保存；无权限返回 403；图片缺失或归档不可用返回 404 `30014`。
12. 发起聊天 SSE → 依次收到 `meta`、`agent_status`、`delta`、`done`；15 秒无事件时收到 `ping`；服务端响应头含 `Cache-Control: no-cache` 与 `X-Accel-Buffering: no`。
13. SSE 过程中断开连接 → 生成停止、已产生内容与 Agent 调用记录可查询；收到 `error` 后连接关闭。
14. 用同一 `client_message_id` 重发消息 → 不新增消息；用同一 `client_request_id` 重发创建示例批次 → 返回同一 `batch_id`。
15. 已有 `queued` / `running` 批次时再次创建 → HTTP 409 `30003`；`sample_ready` 批次不阻塞新批次。
16. 运行契约回归套件 → 全部通过，日志逐条输出请求、预期、实际与结论。

### 5.1 9 号 §10 验收标准覆盖情况

| 9 号 §10 | 本 demo 覆盖 | 说明 |
| --- | --- | --- |
| 1. 除登录外所有接口校验 JWT | 是 | Ticket 02 |
| 2. 越权返回 403 且不泄露数据 | 是 | Ticket 03 |
| 3. 统一响应与分页结构一致 | 是 | Ticket 01 |
| 4. 错误码与文档一致 | 是 | Ticket 01 / 03 |
| 5. SSE 流式、断线可重连、重试不重复消息 | 是 | Ticket 06 / 07 |
| 6. 生成接口幂等 | 是 | Ticket 07（载体为创建示例批次） |
| 7. 上传校验格式、大小、数量 | 是 | Ticket 04 |
| 8. 下载校验权限、归档不可用明确报错 | 是 | Ticket 05 |
| 9. 管理员接口按权限点校验 | 部分 | Ticket 03；仅以 `GET /admin/users` 为载体，模型配置/日志/导出不在本 demo |
| 10. 管理员无法查看超管账号内容 | 部分 | Ticket 03；用户端接口已隔离，管理端下钻属 7 号 PRD |
| 11. 导出仅超管、异步可查 | 否 | 导出属 7 号 PRD；本 demo 只保留 `30008` |
| 12. OpenAPI 可访问且含鉴权、分页、错误码 | 是 | Ticket 08 |

---

## 6. 待确认项

> 按用户确认，本章**只记录，不裁决**。以下事项在正式实现前需要统一；本 demo 不替任何一方做决定。

### 6.1 6 号 demo README 第 6 章的 8 项

1. **用户/日志不存在与账号状态不允许的错误码**：9 号未定义，6 号 demo 暂用 `30017`（用户不存在）、`30018`（账号状态不允许该操作）、`30019`（日志不存在）。
2. **管理员分配超管的错误码**：9 号无专用码，6 号 demo 暂用 `20005`；是否新增专用码待定。
3. **角色最低权限校验的错误码**：6 号 demo 暂用 `30015`（权限点不可授予该角色），与「超管专属权限点」共用。
4. **审计动作码**：6 号 demo 使用 `account.create` / `account.update` / `account.reset_password` / `account.disable` / `account.enable` / `account.delete` / `account.restore` / `role.update`，需与 9 号统一。
5. **统计字段口径**：内容模块接入前固定返回 `0` 并带 `stats_available=false`；接入后是否保留该标志待定。
6. **超管权限存储方式**：6 号 demo 不向 `role_permissions` 写入 `super_admin` 行，按角色即时授予全部权限；种子是否要落行需确认。
7. **用户列表/详情/状态操作的响应结构**：9 号未定义，6 号 demo 约定账号操作返回账号对象（删除与重置密码返回 `null`）。
8. **`demo_super` 演示账号**：为演示账号权限管理与操作日志新增；正式环境由部署脚本创建首个超管，不走演示种子。

### 6.2 本 demo 发现的其他待统一项

9. **鉴权判定顺序**：9 号 §2.2 文字顺序为「签名 → 过期 → `token_version` → 账号状态」；6 号 demo 接口文档为「签名/过期 → 账号状态 → `token_version` → 权限」，以保证禁用/删除返回 `20004`。本 demo 的契约用例按 6 号 demo 的既有顺序编写，差异原样记录。
10. **重复消息在 SSE 下的返回形式**：9 号只写「重复请求返回已保存消息」；3 号 demo 约定 `meta.duplicate=true` + 一条完整 `delta` 重放 + `done`。本 demo 不改变该约定。
11. **图片预览接口**：9 号只定义下载，未定义「只预览、不允许下载」的读取接口；2 号 demo 增加 `GET /images/{image_id}/content`。
12. **上传图缩略图访问方式**：9 号 §8.3 规定缩略图走预签名 URL；2 号 demo 使用带鉴权的 `/thumbnail` 流式读取。本 demo 的下载契约按 9 号描述预签名规则，载体行为以 2 号 demo 为准。
13. **分页非法值的处理**：9 号未明确 `page < 1` 与超出允许值的处理；5 号 demo 返回 400 `10001`，6 号用户列表将 `page < 1` 按 1 处理。本 demo 的契约用例按 400 `10001` / `10004` 编写，差异原样记录。
14. **预签名 URL 的有效期与权限校验**：9 号要求「签发前必须校验权限、有效期不超过 5 分钟」；具体签名算法、时钟偏差容忍、失效后的错误码未定义。
15. **导出接口**：9 号定义 `POST /admin/export` 与 `GET /admin/export/{job_id}`，但导出属 7 号 PRD 范围，本 demo 不实现，`30008` 仅保留在错误码表。
16. **单张下载的权限码**：2 号 demo 结果区使用 `user.generate`，5 号 demo 历史页使用 `user.history`；本 demo 按调用来源分别使用，不合并为新权限码。
