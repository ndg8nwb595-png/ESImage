# admin/audit：管理后台「操作日志」

本目录实现 6 号 PRD 最小 demo 的操作日志查询接口（只读，不提供编辑与删除）。

## 定位

- 上游 PRD：`docs/prd/6-管理后台-账号与权限/6-管理后台-账号与权限prd.md` §14
- 接口文档：`docs/prd/6-管理后台-账号与权限/接口文档-账号与权限最小demo.md` §11
- 复用 1 号登录 demo 的 `audit_logs` 表与 `core/audit.py` 写入函数。
- 日志写入由各业务模块负责；本目录只做查询。

## 计划接口（共 2 个）

| 方法 | 路径 | 权限码 |
| --- | --- | --- |
| GET | `/api/v1/admin/audit-logs` | `admin.audit.view` |
| GET | `/api/v1/admin/audit-logs/{id}` | `admin.audit.view` |

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `router.py` | 路由、权限依赖、筛选参数与统一响应 |
| `schemas.py` | 查询参数校验与响应序列化辅助 |
| `service.py` | 条件查询、分页与日志对象序列化 |

## 边界约定

- 默认按 `created_at DESC, id DESC` 排序。
- `operator` 对 `username_snapshot` 模糊匹配，最长 20 字符。
- 详情返回 `user_agent` 与 `detail`；日志不可编辑、不可删除。
