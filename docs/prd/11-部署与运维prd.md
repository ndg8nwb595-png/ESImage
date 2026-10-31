# 11-部署与运维 PRD

| 项目 | 内容 |
| --- | --- |
| 文档编号 | 11 |
| 文档名称 | 部署与运维 PRD |
| 版本 | v0.1 |
| 编写日期 | 2026-10-31 |
| 文档状态 | 待评审 |
| 上游文档 | `0-系统汇总prd.md` |
| 关联文档 | `9-后端服务与接口prd.md`、`10-数据模型与存储prd.md` |
| 术语依据 | `GLOSSARY.md` |

---

## 1. 文档目的与范围

### 1.1 目的

定义系统在单机 Docker Compose 下的部署拓扑、服务与端口、数据卷、环境变量、Nginx 配置、启动顺序、日志、备份、定时任务、安全与排障规则。

### 1.2 本期范围

- 单机 Docker Compose 部署。
- 服务、端口、网络、卷。
- 环境变量与密钥管理。
- Nginx 反向代理与 SSE 配置。
- 启动顺序、数据库迁移与种子数据。
- 日志保留。
- 每日备份与恢复。
- 归档与清理定时任务。
- 基础监控与排障。

### 1.3 不做

- Kubernetes、多机集群、自动扩缩容。
- 蓝绿发布、灰度发布。
- Prometheus/Grafana 全套监控。
- 跨地域容灾。
- 云厂商托管数据库/对象存储（本期自建）。

---

## 2. 环境

| 环境 | 用途 | 说明 |
| --- | --- | --- |
| 本地开发 | 开发调试 | Docker Compose，端口可映射到本机 |
| 生产/内网 | 内部使用 | 单机 Docker Compose，内网访问 |

- 生产环境时区统一 `Asia/Shanghai`。
- 生产环境不开放公网访问，除非明确需要并配置 HTTPS 与防火墙。
- 生产环境数据库、Redis、MinIO 不对宿主机暴露端口。

---

## 3. 部署拓扑

```
                 ┌─────────────────────────────┐
                 │  浏览器（内网）              │
                 └──────────────┬──────────────┘
                                │ 80/443
                 ┌──────────────▼──────────────┐
                 │  nginx（网关）               │
                 │  /        → frontend:8080   │
                 │  /api/v1  → backend:8000    │
                 └──────┬───────────────┬──────┘
                        │               │
              ┌─────────▼─────┐  ┌──────▼─────────┐
              │ frontend      │  │ backend        │
              │ 静态资源       │  │ FastAPI        │
              └───────────────┘  └──┬───┬───┬─────┘
                                    │   │   │
                     ┌──────────────┘   │   └──────────────┐
                     │                  │                  │
              ┌──────▼──────┐   ┌───────▼──────┐   ┌───────▼──────┐
              │ PostgreSQL  │   │ Redis        │   │ MinIO        │
              └─────────────┘   └───────┬──────┘   └──────────────┘
                                        │
                                ┌───────▼────────┐
                                │ worker / beat  │
                                │ Celery         │
                                └───────┬────────┘
                                        │
                                ┌───────▼────────┐
                                │ 豆包（火山方舟）│
                                │ 文本 / 图像 / 审核 │
                                └────────────────┘
```

---

## 4. Compose 服务

| 服务 | 镜像/构建 | 端口 | 说明 |
| --- | --- | --- | --- |
| `nginx` | nginx:stable | 80 / 443 | 网关，静态与 API 反向代理 |
| `frontend` | 多阶段构建 + nginx:stable | 8080（内部） | 前端静态资源 |
| `backend` | Python 3.11 + FastAPI | 8000（内部） | API 服务 |
| `migrate` | 同 backend 镜像 | 无 | 一次性执行 Alembic 迁移与种子 |
| `worker` | 同 backend 镜像 | 无 | Celery Worker，默认并发 4 |
| `beat` | 同 backend 镜像 | 无 | Celery Beat，定时任务 |
| `postgres` | postgres:16 | 5432（内部） | 数据库 |
| `redis` | redis:7 | 6379（内部） | 缓存与队列 |
| `minio` | minio/minio | 9000/9001（内部） | 对象存储 |
| `minio-init` | minio/mc | 无 | 一次性创建桶与前缀 |

### 4.1 网络

