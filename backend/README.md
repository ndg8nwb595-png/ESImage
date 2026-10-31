# ESImage 后端

FastAPI + SQLAlchemy + PostgreSQL 16。当前已实现：

- `auth`：登录、当前用户、退出登录（1 号 PRD 最小 demo）。
- `workspace`：创作工作台后端（2 号 PRD 最小 demo），含会话、聊天 SSE、商品图上传。
- `chat`：Agent 会话交互增量（3 号 PRD 最小 demo）。
- `generation`：生图任务与结果（4 号 PRD 最小 demo），含真实 8 Agent、豆包文本/视觉/生图、文字合成、示例/全套批次、取消、单张重试、单张/ZIP 下载。
- `history`：历史作品只读接口与共享整组 ZIP（5 号 PRD 最小 demo）。
- `admin`：管理后台账号权限、内容追溯、素材模板、提示词与模型配置（6/7/8 号 PRD 最小 demo）。
- `data` / `ops`：10 号 Alembic 数据底座、11 号部署运维基线。
- 生图管线开发依据：`backend/skills/generation-pipeline/SKILL.md` 与 `references/agents-contract.md`、`references/state-machine.md`。

## 1. 本地启动

在仓库根目录启动 PostgreSQL（独立容器与端口，避免和本机其他项目冲突）：

```bash
docker compose up -d
```

并行开发时不要覆盖其他 agent 的库。4 号生图建议使用独立库 `esimage_generation`：

```bash
docker exec esimage-postgres psql -U esimage -d postgres \
  -c "CREATE DATABASE esimage_generation"   # 已存在时忽略
```

在 `backend/` 目录安装依赖并初始化数据：

```bash
python -m pip install -r requirements.txt

# 复制环境变量模板后填写 ARK_API_KEY
cp .env.example .env

python scripts/init_db.py
python scripts/seed.py
# 正式部署也可使用 10 号迁移：alembic upgrade head
```

启动服务：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

> 8000 端口属于 1 号登录 demo，并行开发时建议使用 8010 / 8011。

## 2. 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 是 | 建议指向独立库 `esimage_generation` |
| `JWT_SECRET` | 是 | 随机长密钥 |
| `ARK_API_KEY` | 是 | 火山方舟 API Key；兼容 `DOUBAO_API_KEY` |
| `ARK_BASE_URL` / `DOUBAO_BASE_URL` | 否 | 默认 `https://ark.cn-beijing.volces.com/api/v3` |
| `ARK_TEXT_MODEL` / `DOUBAO_TEXT_MODEL` | 是 | 文本模型，默认 `doubao-seed-character-260628` |
| `DOUBAO_IMAGE_MODEL` | 是 | 生图模型，默认 `doubao-seedream-5-0-pro-260628` |
| `DOUBAO_VISION_MODEL` | 否 | 视觉理解模型；为空时质量审核跳过并标记「未校验」 |
| `DOUBAO_MODERATION_MODEL` | 是 | 生成图内容审核模型，默认 `doubao-seed-2-1-lite-260915` |
| `BATCH_TIMEOUT_SECONDS` | 否 | 整批超时，默认 `1800` |
| `FONT_PATH` | 否 | 中文字体路径；留空时自动查找系统字体 |
| `STORAGE_BACKEND` | 否 | `local` / `minio`；`.env.example` 默认 `minio` |
| `MINIO_ENDPOINT` | 否 | Docker MinIO 地址，默认 `127.0.0.1:9002` |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | 否 | MinIO 访问密钥（与 docker-compose 一致） |
| `MINIO_BUCKET` | 否 | 默认 `esimage` |
| `MINIO_SECURE` | 否 | 本地默认 `false` |
| `MODEL_CONFIG_ENCRYPTION_KEY` | 是 | base64 编码的 32 字节密钥；用于模型配置加密 |
| `APP_ENV` | 否 | 测试环境设为 `test` 才允许 fake 模型与故障注入 |
| `GENERATION_MODEL_PROVIDER` | 否 | 默认 `doubao`；仅 `APP_ENV=test` 可用 `fake` |

启动时会校验 Key、模型名与中文字体；缺失时 fail-fast，不会静默降级。

### 2.1 生图模型开通

- 需在火山方舟控制台开通 `DOUBAO_IMAGE_MODEL` 对应的 Seedream 模型。
- 若账号开启「安全体验模式」，额度用尽后会返回 429 `SetLimitExceeded`，需在控制台调整或关闭该模式。
- Seedream 5.0 Pro 不接受 `sequential_image_generation` / `stream` 参数，适配层只发送各版本通用的最小参数集。

