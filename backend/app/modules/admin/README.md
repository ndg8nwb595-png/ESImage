# admin 模块（6/7/8 号管理后台后端）

本目录当前承载「7-管理后台-用户与生图记录」最小 demo 的后端实现。

## 目录规划

```text
admin/
├── router.py          # 汇总 dashboard / tokens / content / accounts 子路由
├── service.py         # 管理端公共权限、时间、分页、媒体与存储工具
├── seed.py            # 7 号幂等演示数据种子
├── dashboard/         # 概览四卡与 Token 统计
├── content/           # 内容追溯：用户 → 会话 → 批次 → 图片与媒体
└── accounts/          # 用户列表/详情（复用 6 号结构，统计改为真实值）
```

## 接口清单

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

- 只读接口，不提供导出、删除、重生成、改提示词、直连 SQL。
- 管理员看不到超管账号的内容；超管可看全部。
- 数据表复用 `app/models/workspace.py`，不新增表。
- 本地存储沿用 `app/modules/workspace/storage.py` 的适配层。
- 概览缓存为进程内 60 秒 TTL（`DASHBOARD_CACHE_TTL_SECONDS`），正式实现换 Redis。
- 归档读取超时由 `ARCHIVE_READ_TIMEOUT_SECONDS` 控制，默认 60 秒。

## 验收

- 接口测试：`python -m pytest tests/test_admin_content.py -q`
- curl 冒烟：`DATABASE_URL=... JWT_SECRET=... PYTHON_BIN=<python> bash scripts/curl_smoke_admin7.sh`
- 测试库与开发库默认使用 `esimage_admin7_test` / `esimage_admin7`，避免与同设备并行 agent 冲突。

## 与 6 号 demo 的合并说明

当前 `main` 尚无 6 号账号与权限后端，因此本模块提供只读的 `GET /admin/users` 与
`GET /admin/users/{id}` 以完成 7 号 06 切片的真实统计。6 号后端合并后，应复用其
用户列表/详情路由，只把 `stats` 替换为本模块 `accounts/service.py` 的聚合结果，
避免重复路由。
