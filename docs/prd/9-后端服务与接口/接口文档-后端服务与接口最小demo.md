# 后端服务与接口最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `9-后端服务与接口prd.md` §2~§9；1~6 号 demo 接口文档（契约载体） |
| 覆盖范围 | 统一响应、错误码、JWT 鉴权、权限校验、分页、幂等与并发、文件上传、文件下载、SSE、OpenAPI |
| 文档状态 | 最小 demo 约定；不裁决 6 号 demo 的待确认项 |

> 本文档是 **跨切面契约文档**，不是业务接口清单。本 demo 不新增业务接口；登录、会话、上传、生成、历史、管理后台等接口的字段与业务语义，以 1~6 号 demo 的接口文档为准。本文只规定它们共同遵守的响应、错误码、鉴权、权限、分页、文件与 SSE 规则，并给出「哪条契约由哪个既有接口验证」的覆盖矩阵。

---

## 1. 通用约定

### 1.1 地址与编码

| 项目 | 约定 |
| --- | --- |
| Base URL | `/api/v1` |
| 本地联调 | 前端通过 Vite 开发代理把 `/api` 转发到后端，避免额外 CORS 配置 |
| 请求/响应格式 | JSON：`application/json; charset=utf-8`；文件：`multipart/form-data` / `application/octet-stream`；SSE：`text/event-stream` |
| 字段命名 | `snake_case` |
| ID | 整数，数据库 `BIGSERIAL` |
| 时间格式 | ISO 8601 带时区偏移，例如 `2026-10-31T10:00:00+08:00` |
| 时区 | 服务端统一 Asia/Shanghai；前端按浏览器本地时区展示 |
| 空值 | `null`，不省略字段 |
| 布尔值 | `true` / `false`，不使用 `0` / `1` 或字符串 |

### 1.2 统一响应

除文件流、ZIP 流与 SSE 外，所有接口返回：

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
| `message` | string | 面向用户的提示文案；成功固定 `ok` |
| `data` | object / array / null | 成功时的数据；业务错误时为 `null` 或包含补充信息 |

- 字段不省略：没有值写 `null`，不删除键。
- 分页列表数据放在 `data.items`，分页信息与 `items` 同级，见 §4。
- 文件流与 SSE 不使用该结构，改用 HTTP 状态、响应头与事件帧表达结果。

### 1.3 HTTP 状态码与业务码映射

| HTTP | 场景 | 业务码段 | 示例 |
| --- | --- | --- | --- |
| 200 | 成功 | `0` | 登录成功、列表查询成功 |
| 400 | 参数错误、格式错误、超出范围、上传不符合要求 | `1xxx` / `30006` / `30007` | `10002` 缺少必填参数 |
| 401 | 未登录、登录过期、token 无效或版本不符、用户名或密码错误 | `2xxx` | `20001` / `20002` / `20003` |
| 403 | 账号不可用、无权限、无权操作超管、不能操作自己 | `2xxx` | `20004` / `20005` / `20006` / `20007` |
| 404 | 资源不存在、归档不可用 | `3xxx` | `30004` / `30013` / `30014` |
| 409 | 状态冲突、重复、并发限制、角色组合非法 | `3xxx` | `30003` / `30005` / `30009` / `30010` / `30011` / `30015` |
| 500 | 系统内部、数据库、存储异常 | `5xxx` | `50001` / `50002` / `50003` |

> HTTP 状态码与业务码必须同时正确。前端以业务码做提示与分支，不以 HTTP 状态码单独判断。

### 1.4 参数校验与错误映射

| 场景 | HTTP | 业务码 | 说明 |
| --- | --- | --- | --- |
| 缺少必填字段 | 400 | `10002` | 指明字段名，例如「缺少必填参数：username」 |
| 字段格式错误 | 400 | `10003` | 类型、日期、UUID、枚举值不合法 |
| 字段超出范围 | 400 | `10004` | 长度、数值、分页大小等超出允许范围 |
| 其他参数错误 | 400 | `10001` | 无法归入上述三类的参数问题 |
| 未捕获异常 | 500 | `50001` | 不向客户端返回堆栈 |
| 数据库异常 | 500 | `50002` | 记录服务端日志 |
| 存储服务异常 | 500 | `50003` | 对象存储不可用、读写失败 |