- 单一 bridge 网络 `esimage_net`。
- 只有 `nginx` 对宿主机暴露端口。
- `backend`、`worker`、`beat`、`postgres`、`redis`、`minio` 仅内网互通。
- MinIO 控制台 `9001` 默认不暴露；需要时仅对管理网段开放。

### 4.2 依赖关系

```yaml
backend:
  depends_on:
    postgres: { condition: service_healthy }
    redis: { condition: service_healthy }
    minio: { condition: service_healthy }
worker:
  depends_on:
    backend: { condition: service_started }
    redis: { condition: service_healthy }
beat:
  depends_on:
    backend: { condition: service_started }
    redis: { condition: service_healthy }
nginx:
  depends_on:
    frontend: { condition: service_started }
    backend: { condition: service_healthy }
```

---

## 5. 数据卷

| 卷 | 挂载点 | 用途 |
| --- | --- | --- |
| `pgdata` | `/var/lib/postgresql/data` | 数据库数据 |
| `redisdata` | `/data` | Redis 持久化（可选） |
| `miniodata` | `/data` | MinIO 对象数据 |
| `applogs` | `/app/logs` | 后端/Worker 日志 |
| `nginxlogs` | `/var/log/nginx` | Nginx 访问与错误日志 |
| `backup` | `/backup` | 备份文件（建议挂独立磁盘） |

- 卷必须持久化，`docker compose down` 不删除卷。
- 禁止 `docker compose down -v` 用于生产。
- 备份卷与主数据卷尽量不同盘。

---

## 6. 环境变量

### 6.1 必填

| 变量 | 说明 |
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
| `ENCRYPTION_KEY` | 模型 API Key 加密密钥（32 字节，Base64） |
| `ADMIN_INITIAL_USERNAME` | 初始超管用户名 |
| `ADMIN_INITIAL_PASSWORD` | 初始超管密码；首次初始化必填 |

