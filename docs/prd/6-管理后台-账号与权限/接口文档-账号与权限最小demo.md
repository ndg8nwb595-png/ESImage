# 账号与权限最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `6-管理后台-账号与权限prd.md` §3~§15；`9-后端服务与接口prd.md` §2/§3/§4/§6.2/§6.7；`10-数据模型与存储prd.md` §4.1~§4.5、§4.17 |
| 覆盖范围 | 管理后台「账号与权限」与「操作日志」最小 demo 的用户列表、新建、详情、编辑、重置密码、禁用/启用、软删除/恢复、角色权限、日志查询接口 |
| 文档状态 | 最小 demo 约定；正式实现需与 9 号文档统一 |

> 本文档只描述最小 demo 需要落地的接口。概览、Token 统计、内容追溯、聊天记录、模型配置、系统提示词、素材模板、数据导出等接口不在本次范围内，见第 17 章。

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
| 400 | 参数错误、格式错误、超出范围 | `1xxx` |
| 401 | 未登录、登录过期、token 无效或版本不符 | `2xxx` |
| 403 | 无权限、账号禁用/删除、无权操作超管、不能操作自己 | `2xxx` |
| 404 | 用户、日志不存在 | `30017` / `30019` |
| 409 | 角色组合不合法、用户名重复、最后超管、状态不允许、权限点不可授予 | `30009` / `30010` / `30011` / `30018` / `30015` |
| 500 | 服务端异常 | `5xxx` |

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

> 判定顺序保证：禁用/删除账号返回 `20004`（状态先于版本校验）；重置密码后账号仍为 `active`，旧 token 因版本不符返回 `20003`。
>
> 最小 demo 不接 Redis，每次请求直查 PostgreSQL，权限变更在下一次请求立即生效。

### 1.5 分页

请求：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 1 | 从 1 开始；小于 1 按 1 处理 |
| `page_size` | int | 20 | 用户列表仅接受 20/50/100；日志列表最大 100 |

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

---

## 2. 最小 demo 约定

### 2.1 运行形态

| 项目 | demo 处理 | 正式实现 |
| --- | --- | --- |
| 权限缓存 | 每次请求直查 PostgreSQL | Redis 缓存 ≤30 秒、变更主动失效（9 号 §2.7） |
| 数据库迁移 | 建表脚本 + 幂等种子脚本 | Alembic（10 号 §10） |
| 角色权限并发 | last-write-wins，不检测冲突 | 与 PRD 6 §12.3 一致 |
| 用户统计 | 内容表未建，返回 `0` 且 `stats_available=false` | 2/4 号模块接入后聚合真实数据 |

### 2.2 种子与演示账号

种子脚本必须幂等，重复执行不覆盖已有密码与已修改的权限配置。

| 用户名 | 密码 | 角色 | 说明 |
| --- | --- | --- | --- |
| `demo_super` | `Demo1234` | `super_admin` | 本 demo 新增；用于角色管理与操作日志 |
| `demo_admin` | `Demo1234` | `admin` | 复用 1 号 demo |
| `demo_user` | `Demo1234` | `user` | 复用 1 号 demo |
| `demo_dual` | `Demo1234` | `user` + `admin` | 复用 1 号 demo |

角色种子：

| `code` | `name` | 可编辑权限 |
| --- | --- | --- |
| `user` | 普通用户 | 是 |
| `admin` | 管理员 | 是 |
| `super_admin` | 超管 | 否（恒为全部权限） |

### 2.3 权限点目录

| 权限码 | 名称 | 类型 | 分组 | 超管专属 | 默认角色 |
| --- | --- | --- | --- | --- | --- |
| `user.workspace` | 创作台 | menu | 用户端 | 否 | 普通用户 |
| `user.generate` | 发起生成 | action | 用户端 | 否 | 普通用户 |
| `user.history` | 历史作品 | menu | 用户端 | 否 | 普通用户 |
| `user.profile` | 个人中心 | menu | 用户端 | 否 | 普通用户 |
| `admin.dashboard.view` | 概览 | menu | 管理后台 | 否 | 管理员 |
| `admin.accounts.view` | 用户管理 | menu | 管理后台 | 否 | 管理员 |
| `admin.accounts.create` | 新建账号 | action | 管理后台 | 否 | 管理员 |
| `admin.accounts.edit` | 编辑账号 | action | 管理后台 | 否 | 管理员 |
| `admin.accounts.reset_password` | 重置密码 | action | 管理后台 | 否 | 管理员 |
| `admin.accounts.disable` | 禁用/启用 | action | 管理后台 | 否 | 管理员 |
| `admin.accounts.delete` | 删除/恢复 | action | 管理后台 | 否 | 管理员 |
| `admin.roles.view` | 角色管理 | menu | 管理后台 | 是 | 超管 |
| `admin.roles.edit` | 编辑权限点 | action | 管理后台 | 是 | 超管 |
| `admin.content.view` | 内容追溯 | menu | 管理后台 | 否 | 管理员 |
| `admin.assets.view` | 素材与模板 | menu | 管理后台 | 否 | 管理员 |
| `admin.assets.edit` | 编辑素材/模板/尺寸 | action | 管理后台 | 否 | 管理员 |
| `admin.prompts.view` | 系统提示词 | menu | 管理后台 | 否 | 管理员 |
| `admin.prompts.edit` | 编辑系统提示词 | action | 管理后台 | 否 | 管理员 |
| `admin.model.view` | 模型配置 | menu | 管理后台 | 是 | 超管 |
| `admin.model.edit` | 编辑模型配置 | action | 管理后台 | 是 | 超管 |
| `admin.tokens.view` | Token 统计 | menu | 管理后台 | 否 | 管理员 |
| `admin.audit.view` | 操作日志 | menu | 管理后台 | 是 | 超管 |
| `admin.export` | 数据导出 | action | 管理后台 | 是 | 超管 |

