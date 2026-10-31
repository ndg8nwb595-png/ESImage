# 登录最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `1-登录界面prd.md` §4/§5/§9；`9-后端服务与接口prd.md` §2/§3/§4；`10-数据模型与存储prd.md` §4.1/§4.17 |
| 覆盖范围 | `POST /api/v1/auth/login`、`GET /api/v1/auth/me`、`POST /api/v1/auth/logout` |
| 文档状态 | 最小 demo 约定；正式实现需与 9 号文档统一 |

> 本文档只描述最小 demo 需要落地的接口。未列出的接口（管理后台、生图、聊天、历史作品等）不在本次范围内。

---

## 1. 通用约定

### 1.1 地址与编码

| 项目 | 约定 |
| --- | --- |
| Base URL | `/api/v1` |
| 本地联调 | 前端通过 Vite 开发代理把 `/api` 转发到后端，避免额外 CORS 配置 |
| 请求/响应格式 | `application/json; charset=utf-8` |
| 字段命名 | `snake_case` |
| 时间格式 | ISO 8601 带时区偏移，例如 `2026-11-01T10:00:00+08:00` |

### 1.2 统一响应

所有接口返回统一结构：

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

### 1.3 HTTP 状态码

| HTTP | 场景 | 业务码段 |
| --- | --- | --- |
| 200 | 成功 | `0` |
| 400 | 参数错误 | `1xxx` |
| 401 | 未登录、token 失效、用户名或密码错误 | `2xxx` |
| 403 | 无权限、账号不可用 | `2xxx` |
| 500 | 服务端异常 | `5xxx` |

### 1.4 鉴权头

除登录接口外，所有接口必须携带：

```http
Authorization: Bearer <jwt>
```

---

## 2. JWT 规范

### 2.1 算法与密钥

| 项目 | 约定 |
| --- | --- |
| 算法 | HS256 |
| 实现 | PyJWT |
| 密钥 | 环境变量注入，不写入代码仓库 |
| 刷新 | 无 refresh token；过期后重新登录 |

### 2.2 载荷

```json
{
  "sub": "1",
  "exp": 1761962400,
  "iat": 1761876000,
  "token_version": 0,
  "roles": ["user"],
  "permissions": ["user.workspace", "user.history", "user.profile"]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sub` | string | 用户 ID；JWT 规范要求字符串 |
| `exp` | int | 过期时间，Unix 时间戳（UTC） |
| `iat` | int | 签发时间，Unix 时间戳（UTC） |
| `token_version` | int | 与 `users.token_version` 比对；不一致即失效 |
| `roles` | string[] | 角色码，仅用于前端渲染 |
| `permissions` | string[] | 权限码，仅用于前端渲染与路由守卫 |

### 2.3 有效期

| 登录时 `remember_me` | `exp` |
| --- | --- |
| `false`（默认） | `iat + 24 小时` |
| `true` | `iat + 7 天` |

### 2.4 服务端校验顺序

每次携带 token 的请求按以下顺序校验，任一失败即返回对应错误：

1. JWT 格式与签名。
2. `exp` 是否过期。
3. 用户是否存在。
4. `token_version` 是否与数据库一致。
5. `users.status` 是否为 `active`。
6. 接口所需权限（本次三个接口不额外校验权限）。

> `roles` / `permissions` 只用于前端显示；后端鉴权以数据库与权限表为准，不信任 token 内的角色声明。

---

## 3. 接口明细

### 3.1 登录

```http
POST /api/v1/auth/login
Content-Type: application/json
```

#### 请求字段

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `username` | string | 是 | 去除首尾空格后 4~20 位；仅字母、数字、下划线；区分大小写 |
| `password` | string | 是 | 8~32 位；不去除空格；不做复杂度要求 |
| `remember_me` | boolean | 否 | 默认 `false` |

请求示例：

