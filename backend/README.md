# ESImage 后端

FastAPI + SQLAlchemy + PostgreSQL 16。当前已实现：

- `auth`：登录、当前用户、退出登录（1 号 PRD 最小 demo）。
- `workspace`：创作工作台后端（2 号 PRD 最小 demo），含会话、聊天 SSE、商品图上传、示例图/全套生成、结果预览与单张下载。
- `admin`：管理后台（6/7/8 号 PRD 最小 demo），含账号与权限、角色权限点、操作日志、概览与 Token 统计、内容追溯、素材模板、系统提示词与模型配置。

## 1. 本地启动

在仓库根目录启动 PostgreSQL（独立容器与端口，避免和本机其他项目冲突）：

```bash
docker compose up -d
```

在 `backend/` 目录安装依赖并初始化数据：

```bash
python -m pip install -r requirements.txt

# 复制环境变量模板后按需修改
cp .env.example .env

python scripts/init_db.py
python scripts/seed.py
```

启动服务：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

> 若本机已有可用的 PostgreSQL（例如其他并行开发容器），可通过 `DATABASE_URL` 指向一个独立数据库，复用同一实例，不要覆盖其他项目的库。

## 2. 演示账号

| 用户名 | 密码 | 角色 | 说明 |
| --- | --- | --- | --- |
| `demo_super` | `Demo1234` | `super_admin` | 角色管理、操作日志与全部权限 |
| `demo_user` | `Demo1234` | `user` | 工作台、生成、下载权限 |
| `demo_admin` | `Demo1234` | `admin` | 无工作台权限，用于验证 403 |
| `demo_dual` | `Demo1234` | `user` + `admin` | 双角色演示 |

## 3. curl 验收

工作台验收脚本会临时启动 8010 端口服务，逐条调用全部工作台接口，结束后自动关闭：

```bash
bash scripts/curl_smoke.sh
```

管理后台「账号与权限」验收脚本会临时启动 8016 端口服务（13 个接口 + 权限边界 + 日志双兼容）：

```bash
PYTHON=.venv/Scripts/python.exe bash scripts/curl_admin_smoke.sh
```

该脚本默认连接 `127.0.0.1:55433/esimage_admin`，可用 `DATABASE_URL` 覆盖；启动前会自动对目标库建表并写入幂等种子，新环境无需手工初始化。

工作台脚本默认连接 `127.0.0.1:55433/esimage`（与 `docker compose` 和 `.env.example` 一致）。并行开发时建议为本模块使用独立库，例如：

```bash
docker exec esimage-postgres psql -U esimage -d postgres -c "CREATE DATABASE esimage_workspace"
DATABASE_URL=postgresql+psycopg://esimage:esimage@127.0.0.1:55433/esimage_workspace bash scripts/curl_smoke.sh
```

脚本用 Python 生成 UTF-8 JSON 请求体，再通过 `curl --data-binary @文件` 发送；在 Windows Git Bash 中不要直接把中文 JSON 写进 `-d '...'`，终端可能按本地编码传递导致 400。

> 并行开发时建议为本模块使用独立数据库（如 `esimage_workspace`），不要覆盖登录等其他模块的开发库。

## 4. 测试

```bash
python -m pytest
```

测试默认使用 `127.0.0.1:55433` 的 `esimage_test` 库；并行开发时可用独立库：

```bash
TEST_DB_NAME=esimage_workspace_test python -m pytest
```

## 5. 最小 demo 范围与限制

- 异步任务：FastAPI `BackgroundTasks` + 轮询，不接 Celery/Redis。
- 对象存储：本地目录适配层（`STORAGE_ROOT`），不接 MinIO。
- 聊天：未配置文本模型时返回固定演示回复，不调用真实规划/商品理解模型。
- 生成：演示管线产出占位 PNG，不调用真实豆包模型。
- 尺寸固定 1000×1000（接口仍接受正整数宽高，但演示管线上限 4096，防止占位图 OOM）；不支持模板、尺寸预设、取消任务、单张重生成、整组 ZIP。
- 上传图限制 10MB 且解码后不超过 4000 万像素。
- 幂等键 `client_message_id` / `client_request_id` 按接口文档要求为 UUID。
- 不做历史作品、个人中心、管理后台真实页面。
- 内容审核、Token 计费、审计日志（登录除外）不在本最小 demo 内。
