# 部署与运维最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `./11-部署与运维prd.md` §4~§13；`../9-后端服务与接口/9-后端服务与接口prd.md` §2~§4；`../10-数据模型与存储/10-数据模型与存储prd.md` §6~§10 |
| 覆盖范围 | 双健康探针、网关入口与 SSE、Compose 内部服务契约、运维脚本 CLI、定时任务、日志与 request_id、错误与降级 |
| 文档状态 | 最小 demo 约定；不裁决 9 号统一响应与 11 号健康结构的冲突，按双路径并存记录 |

> 本文档的「接口」包含三类：**HTTP 探针接口**、**网关入口契约**、**运维脚本与定时任务 CLI 契约**。除两个健康接口与一个演示专用 SSE 探针外，本 demo 不新增任何业务 HTTP 接口；登录、会话、上传、生成、历史、管理后台等接口以 1~9 号 demo 的接口文档为准。

---

## 1. 通用约定

### 1.1 地址与端口

| 项目 | 约定 |
| --- | --- |
| 宿主机入口 | `http://<host>/`，只暴露 80；443 仅保留注释模板 |
| API 根路径 | `http://<host>/api`；业务接口统一 `/api/v1` |
| 容器内地址 | `backend:8000`、`frontend:8080`、`postgres:5432`、`redis:6379`、`minio:9000` |
| 内部服务 | 不发布宿主机端口；仅通过 `esimage_net` 互通 |
| 时区 | 全栈 `Asia/Shanghai`；时间字段为 ISO 8601 带时区 |
| 编码 | `application/json; charset=utf-8`；SSE 为 `text/event-stream` |
| 字段命名 | `snake_case`；空值为 `null` 且不省略键；布尔为 `true` / `false` |

### 1.2 请求 ID

| 项目 | 约定 |
| --- | --- |
| 请求头 | `X-Request-ID` |
| 复用规则 | 入站值匹配 `^[A-Za-z0-9_-]{8,64}$` 时复用；否则忽略并生成 UUIDv4 |
| 响应头 | 每个 HTTP 响应返回最终使用的 `X-Request-ID` |
| 日志关联 | 同一请求的 backend 日志、Worker 任务日志使用同一 ID |
| 安全 | 非法或超长值不入日志，避免头注入 |

### 1.3 统一响应与例外

除 SSE、文件流与健康裸探针外，`/api/v1` 接口返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

| 例外 | 说明 |
| --- | --- |
| `GET /api/health` | 按 11 号 §8.3 返回 `{status, checks}`，直接供容器与网关探活 |
| `GET /api/v1/sessions/_probe/stream` | SSE 事件流，不使用 JSON 包装 |
| Nginx 413 / 502 / 504 | 由网关直接返回，不经过应用统一响应 |

> 双健康接口的差异见 §2.3；正式实现是否保留 `/api/v1/health` 见 §10 第 1、2 项。

---

## 2. HTTP 健康探针

### 2.1 `GET /api/health`

**用途**：容器健康检查、Nginx 探活、宿主机监控脚本。

| 项目 | 约定 |
| --- | --- |
| 方法 | `GET` |
| 路径 | `/api/health` |
| 鉴权 | 无 |
| 参数 | 无 |
| 缓存 | `Cache-Control: no-store` |
| 成功状态 | HTTP 200 |
| 降级状态 | HTTP 503 |