- `message` 必须是可直接展示的中文文案，不拼接 SQL、堆栈或内部路径。
- 一次请求有多个参数错误时，返回第一个阻断性错误即可；`data` 可返回 `{"field": "..."}` 作为补充。

---

## 2. 鉴权与权限

### 2.1 鉴权头

```http
Authorization: Bearer <jwt>
```

- 除 `POST /api/v1/auth/login` 外，所有接口必须携带 token。
- token 存前端 `localStorage`，键名 `esimage_token`，沿用 1 号 demo。
- 不使用 refresh token；过期后重新登录。
- 服务端不维护黑名单；`POST /auth/logout` 只写审计日志，不使 token 立即失效。

### 2.2 每次请求的校验内容

| 顺序 | 校验项 | 失败响应 |
| --- | --- | --- |
| 1 | `Authorization` 头存在且为 `Bearer <jwt>` | 401 `20003` |
| 2 | JWT 签名有效 | 401 `20003` |
| 3 | `exp` 未过期 | 401 `20002` |
| 4 | 按 `sub` 找到用户，且 `status=active` | 用户不存在/禁用/删除 → 403 `20004` |
| 5 | token 中 `token_version` 等于用户当前 `token_version` | 401 `20003` |
| 6 | 当前用户拥有接口要求的权限码 | 403 `20005` |

> 本 demo 采用与 6 号 demo 接口文档一致的顺序：账号状态先于 `token_version`，以保证禁用/删除返回 `20004`。9 号 §2.2 的文字顺序为「`token_version` → 账号状态」，差异记录在 README §6.2，本 demo 不裁决。

### 2.3 权限判定

- 权限码来自 `permissions` 表；用户权限为其所有角色在 `role_permissions` 中的权限码并集。
- 角色包含 `super_admin` 时，直接拥有全部权限码，不读取 `role_permissions`。
- 每个非登录接口必须声明一个权限码，或明确标注「登录即可」。
- 缺失权限码返回 403 `20005`，`message` 统一为「无权限」，不返回所需权限码、角色或资源细节。
- 前端从 `GET /auth/me` 拿到的 `roles` / `permissions` 只用于渲染菜单与路由守卫；后端每次请求独立判定，不信任 token 中的权限数组。
- 最小 demo 不接 Redis：权限与账号状态每次请求直查 PostgreSQL，权限变更在下一次请求立即生效。

### 2.4 越权与数据隔离

- 只能访问当前用户自己的会话、消息、上传图、生成批次、图片；他人资源按业务接口文档返回 404 或 403，不得返回资源内容、名称、数量等可用于探测存在性的信息。
- 管理员看不到超管账号的会话与内容；接口层过滤，不依赖前端隐藏。
- 用户端接口与管理员接口使用不同权限码；`demo_admin` 不能调用用户端接口，`demo_user` 不能调用管理端接口。
- 未登录统一 401；已登录但无权限统一 403 `20005`。

---

## 3. 错误码总表

### 3.1 通用错误码

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

> `30012` 原用于「模板与图片角色不匹配」。模板改为整套模板后该错误废弃，编号保留不复用。
>
> 6 号 demo 使用的 `30017` / `30018` / `30019` 不在 9 号总表内，本 demo 不采用、不改写；原样记录在 README §6.1。

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

### 3.3 错误码使用边界

- 同一语义只用一个码；不在本 demo 新增错误码。
- 业务码与 HTTP 状态必须匹配 §1.3；禁止全部返回 200 + 业务码。
- `message` 由后端给出中文文案；前端不得用业务码自行编造与后端不一致的文案。
- 日志与审计记录错误码、请求 ID、用户 ID，不记录密码、token 与完整文件内容。

---

## 4. 分页

### 4.1 请求参数

| 参数 | 类型 | 默认 | 允许范围 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | int | 1 | ≥ 1 | 从 1 开始；小于 1 返回 400 `10001` |
| `page_size` | int | 20 | 1~100 | 大于 100 返回 400 `10004`；各业务接口可在 1~100 内再限定可选值 |

- 分页参数只接受整数；非整数返回 400 `10003`。
- 业务接口可增加 `keyword`、`status`、时间范围等筛选参数，但不得改变分页结构与默认值。
- 不接受通过 query 传入排序字段；排序由各业务接口固定，避免注入。