默认权限：

- `user`：`user.workspace`、`user.generate`、`user.history`、`user.profile`（4 个）。
- `admin`：`admin.dashboard.view`、`admin.accounts.view/create/edit/reset_password/disable/delete`、`admin.content.view`、`admin.assets.view/edit`、`admin.prompts.view/edit`、`admin.tokens.view`（13 个）。
- `super_admin`：不写入 `role_permissions`，按角色即时授予全部 23 个权限码。

### 2.4 统计字段

| 字段 | 口径 | demo 取值 |
| --- | --- | --- |
| `image_count` | 该用户 `image_type=final` 且 `success` 的图片数 | `0` |
| `session_count` | 该用户未删除与已隐藏的会话总数 | `0` |
| `token_total` | 该用户所有 Agent 调用的输入 + 输出 Token | `0` |
| `failed_task_count` | 该用户失败任务数 | `0` |
| `stats_available` | 统计是否来自真实内容表 | `false` |

> 列表与详情共用同一 `stats` 结构；列表展示前三项，详情展示四项。内容模块接入后把 `stats_available` 置为 `true` 并返回真实值，接口结构不变。

### 2.5 操作日志

- 日志写入与业务操作同事务；业务失败时记录 `result=failed` 与失败原因（`detail.reason`）。
- 敏感值（密码、密码哈希、API Key）不入库。
- demo 动作码：

| 动作 | 对象类型 | 对象标识 | 说明 |
| --- | --- | --- | --- |
| `auth.login` | account | 用户名 | 登录成功（1 号 demo 已有） |
| `auth.login_failed` | account | 用户名 | 登录失败（1 号 demo 已有） |
| `auth.logout` | account | 用户名 | 退出登录（1 号 demo 已有） |
| `account.create` | account | 用户名 | 新建账号 |
| `account.update` | account | 用户名 | 编辑显示名/角色/状态 |
| `account.reset_password` | account | 用户名 | 重置密码 |
| `account.disable` | account | 用户名 | 禁用 |
| `account.enable` | account | 用户名 | 启用 |
| `account.delete` | account | 用户名 | 软删除 |
| `account.restore` | account | 用户名 | 恢复 |
| `role.update` | role | 角色 code | 保存角色权限点 |

---