**成功响应**

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "minio": "ok"
  }
}
```

**降级响应（以 Redis 不可用为例）**

```json
{
  "status": "degraded",
  "checks": {
    "database": "ok",
    "redis": "error",
    "minio": "ok"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string | 全部依赖正常为 `ok`；任一失败为 `degraded` |
| `checks.database` | string | `ok` / `error` |
| `checks.redis` | string | `ok` / `error` |
| `checks.minio` | string | `ok` / `error` |

**检测规则**

| 依赖 | 检测方式 | 超时 | 失败值 |
| --- | --- | --- | --- |
| PostgreSQL | 执行轻量查询 | 2 秒 | `error` |
| Redis | `PING` | 2 秒 | `error` |
| MinIO | 检查 `esimage` 桶存在 | 2 秒 | `error` |

- 三项并发检测，整体不超过 5 秒；单项失败不阻断其他项。
- 降级时仍返回全部三项状态，便于定位。
- 依赖恢复后下一次请求立即返回 200，无需重启。
- 响应不返回堆栈、SQL、DSN、内部地址、密钥或上游错误。
- 请求与响应均带 `X-Request-ID`，日志可关联。

**curl 示例**

```bash
curl -i http://localhost/api/health
curl -i -H "X-Request-ID: demo-health-0001" http://localhost/api/health
```

### 2.2 `GET /api/v1/health`

**用途**：需要统一响应结构的调用方（前端、契约回归、后续监控面板）。

| 项目 | 约定 |
| --- | --- |
| 方法 | `GET` |
| 路径 | `/api/v1/health` |
| 鉴权 | 无（探针例外） |
| 参数 | 无 |
| 缓存 | `Cache-Control: no-store` |
| 成功状态 | HTTP 200，`code=0` |
| 降级状态 | HTTP 503，`code=50001` |

**成功响应**

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "status": "ok",
    "checks": {
      "database": "ok",
      "redis": "ok",
      "minio": "ok"
    }
  }
}
```

**降级响应**

```json
{
  "code": 50001,
  "message": "服务依赖不可用",
  "data": {
    "status": "degraded",
    "checks": {
      "database": "ok",
      "redis": "error",
      "minio": "ok"
    }
  }
}
```

- 与 `/api/health` 共用同一次检测结果，不重复探活。
- 降级时 HTTP 503 是 11 号 §8.3 的要求；业务码 `50001` 沿用 9 号「系统内部错误」。9 号错误码表把 `5xxx` 映射到 HTTP 500，此处存在跨文档差异，见 §10 第 1 项。
- 其余字段、检测规则、超时与安全要求同 §2.1。

### 2.3 双路径关系

```text
同一个健康检测结果
        ├── GET /api/health       → {status, checks}                  （11 号原文，探针）
        └── GET /api/v1/health    → {code, message, data:{...}}       （9 号统一响应）
```

- 两者不缓存、不鉴权、不写业务数据。
- 容器健康检查固定使用 `/api/health`；网关健康检查固定使用 `/api/health`。
- `/api/v1/health` 只用于需要统一响应的消费者，不替代容器探针。

### 2.4 演示专用 SSE 探针

`GET /api/v1/sessions/_probe/stream`

**用途**：在聊天业务尚未落地时验证 Nginx 对 SSE 不缓冲。**不是产品接口**，生产环境返回 404，不进入 OpenAPI。

| 项目 | 约定 |
| --- | --- |
| 启用条件 | `APP_ENV != production` |
| 鉴权 | 无 |
| 参数 | 无 |
| 响应头 | `Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`、`Connection: keep-alive` |
| 事件顺序 | `meta` → 多条 `delta`（每 1 秒一条）→ `done` |
| 心跳 | 无事件时每 15 秒发送 `ping` |
| 断开 | 客户端断开后停止发送，不产生业务数据 |

**事件帧示例**

```text
event: meta
data: {"probe":true,"request_id":"demo-sse-0001"}

event: delta
data: {"seq":1,"text":"逐"}

event: delta
data: {"seq":2,"text":"字"}

event: ping
data: {"ts":"2026-10-31T10:00:15+08:00"}