### 4.2 响应结构

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

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `items` | array | 当前页数据；无数据时为 `[]`，不为 `null` |
| `total` | int | 满足筛选条件的总条数 |
| `page` | int | 当前页码，回显请求值 |
| `page_size` | int | 当前页大小，回显实际生效值 |

### 4.3 边界行为

- 页码超过总页数：返回 200，`items=[]`，`total` 仍为真实总数。
- 从第 1 页开始；筛选条件变化后前端必须回到第 1 页。
- 排序必须包含唯一键兜底（如 `created_at DESC, id DESC`），保证翻页不重复、不遗漏。
- 一次请求最多返回 100 条；不允许通过 `page_size` 绕过上限。
- 分页查询不得返回已删除、已隐藏或不属于当前用户的数据；过滤在 SQL 层完成，不在应用层截断。

> 5 号 demo 对 `page < 1` 返回 400 `10001`；6 号用户列表将 `page < 1` 按 1 处理。本 demo 契约用例按 400 `10001` 编写，差异记录在 README §6.2，不裁决。

---

## 5. 幂等与并发

### 5.1 幂等键

| 场景 | 幂等键 | 作用域 | 重复请求行为 |
| --- | --- | --- | --- |
| 发送聊天消息 | `client_message_id` | 同一会话内唯一 | 返回已保存消息，不新增消息、不重复调用 Agent、不重复计 Token |
| 首条消息建会话 | `client_message_id` | 同一用户 + `client_message_id` | 返回同一会话与同一消息，不重复创建会话 |
| 创建生成批次 | `client_request_id` | 全局唯一 | 返回已有批次，不重复创建任务 |
| 创建导出任务 | 同一超管同时只允许 1 个 | 超管 | 返回已有任务（本 demo 不实现） |

### 5.2 并发限制

| 场景 | 限制 | 超出响应 |
| --- | --- | --- |
| 同一用户创建生成批次 | 同时只允许 1 个 `queued` / `running` 批次 | 409 `30003` |
| `sample_ready` 示例批次 | 等待用户操作，不计入并发 | 不阻断新批次 |
| 确认全套 | 被确认的 `sample_ready` 示例批次不参与并发校验 | 允许创建 `full` 批次 |
| 同一超管创建导出任务 | 同时只允许 1 个 | 409 `30008`（本 demo 不实现） |

### 5.3 幂等与并发的一致性要求

- 幂等判定与写入必须在同一事务或数据库唯一约束下完成，避免两个并发请求同时通过检查后各写一条。
- 重复请求返回的 `id`、`batch_id`、`session_id` 必须与首次请求一致；状态取当前最新状态，不返回过期快照。
- 幂等命中不重复写审计日志、不重复计 Token、不重复生成缩略图。
- 并发限制按数据库当前状态判断，不依赖进程内计数器；单实例 demo 也要保证多线程下正确。

---

## 6. 文件上传