## 3. 接口清单

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/v1/admin/users` | `admin.accounts.view` | 用户列表 |
| POST | `/api/v1/admin/users` | `admin.accounts.create` | 新建账号 |
| GET | `/api/v1/admin/users/{id}` | `admin.accounts.view` | 用户详情 |
| PATCH | `/api/v1/admin/users/{id}` | `admin.accounts.edit` | 编辑显示名、角色、状态 |
| POST | `/api/v1/admin/users/{id}/reset-password` | `admin.accounts.reset_password` | 重置密码 |
| POST | `/api/v1/admin/users/{id}/disable` | `admin.accounts.disable` | 禁用 |
| POST | `/api/v1/admin/users/{id}/enable` | `admin.accounts.disable` | 启用 |
| DELETE | `/api/v1/admin/users/{id}` | `admin.accounts.delete` | 软删除 |
| POST | `/api/v1/admin/users/{id}/restore` | `admin.accounts.delete` | 恢复 |
| GET | `/api/v1/admin/roles` | `admin.roles.view` | 三个角色与权限点 |
| PUT | `/api/v1/admin/roles/{code}/permissions` | `admin.roles.edit` | 保存角色权限点 |
| GET | `/api/v1/admin/audit-logs` | `admin.audit.view` | 操作日志列表 |
| GET | `/api/v1/admin/audit-logs/{id}` | `admin.audit.view` | 操作日志详情 |

> `super_admin` 天然拥有以上全部权限；权限码校验仍按 §1.4 执行。

---

## 4. 用户列表

```http
GET /api/v1/admin/users?keyword=张&role=admin&status=all&created_from=2026-10-01&created_to=2026-10-31&page=1&page_size=20
Authorization: Bearer <jwt>
```

### 4.1 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `keyword` | string | 否 | — | 去除首尾空格后 ≤50 字符；对用户名或显示名模糊匹配；空串视为未填 |
| `role` | string | 否 | — | `user` / `admin` / `super_admin`；按角色过滤，不传为全部 |
| `status` | string | 否 | `all` | `active` / `disabled` / `deleted` / `all` |
| `created_from` | string | 否 | — | `YYYY-MM-DD`，含当天 00:00:00 |
| `created_to` | string | 否 | — | `YYYY-MM-DD`，含当天 23:59:59.999 |
| `page` | int | 否 | 1 | 从 1 开始 |
| `page_size` | int | 否 | 20 | 仅接受 20/50/100 |

- 默认排序：`created_at DESC, id DESC`。
- 已删除账号只有在 `status=all` 或 `status=deleted` 时出现。
- `created_from` 晚于 `created_to` 返回 400 `10003`。

### 4.2 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "user_id": 7,
        "username": "zhangsan",
        "display_name": "张三",
        "roles": [
          { "code": "admin", "name": "管理员" },
          { "code": "user", "name": "普通用户" }
        ],
        "status": "active",
        "stats": {
          "image_count": 0,
          "session_count": 0,
          "token_total": 0,
          "failed_task_count": 0,
          "stats_available": false
        },
        "last_login_at": "2026-10-31T09:30:00+08:00",
        "created_at": "2026-10-20T14:00:00+08:00",
        "updated_at": "2026-10-31T09:30:00+08:00",
        "deleted_at": null
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
| `user_id` | int | 对应 `users.id` |
| `username` | string | 登录名，唯一，不可修改 |
| `display_name` | string | 显示名 |
| `roles` | array | 1~2 个角色，元素为 `{code,name}` |
| `status` | string | `active` / `disabled` / `deleted` |
| `stats` | object | 统计，见 §2.4 |
| `last_login_at` | string / null | 最后登录；从未登录为 `null`，前端显示「—」 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 最后修改时间 |
| `deleted_at` | string / null | 软删除时间 |

### 4.3 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 关键词超过 50 字符 | 400 | 10004 | 关键词不能超过 50 个字符 |
| 角色取值非法 | 400 | 10003 | 角色参数不合法 |
| 状态取值非法 | 400 | 10003 | 状态参数不合法 |
| 日期格式错误或起止颠倒 | 400 | 10003 | 创建时间范围不合法 |
| `page_size` 非 20/50/100 | 400 | 10003 | 每页条数不合法 |
| 无 `admin.accounts.view` | 403 | 20005 | 无权限 |

---

## 5. 新建账号

```http
POST /api/v1/admin/users
Authorization: Bearer <jwt>
Content-Type: application/json
```

### 5.1 请求体

```json
{
  "username": "zhangsan",
  "display_name": "张三",
  "password": "Passw0rd!",
  "roles": ["user"],
  "status": "active"
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `username` | string | 是 | 去除首尾空格后 4~20 位 `[A-Za-z0-9_]`；全局唯一（含已删除） |
| `display_name` | string | 是 | 去除首尾空格后 1~30 个字符 |
| `password` | string | 是 | 8~32 位；不做复杂度要求；不可为纯空格 |
| `roles` | string[] | 是 | 1~2 个；只允许五种组合（见下） |
| `status` | string | 否 | `active` / `disabled`，默认 `active` |

允许的角色组合：

1. `["user"]`
2. `["admin"]`
3. `["super_admin"]`
4. `["admin", "user"]`
5. `["super_admin", "user"]`

禁止：`["super_admin", "admin"]`、超过 2 个角色、空数组。

操作者限制：

- `admin` 只能分配 `user`、`admin` 及其组合，不能分配 `super_admin`。
- `super_admin` 可分配全部允许组合。

### 5.2 成功响应

HTTP 200，返回新建账号对象（结构同 §4.2 `items[0]`）：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "user_id": 9,
    "username": "zhangsan",
    "display_name": "张三",
    "roles": [{ "code": "user", "name": "普通用户" }],
    "status": "active",
    "stats": {
      "image_count": 0,
      "session_count": 0,
      "token_total": 0,
      "failed_task_count": 0,
      "stats_available": false
    },
    "last_login_at": null,
    "created_at": "2026-10-31T10:00:00+08:00",
    "updated_at": "2026-10-31T10:00:00+08:00",
    "deleted_at": null
  }
}
```

- 响应不含密码、密码哈希。
- 密码以 bcrypt cost=12 写入 `password_hash`。

### 5.3 处理流程

1. 校验 token、权限、请求体格式。
2. 校验用户名格式与唯一性（含 `status=deleted`）。
3. 校验角色组合与操作者分配权限。
4. 在事务内写入 `users`、`user_roles`，写入操作日志 `account.create`。
5. 提交事务，返回账号对象。

### 5.4 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 缺少用户名/显示名/密码，或缺少 `roles` 字段 | 400 | 10002 | 请填写完整账号信息 |
| 用户名格式不合法 | 400 | 10003 | 用户名需为 4~20 位字母、数字或下划线 |
| 显示名超过 30 字符 | 400 | 10004 | 显示名不能超过 30 个字符 |
| 密码不在 8~32 位 | 400 | 10004 | 密码长度需为 8~32 位 |
| 状态非 `active`/`disabled` | 400 | 10003 | 状态参数不合法 |
| 角色组合不合法 | 409 | 30009 | 角色组合不合法 |
| 管理员分配超管 | 403 | 20005 | 无权分配超管角色 |
| 用户名已存在 | 409 | 30010 | 用户名已存在 |
| 无 `admin.accounts.create` | 403 | 20005 | 无权限 |

---

## 6. 用户详情

```http
GET /api/v1/admin/users/{id}
Authorization: Bearer <jwt>
```

### 6.1 成功响应

HTTP 200，`data` 结构与 §4.2 `items[0]` 完全一致。

### 6.2 规则

- 管理员可查看非超管账号详情；查看超管账号返回 403 `20006`。
- 超管可查看所有账号详情。
- 不返回密码或密码哈希。

### 6.3 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 用户不存在 | 404 | 30017 | 用户不存在 |
| 管理员查看超管账号 | 403 | 20006 | 无权操作超管账号 |
| 无 `admin.accounts.view` | 403 | 20005 | 无权限 |

---

## 7. 编辑账号

```http
PATCH /api/v1/admin/users/{id}
Authorization: Bearer <jwt>
Content-Type: application/json
```

### 7.1 请求体

```json
{
  "display_name": "张三",
  "roles": ["admin", "user"],
  "status": "active"
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `display_name` | string | 否 | 去除首尾空格后 1~30 个字符 |
| `roles` | string[] | 否 | 1~2 个；组合规则同 §5.1 |
| `status` | string | 否 | 仅 `active` / `disabled`；不能用本接口置为 `deleted` |

- 至少传一个字段，全部省略返回 400 `10002`。
- 用户名不可编辑；未传的字段保持原值。

### 7.2 账号边界

| 操作者 | 目标 | 可改字段 |
| --- | --- | --- |
| `admin` | 普通用户 | 显示名、角色、状态 |
| `admin` | 其他管理员 | 显示名、状态；**不能改角色** |
| `admin` | 超管 | 全部禁止 |
| `admin` | 自己 | 显示名；**不能改角色，不能改状态** |
| `super_admin` | 任意非自己账号 | 显示名、角色、状态（含其他超管，需保留至少一个可用超管） |
| `super_admin` | 自己 | 显示名；**不能移除自己的超管角色，不能改状态** |

补充：

- 管理员不能把任何账号的角色改为 `super_admin`；超管可以给他人授予 `super_admin`，但不能移除自己的超管角色。
- 不能移除或降级最后一个可用超管（`status=active` 且拥有 `super_admin`）。

### 7.3 成功响应

HTTP 200，返回更新后的账号对象（结构同 §4.2 `items[0]`）。

### 7.4 处理流程

1. 校验 token、权限、请求体。
2. 读取目标账号并校验账号边界。
3. 校验角色组合、状态取值与最后超管约束。
4. 在事务内更新 `users`、`user_roles`，写入日志 `account.update`，`detail` 记录修改前后值。
5. 提交并返回账号对象。

### 7.5 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 未传任何可改字段 | 400 | 10002 | 请至少修改一个字段 |
| 显示名超长 | 400 | 10004 | 显示名不能超过 30 个字符 |
| 状态非 `active`/`disabled` | 400 | 10003 | 状态参数不合法 |
| 角色组合不合法 | 409 | 30009 | 角色组合不合法 |
| 管理员操作超管账号 | 403 | 20006 | 无权操作超管账号 |
| 管理员修改自己的角色/状态 | 403 | 20007 | 不能修改自己的角色或状态 |
| 超管移除自己的超管角色 | 403 | 20007 | 不能移除自己的超管角色 |
| 管理员把账号改为超管 | 403 | 20005 | 无权分配超管角色 |
| 管理员修改其他管理员的角色 | 403 | 20005 | 无权修改其他管理员的角色 |
| 降级或禁用最后一个可用超管 | 409 | 30011 | 必须保留至少一个可用超管 |
| 用户不存在 | 404 | 30017 | 用户不存在 |
| 无 `admin.accounts.edit` | 403 | 20005 | 无权限 |

---

## 8. 重置密码

```http
POST /api/v1/admin/users/{id}/reset-password
Authorization: Bearer <jwt>
Content-Type: application/json
```

### 8.1 请求体

```json
{
  "new_password": "NewPass123"
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `new_password` | string | 是 | 去除首尾空格后 8~32 位；不做复杂度要求 |

> 「确认密码」由前端校验，不随请求提交。

### 8.2 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": null
}
```

### 8.3 生效规则

- 密码以 bcrypt cost=12 覆盖 `password_hash`。
- `token_version` 递增，旧 token 下一次请求返回 401 `20003`。
- 不强制用户下次登录修改密码。
- 账号状态保持原值。

### 8.4 权限

| 操作者 | 目标 | 允许 |
| --- | --- | --- |
| `admin` | 普通用户、其他管理员 | 允许 |
| `admin` | 超管 | 禁止，403 `20006` |
| `super_admin` | 除自己以外任何账号 | 允许 |
| `super_admin` | 自己 | 禁止，403 `20007`（走个人中心） |

### 8.5 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 缺少新密码 | 400 | 10002 | 请输入新密码 |
| 密码不在 8~32 位 | 400 | 10004 | 密码长度需为 8~32 位 |
| 管理员重置超管密码 | 403 | 20006 | 无权操作超管账号 |
| 超管重置自己的密码 | 403 | 20007 | 请通过个人中心修改自己的密码 |
| 用户不存在 | 404 | 30017 | 用户不存在 |
| 无 `admin.accounts.reset_password` | 403 | 20005 | 无权限 |

审计写入 `account.reset_password`，`detail` 只含 `user_id` 与 `username`。

---

## 9. 禁用 / 启用 / 软删除 / 恢复

### 9.1 禁用

```http
POST /api/v1/admin/users/{id}/disable
Authorization: Bearer <jwt>
```

- 状态由 `active` 变为 `disabled`，`token_version` 递增。
- 该账号后续请求返回 403 `20004`。
- 历史会话、生图记录、图片全部保留。
- 写入 `account.disable`。
- 对已禁用账号再次调用：返回 200 与当前账号对象，不重复写日志。
- 成功响应：HTTP 200，`data` 为更新后的账号对象。

### 9.2 启用

```http
POST /api/v1/admin/users/{id}/enable
Authorization: Bearer <jwt>
```

- 状态由 `disabled` 变为 `active`。
- 写入 `account.enable`。
- 对已启用账号再次调用：返回 200 与当前账号对象，不重复写日志。
- 已删除账号不能直接启用，返回 409 `30018`。
- 成功响应：HTTP 200，`data` 为更新后的账号对象。

### 9.3 软删除

```http
DELETE /api/v1/admin/users/{id}
Authorization: Bearer <jwt>
```

- 状态变为 `deleted`，写入 `deleted_at`，`token_version` 递增。
- 账号不能登录，已签发 token 失效。
- 用户名继续被占用，不能被新账号复用。
- 会话、消息、生图记录、图片全部保留。
- 写入 `account.delete`。
- 对已删除账号再次调用返回 409 `30018`。
- 成功响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": null
}
```

### 9.4 恢复

```http
POST /api/v1/admin/users/{id}/restore
Authorization: Bearer <jwt>
```

- 状态由 `deleted` 变为 `active`，清空 `deleted_at`，`token_version` 递增。
- 恢复后用户名不变，历史数据自动关联。
- 写入 `account.restore`。
- 对非删除账号调用返回 409 `30018`。
- 成功响应：HTTP 200，`data` 为更新后的账号对象。

### 9.5 状态操作边界

| 操作者 | 目标 | 禁用 | 启用 | 删除 | 恢复 |
| --- | --- | --- | --- | --- | --- |
| `admin` | 普通用户 | 允许 | 允许 | 允许 | 允许 |
| `admin` | 其他管理员 | 允许 | 允许 | 允许 | 允许 |
| `admin` | 超管 | 禁止 | 禁止 | 禁止 | 禁止 |
| `admin` | 自己 | 禁止 | — | 禁止 | — |
| `super_admin` | 任意非自己账号 | 允许 | 允许 | 允许 | 允许 |
| `super_admin` | 自己 | 禁止 | — | 禁止 | — |

- 不能禁用/删除最后一个可用超管（`status=active` 且拥有 `super_admin`），返回 409 `30011`。
- 管理员操作超管返回 403 `20006`；操作自己返回 403 `20007`。

### 9.6 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 管理员操作超管 | 403 | 20006 | 无权操作超管账号 |
| 操作自己 | 403 | 20007 | 不能对自己执行该操作 |
| 最后可用超管 | 409 | 30011 | 必须保留至少一个可用超管 |
| 禁用/删除已删除账号、启用已删除账号、恢复未删除账号 | 409 | 30018 | 当前账号状态不允许该操作 |
| 用户不存在 | 404 | 30017 | 用户不存在 |
| 无对应权限码 | 403 | 20005 | 无权限 |

---

## 10. 角色与权限

### 10.1 读取角色与权限点

```http
GET /api/v1/admin/roles
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "roles": [
      {
        "code": "user",
        "name": "普通用户",
        "editable": true,
        "permissions": ["user.workspace", "user.generate", "user.history", "user.profile"]
      },
      {
        "code": "admin",
        "name": "管理员",
        "editable": true,
        "permissions": [
          "admin.dashboard.view",
          "admin.accounts.view",
          "admin.accounts.create",
          "admin.accounts.edit",
          "admin.accounts.reset_password",
          "admin.accounts.disable",
          "admin.accounts.delete",
          "admin.content.view",
          "admin.assets.view",
          "admin.assets.edit",
          "admin.prompts.view",
          "admin.prompts.edit",
          "admin.tokens.view"
        ]
      },
      {
        "code": "super_admin",
        "name": "超管",
        "editable": false,
        "permissions": ["全部 23 个权限码"]
      }
    ],
    "permissions": [
      {
        "code": "user.workspace",
        "name": "创作台",
        "type": "menu",
        "group_name": "用户端",
        "is_super_only": false
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `roles` | array | 固定三个角色，顺序为普通用户、管理员、超管 |
| `roles[].editable` | bool | `user`/`admin` 为 `true`；`super_admin` 为 `false` |
| `roles[].permissions` | string[] | 当前权限码；`super_admin` 返回全部 23 个 |
| `permissions` | array | 权限点目录，按 `group_name` 再按 `code` 排序 |

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 非超管访问 | 403 | 20005 | 无权限 |

### 10.2 保存角色权限点

```http
PUT /api/v1/admin/roles/{code}/permissions
Authorization: Bearer <jwt>
Content-Type: application/json
```

#### 请求体

```json
{
  "permissions": ["admin.dashboard.view", "admin.accounts.view"]
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `permissions` | string[] | 是 | 全量覆盖；允许空数组以外的任意子集，但需满足最低权限 |

#### 规则

1. 仅 `user`、`admin` 可编辑；`super_admin` 返回 403 `20005`。
2. 权限码必须存在于 `permissions` 表，未知码返回 400 `10003`。
3. `is_super_only=true` 的权限点不能授予 `user` / `admin`，返回 409 `30015`。
4. `user` 至少保留 `user.workspace`；`admin` 至少保留 `admin.dashboard.view`；否则返回 409 `30015`。
5. 重复权限码自动去重。
6. 事务内全量替换 `role_permissions`，写入日志 `role.update`，`detail` 记录 before/after。
7. 不做并发冲突检测，后保存者覆盖先保存者。
8. 保存后下一次请求即生效；其他在线用户在下一次请求生效。

#### 成功响应

HTTP 200，返回更新后的角色：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "code": "admin",
    "name": "管理员",
    "editable": true,
    "permissions": ["admin.dashboard.view", "admin.accounts.view"]
  }
}
```

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 缺少 `permissions` | 400 | 10002 | 请选择权限点 |
| 权限码不存在 | 400 | 10003 | 权限点不存在 |
| 授予超管专属权限点 | 409 | 30015 | 超管专属权限点不能授予该角色 |
| 缺少最低权限 | 409 | 30015 | 普通用户角色至少保留「创作台」 |
| 缺少最低权限（管理员） | 409 | 30015 | 管理员角色至少保留「概览」 |
| 编辑超管角色 | 403 | 20005 | 超管角色权限不可编辑 |
| 角色取值非法（如 `super_admin` 以外的未知 code） | 400 | 10003 | 角色参数不合法 |
| 无 `admin.roles.edit` | 403 | 20005 | 无权限 |

---

## 11. 操作日志

### 11.1 日志列表

```http
GET /api/v1/admin/audit-logs?start_time=2026-10-01T00:00:00%2B08:00&end_time=2026-10-31T23:59:59%2B08:00&operator=demo&action=account.create&result=success&page=1&page_size=20
Authorization: Bearer <jwt>
```

#### 请求参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `start_time` | string | 否 | — | ISO 8601 带时区；含边界 |
| `end_time` | string | 否 | — | ISO 8601 带时区；含边界 |
| `operator` | string | 否 | — | 操作人用户名关键词，≤20 字符，模糊匹配 `username_snapshot` |
| `action` | string | 否 | — | 动作码精确匹配 |
| `result` | string | 否 | `all` | `success` / `failed` / `all` |
| `page` | int | 否 | 1 | 从 1 开始 |
| `page_size` | int | 否 | 20 | 最大 100 |

- 排序：`created_at DESC, id DESC`。
- `start_time` 晚于 `end_time` 返回 400 `10003`。

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "log_id": 301,
        "created_at": "2026-10-31T10:05:00+08:00",
        "operator_user_id": 1,
        "operator_username": "demo_super",
        "action": "account.create",
        "target_type": "account",
        "target_id": "zhangsan",
        "result": "success",
        "ip": "192.168.1.10"
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
| `log_id` | int | 对应 `audit_logs.id` |
| `created_at` | string | 时间，精确到秒 |
| `operator_user_id` | int / null | 操作人 ID；登录失败时可能为 `null` |
| `operator_username` | string / null | 操作人用户名快照 |
| `action` | string | 动作码 |
| `target_type` | string / null | 对象类型 |
| `target_id` | string / null | 对象标识 |
| `result` | string | `success` / `failed` |
| `ip` | string / null | 操作来源 IP |

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 时间格式错误或起止颠倒 | 400 | 10003 | 时间范围不合法 |
| 操作人关键词超过 20 字符 | 400 | 10004 | 操作人关键词不能超过 20 个字符 |
| 结果取值非法 | 400 | 10003 | 结果参数不合法 |
| 非超管访问 | 403 | 20005 | 无权限 |

### 11.2 日志详情

```http
GET /api/v1/admin/audit-logs/{id}
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "log_id": 301,
    "created_at": "2026-10-31T10:05:00+08:00",
    "operator_user_id": 1,
    "operator_username": "demo_super",
    "action": "account.update",
    "target_type": "account",
    "target_id": "zhangsan",
    "result": "success",
    "ip": "192.168.1.10",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    "detail": {
      "before": {
        "display_name": "张三",
        "roles": ["user"],
        "status": "active"
      },
      "after": {
        "display_name": "张三",
        "roles": ["admin", "user"],
        "status": "active"
      }
    }
  }
}
```

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 日志不存在 | 404 | 30019 | 操作日志不存在 |
| 非超管访问 | 403 | 20005 | 无权限 |

### 11.3 不可变

不提供编辑、删除日志的接口与页面入口；日志随业务数据保留。

---

## 12. 数据结构

### 12.1 账号对象

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | int | `users.id` |
| `username` | string | 登录名 |
| `display_name` | string | 显示名 |
| `roles` | array | `{code,name}`，1~2 个 |
| `status` | string | `active` / `disabled` / `deleted` |
| `stats` | object | `image_count`、`session_count`、`token_total`、`failed_task_count`、`stats_available` |
| `last_login_at` | string / null | 最后登录 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 最后修改时间 |
| `deleted_at` | string / null | 软删除时间 |

### 12.2 角色对象

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string | `user` / `admin` / `super_admin` |
| `name` | string | 角色名称 |
| `editable` | bool | 是否可编辑权限点 |
| `permissions` | string[] | 权限码列表 |

### 12.3 权限点对象

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | string | 权限码 |
| `name` | string | 中文名称 |
| `type` | string | `menu` / `action` |
| `group_name` | string | `用户端` / `管理后台` |
| `is_super_only` | bool | 是否超管专属 |

### 12.4 日志对象

列表字段见 §11.1；详情额外包含 `user_agent` 与 `detail`。

---

## 13. 账号边界与状态机

### 13.1 账号状态

```text
active ──禁用──> disabled ──启用──> active
   │                  │
   │                  └──删除──┐
   └──────────删除────────────> deleted ──恢复──> active
```

- `deleted` 是软删除态，数据保留、用户名占用、不能登录。
- 已删除账号必须先恢复，不能直接启用。
- 禁用、删除、恢复、重置密码都会递增 `token_version`。

### 13.2 边界汇总

| 操作者 | 目标 | 允许 |
| --- | --- | --- |
| 管理员 | 普通用户 | 查看、编辑、重置密码、禁用/启用、删除/恢复 |
| 管理员 | 其他管理员 | 查看、编辑（不含角色）、重置密码、禁用/启用、删除/恢复 |
| 管理员 | 超管 | 全部禁止 |
| 管理员 | 自己 | 查看、改显示名；不能改角色、不能禁用、不能删除；改密码走个人中心 |
| 超管 | 任意非自己账号 | 查看、编辑、重置密码、禁用/启用、删除/恢复（含其他超管，需保留至少一个可用超管） |
| 超管 | 自己 | 查看、改显示名；改密码走个人中心；不能移除超管角色、不能禁用、不能删除 |

---

## 14. 错误码（最小集）

| code | HTTP | 含义 | 本 demo 使用场景 |
| --- | --- | --- | --- |
| 0 | 200 | 成功 | 全部 |
| 10001 | 400 | 参数错误 | 通用 |
| 10002 | 400 | 缺少必填参数 | 账号字段、密码、权限点、修改字段 |
| 10003 | 400 | 参数格式错误 | 用户名格式、状态/角色/结果取值、日期范围、未知权限码 |
| 10004 | 400 | 参数超出范围 | 显示名、密码、关键词、操作人关键词超长 |
| 20002 | 401 | 登录已过期 | token 过期 |
| 20003 | 401 | token 无效 | 未携带、签名错误、版本不符（含重置密码后） |
| 20004 | 403 | 账号不可用 | 账号禁用或删除 |
| 20005 | 403 | 无权限 | 缺权限码、管理员分配超管、改其他管理员角色、编辑超管角色 |
| 20006 | 403 | 无权操作超管账号 | 管理员查看/编辑/重置/禁用/删除/恢复超管 |
| 20007 | 403 | 不能操作自己 | 改自己角色/状态、禁用/删除自己、重置自己密码 |
| 30009 | 409 | 角色组合不合法 | 新建/编辑角色 |
| 30010 | 409 | 用户名已存在 | 新建账号 |
| 30011 | 409 | 必须保留至少一个可用超管 | 降级、禁用、删除 |
| 30015 | 409 | 权限点不可授予该角色 | 超管专属权限点、最低权限缺失 |
| 30017 | 404 | 用户不存在 | 详情、编辑、状态操作、重置密码（demo 约定） |
| 30018 | 409 | 账号状态不允许该操作 | 启用已删除、删除已删除、恢复未删除（demo 约定） |
| 30019 | 404 | 操作日志不存在 | 日志详情（demo 约定） |
| 50001 | 500 | 系统内部错误 | 兜底 |
| 50002 | 500 | 数据库错误 | 兜底 |

错误响应统一为：

```json
{
  "code": 30011,
  "message": "必须保留至少一个可用超管",
  "data": null
}
```

---

## 15. 前端约定

### 15.1 路由与菜单

| 路径 | 可见角色 | 说明 |
| --- | --- | --- |
| `/admin/accounts` | 管理员、超管 | 用户管理 Tab、角色管理 Tab（仅超管可见） |
| `/admin/audit-logs` | 超管 | 操作日志 |

- 菜单与路由守卫使用 `/auth/me` 返回的 `permissions`；前端隐藏只是体验优化，后端仍是最终判定。
- 无权限访问跳 `/403`。

### 15.2 用户管理页

- 筛选区：关键词输入框、角色下拉（全部/普通用户/管理员/超管）、状态下拉（全部/启用/禁用/已删除）、创建时间范围。
- 任意筛选变化或每页条数变化后回到第 1 页。
- 行内操作：查看详情、编辑、重置密码、禁用/启用、删除/恢复。
- 管理员视角下超管行的操作按钮隐藏或置灰并提示「无权操作超管账号」。
- 自己的「编辑」弹窗中角色字段只读；自己的禁用/删除按钮不可用。
- 删除与恢复使用二次确认弹窗。
- 操作成功后刷新列表并 Toast；失败 Toast 显示后端 `message`。
- 空状态「暂无用户，点击新建账号」；加载失败「加载失败，点击重试」。

### 15.3 新建/编辑弹窗

- 用户名输入框 `maxLength=20`，创建后只读。
- 显示名 `maxLength=30`，去除首尾空格后校验非空。
- 密码输入框 `maxLength=32`，前端校验 8~32 位；重置密码弹窗额外校验两次一致。
- 角色使用多选，最多 2 个；前端即时拦截 `super_admin + admin`；管理员登录时 `super_admin` 选项不出现。
- 前端校验失败不发请求。

### 15.4 用户详情

- 基本信息与统计分区展示；统计为 `0` 且 `stats_available=false` 时显示提示「统计将在生图模块接入后显示」。
- 操作按钮按账号边界与当前操作者身份启用/禁用。
- 「查看会话」「查看生图记录」按钮禁用，悬浮提示「内容追溯将在 7 号 PRD 实现后开放」。

### 15.5 角色管理页

- 三张角色卡：普通用户、管理员、超管；前两张可编辑，超管卡只读并提示「超管拥有全部权限」。
- 权限树按「用户端 / 管理后台」分组，菜单与操作权限点分开显示。
- 超管专属权限点在普通用户/管理员视图中置灰，提示「仅超管可用」。
- 保存前前端校验最低权限；保存成功后重新请求 `/auth/me` 刷新菜单。
- 保存按钮二次确认，提示「将覆盖他人此前的修改」。

### 15.6 操作日志页

- 筛选区：时间范围、操作人关键词、动作下拉、结果下拉。
- 表格列：时间、操作人、动作、对象类型、对象标识、结果、IP。
- 点击行打开抽屉，格式化展示 `user_agent` 与 `detail` JSON。
- 不提供编辑、删除入口。

### 15.7 错误处理

| 场景 | 前端行为 |
| --- | --- |
| 401（`20002` / `20003`） | 清除 token 与全局用户状态，跳 `/login?redirect=当前路径` |
| 403（`20004`） | 清除 token，跳 `/login`，提示「账号已被禁用或删除」 |
| 403（`20005` / `20006` / `20007`） | Toast 后端 `message`；页面级无权限跳 `/403` |
| 409（`30009` / `30010` / `30011` / `30015` / `30018`） | 弹窗或 Toast 后端 `message`，保留表单内容 |
| 404（`30017` / `30019`） | Toast 后端 `message`，返回列表或关闭抽屉 |
| 5xx | Toast「系统繁忙，请稍后重试」，不自动登出 |
| 网络异常 | Toast「网络异常，请稍后重试」 |

---

## 16. 与 9 号 / 10 号文档的差异与待统一项

| 项目 | 本文 demo 口径 | 9 号 / 10 号 | 处理建议 |
| --- | --- | --- | --- |
| 用户不存在错误码 | 404 `30017` | 9 号未定义 | 在 9 号错误码表补充 |
| 账号状态不允许错误码 | 409 `30018` | 9 号未定义 | 在 9 号错误码表补充 |
| 日志不存在错误码 | 404 `30019` | 9 号未定义 | 在 9 号错误码表补充 |
| 管理员分配超管 | 403 `20005` | 9 号无专用码 | 确认是否新增专用码 |
| 最低权限校验 | 409 `30015` | 9 号 `30015` 只描述「权限点不可授予该角色」 | 扩展含义或新增码 |
| 用户列表响应字段 | 含 `stats`、`roles` 对象数组、`deleted_at` | 9 号只给接口用途，无响应结构 | 正式实现前补全 9 号 |
| 状态操作响应 | 启用/禁用/恢复返回账号对象；删除/重置密码返回 `null` | 9 号未定义 | 与前端约定后固化 |
| 统计字段 | `stats_available=false`、计数为 `0` | 10 号定义了内容表，但本 demo 未建 | 内容模块接入后置 `true` |
| 超管权限存储 | 不写 `role_permissions`，按角色全量授予 | 6 号 §10.3 一致；10 号未规定种子 | 确认种子是否落行 |
| 审计动作码 | `account.*` / `role.update` | 9 号只给示例 | 统一动作码清单 |
| 权限缓存 | 每请求直查 PostgreSQL | 9 号 §2.7 Redis ≤30 秒 | demo 取舍，正式实现替换 |
| 角色权限并发 | last-write-wins | 6 号 §12.3 一致 | 保持 |

---

## 17. 未实现接口

以下接口明确不在最小 demo 内，调用方不得依赖：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/admin/dashboard/summary` | 概览统计 |
| GET | `/api/v1/admin/tokens/stats` | Token 统计 |
| GET | `/api/v1/admin/content/*` | 内容追溯 |
| GET | `/api/v1/admin/chat/*` | 聊天记录 |
| GET | `/api/v1/admin/agent-runs/{run_id}` | Agent 调用明细 |
| GET / PUT | `/api/v1/admin/model-config` | 模型配置 |
| GET / PUT | `/api/v1/admin/prompts/*` | 系统提示词 |
| GET / POST / PATCH | `/api/v1/admin/templates/*` | 模板 |
| GET / POST / PATCH | `/api/v1/admin/materials/*` | 素材 |
| GET / POST / PATCH | `/api/v1/admin/sizes/*` | 尺寸预设 |
| POST | `/api/v1/admin/export` | 创建导出任务 |
| GET | `/api/v1/admin/export/{job_id}` | 导出状态 |
| PUT | `/api/v1/auth/password` | 个人修改密码（登录/个人中心范围） |

---

## 18. 验收调用序列

以下序列对应 README 第 5 章的演示脚本：

| 步骤 | 调用 | 期望 |
| --- | --- | --- |
| 1 | `POST /auth/login`（`demo_super`） | 返回 token |
| 2 | `GET /auth/me` | 返回 `super_admin` 与全部权限 |
| 3 | `GET /admin/users` | 分页用户列表，含演示账号 |
| 4 | `GET /admin/users?keyword=demo&role=admin&status=all` | 只返回管理员账号 |
| 5 | `POST /admin/users`（`demo_editor`，`["user"]`） | 200，返回账号对象；日志新增 `account.create` |
| 6 | `POST /admin/users`（用户名重复） | 409 `30010` |
| 7 | `POST /admin/users`（`["super_admin","admin"]`） | 409 `30009` |
| 8 | `GET /admin/users/{demo_editor_id}` | 200，统计为 0 且 `stats_available=false` |
| 9 | `PATCH /admin/users/{demo_editor_id}`（追加 `admin`） | 200，角色更新；日志新增 `account.update` |
| 10 | `POST /admin/users/{demo_editor_id}/disable` | 200；该账号旧 token 请求返回 403 `20004` |
| 11 | `POST /admin/users/{demo_editor_id}/enable` | 200，账号恢复 |
| 12 | `POST /admin/users/{demo_editor_id}/reset-password` | 200；旧 token 返回 401 `20003` |
| 13 | `DELETE /admin/users/{demo_editor_id}` | 200；`status=deleted` 可筛选到 |
| 14 | `POST /admin/users`（复用 `demo_editor` 用户名） | 409 `30010` |
| 15 | `POST /admin/users/{demo_editor_id}/restore` | 200，状态回到 `active` |
| 16 | `GET /admin/roles` | 三个角色与 23 个权限点 |
| 17 | `PUT /admin/roles/admin/permissions`（去掉 `admin.accounts.view`） | 200；管理员下一次请求访问用户列表返回 403 `20005` |
| 18 | `PUT /admin/roles/admin/permissions`（加入 `admin.audit.view`） | 409 `30015` |
| 19 | `PUT /admin/roles/super_admin/permissions` | 403 `20005` |
| 20 | `GET /admin/audit-logs?action=account.create` | 返回创建日志 |
| 21 | `GET /admin/audit-logs/{log_id}` | 返回 `detail`，无密码字段 |
| 22 | `demo_admin` 的 token 调 `GET /admin/roles` | 403 `20005` |
| 23 | `demo_admin` 的 token 调 `PATCH /admin/users/{demo_super_id}` | 403 `20006` |
| 24 | 禁用唯一可用超管 | 409 `30011` |

### 18.1 示例：新建账号

```bash
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "demo_editor",
    "display_name": "编辑小王",
    "password": "Demo1234",
    "roles": ["user"],
    "status": "active"
  }'
```

### 18.2 示例：保存角色权限

```bash
curl -X PUT http://localhost:8000/api/v1/admin/roles/admin/permissions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "permissions": [
      "admin.dashboard.view",
      "admin.accounts.view",
      "admin.accounts.create"
    ]
  }'
```

### 18.3 示例：查询操作日志

```bash
curl -G http://localhost:8000/api/v1/admin/audit-logs \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "action=account.create" \
  --data-urlencode "result=success" \
  --data-urlencode "page=1" \
  --data-urlencode "page_size=20"
```