### 2.2 对象存储

- `docker compose up -d` 会启动 `esimage-minio`（宿主 9002/9003）并初始化 `esimage` 桶与
  `uploads/ generated/ thumbnails/ archive/ exports/ templates/ materials/ avatars/` 前缀。
- `.env` 中设置 `STORAGE_BACKEND=minio` 与 `MINIO_*` 后，上传图、生成图、缩略图、模板/素材种子
  都通过 `app/modules/workspace/storage.py` 的统一门面读写；本地后端仍保留 `storage/` 目录。
- 4 号 generation 的预览/下载/缩略图统一使用 `media_response` / `read_image_bytes`，不直接依赖本地文件路径。
- 首次切换 MinIO 后执行一次 `python scripts/seed.py`，把模板/素材占位对象上传到桶内。

## 3. 演示账号

| 用户名 | 密码 | 角色 | 说明 |
| --- | --- | --- | --- |
| `demo_user` | `Demo1234` | `user` | 工作台、生成、下载权限 |
| `demo_admin` | `Demo1234` | `admin` | 无生成/历史权限，用于验证 403 |
| `demo_dual` | `Demo1234` | `user` + `admin` | 双角色演示 |

## 4. curl 验收

### 4.1 生图任务（4 号）

```bash
bash scripts/curl_smoke_generation.sh
```

- 脚本默认临时启动 8011 端口，使用真实豆包模型，结束后自动关闭。
- 脚本要求 `backend/.env` 已配置 Key 与模型，且已执行建表/种子。
- 本地无模型额度时，可用确定性测试替身验证接口契约：

```bash
APP_ENV=test GENERATION_MODEL_PROVIDER=fake AGENT_RETRY_BACKOFF_SCALE=0 \
  bash scripts/curl_smoke_generation.sh
```

### 4.2 创作工作台（2 号）

脚本会临时启动 8010 端口服务，逐条调用全部工作台接口，结束后自动关闭：

```bash
bash scripts/curl_smoke.sh
```

### 4.3 管理后台「账号与权限」（6 号）

脚本会临时启动 8016 端口服务（13 个接口 + 权限边界 + 日志双兼容）：

```bash
PYTHON=.venv/Scripts/python.exe bash scripts/curl_admin_smoke.sh
```

该脚本默认连接 `127.0.0.1:55433/esimage_admin`，可用 `DATABASE_URL` 覆盖；启动前会自动对目标库建表并写入幂等种子，新环境无需手工初始化。

> Windows Git Bash 中不要直接把中文 JSON 写进 `curl -d '...'`；脚本统一用 Python 生成 UTF-8 JSON 文件，再通过 `curl --data-binary @文件` 发送。

## 5. 测试

```bash
# 建议为本模块使用独立测试库，避免覆盖其他 agent 的 esimage_test
TEST_DB_NAME=esimage_generation_test python -m pytest
```

测试中的生成链路使用确定性模型替身（`APP_ENV=test`），不访问外网；真实模型验收由 curl 脚本负责。

## 6. 生图任务接口（4 号）

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| GET | `/api/v1/templates` | `user.generate` |
| GET | `/api/v1/templates/{id}/thumbnail` | `user.generate` |
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

管理端素材/模板/尺寸维护在 `/api/v1/admin/templates|materials|sizes`，与用户端只读接口隔离。
详细字段、错误码与 Agent 契约见
`docs/prd/4-生图任务与结果/接口文档-生图任务最小demo.md`。

## 7. 范围与限制

- 4 号生图链路使用 FastAPI `BackgroundTasks` + 统一对象存储门面（`STORAGE_BACKEND=local` 或 `minio`）+ 建表/幂等种子。
- 本地开发默认 Docker MinIO（API 9002 / 控制台 9003）；测试强制 `STORAGE_BACKEND=local`，不依赖真实 MinIO。
- 主分支另有 10 号 Alembic 数据底座、11 号 Celery/Redis 运维基线；4 号 demo 可按需切换。
- 生成配置（模板/素材/尺寸）用户端只读；后台维护入口在 `/api/v1/admin/templates|materials|sizes`。
- 整组 ZIP 与 `manifest.csv` 复用 5 号历史模块实现，4 号 `/batches/{id}/download` 直接使用同一契约。
- 只审核生成图，不审核上传商品图。
- 聊天轻链路仍是 2 号 demo 的行为，不触发生图。
- 不提供批次级重新生成；整批失败后从批次入口重新创建示例/全套。
- 质量审核若仅留白不足，不判整张失败，由文字合成加半透明底兜底。