event: done
data: {"probe":true,"seq":2}
```

- 事件名与 9 号 SSE 基线保持一致，便于后续替换为真实聊天事件。
- 生产环境不注册该路由；若被请求返回 404，不泄露演示信息。

---

## 3. 网关契约（Nginx）

### 3.1 路由表

| 优先级 | 路径 | 目标 | 关键配置 |
| --- | --- | --- | --- |
| 1 | `/api/v1/sessions/` | `backend:8000` | `proxy_buffering off`、`proxy_cache off`、`Connection ""`、读超时 300s |
| 2 | `/api/docs`、`/api/openapi.json` | `backend:8000` | 仅回环与 RFC1918 可访问，其余 403 |
| 3 | `/api/` | `backend:8000` | HTTP/1.1、读超时 300s |
| 4 | `/` | `frontend:8080` | 静态资源与占位页 |

- Nginx 前缀匹配取最长匹配，因此 `/api/v1/sessions/` 优先于 `/api/`。
- 所有代理请求保留 `Host`、`X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto`。
- 同源部署，不启用 CORS；`CORS_ORIGINS` 留空。

### 3.2 SSE 要求

| 要求 | 值 |
| --- | --- |
| 缓冲 | 关闭（`proxy_buffering off`） |
| 缓存 | 关闭（`proxy_cache off`） |
| 连接头 | 清空 `Connection`，使用 HTTP/1.1 |
| 读超时 | 300 秒 |
| 应用响应头 | `Cache-Control: no-cache`、`X-Accel-Buffering: no` |
| 心跳 | 15 秒无事件发送 `ping`，由应用产生，网关透传 |

- 验收标准：`delta` 事件按 1 秒节奏逐条到达；若网关缓冲，客户端会在连接结束后一次性收到全部事件，判定失败。
- 聊天业务接线后，路径 `/api/v1/sessions/` 保持不变，无需改网关。

### 3.3 上传与超时

| 项目 | 约定 |
| --- | --- |
| `client_max_body_size` | 12m（10MB 文件 + 表单开销） |
| 10MB 请求 | 不返回 413，转发到 backend；backend 未实现上传时返回 404/405 亦视为通过 |
| 超过 12MB | 返回 413，请求不进入 backend |
| API 读超时 | 300 秒 |
| 生成/上传接口 | 不低于 300 秒 |

### 3.4 静态资源

| 项目 | 约定 |
| --- | --- |
| gzip | JS、CSS、JSON、SVG、字体启用 |
| 哈希静态资源 | 长缓存（`immutable`） |
| `index.html` | 不缓存，保证发版后拿到新入口 |
| 占位页 | `GET /` 返回 200 |

### 3.5 安全响应头

| 头 | 值 |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |

- 使用 `add_header ... always`，保证 403、413、502、504 等错误响应也带安全头。
- 取值为 demo 约定，PRD 未规定；见 §10 第 6 项。

### 3.6 文档访问限制

- `/api/docs` 与 `/api/openapi.json` 仅允许 `127.0.0.1/32`、`::1/128`、`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16` 访问。
- 其他来源返回 403，不返回文档内容。
- 该限制在网关层完成，不依赖后端鉴权。

### 3.7 网关错误

| 状态 | 场景 | 处理 |
| --- | --- | --- |
| 502 | backend 未启动或崩溃 | 查看 backend 日志与 `/api/health` |
| 504 | 上游超过 300 秒 | 查看 backend 与生成任务日志 |
| 413 | 请求体超过 12m | 调整文件大小或 `client_max_body_size` |
| 403 | 非内网访问 `/api/docs` | 从内网访问或临时调整允许网段 |

- 413 使用 Nginx 默认 HTML 响应，不包装统一 JSON；见 §10 第 9 项。

---

## 4. 内部服务契约（Compose）

### 4.1 服务

| 服务 | 镜像 / 构建 | 容器端口 | 宿主机端口 | 健康检查 | 重启策略 |
| --- | --- | --- | --- | --- | --- |
| `nginx` | `nginx:stable` | 80 / 443 | 80（443 注释） | 经网关 `GET /api/health` | `unless-stopped` |
| `frontend` | 多阶段构建 + `nginx:stable` | 8080 | 无 | `GET /` | `unless-stopped` |
| `backend` | Python 3.11 + FastAPI | 8000 | 无 | `GET /api/health` | `unless-stopped` |
| `migrate` | 同 backend 镜像 | 无 | 无 | 退出码 0 | `"no"` |
| `worker` | 同 backend 镜像 | 无 | 无 | `celery inspect ping`（运维检查） | `unless-stopped` |
| `beat` | 同 backend 镜像 | 无 | 无 | 进程存活 + 日志 | `unless-stopped` |
| `postgres` | `postgres:16` | 5432 | 无 | `pg_isready` | `unless-stopped` |
| `redis` | `redis:7` | 6379 | 无 | `redis-cli ping` | `unless-stopped` |
| `minio` | `minio/minio` | 9000 / 9001 | 无 | `/minio/health/live` | `unless-stopped` |
| `minio-init` | `minio/mc` | 无 | 无 | 退出码 0 | `"no"` |

### 4.2 网络与卷

| 项目 | 约定 |
| --- | --- |
| 网络 | 单一 bridge `esimage_net` |
| 宿主机暴露 | 只有 `nginx` 的 80；443 模板保留 |
| 卷 | `pgdata`、`redisdata`、`miniodata`、`applogs`、`nginxlogs`、`backup` |
| 卷持久化 | `docker compose down` 不删除；禁止生产使用 `down -v` |
| MinIO 桶 | `esimage` 桶不公开，不设置匿名读写策略；所有访问经后端鉴权 |

| 卷 | 挂载点 | 用途 |
| --- | --- | --- |
| `pgdata` | PostgreSQL 数据目录 | 数据库数据 |
| `redisdata` | `/data` | Redis 持久化（可选） |
| `miniodata` | `/data` | MinIO 对象数据 |
| `applogs` | `/app/logs` | backend / worker / beat 日志 |
| `nginxlogs` | `/var/log/nginx` | 访问与错误日志 |
| `backup` | `/backup` | 数据库与 MinIO 备份 |

### 4.3 环境变量

#### 必填

| 变量 | 示例 / 说明 |
| --- | --- |
| `APP_ENV` | `development` / `production` |
| `TZ` | `Asia/Shanghai` |
| `SECRET_KEY` | 应用通用密钥 |
| `JWT_SECRET` | JWT 签名密钥 |
| `DATABASE_URL` | `postgresql+psycopg://user:pass@postgres:5432/esimage` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `MINIO_ENDPOINT` | `minio:9000` |
| `MINIO_ACCESS_KEY` | MinIO 访问键 |
| `MINIO_SECRET_KEY` | MinIO 密钥 |
| `MINIO_BUCKET` | `esimage` |
| `ENCRYPTION_KEY` | 32 字节 Base64，模型 API Key 加密密钥 |
| `ADMIN_INITIAL_USERNAME` | 初始超管用户名，满足 `^[A-Za-z0-9_]{4,20}$` |
| `ADMIN_INITIAL_PASSWORD` | 初始超管密码，首次初始化必填 |

