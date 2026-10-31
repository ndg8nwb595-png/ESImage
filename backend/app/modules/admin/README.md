# admin 模块（6/7/8 号管理后台后端）

本目录承载管理后台的账号与权限（6 号）、概览与用户/生图记录（7 号）、聊天记录（8 号）后端。

## 目录规划

```text
admin/
├── router.py          # 汇总 dashboard / tokens / accounts / content / chat / assets / prompts / audit
├── service.py         # 管理端公共权限、时间、分页、媒体与存储工具
├── seed.py            # 配置域种子：尺寸预设与 8 个系统提示词
├── seed_content.py    # 7 号幂等内容种子：用户、会话、批次、图片、Agent 调用
├── dashboard/         # 概览四卡（60 秒进程内缓存）与 Token 统计
├── content/           # 7 号内容追溯与媒体；8 号聊天记录拆在 chat_router.py
└── accounts/          # 6 号账号与权限 CRUD；stats 使用真实批量聚合
```

## 7 号接口清单

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| GET | `/api/v1/admin/dashboard/summary` | `admin.dashboard.view` |
| GET | `/api/v1/admin/tokens/stats` | `admin.tokens.view` |
| GET | `/api/v1/admin/content/users` | `admin.content.view` |
| GET | `/api/v1/admin/content/users/{user_id}/sessions` | `admin.content.view` |
| GET | `/api/v1/admin/content/sessions/{session_id}/batches` | `admin.content.view` |
| GET | `/api/v1/admin/content/batches/{batch_id}/images` | `admin.content.view` |
| GET | `/api/v1/admin/content/images/{image_id}` | `admin.content.view` |
| GET | `/api/v1/admin/content/images/{image_id}/thumbnail` | `admin.content.view` |
| GET | `/api/v1/admin/content/images/{image_id}/content` | `admin.content.view` |
| GET | `/api/v1/admin/content/images/{image_id}/download` | `admin.content.view` |
| GET | `/api/v1/admin/users` | `admin.accounts.view` |
| GET | `/api/v1/admin/users/{user_id}` | `admin.accounts.view` |

## 边界

- 7 号只读接口，不提供导出、删除、重生成、改提示词、直连 SQL。
- 管理员看不到超管账号的内容；超管可看全部。
- 数据表复用 `app/models/workspace.py`，不新增表。
- 本地存储沿用 `app/modules/workspace/storage.py` 的适配层。
- 概览缓存为进程内 60 秒 TTL（`DASHBOARD_CACHE_TTL_SECONDS`），正式实现换 Redis。
- 归档读取超时由 `ARCHIVE_READ_TIMEOUT_SECONDS` 控制，默认 60 秒。

## 验收

- 7 号接口测试：`python -m pytest tests/test_admin_content.py -q`
- curl 冒烟：`DATABASE_URL=... JWT_SECRET=... PYTHON_BIN=<python> bash scripts/curl_smoke_admin7.sh`
- 测试库与开发库默认使用 `esimage_admin7_test` / `esimage_admin7`，避免与同设备并行 agent 冲突。

## 与 6 / 8 号的整合说明

- 6 号账号 CRUD 保留在 `accounts/router.py`；列表统计改为 `accounts/service.py`
  的批量聚合，`failed_task_count` 计入 `failed` 与 `partially_failed`，Token 口径与
  7 号 Token 统计一致。
- 8 号聊天记录接口拆到 `content/chat_router.py`，路径仍为
  `/api/v1/admin/chat/*` 与 `/api/v1/admin/agent-runs/{run_id}`，避免与 7 号内容路由冲突。
- `accounts`、`assets`、`prompts`、`audit`、`chat` 子路由统一挂载到 `/api/v1/admin`；
  `dashboard`、`tokens`、`content` 自带 `/admin/...` 前缀。