### 6.1 接口

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/v1/uploads` | `user.generate` | `multipart/form-data`，字段名 `file` |
| GET | `/api/v1/uploads/{upload_id}` | `user.generate` | 读取元数据与缩略图地址 |
| DELETE | `/api/v1/uploads/{upload_id}` | `user.generate` | 软删除，从当前会话移除 |
| GET | `/api/v1/uploads/{upload_id}/content` | `user.generate` | 读取原件（2 号 demo 约定） |
| GET | `/api/v1/uploads/{upload_id}/thumbnail` | `user.generate` | 读取缩略图（2 号 demo 约定） |

### 6.2 校验矩阵

| 校验项 | 规则 | 失败响应 |
| --- | --- | --- |
| 字段 | 必须存在 `file` | 400 `10002` |
| 扩展名 | `.jpg` / `.jpeg` / `.png` / `.webp` | 400 `30006` |
| MIME | `image/jpeg` / `image/png` / `image/webp` | 400 `30006` |
| 文件头 | 与声明格式一致，不能只信扩展名与 MIME | 400 `30006` |
| 大小 | ≤ 10MB（`10 * 1024 * 1024` 字节） | 400 `30006` |
| 可解码 | 能被图像库完整解码，宽高 > 0 | 400 `30006` |
| 数量 | 当前用户「`session_id IS NULL` 且 `status=active`」的上传总数 ≤ 5 | 400 `30006` |
| 归属 | 只能读取/删除自己的上传图 | 不存在/已删除/不属于当前用户 → 404 `30014`；缺少权限码 → 403 `20005` |

- 单文件上传，不做批量接口；前端循环上传（9 号 §11 已确定）。
- 校验顺序：字段 → 扩展名/MIME → 大小 → 解码 → 数量；返回第一个失败项。
- 上传成功后的存储路径与文件名规则见 10 号 §6；不把原始文件名直接作为存储路径。

### 6.3 成功响应

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
    "size_bytes": 345678
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `upload_id` | int | 上传图 ID |
| `file_url` | string | 原件相对地址；需带 token 读取 |
| `thumbnail_url` | string | 缩略图相对地址；需带 token 读取 |
| `width` | int | 原图像素宽 |
| `height` | int | 原图像素高 |
| `size_bytes` | int | 原图字节数 |

> 9 号 §5.2 定义的最小字段为上述 6 个；2 号 demo 还返回 `mime_type`、`original_name`、`sort_order`、`status`、`created_at`。本 demo 不删减载体已有字段，字段全集以 2 号 demo 接口文档为准。

- 响应中的 URL 是相对路径，前端拼接 Base URL 后用 `fetch` + `Authorization` 读取，再转 `blob:` URL；不得把 token 写进 `<img src>` 或查询串。
- 上传图在首次用于生成时回填 `session_id`；绑定后释放未绑定名额。

### 6.4 生命周期

- 未绑定会话且 `active` 的上传图计入 5 张名额；绑定会话后不再计入。
- 删除为软删除：`status=deleted`，不再出现在会话与名额统计中；文件清理由孤儿上传任务负责（10 号 §7）。
- 上传图不属于当前用户、已删除、已绑定其他会话时，读取与删除按 6.2 的归属规则返回，不泄露存在性。

### 6.5 访问与预签名

- 原件始终经后端鉴权后流式返回，不直接暴露存储桶。
- 缩略图正式实现使用预签名 URL：签发前校验当前用户对图片的权限，有效期 ≤ 5 分钟；过期或签名不匹配返回 403 `20005` 或 404 `30014`。
- 最小 demo 沿用 2 号 demo 的带鉴权 `/thumbnail` 读取；预签名用本地 HMAC 适配器模拟，保留「有效期 + 权限校验」语义，不改变接口字段。
- 9 号与 2 号 demo 在缩略图访问方式上的差异记录在 README §6.2，本 demo 不裁决。

---

## 7. 文件下载

### 7.1 接口

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/v1/images/{image_id}/download` | `user.history` 或 `user.generate` | 下载单张 PNG |
| GET | `/api/v1/batches/{batch_id}/download` | `user.history` | 下载整组 ZIP + `manifest.csv` |
| GET | `/api/v1/images/{image_id}/content` | `user.history` 或 `user.generate` | 预览读取（2 号 demo 约定） |
| GET | `/api/v1/images/{image_id}/thumbnail` | `user.history` 或 `user.generate` | 缩略图读取（5 号 demo 约定） |

> 单张下载的权限码在 2 号 demo（结果区）为 `user.generate`，在 5 号 demo（历史页）为 `user.history`。本 demo 不把两者合并为一个新码：按调用来源使用对应权限码；差异记录在 README §6.2。

### 7.2 响应头与文件名

```http
HTTP/1.1 200 OK
Content-Type: image/png
Content-Disposition: attachment; filename*=UTF-8''%E7%A7%8B%E5%AD%A3%E9%80%9A%E5%8B%A4%E8%A1%AC%E8%A1%AB_%E4%B8%BB%E5%9B%BE_1_20261031100512.png
Cache-Control: no-store
```

- `Content-Disposition` 使用 RFC 5987 `filename*=UTF-8''...`，与 5 号 demo 一致；不额外约定 ASCII 回退字段。
- 文件名规则以 5 号 demo 为准：`{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`；ZIP 为 `{商品名称}_全套_{yyyyMMddHHmmss}.zip`。
- 时间戳取图片或批次的 `created_at`，按 Asia/Shanghai 计算。
- 文件流必须边读边写，不把整张图或整个 ZIP 一次性读入内存。
- 下载响应不使用统一 JSON 结构；失败时（参数/鉴权/不存在）返回统一 JSON 错误结构。