#### 可选 / 调优

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `JWT_ACCESS_HOURS` | 24 | 普通登录有效期 |
| `JWT_REMEMBER_DAYS` | 7 | 记住我有效期 |
| `ARK_BASE_URL` | 火山方舟地址 | 豆包 API 地址 |
| `ARK_API_KEY` | 空 | 首次启动兜底 Key；后台配置优先 |
| `CORS_ORIGINS` | 空 | 同源部署留空 |
| `MAX_UPLOAD_MB` | 10 | 单文件上限 |
| `MAX_UPLOADS_PER_SESSION` | 5 | 每会话上传上限 |
| `GENERATION_TIMEOUT_SECONDS` | 120 | 单张生图超时 |
| `BATCH_TIMEOUT_SECONDS` | 1800 | 整批超时 |
| `WORKER_CONCURRENCY` | 4 | Worker 并发数 |
| `EXPORT_TTL_HOURS` | 24 | 导出文件有效期 |
| `ARCHIVE_RETENTION_YEARS` | 5 | 热存年限 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_RETENTION_DAYS` | 90 | 应用日志保留天数 |
| `BACKUP_RETAIN_DAYS` | 7 | 备份保留天数 |

- `.env` 不提交 Git，权限 600；生产密钥与开发密钥分离。
- 更换 `JWT_SECRET` 会使全部已签发 token 失效；更换 `ENCRYPTION_KEY` 需先解密再重加密模型 API Key。
- 镜像不硬编码密钥，全部通过环境变量注入。

### 4.4 启动顺序

```text
postgres / redis / minio 全部 healthy
        ↓
