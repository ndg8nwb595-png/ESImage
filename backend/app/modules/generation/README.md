# generation 模块（4 号 PRD 生图任务与结果后端最小 demo）

对应需求：

- `docs/prd/4-生图任务与结果/4-生图任务与结果prd.md`
- `docs/prd/4-生图任务与结果/接口文档-生图任务最小demo.md`
- `docs/prd/4-生图任务与结果/issues/01` ~ `08`
- 开发依据：`backend/skills/generation-pipeline/SKILL.md` 与 `references/agents-contract.md`、`references/state-machine.md`

## 模块定位

本模块替换 2 号 demo `workspace` 中的「演示生成管线」（占位 PNG + 桩 Agent），
升级为真实 8 Agent + 豆包 Seedream + 文字合成；**不改变 2 号 demo 已定义的对外接口契约**，
只做增量字段与新增接口。

## 文件

| 文件 | 职责 |
| --- | --- |
| `router.py` | 汇总配置只读接口与生成任务接口 |
| `config_router.py` | `GET /templates`、`GET /templates/{id}/thumbnail`、`GET /sizes` |
| `generation_router.py` | 示例批次、批次查询、确认全套、取消、单张重试、预览/下载 |
| `schemas.py` | 请求体模型 |
| `service.py` | 参数校验、归属校验、幂等、并发、状态机、序列化与文件名 |
| `config_service.py` | 生成配置只读缓存（60 秒 + 手动刷新） |
| `doubao.py` | 豆包文本/视觉/图像/内容审核适配层（ARK_* / DOUBAO_*） |
| `agents.py` | 8 Agent 契约、结构化输出校验、重试与 `agent_runs` 落库 |
| `composition.py` | 文字留白合成与默认版式；留白不足时半透明底兜底 |
| `pipeline.py` | 示例批次、全套批次、单张重试的生成管线 |
| `state.py` | 批次/单图状态机 |
| `seed.py` | 8 条提示词、模型配置、模板/素材/尺寸种子 |

> 整组 ZIP 与 `manifest.csv` 统一由 5 号历史模块的
> `app/modules/history/zip_export.py` 提供，避免两套实现漂移；
> 4 号 `/batches/{id}/download` 直接复用该契约。

## 依赖与边界

- 数据表复用 `app/models/workspace.py` 中已有的 `generation_batches`、
  `generated_images`、`agent_runs`；生成配置表复用 `app/models/config.py`。
- 生成配置只做读取与种子，不做后台 CRUD；后台维护入口在
  `/api/v1/admin/templates`、`/api/v1/admin/materials`、`/api/v1/admin/sizes`。
- 异步任务沿用 FastAPI `BackgroundTasks` + PostgreSQL 轮询，单实例；不接 Celery / Redis。
- 对象存储沿用本地目录适配层，不接 MinIO。
- 模型 Key 只从环境变量读取；`ARK_API_KEY`（或 `DOUBAO_API_KEY`）缺失时启动校验失败。

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
| GET | `/api/v1/images/{image_id}/content` | `user.generate` 或 `user.history` |
| GET | `/api/v1/images/{image_id}/thumbnail` | `user.generate` 或 `user.history` |
| GET | `/api/v1/images/{image_id}/download` | `user.history` |
| GET | `/api/v1/batches/{batch_id}/download` | `user.history`（复用历史模块实现） |

## 关键实现口径

- **真实出图**：`image_generator` 真实调用 Seedream；失败 2 次整批 `failed`，不落占位图。
- **顺序固定**：planner → product_understanding → copywriter → prompt_builder →
  image_generator → quality_reviewer →（repairer → image_generator）→ platform_rule → text_composition。
- **留白兜底**：prompt 追加显式留白比例；质量审核若仅 `whitespace_available=fail`，
  不判整张失败，改为文字合成加半透明白底兜底（对齐 PRD §7.3 与 skill 铁律 5）。
- **全套复用**：full 复用 sample 的计划/画像/文案/提示词，示例图即主图，只串行生成 2~6。
- **状态机**：`sample_ready → confirmed`、`cancelled` 终态、重生成 `superseded` 旧图；
  单批次只允许一个 `pending/generating` 重试。
- **归档读取**：预览/下载通过 `read_image_bytes` 统一处理热存储与 `archive/` 前缀。

## 状态

- [x] 模块骨架与目录
- [x] 数据模型与配置种子（复用 10 号 `models/config.py`）
- [x] Agent 运行时与豆包适配层
- [x] 文字合成
- [x] 示例批次 / 全套批次 / 取消 / 重试 / ZIP（ZIP 复用历史模块）
- [x] pytest（确定性模型替身）
- [x] curl 验收脚本（`backend/scripts/curl_smoke_generation.sh`）
- [x] 真实 Seedream 单图与示例批次验收
- [ ] 真实全套 6/6 复验（留白兜底优化后）

## 模型

- 文本：`doubao-seed-character-260628`
- 视觉/审核：`doubao-seed-2-1-lite-260915`
- 生图：`doubao-seedream-5-0-pro-260628`