### 7.3 归档与降级

| 情况 | 读取位置 | 响应 |
| --- | --- | --- |
| `archived_at IS NULL` | `generated_images.file_path` | 200 文件流 |
| `archived_at` 非空 | `archive/{file_path}` | 200 文件流 |
| 归档对象暂不可用 | — | 404 `30014`，「文件归档中，请稍后重试」 |
| 图片不存在或不属于当前用户 | — | 404 `30014`，不泄露存在性 |
| 示例图确认前下载 | — | 409 `30005` |
| 批次状态不允许整组下载 | — | 409 `30005` |

- 归档不可用时不得返回残缺 ZIP；整个请求失败，并记录服务端错误日志。
- 最小 demo 不做归档任务；用「文件缺失 / 归档路径缺失」模拟 `30014` 降级。

### 7.4 权限与越权

- 下载前校验当前用户对图片/批次的归属与权限码；不通过返回 403 `20005` 或 404 `30014`，按业务接口文档执行。
- 管理员不能通过用户端下载接口读取普通用户作品；超管查看内容走下钻接口（7 号 PRD，本 demo 不实现）。
- 预签名 URL 只用于缩略图，不用于原件下载；签发前同样校验权限。

### 7.5 预签名 URL

| 项目 | 约定 |
| --- | --- |
| 适用对象 | 缩略图访问；导出下载链接（本 demo 不实现） |
| 有效期 | 缩略图 ≤ 5 分钟；导出链接 24 小时 |
| 签发前 | 必须校验当前用户对该图片的权限 |
| 失效后 | 返回 403 `20005` 或 404 `30014`，不返回文件 |
| 正式实现 | MinIO 预签名；demo 用本地 HMAC 适配器模拟 |
| 禁止 | 把存储桶地址、access key、secret key 暴露给前端 |

---

## 8. SSE 协议

### 8.1 请求

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

- 首条消息可调用 `POST /api/v1/sessions/messages` 并传 `session_id: null`；`meta` 事件返回新建的 `session_id`。
- `params` 由前端 `localStorage` 读取，只用于本轮上下文，不通过会话详情持久化。
- 聊天只调用规划 + 商品理解两个 Agent（轻链路）；生图走生成接口，不在聊天中触发。

### 8.2 响应头

```http
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

- 反向代理配置见 9 号 §7.4 与 11 号部署文档；本 demo 只要求后端输出上述响应头。
- 不得对 SSE 响应做 gzip 或缓冲；不得在 `done` 前主动关闭连接。

### 8.3 事件表

| event | data | 说明 |
| --- | --- | --- |
| `meta` | `{ "message_id": 1001, "session_id": 12 }` | 连接建立；`message_id` 为 Agent 回复消息 ID；首条消息时 `session_id` 为新建会话 ID |
| `agent_status` | `{ "agent_code": "planner", "status": "started" }` | `status` 取值 `started` / `finished` / `skipped` |
| `delta` | `{ "content": "好的，" }` | 增量文本；只拼接展示，不落库为多条消息 |
| `done` | `{ "message_id": 1001, "token_in": 120, "token_out": 300, "requirement_summary": {}, "requirement_changed": false }` | 完成；`requirement_summary` 为最新需求摘要 |
| `error` | `{ "code": 30001, "message": "模型调用失败" }` | 流建立后的错误；发送后关闭连接 |
| `ping` | `{}` | 心跳，每 15 秒一次 |

- `agent_status` 的顺序必须与真实执行顺序一致；跳过的 Agent 发 `skipped`，不能省略。
- `delta` 只出现在需要流式输出的 Agent 阶段；没有增量时可以不发。
- `done` 与 `error` 互斥，二者之后不得再发任何事件。
- 3 号 demo 的 `meta.duplicate`、`done.requirement_changed` 等增量字段沿用其接口文档；本 demo 不改变。

### 8.4 帧格式

每个事件由 `event:` 与 `data:` 两行组成，事件之间用空行分隔：

```text
event: meta
data: {"message_id":1001,"session_id":12}

event: agent_status
data: {"agent_code":"planner","status":"started"}

event: delta
data: {"content":"好的，"}

event: done
data: {"message_id":1001,"token_in":120,"token_out":300,"requirement_summary":{},"requirement_changed":false}

