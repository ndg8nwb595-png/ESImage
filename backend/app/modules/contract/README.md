# 9 号：后端服务与接口（契约基线）

对应上游文档 `docs/prd/9-后端服务与接口/`。本模块**不新增业务接口**，只固化
1~6 号 demo 共同遵守的跨切面规则，并用既有接口做端到端验证。

## 定位

业务接口（登录、会话、上传、生成、历史、管理后台等）沿用 1~6 号 demo；
本模块提供它们共同依赖的契约层，并把它标注进 OpenAPI：

| 文件 | 职责 |
| --- | --- |
| `errors.py` | 9 号 §3.1 错误码总表（单一来源） |
| `pagination.py` | 共享分页：`page`/`page_size` 校验与 `10001`/`10003`/`10004` 映射 |
| `openapi.py` | OpenAPI 契约标注：Bearer 鉴权、统一响应/分页结构、错误码表、`x-permission` 权限码 |

## 权限码

`openapi.PERMISSION_MAP` 是「接口契约」的单一来源，逐条列出每个接口的权限码。
标注约定：

- `None` → 无需鉴权（登录、健康探针、非生产 SSE 探针）。
- `"login"` → 登录即可（`/auth/me`、`/auth/logout`、`/auth/password`）。
- 单个权限码字符串或元组 → 需要对应权限码；元组表示「任一即可」。

## 契约载体接口（README §3.2 摘要）

| 方法/路径 | 权限码 |
| --- | --- |
| `POST /api/v1/auth/login` | 无需鉴权 |
| `GET /api/v1/auth/me` | 登录即可 |
| `GET /api/v1/sessions/{id}/messages` | `user.workspace` |
| `POST /api/v1/sessions/messages` / `.../sessions/{id}/messages` | `user.workspace` |
| `POST /api/v1/uploads` | `user.generate` |
| `GET/DELETE /api/v1/uploads/{id}` | `user.generate` |
| `POST /api/v1/generations/sample` | `user.generate` |
| `GET /api/v1/images/{id}/download` | `user.history` |
| `GET /api/v1/batches/{id}/download` | `user.history` |
| `GET /api/v1/admin/users`（管理端） | `admin.accounts.view` |

## 验证

- 契约回归套件：`backend/tests/test_contract.py`（pytest，TestClient 进程内）。
- curl 验收：`backend/scripts/curl_contract_smoke.sh`（启动 uvicorn 后逐接口 curl）。
- Swagger：启动后访问 `/api/docs`；机器可读契约 `/api/openapi.json`。

## 明确不做（沿用 README）

不新增业务接口；不接 Redis/Alembic/Celery/MinIO（沿用既有 demo 的
`BackgroundTasks` + 本地存储适配层）；不做导出接口、归档任务、接口级限流。
