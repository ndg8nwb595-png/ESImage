# generation 模块（4 号 PRD 生图任务与结果后端最小 demo）

对应需求：

- `docs/prd/4-生图任务与结果/4-生图任务与结果prd.md`
- `docs/prd/4-生图任务与结果/接口文档-生图任务最小demo.md`
- `docs/prd/4-生图任务与结果/issues/01` ~ `08`

## 模块定位

本模块替换 2 号 demo `workspace` 中的「演示生成管线」（占位 PNG + 桩 Agent），
升级为真实 8 Agent + 豆包模型 + 文字合成；**不改变 2 号 demo 已定义的对外接口契约**，
只做增量字段与新增接口。

## 计划文件

| 文件 | 职责 |
| --- | --- |
| `router.py` | 汇总模板/尺寸只读接口与生成任务接口 |
| `config_router.py` | `GET /templates`、`GET /templates/{id}/thumbnail`、`GET /sizes` |
| `generation_router.py` | 示例批次、批次查询、确认全套、取消、单张重试、预览/下载、整组 ZIP |
| `schemas.py` | 请求体模型 |
| `service.py` | 参数校验、归属校验、幂等、并发、状态机、序列化与文件名 |
| `config_service.py` | 生成配置只读缓存（60 秒 + 手动刷新） |
| `doubao.py` | 豆包文本/视觉/图像/内容审核适配层 |
| `agents.py` | 8 Agent 契约、结构化输出校验、重试与 `agent_runs` 落库 |
| `composition.py` | 文字留白合成与默认版式 |
| `pipeline.py` | 示例批次、全套批次、单张重试的生成管线 |
| `zip_export.py` | 整组 ZIP 与 `manifest.csv` |
| `seed.py` | 8 条提示词、模型配置、模板/素材/尺寸种子 |

## 依赖与边界

- 数据表复用 `app/models/workspace.py` 中已有的 `generation_batches`、
  `generated_images`、`agent_runs`；生成配置表复用 `app/models/config.py`。
- 生成配置只做读取与种子，不做后台 CRUD。
- 异步任务沿用 FastAPI `BackgroundTasks` + PostgreSQL 轮询，单实例；不接 Celery / Redis。
- 对象存储沿用本地目录适配层，不接 MinIO。
- 模型 Key 只从环境变量读取；缺失时启动校验失败（fail-fast）。

## 接口清单

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| GET | `/api/v1/templates` | `user.generate` |
| GET | `/api/v1/templates/{template_id}/thumbnail` | `user.generate` |
| GET | `/api/v1/sizes` | `user.generate` |
| POST | `/api/v1/generations/sample` | `user.generate` |
| GET | `/api/v1/generations/{batch_id}` | `user.generate` |
| POST | `/api/v1/generations/{batch_id}/confirm` | `user.generate` |
| POST | `/api/v1/generations/{batch_id}/cancel` | `user.generate` |
| POST | `/api/v1/images/{image_id}/regenerate` | `user.generate` |
| GET | `/api/v1/images/{image_id}/content` | `user.generate` |
| GET | `/api/v1/images/{image_id}/thumbnail` | `user.generate` |
| GET | `/api/v1/images/{image_id}/download` | `user.history` |
| GET | `/api/v1/batches/{batch_id}/download` | `user.history` |

## 状态

- [x] 模块骨架与目录
- [x] 数据模型与配置种子
- [x] Agent 运行时与豆包适配层
- [x] 文字合成
- [x] 示例批次 / 全套批次 / 取消 / 重试 / ZIP
- [x] pytest（确定性模型替身）
- [x] curl 验收脚本（`backend/scripts/curl_smoke_generation.sh`）
- [ ] 真实 Seedream 全链路验收（等待账号额度调整）

## 模型

- 文本：`doubao-seed-character-260628`
- 视觉/审核：`doubao-seed-2-1-lite-260915`
- 生图：`doubao-seedream-5-0-pro-260628`（需在方舟控制台开通并调整体验额度）