```json
{
  "username": "demo_user",
  "password": "Demo1234",
  "remember_me": false
}
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "token": "<jwt>",
    "expires_at": "2026-11-01T10:00:00+08:00",
    "user": {
      "id": 1,
      "username": "demo_user",
      "display_name": "演示用户",
      "avatar_url": null,
      "roles": ["user"],
      "permissions": ["user.workspace", "user.history", "user.profile"]
    }
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `token` | string | JWT |
| `expires_at` | string | token 过期时间；与 JWT `exp` 表示同一时刻 |
| `user.id` | int | 用户 ID |
| `user.username` | string | 登录名 |
| `user.display_name` | string | 显示名 |
| `user.avatar_url` | string / null | 最小 demo 固定为 `null` |
| `user.roles` | string[] | 角色码 |
| `user.permissions` | string[] | 权限码 |

#### 失败响应

用户名或密码错误、账号禁用、账号删除均返回同一结果：

HTTP 401：

```json
{
  "code": 20001,
  "message": "用户名或密码错误",
  "data": null
}
```

参数错误示例：

HTTP 400：

```json
{
  "code": 10003,
  "message": "用户名需为 4~20 位字母、数字或下划线",
  "data": null
}
```

#### 处理流程

1. 去除 `username` 首尾空格；`password` 原样处理。
2. 校验字段格式；失败返回 `10002` / `10003`。
3. 按 `username` 精确查询用户（包含已删除账号）。
4. 用户不存在、密码不匹配、`status != active`，统一返回 `20001`。
5. 校验成功：签发 JWT、更新 `last_login_at`、写登录成功审计。
6. 校验失败：写登录失败审计，`user_id` 可为 `null`，`username_snapshot` 记录输入的用户名。

> 登录失败不得提示账号是否存在；审计与日志不得记录密码。

---

### 3.2 当前用户

```http
GET /api/v1/auth/me
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "user": {
      "id": 1,
      "username": "demo_user",
      "display_name": "演示用户",
      "avatar_url": null
    },
    "roles": ["user"],
    "permissions": ["user.workspace", "user.history", "user.profile"]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user` | object | 当前用户基础信息 |
| `roles` | string[] | 角色码 |
| `permissions` | string[] | 权限码；前端用于渲染导航与路由守卫 |

> 该结构遵循 9 号文档 `{ user, roles, permissions }`；登录响应中的 `user` 则按 1 号文档内嵌 `roles` / `permissions`。前端需把两者归一化为同一份全局用户状态。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 未携带 token | 401 | 20003 | token 无效 |
| token 格式错误或签名错误 | 401 | 20003 | token 无效 |
| token 已过期 | 401 | 20002 | 登录已过期 |
| `token_version` 不一致 | 401 | 20003 | token 无效 |
| 账号禁用或删除 | 403 | 20004 | 账号不可用 |

---

### 3.3 退出登录

```http
POST /api/v1/auth/logout
Authorization: Bearer <jwt>
Content-Type: application/json
```

#### 请求体

无。

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

- 服务端只写退出审计，不维护 token 黑名单。
- token 无效或已过期时返回 401；前端无论接口结果如何都必须清除本地 token。
- 退出后旧 token 在 `exp` 到期前仍可能通过服务端校验，这是本期无状态 JWT 的已知限制；强制下线由管理员禁用账号实现。

---

## 4. 错误码（最小集）

| code | HTTP | 含义 | 本次是否使用 |
| --- | --- | --- | --- |
| 0 | 200 | 成功 | 是 |
| 10001 | 400 | 参数错误 | 是 |
| 10002 | 400 | 缺少必填参数 | 是 |
| 10003 | 400 | 参数格式错误 | 是 |
| 10004 | 400 | 参数超出范围 | 是 |
| 20001 | 401 | 用户名或密码错误 | 是 |
| 20002 | 401 | 登录已过期 | 是 |
| 20003 | 401 | token 无效 | 是 |
| 20004 | 403 | 账号不可用（禁用/删除） | 是 |
| 20005 | 403 | 无权限 | 前端路由守卫使用；本次三个接口不返回 |
| 50001 | 500 | 系统内部错误 | 是 |
| 50002 | 500 | 数据库错误 | 是 |

错误响应统一为：

```json
{
  "code": 20001,
  "message": "用户名或密码错误",
  "data": null
}
```

---

## 5. 前端处理约定

### 5.1 请求注入

- 所有请求从 `localStorage` 读取 `esimage_token`，非空时注入 `Authorization: Bearer <token>`。
- token 不写入 URL、日志、错误上报。

### 5.2 状态码处理

| 场景 | 前端行为 |
| --- | --- |
| 401（`20001`） | 登录页表单下方显示「用户名或密码错误」 |
| 401（`20002` / `20003`） | 清除 token 与全局用户状态，跳 `/login?redirect=当前路径` |
| 403（`20004`） | 清除 token 与全局用户状态，跳 `/login`（账号不可用特判） |
| 403（`20005`） | 跳 `/403`，不清除 token |
| 5xx | 显示「系统繁忙，请稍后重试」，不自动登出 |
| 网络异常 | 显示「网络异常，请稍后重试」 |

### 5.3 回跳安全

- `redirect` 只接受以单个 `/` 开头、且不以 `//` 开头的站内路径。
- 含协议、域名、`\`、`..` 或无法解析为站内路径的值一律忽略。
- 登录成功后优先回跳 `redirect`；无合法 `redirect` 时按角色进入默认页。

### 5.4 默认落地页

| 角色组合 | 默认落地页 |
| --- | --- |
| 仅 `user` | `/workspace` |
| 仅 `admin` / 仅 `super_admin` | `/admin/dashboard` |
| `user` + `admin` | `/workspace` |
| `user` + `super_admin` | `/workspace` |

---

## 6. 审计日志约定

### 6.1 记录时机

| 场景 | `action` | `result` |
| --- | --- | --- |
| 登录成功 | `auth.login` | `success` |
| 登录失败 | `auth.login` | `failed` |
| 退出登录 | `auth.logout` | `success` |

> `auth.login` / `auth.logout` 是最小 demo 的动作码约定；正式实现需与 8 号文档的操作日志动作码统一。

### 6.2 字段映射

| `audit_logs` 字段 | 登录成功 | 登录失败 | 退出 |
| --- | --- | --- | --- |
| `user_id` | 用户 ID | 能定位到时填用户 ID，否则 `null` | 用户 ID |
| `username_snapshot` | 输入用户名 | 输入用户名 | 当前用户名 |
| `action` | `auth.login` | `auth.login` | `auth.logout` |
| `result` | `success` | `failed` | `success` |
| `ip` | 请求 IP | 请求 IP | 请求 IP |
| `user_agent` | 请求头 | 请求头 | 请求头 |
| `detail` | `null` | `{"reason":"bad_credentials"}` | `null` |

### 6.3 安全约束

- 审计日志不得包含密码、JWT、API Key。
- 登录失败消息不得区分账号不存在、密码错误、账号禁用、账号删除。

---

## 7. 最小 demo 未实现项与已知限制

| 项目 | 最小 demo 处理 | 影响 |
| --- | --- | --- |
| Redis 权限/状态缓存 | 每次请求直接查 PostgreSQL | 行为即时生效；与 PRD「≤30 秒缓存」不冲突 |
| Alembic 迁移 | 建表脚本 + 幂等种子脚本 | 不提供版本化迁移 |
| refresh token | 不做 | token 过期必须重新登录 |
| 登录失败锁定、图形验证码 | 不做 | 与 1 号 PRD 的已知风险一致 |
| 管理后台账号 CRUD | 不做 | 用 SQL 修改账号状态演示失效 |
| 超管账号 | 不预置 | 超管落地页与管理员相同 |
| `avatar_url` | 固定 `null` | 不展示头像 |
| `/history`、`/profile`、`/admin/*` | 占位页 | 只验证路由守卫与角色分流 |
| HTTPS | 本地 HTTP | 部署时按 1 号/11 号文档处理 |

---

## 8. 待确认项

1. **账号不可用的响应码**：1 号 PRD §5.4 规定 403 不跳登录页，§10.10 又要求禁用后前端回登录页；本文档采用 `403 + 20004`，前端对 `20004` 特判回登录。若希望统一为 `401`，只需调整错误码映射。
2. **审计动作码**：`auth.login` / `auth.logout` 为最小 demo 约定，需与 8 号文档的统一动作码表对齐。
3. **响应结构差异**：登录响应的 `user` 内嵌 `roles` / `permissions`（1 号），`/auth/me` 顶层返回 `roles` / `permissions`（9 号）；前端需归一化。若要统一，需修改 PRD。
4. **`remember_me` 是否必传**：1 号 PRD 的请求示例包含该字段，规则表写默认 `false`；本文档按可选字段处理。
