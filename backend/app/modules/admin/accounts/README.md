# admin/accounts：管理后台「账号与权限」

本目录实现 6 号 PRD「管理后台-账号与权限」最小 demo 的用户管理、用户详情、角色与权限点配置接口。

## 定位

- 上游 PRD：`docs/prd/6-管理后台-账号与权限/6-管理后台-账号与权限prd.md`
- 接口文档：`docs/prd/6-管理后台-账号与权限/接口文档-账号与权限最小demo.md`
- 复用 1 号登录 demo 的 `users` / `roles` / `permissions` / `user_roles` / `role_permissions` / `audit_logs` 六张表，不重复建模。
- 操作日志查询在 `../audit/`；本目录只负责写审计，不提供日志查询接口。

## 计划接口（共 11 个）

| 方法 | 路径 | 权限码 |
| --- | --- | --- |
| GET | `/api/v1/admin/users` | `admin.accounts.view` |
| POST | `/api/v1/admin/users` | `admin.accounts.create` |
| GET | `/api/v1/admin/users/{id}` | `admin.accounts.view` |
| PATCH | `/api/v1/admin/users/{id}` | `admin.accounts.edit` |
| POST | `/api/v1/admin/users/{id}/reset-password` | `admin.accounts.reset_password` |
| POST | `/api/v1/admin/users/{id}/disable` | `admin.accounts.disable` |
| POST | `/api/v1/admin/users/{id}/enable` | `admin.accounts.disable` |
| DELETE | `/api/v1/admin/users/{id}` | `admin.accounts.delete` |
| POST | `/api/v1/admin/users/{id}/restore` | `admin.accounts.delete` |
| GET | `/api/v1/admin/roles` | `admin.roles.view` |
| PUT | `/api/v1/admin/roles/{code}/permissions` | `admin.roles.edit` |

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `router.py` | FastAPI 路由、权限依赖、请求解析与统一响应 |
| `schemas.py` | 请求体模型（字段规则在 service 中二次校验，保证错误码稳定） |
| `service.py` | 账号边界、角色组合、状态机、最后超管保护、事务与审计 |

## 边界约定

- 权限与账号状态每次请求直查 PostgreSQL，不接 Redis。
- `super_admin` 始终拥有全部 23 个权限码，不依赖 `role_permissions`。
- 账号操作响应结构以接口文档 §4.2 为准；列表与详情共用同一账号对象。
- 统计字段在内容表未接入前固定返回 `0`，并返回 `stats_available=false`。