### 6.2 可选/调优

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `JWT_ACCESS_HOURS` | 24 | 普通登录有效期 |
| `JWT_REMEMBER_DAYS` | 7 | 记住我有效期 |
| `ARK_BASE_URL` | 火山方舟地址 | 豆包 API 地址 |
| `ARK_API_KEY` | 空 | 首次启动的兜底 Key；后台模型配置优先 |
| `CORS_ORIGINS` | 空 | 同源部署时留空 |
| `MAX_UPLOAD_MB` | 10 | 单文件上限 |
| `MAX_UPLOADS_PER_SESSION` | 5 | 每会话上传上限 |
| `GENERATION_TIMEOUT_SECONDS` | 120 | 单张生图超时 |
| `BATCH_TIMEOUT_SECONDS` | 1800 | 整批超时 |
| `WORKER_CONCURRENCY` | 4 | Worker 并发 |
| `EXPORT_TTL_HOURS` | 24 | 导出文件有效期 |
| `ARCHIVE_RETENTION_YEARS` | 5 | 热存年限 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_RETENTION_DAYS` | 90 | 应用日志保留 |
| `BACKUP_RETAIN_DAYS` | 7 | 备份保留 |

### 6.3 密钥管理

- `.env` 不提交 Git，权限设置为仅部署账号可读。
- 生产密钥与开发密钥分离。
- 更换 `JWT_SECRET` 会使所有已签发 token 失效。
- 更换 `ENCRYPTION_KEY` 需先解密再用新密钥加密模型 API Key，不能直接替换。
- 初始超管密码不得使用默认弱口令；未设置时迁移/初始化脚本应失败并提示。

---

## 7. Nginx 配置

### 7.1 基础

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 12m;

    # 前端静态资源
    location / {
        proxy_pass http://frontend:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # SSE：关闭缓冲
    location /api/v1/sessions/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

### 7.2 要求

1. SSE 路径必须关闭缓冲，否则聊天不会逐字显示。
2. `client_max_body_size` 至少 12MB（10MB 文件 + 表单开销）。
3. 上传与生成接口的超时不低于 300 秒。
4. 静态资源开启 gzip 与缓存。
5. 安全响应头：`X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`。
6. `/api/docs` 默认仅内网访问；如对外，需加鉴权。
7. 如启用 HTTPS，证书挂载到容器并配置 443；HTTP 跳转 HTTPS。

---

## 8. 启动顺序与初始化

### 8.1 首次部署

1. 准备服务器、Docker、Docker Compose。
2. 复制 `.env.example` 为 `.env`，填写密钥与初始超管账号。
3. `docker compose build`。
4. `docker compose up -d postgres redis minio`。
5. 等待健康检查通过。
6. `docker compose run --rm migrate`：执行 Alembic 迁移与种子数据。
7. `docker compose up -d backend worker beat frontend nginx`。
8. 访问 `/api/health` 确认健康。
9. 使用初始超管登录，立即修改密码。
10. 在后台配置豆包 API Key、模型名，验证一次生成。

### 8.2 日常更新

1. 备份数据库与 MinIO。
2. 拉取新代码/镜像。
3. `docker compose build`。
4. `docker compose run --rm migrate`。
5. `docker compose up -d --no-deps backend worker beat frontend nginx`。
6. 检查健康与关键接口。
7. 出现问题时回滚镜像，并按备份恢复。

### 8.3 健康检查

| 服务 | 检查 |
| --- | --- |
| `postgres` | `pg_isready` |
| `redis` | `redis-cli ping` |
| `minio` | `/minio/health/live` |
| `backend` | `GET /api/health` |
| `frontend` | `GET /` 返回 200 |
| `nginx` | `GET /api/health` 经网关返回 200 |

`/api/health` 返回：

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

任一依赖不可用时返回 HTTP 503，`status=degraded`。

---

## 9. 日志

### 9.1 日志类型

| 日志 | 位置 | 保留 |
| --- | --- | --- |
| 后端应用日志 | `applogs/backend.log` + stdout | 90 天 |
| Worker 日志 | `applogs/worker.log` + stdout | 90 天 |
| Beat 日志 | `applogs/beat.log` + stdout | 90 天 |
| Nginx 访问日志 | `nginxlogs/access.log` | 90 天 |
| Nginx 错误日志 | `nginxlogs/error.log` | 90 天 |
| 操作日志 | 数据库 `audit_logs` | 5 年 |
| 生成/Agent 记录 | 数据库 | 长期 |

### 9.2 格式要求

- 应用日志使用结构化格式（JSON 或键值对），至少包含：时间、级别、模块、request_id、用户 ID（如有）、消息。
- 每个请求生成 `request_id`，贯穿后端与 Worker。
- 禁止记录：密码、JWT、API Key、完整身份证/手机号等敏感信息。
- 日志轮转：按天，保留 90 天，压缩归档。

### 9.3 审计日志

- 写入数据库，不依赖文件日志。
- 覆盖登录、账号、权限、配置、提示词、导出等操作。
- 详情字段脱敏。

---

## 10. 备份与恢复

### 10.1 备份

| 项目 | 时间 | 命令/方式 | 保留 |
| --- | --- | --- | --- |
| PostgreSQL | 每日 02:00 | `pg_dump -Fc` | 7 天 |
| MinIO | 每日 02:30 | `mc mirror` 到备份卷/远端 | 7 天 |

- 备份文件命名：`esimage_db_{yyyyMMdd}.dump`、`esimage_minio_{yyyyMMdd}/`。
- 备份完成后校验文件存在与大小。
- 备份任务失败需告警（邮件/IM 由运维接入，本期可先看日志）。

### 10.2 恢复

1. 停止 `backend`、`worker`、`beat`。
2. 恢复数据库：`pg_restore -d esimage <dump>`。
3. 恢复 MinIO：`mc mirror <backup> myminio/esimage`。
4. 启动服务。
5. 验证：健康检查、登录、历史作品、图片下载、一次生成。
6. 记录恢复时间与影响范围。

### 10.3 演练

- 建议每季度做一次恢复演练。
- 演练不影响生产，可在独立环境进行。

---

## 11. 定时任务

| 任务 | 频率 | 说明 |
| --- | --- | --- |
| 归档任务 | 每日 03:00 | 5 年以上的图片原件转 `archive/` |
| 孤儿上传清理 | 每日 04:00 | 30 天未绑定会话且未被引用的上传软删除并清理对象 |
| 导出清理 | 每小时 | 清理过期导出 ZIP 与 Redis 状态 |
| 备份 | 每日 02:00 / 02:30 | 数据库与 MinIO |
| 日志轮转 | 每日 | 应用与 Nginx 日志 |
| 权限缓存刷新 | 权限变更时 | 主动失效，不依赖定时 |

- 归档与导出清理由 Celery Beat 调度。
- 备份由宿主机 cron 或独立备份容器执行。
- 定时任务需记录执行结果与耗时；失败可重试。

---

## 12. 安全

1. 生产 `.env` 权限 600，仅部署账号可读。
2. 数据库、Redis、MinIO 端口不对宿主机/公网暴露。
3. MinIO 桶不公开，所有访问经后端鉴权。
4. 建议启用 HTTPS；仅内网 HTTP 时需限制来源网段。
5. 初始超管密码必须强密码，首次登录后立即修改。
6. JWT 密钥、加密密钥、MinIO 密钥分离，不共用。
7. API Key 加密存储，日志与审计中脱敏。
8. 备份文件加密传输，备份卷权限受限。
9. 服务器开启防火墙，仅开放 80/443（或内网端口）。
10. 定期更新基础镜像与依赖，修复已知漏洞。
11. 不在镜像中硬编码密钥；通过环境变量注入。
12. 生产禁用调试模式与详细错误堆栈回显。

---

## 13. 监控与排障

### 13.1 基础监控

| 项目 | 方式 |
| --- | --- |
| 容器状态 | `docker compose ps` / 健康检查 |
| 磁盘使用 | 宿主机监控，低于 20% 告警 |
| 数据库连接 | `/api/health` |
| Redis 队列长度 | Celery inspect 或 Redis 命令 |
| 生成失败率 | 统计 `generation_batches.status=failed` |
| 模型调用错误 | 统计 `agent_runs.status=failed` |
| 备份结果 | 备份脚本日志 |

本期不强制接入 Prometheus/Grafana；如需可后续补充。

### 13.2 常见问题

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 502 Bad Gateway | backend 未启动/崩溃 | 查看 backend 日志与健康检查 |
| 聊天不逐字输出 | Nginx 缓冲未关闭 | 检查 SSE location 配置 |
| 上传 413 | `client_max_body_size` 太小 | 调整为 12m 以上 |
| 生成一直排队 | worker 未启动/队列阻塞 | 检查 worker 与 Redis |
| 生成失败「模型未配置」 | 后台未填 API Key | 超管配置模型 |
| 401 频繁 | JWT 过期/密钥变更 | 重新登录；检查 `JWT_SECRET` |
| 图片打不开 | MinIO 不可用/权限错 | 检查 MinIO 健康与密钥 |
| 归档图片读取失败 | 归档未完成/对象缺失 | 检查归档任务与 `archive/` |
| 磁盘满 | 日志/图片/备份增长 | 清理日志、扩容、检查备份保留 |
| 数据库连接失败 | 连接数/容器未起 | 检查 postgres 健康与连接池 |

### 13.3 排障原则

1. 先看 `/api/health` 与容器状态。
2. 再看后端日志中的 `request_id`。
3. 生成问题看 `agent_runs` 与 `generation_batches.error_message`。
4. 存储问题看 MinIO 与对象路径。
5. 不直接修改生产数据库；需要改数据时先备份并记录。

---

## 14. 验收标准

1. 单机 Docker Compose 可一键启动全部服务。
2. 只有 nginx 暴露端口；数据库、Redis、MinIO 不对外。
3. `migrate` 可执行迁移与种子数据，初始超管可登录。
4. `/api/health` 正确反映数据库、Redis、MinIO 状态。
5. Nginx 正确代理前端与 API，SSE 不缓冲、逐字输出。
6. 上传 10MB 文件不被 413 拦截。
7. 日志按天轮转，保留 90 天；审计日志保留 5 年。
8. 每日备份可执行，保留 7 天，可按文档恢复。
9. 归档任务每日执行，5 年以上原件转入 `archive/`。
10. 导出文件 24 小时后清理。
11. 生产环境密钥不入库、不硬编码、不写日志。
12. 常见故障可按第 13.2 节定位。

---

## 15. 待确认项

| 序号 | 事项 | 当前处理 |
| --- | --- | --- |
| 1 | 是否启用 HTTPS 与域名 | 本期按内网 HTTP 设计，部署时决定 |
| 2 | 备份是否复制到远端对象存储 | 本期先本地备份卷，远端可选 |
| 3 | 是否暴露 MinIO 控制台 | 默认不暴露，仅管理网段按需开放 |
| 4 | 是否接入 Prometheus/Grafana | 本期不接入，保留扩展 |
| 5 | 豆包 API Key 的提供时间 | 开发联调前必须提供 |
| 6 | 初始超管账号由谁设置 | 部署人通过环境变量设置，首次登录改密 |