```

- `data` 必须是单行 JSON，不换行；中文不转义，按 UTF-8 输出。
- 不使用 `id:`、`retry:` 字段；断线重试由前端复用同一 `client_message_id` 完成。
- `ping` 事件同样使用 `event: ping` + `data: {}`。

### 8.5 心跳、关闭与断线

- 连接建立后每 15 秒发送一次 `ping`；心跳可穿插在任意事件之间，前端忽略。
- 收到 `done` 或 `error` 后，服务端主动关闭连接。
- 客户端断开时，服务端必须停止后续 Agent 调用、释放连接与任务资源；已完成的内容与 Agent 调用记录保留。
- 聊天消息与 Agent 调用记录必须在生成过程中落库，断线后可通过消息分页接口查询。
- 断线重试由前端发起，复用同一 `client_message_id`；后端按幂等规则返回已保存消息或继续处理，不重复落库。

### 8.6 错误

- 流建立前的错误（参数、鉴权、权限、会话不存在）使用普通 HTTP 状态 + 统一 JSON 错误结构，不建立 SSE。
- 流建立后的错误使用 `error` 事件，`data.code` 取 §3.1 的业务码，随后关闭连接。
- 不得把堆栈、内部路径、上游模型原始错误直接放进 `message`。

---

## 9. OpenAPI

### 9.1 访问路径

| 项目 | 约定 |
| --- | --- |
| Swagger UI | `/api/docs` |
| OpenAPI JSON | `/api/openapi.json` |
| 规范版本 | OpenAPI 3.0（FastAPI 自动生成） |
| 生产访问 | 默认仅内网；由 11 号部署文档配置，本 demo 本地始终可访问 |

### 9.2 文档必须包含

- Bearer 鉴权安全方案：`Authorization: Bearer <jwt>`。
- 统一响应结构 `{ code, message, data }`，以及成功、参数错误、鉴权失败、无权限、业务错误、系统错误的响应示例。
- 分页响应结构 `{ items, total, page, page_size }` 与 `page` / `page_size` 约束。
- §3.1 错误码表与含义。
- 每个接口的权限码（写在接口描述或 OpenAPI 扩展字段中）。
- 上传接口的 `multipart/form-data` 与字段名 `file`。
- 下载接口的二进制响应与 `Content-Disposition` 说明。
- SSE 接口的 `text/event-stream` 响应、事件表与心跳说明。

### 9.3 权限码标注

- 每个非登录接口必须能在文档中看到所需权限码，例如 `admin.accounts.view`、`user.generate`。
- 「登录即可」的接口明确标注「无需权限码，仅需登录」。
- 登录接口标注「无需鉴权」。
- 文档中的权限码必须与后端实际校验一致；契约回归套件至少抽查 3 个接口的标注与实际行为。

### 9.4 demo 约定

- 本地 demo 不限制 `/api/docs` 访问；生产仅内网的限制不在本 demo 实现。
- OpenAPI 文档不包含本 demo 未实现的业务接口，避免出现「文档有、接口无」。
- 契约回归套件读取 `/api/openapi.json`，检查统一响应、分页、鉴权方案与权限码标注是否存在。

---

## 10. 契约覆盖矩阵

| # | 契约 | 验证接口 | 载体 | 通过标准 | Ticket |
| --- | --- | --- | --- | --- | --- |
| 1 | 统一响应 | `POST /auth/login` | 1 号 demo 02 | 成功 `code=0`；失败 `code≠0`，`data=null` | 01 |
| 2 | 参数校验 | `POST /auth/login` | 1 号 demo 02 | 缺参 `10002`、格式错 `10003`、越界 `10004` | 01 |
| 3 | 分页结构 | `GET /sessions/{id}/messages` | 2 号 demo 04 | 返回 `items/total/page/page_size`；空页 `items=[]` | 01 |
| 4 | 分页边界 | `GET /sessions/{id}/messages` | 2 号 demo 04 | `page_size>100` → 400 `10004`；`page<1` → 400 `10001` | 01 |
| 5 | JWT 签名 | `GET /auth/me` | 1 号 demo 03 | 无 token / 坏签名 → 401 `20003` | 02 |
| 6 | JWT 过期 | `GET /auth/me` | 1 号 demo 03 | 过期 token → 401 `20002` | 02 |
| 7 | token 版本 | `GET /auth/me` | 1 号 demo 05 / 6 号 demo 05 | 旧 token → 401 `20003` | 02 |
| 8 | 账号状态 | `GET /auth/me` | 1 号 demo 05 | 禁用/删除 → 403 `20004` | 02 |
| 9 | 权限点 | `GET /admin/users` | 6 号 demo 01 | `demo_user` → 403 `20005` | 03 |
| 10 | 超管全量 | `GET /admin/users` | 6 号 demo 01 / 07 | `demo_super` → 200 | 03 |
| 11 | 数据隔离 | `GET /sessions/{id}/messages` | 2 号 demo 04 | 他人会话 → 404/403，无数据 | 03 |
| 12 | 上传校验 | `POST /uploads` | 2 号 demo 03 | 格式/大小/损坏/数量 → `30006` | 04 |
| 13 | 上传元数据 | `POST /uploads` | 2 号 demo 03 | 返回 `upload_id/file_url/thumbnail_url/width/height/size_bytes` | 04 |
| 14 | 下载头 | `GET /images/{id}/download` | 2 号 demo 07 / 5 号 demo 03 | RFC 5987 中文文件名；流式返回 | 05 |
| 15 | 归档降级 | `GET /images/{id}/download` | 5 号 demo 05 | 归档不可用 → 404 `30014` | 05 |
| 16 | SSE 事件 | `POST /sessions/{id}/messages` | 2 号 demo 04 / 3 号 demo 03 | `meta` → `agent_status` → `delta` → `done` | 06 |
| 17 | SSE 心跳 | 同上 | 2 号 demo 04 | 15 秒内收到 `ping`；响应头正确 | 06 |
| 18 | SSE 断线 | 同上 | 2 号 demo 04 | 断开后停止生成；消息可查 | 06 |
| 19 | 消息幂等 | `POST /sessions/messages` | 2 号 demo 04 | 重复 `client_message_id` 不新增消息 | 07 |
| 20 | 批次幂等 | `POST /generations/sample` | 2 号 demo 05 | 重复 `client_request_id` 返回同一 `batch_id` | 07 |
| 21 | 生成并发 | `POST /generations/sample` | 2 号 demo 05 | 第二个 `queued/running` → 409 `30003` | 07 |
| 22 | OpenAPI | `GET /api/openapi.json` | 08 | 含 Bearer、统一响应、分页、错误码、权限码 | 08 |

---

## 11. 本 demo 不覆盖

- 9 号 §5.1 配置读取、§5.3 会话创建/重命名/删除、§5.5 生成批次查询/确认/取消、§5.7 个人中心。
- 9 号 §6.1 概览与 Token 统计、§6.3 内容追溯、§6.4 聊天记录后台、§6.5 Agent 配置、§6.6 素材与模板管理、§6.7 导出。
- 9 号 §4.4 修改密码（`PUT /auth/password`）。
- 生产环境 OpenAPI 内网限制、Nginx SSE 配置、MinIO 预签名正式实现、归档任务、5 年保留。
- 接口级 QPS 限流、Webhook、GraphQL、第三方登录、API Key 管理。
- 6 号 demo 的 8 个待确认项的裁决。

---

## 12. 待确认项（只记录）

> 完整清单与上下文见 [`README.md`](./README.md) 第 6 章。本章只列与本文契约直接相关的项。

1. 鉴权判定顺序：9 号 §2.2 与 6 号 demo 的「账号状态先于 `token_version`」不一致。
2. 重复消息在 SSE 下的返回形式：9 号只写「返回已保存消息」；3 号 demo 用 `meta.duplicate` + `delta` 重放。
3. 图片预览接口：9 号未定义，2 号 demo 增加 `GET /images/{id}/content`。
4. 上传图缩略图访问方式：9 号 §8.3 预签名 URL vs 2 号 demo 鉴权流式。
5. 分页非法值处理：5 号 demo 返回 400，6 号用户列表将 `page<1` 按 1 处理。
6. 预签名 URL 的签名算法、时钟偏差容忍与失效后的错误码未定义。
7. 6 号 demo 使用的 `30017` / `30018` / `30019` 不在 9 号总表内。
8. 单张下载的权限码：2 号 demo 用 `user.generate`，5 号 demo 用 `user.history`。