minio-init 退出码 0
        ↓
migrate 退出码 0（Alembic + 种子 + 初始超管）
        ↓
backend healthy
        ├── worker（backend started + redis healthy）
        ├── beat（backend started + redis healthy）
        ├── frontend（healthy）
        └── nginx（frontend started + backend healthy）
```

- 首次部署与日常更新均先执行 `migrate` 再启动应用服务，符合 11 号 §8.1 与 §8.2。
- 迁移失败时应用服务不启动；启动脚本以非 0 退出。

---

## 5. 运维脚本 CLI 契约

### 5.1 通用约定

| 项目 | 约定 |
| --- | --- |
| 解释器 | `bash` |
| 工作目录 | 仓库根目录或脚本所在目录，脚本自行定位 Compose 文件 |
| 配置来源 | `.env` 与进程环境变量；`.env` 优先用于本地演示 |
| 日志 | 中文；时间戳 + 步骤 + 结果；错误写 stderr |
| 幂等 | 可重复执行，不重复建卷、不重复插种子、不覆盖已有数据 |
| 退出码 | 见 §8.2 |

### 5.2 `demo_up.sh`

```text
demo_up.sh [--no-build]
```

| 参数 | 说明 |
| --- | --- |
| `--no-build` | 跳过镜像构建，使用现有镜像 |

**行为**

1. 检查 Docker、Compose v2、80 端口、`.env` 与必填变量。
2. 构建镜像（除非 `--no-build`）。
3. 启动 postgres、redis、minio，等待三者 healthy。
4. 执行 `migrate`，失败即停。
5. 启动 backend、worker、beat、frontend、nginx，等待 backend/frontend/nginx 健康。
6. 输出访问地址、日志与备份目录、初始超管用户名来源。

**退出码**：0 成功；2 参数错误；3 前置条件不满足；4 健康等待超时；5 迁移或启动失败。

### 5.3 `demo_verify.sh`

```text
demo_verify.sh [--verbose]
```

- 逐项执行本书 §9 的验收用例。
- 每个用例输出：用例名、请求/操作、预期、实际、结论。
- 任一失败立即非 0 退出，保留现场；`--verbose` 输出完整命令与日志片段。
- 不依赖人工点击、不手工改库；测试数据由脚本准备与清理。
- 退出码：0 全部通过；5 存在失败用例。

### 5.4 `demo_down.sh`

```text
demo_down.sh [--purge]
```

| 参数 | 说明 |
| --- | --- |
| 默认 | 停止容器，保留全部命名卷 |
| `--purge` | 停止并删除卷，仅用于演示环境清理；执行前二次确认 |

- 帮助信息明确警告：生产禁止 `docker compose down -v`。
- 退出码：0 成功；2 参数错误；6 停止失败。

### 5.5 `backup_db.sh`

```text
backup_db.sh
```

| 项目 | 约定 |
| --- | --- |
| 触发 | 宿主机 cron 每日 02:00；也可手动执行 |
| 命令 | `pg_dump -Fc` 经 Compose 在 postgres 容器内执行 |
| 输出 | `/backup/esimage_db_{yyyyMMdd}.dump` |
| 校验 | 文件存在、大小 > 0、`pg_restore -l` 可读 |
| 保留 | 按 `BACKUP_RETAIN_DAYS`（默认 7）删除过期 `esimage_db_*.dump` |
| 日志 | 开始/结束时间、路径、大小、校验、耗时、结果 |
| 退出码 | 0 成功；6 备份或校验失败 |

### 5.6 `backup_minio.sh`

```text
backup_minio.sh
```

| 项目 | 约定 |
| --- | --- |
| 触发 | 宿主机 cron 每日 02:30；也可手动执行 |
| 命令 | `mc mirror` 将 `esimage` 桶镜像到备份目录 |
| 输出 | `/backup/esimage_minio_{yyyyMMdd}/` |
| 校验 | 目录存在、对象数 > 0 |
| 保留 | 按 `BACKUP_RETAIN_DAYS`（默认 7）删除过期目录 |
| 日志 | 开始/结束时间、路径、对象数、耗时、结果 |
| 退出码 | 0 成功；6 备份或校验失败 |

### 5.7 `restore.sh`

```text
restore.sh --db <esimage_db_yyyyMMdd.dump> --minio <esimage_minio_yyyyMMdd> --yes
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--db` | 是 | 数据库转储路径（位于 `backup` 卷） |
| `--minio` | 是 | MinIO 备份目录名 |
| `--yes` | 是 | 确认执行；缺少时退出且不改动数据 |

**行为**

1. 校验备份文件/目录存在且可读。
2. 停止 backend、worker、beat。
3. `pg_restore` 恢复数据库（demo 栈使用 `--clean --if-exists`）。
4. `mc mirror` 恢复 MinIO 对象。
5. 启动 backend、worker、beat。
6. 调用两个健康接口，检查关键种子数据。
7. 输出恢复耗时、数据库对象数、MinIO 对象数、健康结果。

**退出码**：0 成功；2 参数错误；6 恢复失败；4 健康检查超时。

---

## 6. 定时任务契约

### 6.1 宿主机 cron

| 时间 | 任务 | 说明 |
| --- | --- | --- |
| 每日 02:00 | `backup_db.sh` | PostgreSQL `pg_dump -Fc` |
| 每日 02:30 | `backup_minio.sh` | MinIO `mc mirror` |
| 每日（建议 03:30） | `logrotate` | Nginx 访问/错误日志轮转，保留 90 天 |

- 备份由宿主机 cron 执行，不随应用生命周期耦合。
- cron 文件随仓库交付，部署人按实际路径安装；安装后 `crontab -l` 可见。
- 备份失败通过脚本非 0 退出与日志体现；邮件/IM 告警不在本 demo。

### 6.2 Celery Beat

| 项目 | 约定 |
| --- | --- |
| 时区 | `Asia/Shanghai` |
| 调度表 | 本 demo 为空，不注册业务任务 |
| 运行时 | 随 Compose 启动，日志写入 `beat.log` |
| 失败 | 调度配置错误时启动失败并输出原因 |

### 6.3 `ops.selftest`

**演示专用任务**，仅 `APP_ENV != production` 注册。

| 项目 | 约定 |
| --- | --- |
| 任务名 | `ops.selftest` |
| 参数 | `request_id`（可选，字符串）、`delay_ms`（可选，整数，默认 0） |
| 返回 | `{status:"ok", request_id:"...", duration_ms:123}` |
| 日志 | JSON；包含开始、结束、耗时、结果与 `request_id` |
| 用途 | 验证 Worker 可执行、队列连通、request_id 从 HTTP 透传到 Worker |

**手动触发示例**

```bash
docker compose exec backend celery -A <app> call ops.selftest --kwargs '{"request_id":"demo-selftest-0001","delay_ms":100}'
docker compose exec backend celery -A <app> inspect registered
docker compose exec backend celery -A <app> inspect ping
```

### 6.4 明确未实现的定时任务

| 任务 | PRD 频率 | 本 demo 处理 |
| --- | --- | --- |
| 5 年归档 | 每日 03:00 | 不做；Worker/Beat 仅保留基线 |
| 孤儿上传清理 | 每日 04:00 | 不做；依赖上传业务链路 |
| 导出文件清理 | 每小时 | 不做；导出功能未实现 |
| 权限缓存刷新 | 权限变更时 | 不做；本 demo 未接权限缓存 |

---

## 7. 日志契约

### 7.1 应用日志字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `time` | string | 是 | ISO 8601 带时区，`Asia/Shanghai` |
| `level` | string | 是 | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `module` | string | 是 | 模块或 logger 名 |
| `request_id` | string | 是 | 请求或任务关联 ID；无请求时为新生成或空任务 ID |
| `user_id` | int / null | 是 | 已登录用户 ID；无用户时为 `null`，键不省略 |
| `message` | string | 是 | 可读消息 |
| 其他 | any | 否 | 业务上下文，禁止敏感信息 |

**示例**

```json
{"time":"2026-10-31T10:00:00+08:00","level":"INFO","module":"health","request_id":"demo-health-0001","user_id":null,"message":"health check completed","status":"ok"}
```

### 7.2 文件与轮转

| 日志 | 位置 | 轮转 | 保留 |
| --- | --- | --- | --- |
| backend | `applogs/backend.log` + stdout | 按天 | `LOG_RETENTION_DAYS`（默认 90），压缩 |
| worker | `applogs/worker.log` + stdout | 按天 | 同上 |
| beat | `applogs/beat.log` + stdout | 按天 | 同上 |
| Nginx 访问 | `nginxlogs/access.log` | 宿主机 logrotate 每日 | 90 天，压缩 |
| Nginx 错误 | `nginxlogs/error.log` | 宿主机 logrotate 每日 | 90 天，压缩 |

- 应用侧使用 TimedRotatingFileHandler；同一进程只注册一次 handler。
- 容器 stdout 使用 json-file，单文件 10MB、保留 3 个。
- 日志文件不提交 Git。

### 7.3 敏感信息

禁止记录：

- 密码、密码哈希、重置密码明文。
- JWT、`Authorization` 头、`JWT_SECRET`。
- 豆包 API Key、`ENCRYPTION_KEY`、MinIO 访问键/密钥。
- 完整身份证号、完整手机号、完整银行卡号。
- 上传文件内容、完整请求体/响应体。

错误日志只记录错误类型、业务码、`request_id` 与必要上下文。

### 7.4 审计日志

- 审计日志写入数据库 `audit_logs`，不依赖文件日志。
- 本 demo 不实现审计动作与查询接口；表结构与保留期由 10 号定义。
- 正式实现覆盖登录、账号、权限、配置、提示词、导出等操作，详情字段脱敏。

---

## 8. 错误与状态总表

### 8.1 HTTP 状态

| 状态 | 场景 | 响应来源 |
| --- | --- | --- |
| 200 | 健康、占位页、正常 API | backend / frontend |
| 403 | 非内网访问 `/api/docs` | nginx |
| 404 | 生产环境请求 SSE 演示探针 | backend |
| 413 | 请求体超过 12m | nginx |
| 502 | backend 未启动或崩溃 | nginx |
| 503 | 健康探针降级（任一依赖不可用） | backend |
| 504 | 上游超过 300 秒 | nginx |

### 8.2 脚本退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 2 | 参数错误 |
| 3 | 前置条件不满足 |
| 4 | 健康检查或等待超时 |
| 5 | 验收用例失败 / 迁移失败 |
| 6 | 备份、恢复或停止失败 |

---

## 9. 验收覆盖矩阵

### 9.1 演示步骤

| # | 用例 | 预期 | Ticket |
| --- | --- | --- | --- |
| 1 | 干净机器执行 `demo_up.sh` | 全部长驻服务健康；只有 nginx 发布 80 | 08 |
| 2 | 重复执行 `migrate` | 退出码 0；无重复种子；超管不重建 | 02 |
| 3 | 清空/弱化初始密码后执行 `migrate` | 非 0 退出；中文提示明确 | 02 |
| 4 | `GET /api/health` | 200，三项 `ok` | 03 |
| 5 | `GET /api/v1/health` | 200，`code=0`，`data` 含三项 `ok` | 03 |
| 6 | 停止 Redis 后请求两个健康接口 | 503，`degraded`，`checks.redis="error"` | 03 |
| 7 | 恢复 Redis 后再次请求 | 200；无需重启 backend | 03 |
| 8 | 经网关 `GET /` 与 `GET /api/health` | 均 200 | 04 |
| 9 | 非内网访问 `/api/docs` | 403 | 04 |
| 10 | 经网关发送 10MB / 13MB 请求 | 10MB 非 413；13MB 返回 413 | 04 |
| 11 | 请求 SSE 演示探针 | `meta` → `delta`（逐秒）→ `done`；含 `ping` 与 `X-Accel-Buffering: no` | 04 |
| 12 | 检查响应头与日志 | `X-Request-ID` 一致；日志为 JSON；无敏感信息 | 05 |
| 13 | 触发日志轮转 | 生成 `.gz`；保留份数符合配置 | 05 |
| 14 | 执行两类备份 | 命名、大小、可读性、保留 7 天符合约定 | 06 |
| 15 | 删除一条尺寸预设与一个 MinIO 对象后执行恢复 | 数据与对象恢复；两个健康接口 200 | 06 |
| 16 | `celery inspect ping` / `ops.selftest` | pong；任务返回 `ok` 且日志含同一 `request_id` | 07 |
| 17 | Beat 启动 | 时区 `Asia/Shanghai`；无业务调度 | 07 |
| 18 | `demo_down.sh` 后重新 `demo_up.sh` | 卷保留；数据仍在 | 08 |

### 9.2 11 号 §14 覆盖

| 11 号 §14 | 覆盖 | 说明 |
| --- | --- | --- |
| 1. 一键启动全部服务 | 是 | 08 |
| 2. 只有 nginx 暴露端口 | 是 | 01、08 |
| 3. 迁移与种子，初始超管可登录 | 部分 | 02；登录属 1 号 demo |
| 4. `/api/health` 反映三依赖 | 是 | 03 |
| 5. Nginx 代理与 SSE 不缓冲 | 是 | 04 |
| 6. 10MB 不被 413 | 是 | 04 |
| 7. 日志轮转 90 天；审计 5 年 | 部分 | 05；审计业务属 6/9 号 demo |
| 8. 每日备份、保留 7 天、可恢复 | 是 | 06 |
| 9. 归档任务每日执行 | 否 | 按确认不做归档 |
| 10. 导出 24 小时清理 | 否 | 导出未实现 |
| 11. 密钥不入库、不硬编码、不写日志 | 是 | 01、03、05 |
| 12. 常见故障可定位 | 是 | §3.7、§7、README §7.4 |

---

## 10. 待确认项

1. **双健康接口的响应差异**：`/api/health` 保持 11 号裸结构，`/api/v1/health` 返回 9 号统一响应。后者降级时使用 HTTP 503 + `50001`，与 9 号「`5xxx` 对应 HTTP 500」不一致；需要统一确认。
2. **健康接口鉴权**：9 号要求除登录外所有接口校验 JWT；本 demo 两个健康接口与 SSE 探针均不鉴权。正式实现是否保留 `/api/v1/health`、是否需要鉴权待定。
3. **`X-Request-ID` 头名与格式**：PRD 未定义；demo 约定 `X-Request-ID` 与 `[A-Za-z0-9_-]{8,64}`。
4. **健康检查失败值**：demo 使用 `ok` / `error`；是否需要 `down`、`timeout` 等细分待定。
5. **健康检查超时**：demo 约定单依赖 2 秒、整体 5 秒；PRD 未定义。
6. **安全响应头取值**：demo 使用 `SAMEORIGIN` 与 `strict-origin-when-cross-origin`；是否改为 `DENY` 待定。
7. **初始超管强密码规则**：demo 约定长度 ≥12 且至少 3 类字符；PRD 只要求「不得使用默认弱口令」。
8. **演示专用接口与任务**：`GET /api/v1/sessions/_probe/stream` 与 `ops.selftest` 是否保留为长期运维自检能力，还是正式实现前删除。
9. **413 响应体**：demo 使用 Nginx 默认 HTML；是否需要统一 JSON 错误页待定。
10. **恢复覆盖语义**：demo 在一次性栈使用 `pg_restore --clean --if-exists`；生产是否允许 drop 现有对象待运维确认。
11. **Nginx 日志轮转方式**：demo 使用宿主机 logrotate；是否改为容器内 sidecar 待定。
12. **MinIO 前缀创建**：前缀为虚拟目录；demo 用临时探针对象验证后删除，不保留 `.keep` 对象。
13. **Worker/Beat 空调度**：本 demo 不注册业务定时任务；归档、孤儿清理、导出清理的频率与重试策略留待正式实现。
14. **容器 stdout 保留**：demo 约定单文件 10MB、保留 3 个；PRD 未定义，需与磁盘预算统一。
