# 11-部署与运维：最小实现 demo

| 项目 | 内容 |
| --- | --- |
| 上游 PRD | [`11-部署与运维prd.md`](./11-部署与运维prd.md) |
| 目标 | 用最小范围跑通「单机 Compose 起栈 → 依赖健康 → 迁移与种子 → 应用与双健康探针 → Nginx 网关与 SSE → 结构化日志 → 备份恢复 → Worker/Beat 基线 → 一键验收」 |
| 任务形式 | 8 个垂直切片，按依赖顺序编号，存放在 `issues/` |
| 接口文档 | [`接口文档-部署与运维最小demo.md`](./接口文档-部署与运维最小demo.md) |

> 本目录只覆盖 11 号 PRD 中与「部署骨架、健康探针、网关、日志、备份恢复、队列基线」直接相关的最小集合，不代表 11 号 PRD 的全部验收项。业务页面、业务接口、8 Agent 链路、上传/生成/历史/管理后台均不在本 demo 内；本 demo 只交付可部署、可探活、可备份、可验收的运行壳。

---

## 1. 最小 demo 范围

### 1.1 做

- Compose 基线：单一 bridge 网络、持久化命名卷、完整 `.env.example`；只有 nginx 暴露 80，443 只保留注释模板。
- 依赖服务：`postgres:16`、`redis:7`、`minio` 三项健康检查；`minio-init` 幂等创建 `esimage` 桶并校验 8 个前缀可写；桶不公开。
- 迁移与种子：`migrate` 一次性服务执行 Alembic 正向迁移与幂等种子；创建初始超管；密码缺失或过弱时失败并给出中文提示；重复执行不覆盖数据。
- 应用镜像：backend（Python 3.11 + FastAPI + uvicorn）、frontend（静态占位 + 多阶段构建）、worker、beat；backend/worker/beat 以非 root 运行，frontend 使用官方 nginx 镜像，镜像内无硬编码密钥。
- 双健康探针：`GET /api/health` 保持 11 号裸结构供容器探活；`GET /api/v1/health` 返回 9 号统一响应；两者共用同一次依赖检测。数据库、Redis、MinIO 并发探活，任一不可用返回 503 `degraded`。
- Nginx 网关：`/` 代理静态、`/api/` 代理后端、`/api/v1/sessions/` 关闭缓冲支持 SSE；12MB 上传上限、300 秒读超时、gzip 与静态缓存、三项安全响应头；`/api/docs` 仅内网可访问。
- 结构化日志：backend/worker/beat 输出 JSON 行；`X-Request-ID` 贯穿 HTTP 与 Worker；按天轮转、保留 90 份并压缩；Nginx 日志由宿主机 logrotate 轮转；密码、JWT、API Key 等敏感信息禁记。
- 备份与恢复：宿主机 cron 执行 `pg_dump -Fc` 与 `mc mirror`；文件命名、7 天保留、大小与可读性校验；提供恢复脚本与一次可复验的恢复演练。
- Worker/Beat 基线：真实 Celery + Redis，Worker 并发默认 4，Beat 时区 `Asia/Shanghai`；验证队列连通、任务可执行与日志关联。**不实现归档、孤儿上传清理、导出清理等业务定时任务。**
- 一键启动与验收：`demo_up`、`demo_verify`、`demo_down` 三个脚本；中文日志逐项输出请求、预期、实际与结论；失败即停；停止不删卷。

### 1.2 不做

- 5 年归档任务、孤儿上传清理、导出清理、权限缓存刷新。
- 登录、会话、上传、生成、历史、管理后台等业务接口与页面；frontend 仅静态占位页。
- 审计日志的业务写入（登录、账号、权限、配置、提示词、导出等动作）；只保留表结构与保留期约定，业务实现属 6/9 号 demo。
- 初始超管的登录闭环；本 demo 只校验账号行、角色、bcrypt 哈希与强密码校验，登录接口属 1 号 demo。
- HTTPS、证书、HTTP 跳转 HTTPS、MinIO 控制台、Prometheus/Grafana、告警接入。
- 多机、集群、自动扩缩容、蓝绿/灰度发布、跨地域容灾。
- 备份远端复制、备份加密传输、恢复演练季度制度。
- 业务数据种子（会话、批次、图片、Agent 调用）；本 demo 只种角色、权限、尺寸预设、系统提示词、模型配置与初始超管。

### 1.3 相对 PRD 的最小化取舍

| PRD 要求 | 最小 demo 处理 | 原因 / 影响 |
| --- | --- | --- |
| 归档、孤儿上传清理、导出清理由 Celery Beat 调度 | 只保留 Worker/Beat 与队列连通，不注册业务定时任务 | 三个任务都依赖业务数据链路；最小 demo 先用 `ops.selftest` 验证队列与日志关联，正式实现再补调度 |
| 初始超管可登录并立即改密 | 校验数据库账号行、`super_admin` 角色与 bcrypt 哈希；若 1 号 demo 已落地再用其登录接口复验 | 登录接口属 1 号 demo；部署 demo 不重复实现业务鉴权 |
| 审计日志保留 5 年 | 不改 `audit_logs` 表结构，不写业务审计 | 审计动作分散在 6/9 号 demo；11 号只保证存储与保留期约定 |
| 生产 HTTPS/443 | 只保留注释模板，默认仅 80 | 11 号 §15 已确定本期内网 HTTP |
| 启用 Prometheus/Grafana | 只用 `/api/health`、`docker compose ps` 与脚本检查 | 11 号 §15 已确定不接入 |
| 备份失败告警 | 脚本日志记录失败并返回非 0 退出码 | 邮件/IM 由运维接入，本期按 PRD 允许先看日志 |
| 每季度恢复演练 | 在一次性 demo 栈执行一次脚本化恢复演练 | 不触碰生产数据；制度性演练不在 demo 内 |
| 业务前端页面 | 多阶段构建的静态占位页 | 页面属 1~8 号 demo；本 demo 只验证静态托管与网关代理 |
| 9 号统一响应覆盖所有接口 | `/api/health` 作为运维探针例外；新增 `/api/v1/health` 返回统一响应 | 兼顾 11 号原文与 9 号契约；双路径共用检测逻辑，不重复探活 |
| 健康检查失败语义 | `checks.*` 只返回 `ok` / `error`，不返回异常详情 | PRD 未定义失败值；避免泄露 DSN、地址与上游错误 |
| Nginx 413 响应 | 使用 Nginx 默认 413 页面，不包装 JSON | PRD 未定义 413 响应体；网关拦截发生在应用之前 |
| 恢复脚本的覆盖语义 | 在一次性 demo 栈使用 `pg_restore --clean --if-exists` | 生产恢复按 11 号 §10.2 步骤执行；demo 栈数据可丢弃 |
| 容器 stdout 日志 | json-file 驱动限制单文件 10MB、保留 3 个 | 防止 stdout 无限增长；应用文件日志仍按 90 天轮转 |

### 1.4 与前后 demo 的关系

| 关系 | 说明 |
| --- | --- |
| 对 1~10 号 demo | 11 号提供统一的部署壳、网络、卷、环境变量、网关、日志、备份与验收脚本；不实现任何业务功能 |
| 对 1 号 demo | 初始超管由 `migrate` 创建；若 1 号 demo 已实现登录，可用 `POST /api/v1/auth/login` 复验，否则以数据库与 bcrypt 校验为准 |
| 对 9 号 demo | 9 号固化统一响应、错误码、SSE、上传下载等契约；11 号只新增健康探针，并为 SSE 提供网关配置与演示探针 |
| 对 10 号文档 | 迁移、种子、MinIO 桶与前缀、5 年归档规则以 10 号为准；本 demo 只执行迁移与种子，不执行归档 |

---

## 2. 前置与演示配置

### 2.1 前置

| 项目 | 要求 |
| --- | --- |
| 宿主机 | Linux 或 WSL2；Docker Engine 24+；Docker Compose v2 |
| 资源 | 建议 4 核 / 4GB 内存 / 20GB 可用磁盘 |
| 端口 | 宿主机 80 未被占用；443 仅保留模板，不要求开放；防火墙只放行 80（启用 HTTPS 后再放行 443） |
| 工具 | `bash`、`curl`、`git`；MinIO 客户端通过 `minio/mc` 容器执行，不要求宿主机安装 |
| 网络 | 首次构建需拉取镜像；生产内网可提前导入镜像 |
| 配置 | 复制 `.env.example` 为 `.env`，填写密钥与初始超管账号；`.env` 不提交 Git |

### 2.2 演示账号

| 账号 | 来源 | 用途 |
| --- | --- | --- |
| `ADMIN_INITIAL_USERNAME` / `ADMIN_INITIAL_PASSWORD` | `.env` 由部署人设置 | 验证初始超管创建、角色绑定与强密码校验 |

- 不提供固定演示账号，避免弱口令进入仓库。
- 初始密码规则（demo 约定）：长度 ≥12，且至少包含大写、小写、数字、符号中的 3 类；不得等于用户名。
- 若 1 号 demo 已落地，首次登录后立即改密；本 demo 不实现改密接口。

### 2.3 演示数据

`migrate` 只写入 10 号 §10.2 规定的种子：

- 3 个内置角色与权限点。
- `size_presets` 四个平台，均 1000×1000。
- 8 个 Agent 初始系统提示词与 `platform_rule` 初始规则。
- 一条 `api_key` 为空的默认模型配置。
- 初始超管账号。

不写入会话、消息、批次、图片、上传图等业务数据；Worker/Beat 基线只执行 `ops.selftest`，不产生业务数据。

### 2.4 验证方式

- `scripts/demo_up.sh`：一键构建、启动、迁移、等待健康。
- `scripts/demo_verify.sh`：逐项验收，中文日志输出。
- `curl`：验证双健康探针、413、SSE 增量输出。
- `docker compose ps` / `docker compose logs`：查看容器与日志。
- 具体命令与预期见接口文档 §9。

---

## 3. 接口总览

### 3.1 本 demo 新增的 HTTP 接口

| 方法 | 路径 | 鉴权 | 用途 | 说明 |
| --- | --- | --- | --- | --- |
| GET | `/api/health` | 无 | 容器/网关探活 | 保持 11 号 §8.3 裸结构 `{status, checks}` |
| GET | `/api/v1/health` | 无 | 统一响应健康检查 | 返回 `{code, message, data}`，与 9 号契约一致 |
| GET | `/api/v1/sessions/_probe/stream` | 无 | 网关 SSE 验证 | **演示专用**，仅 `APP_ENV != production` 启用，生产返回 404，不进入 OpenAPI |

> 除上述接口外不新增任何业务 HTTP 接口。`/api/v1/sessions/_probe/stream` 只是为了在没有聊天业务的情况下验证 Nginx 不缓冲；正式环境由 3 号 demo 的聊天 SSE 替代。

### 3.2 网关入口

| 前缀 | 目标 | 说明 |
| --- | --- | --- |
| `/` | `frontend:8080` | 静态资源；占位页返回 200 |
| `/api/` | `backend:8000` | JSON API；读超时 300 秒 |
| `/api/v1/sessions/` | `backend:8000` | 关闭缓冲与缓存；SSE 逐字输出 |
| `/api/docs`、`/api/openapi.json` | `backend:8000` | 仅 RFC1918 与回环地址可访问 |

### 3.3 明确不提供的接口

本 demo 不实现、也不新增以下接口；它们属于 1~10 号 demo：

`/api/v1/auth/*`、`/api/v1/sessions`（除演示探针）、`/api/v1/sessions/{id}/*`、`/api/v1/uploads/*`、`/api/v1/generations/*`、`/api/v1/images/*`、`/api/v1/batches/*`、`/api/v1/history`、`/api/v1/profile`、`/api/v1/admin/*`、`/api/v1/sizes`、`/api/v1/templates`、`/api/v1/materials`。

### 3.4 运维脚本与任务

| 名称 | 类型 | 用途 |
| --- | --- | --- |
| `demo_up.sh` | CLI | 一键构建、启动、迁移与健康等待 |
| `demo_verify.sh` | CLI | 逐项验收并输出中文日志 |
| `demo_down.sh` | CLI | 停止服务，默认保留卷 |
| `backup_db.sh` | CLI / 宿主机 cron | PostgreSQL 每日备份与保留清理 |
| `backup_minio.sh` | CLI / 宿主机 cron | MinIO 每日镜像备份与保留清理 |
| `restore.sh` | CLI | 按备份恢复数据库与 MinIO |
| `ops.selftest` | Celery 任务 | **演示专用**队列自检任务，验证 Worker 执行与 `request_id` 透传 |

---

## 4. 任务依赖

```text
01 Compose 基线与依赖服务
        ↓
02 迁移、种子与初始超管
        ↓
03 应用镜像与双健康探针
        ├──────────────────┬──────────────────┬──────────────────┐
        ↓                  ↓                  ↓                  ↓
04 Nginx 网关与 SSE   05 结构化日志与    06 备份与恢复      07 Worker/Beat
  代理                request_id                          基线
        │                  │                  │                  │
        └──────────────────┴─────────┬────────┴──────────────────┘
                                     ↓
                        08 一键启动与验收脚本
```

> 06 只额外依赖 02（数据库与种子）与 03（健康检查），与 04、05、07 并行。
> 08 在 04~07 全部完成后执行，负责端到端串验。
> 预重构：01 先把网络、卷、环境变量与依赖服务固定为共享基线；02 复用同一 backend 镜像执行迁移；03 之后的所有切片只接基线，不重复搭栈。

| # | Ticket | 阻塞于 | 交付的可演示行为 |
| --- | --- | --- | --- |
| 01 | [Compose 基线与依赖服务](./issues/01-Compose基线与依赖服务.md) | 无 | 三依赖健康、桶与前缀就绪；只有 nginx 暴露端口；卷持久化 |
| 02 | [迁移、种子与初始超管](./issues/02-迁移种子与初始超管.md) | 01 | 迁移到 head、种子幂等、初始超管创建；弱密码失败 |
| 03 | [应用镜像与双健康探针](./issues/03-应用镜像与双健康探针.md) | 02 | 四个应用容器可启动；两个健康接口正确反映三依赖状态 |
| 04 | [Nginx 网关与 SSE 代理](./issues/04-Nginx网关与SSE代理.md) | 03 | 静态/API 代理正确；SSE 逐字输出；10MB 通过、超限 413 |
| 05 | [结构化日志与 request_id](./issues/05-结构化日志与request_id.md) | 03 | JSON 日志、请求关联、按天轮转 90 份压缩、敏感信息禁记 |
| 06 | [备份与恢复](./issues/06-备份与恢复.md) | 02、03 | 每日备份命名/校验/保留 7 天；恢复后健康与数据复验通过 |
| 07 | [Worker/Beat 基线](./issues/07-Worker-Beat基线.md) | 02、03 | Worker 可执行任务、Beat 按时区运行、队列与 Redis 连通 |
| 08 | [一键启动与验收脚本](./issues/08-一键启动与验收脚本.md) | 04、05、06、07 | 一条命令起栈并逐项验收，失败即停，停止不删卷 |

---

## 5. 验收总口径（演示脚本）

最小 demo 完成时，至少能完整演示以下路径：

1. 在干净机器复制 `.env.example` 为 `.env`，填写强密码初始超管与各密钥；`demo_up.sh` 完成构建、依赖启动、迁移、应用启动与健康等待。
2. `docker compose ps` 显示全部长驻服务健康；`docker port` 显示只有 nginx 发布 80；postgres/redis/minio/backend/worker/beat/frontend 无宿主机端口。
3. 重复执行 `docker compose run --rm migrate` → 退出码 0，不重复插入角色、权限、尺寸、提示词或超管。
4. 清空 `ADMIN_INITIAL_PASSWORD` 或改为弱密码 → `migrate` 非 0 退出，日志给出明确中文提示。
5. `GET /api/health` → 200 `{status:"ok", checks:{database:"ok",redis:"ok",minio:"ok"}}`；`GET /api/v1/health` → 200 `{code:0,message:"ok",data:{...}}`。
6. 停止 Redis 后请求两个健康接口 → 均 503 `degraded`，`checks.redis="error"`，其余依赖仍返回各自状态；恢复 Redis 后无需重启即回到 200。
7. 经网关 `GET /` → 200 占位页；`GET /api/health` → 200；非内网来源访问 `/api/docs` → 403。
8. 经网关 `POST /api/v1/uploads` 携带 10MB 文件 → 不返回 413；携带 13MB → 413。
9. 经网关请求 SSE 演示探针 → 依次收到 `meta`、多条 `delta`、`done`，事件按 1 秒间隔到达而非结束后一次性到达；无事件时收到 `ping`；响应头含 `Cache-Control: no-cache` 与 `X-Accel-Buffering: no`。
10. 每个响应带 `X-Request-ID`；同一请求在 backend 日志中可检索到相同 `request_id`；Worker 执行 `ops.selftest` 后 worker 日志含同一 `request_id`；日志为合法 JSON，且不含密码、JWT、API Key。
11. 触发日志轮转 → `applogs` 下生成按天命名的 `.log` 与 `.gz`；`LOG_RETENTION_DAYS=90` 生效；Nginx 日志经 `logrotate -f` 生成轮转文件。
12. 执行数据库与 MinIO 备份 → 生成 `esimage_db_{yyyyMMdd}.dump` 与 `esimage_minio_{yyyyMMdd}/`；文件非空且 `pg_restore -l` 可读；超过 7 天的备份被清理。
13. 删除一条尺寸预设与一个 MinIO 对象后执行恢复 → 数据与对象恢复，`/api/health` 与 `/api/v1/health` 均 200。
14. `celery inspect ping` → 返回 pong；Redis 中存在队列键；Beat 启动日志显示 `Asia/Shanghai` 时区；`ops.selftest` 可被 Worker 执行并记录耗时。
15. `demo_down.sh` → 容器停止但卷保留；再次 `demo_up.sh` 后数据仍在；脚本明确警告不要使用 `docker compose down -v`。
16. `demo_verify.sh` → 全部用例通过，逐条输出请求、预期、实际与结论；任一失败立即非 0 退出。

### 5.1 11 号 §14 验收标准覆盖情况

| 11 号 §14 | 本 demo 覆盖 | 说明 |
| --- | --- | --- |
| 1. 单机 Compose 一键启动全部服务 | 是 | Ticket 08 |
| 2. 只有 nginx 暴露端口 | 是 | Ticket 01 / 08 |
| 3. `migrate` 执行迁移与种子，初始超管可登录 | 部分 | Ticket 02；登录接口属 1 号 demo，本 demo 校验账号行与 bcrypt |
| 4. `/api/health` 反映三依赖状态 | 是 | Ticket 03；同时提供 `/api/v1/health` 统一响应 |
| 5. Nginx 代理前端与 API，SSE 不缓冲 | 是 | Ticket 04 |
| 6. 10MB 文件不被 413 拦截 | 是 | Ticket 04 |
| 7. 日志按天轮转 90 天；审计日志 5 年 | 部分 | Ticket 05 覆盖应用与 Nginx 日志；审计业务写入属 6/9 号 demo |
| 8. 每日备份可执行、保留 7 天、可恢复 | 是 | Ticket 06 |
| 9. 归档任务每日执行 | 否 | 按确认，本 demo 不做归档；Worker/Beat 仅保留基线 |
| 10. 导出文件 24 小时清理 | 否 | 导出功能未实现，清理任务不在本 demo |
| 11. 密钥不入库、不硬编码、不写日志 | 是 | Ticket 01 / 03 / 05 |
| 12. 常见故障可按 §13.2 定位 | 是 | 接口文档 §8 与各 Ticket 验收 |

---

## 6. 待确认项

> 以下事项在 PRD 中未给出唯一结论，本 demo 先按「演示约定」实现并记录，不替正式实现做最终裁决。

1. **双健康接口的差异**：`/api/health` 保持 11 号裸结构，`/api/v1/health` 返回 9 号统一响应。后者在降级时使用 HTTP 503 + 业务码 `50001`；9 号错误码表把 `5xxx` 映射到 HTTP 500，此处为满足 11 号 §8.3 的 503 语义而偏离，需要统一确认。
2. **健康接口的鉴权例外**：9 号要求除登录外所有接口校验 JWT；本 demo 的两个健康接口与 SSE 演示探针均不鉴权，作为探针例外。正式实现是否保留 `/api/v1/health` 需要确认。
3. **`request_id` 头名称**：PRD 只要求贯穿后端与 Worker，未定义头名。demo 约定 `X-Request-ID`，合法入站值（`[A-Za-z0-9_-]{8,64}`）复用，否则生成 UUIDv4。
4. **健康检查失败值**：PRD 只给出 `ok` 示例，未定义失败值。demo 使用 `error`，不返回异常详情；是否需要 `down` / `degraded` 等细分待定。
5. **健康检查超时**：PRD 未定义。demo 约定单依赖 2 秒、整体 5 秒，三项并发检测。
6. **安全响应头取值**：PRD 只列头名。demo 使用 `X-Frame-Options: SAMEORIGIN`、`Referrer-Policy: strict-origin-when-cross-origin`；是否改为 `DENY` 待定。
7. **初始超管强密码规则**：PRD 只要求「不得使用默认弱口令」。demo 约定长度 ≥12 且至少 3 类字符，并拒绝与用户名相同；具体规则需与账号模块统一。
8. **演示专用接口与任务**：`GET /api/v1/sessions/_probe/stream` 与 `ops.selftest` 只用于本 demo 验证网关与队列，生产禁用/移除；是否保留为长期运维自检能力需要确认。
9. **Nginx 413 响应体**：PRD 未定义。demo 使用 Nginx 默认 HTML 413，不包装统一 JSON；若前端需要可读提示，需在网关增加定制错误页。
10. **恢复脚本覆盖语义**：demo 使用 `pg_restore --clean --if-exists` 覆盖一次性栈；生产恢复是否允许 drop 现有对象，需要运维确认。
11. **Nginx 日志轮转方式**：PRD 只要求每日轮转。demo 由宿主机 logrotate 执行，不启用容器内 cron；是否改为独立 sidecar 待定。
12. **MinIO 前缀创建**：MinIO 前缀是虚拟目录。demo 用临时探针对象验证 8 个前缀可写后删除，不保留 `.keep` 对象。
13. **Worker/Beat 空调度**：本 demo 的 Beat 不注册任何业务定时任务，只验证运行时；归档、孤儿清理、导出清理的调度频率与重试策略留待正式实现。
14. **容器 stdout 保留**：demo 约定 json-file 单文件 10MB、保留 3 个；PRD 未定义，需与运维磁盘预算统一。

---

## 7. 快速开始

### 7.1 首次启动

```bash
cp .env.example .env
# 编辑 .env：填写密钥、MinIO 凭据、初始超管用户名与强密码
bash scripts/demo_up.sh
```

预期：依赖服务全部 healthy；`migrate` 退出码 0；backend/frontend/nginx 健康；控制台输出访问地址、日志与备份目录。

### 7.2 验收

```bash
bash scripts/demo_verify.sh
```

预期：§5 的 16 个步骤逐条通过；失败时脚本保留现场并以非 0 退出。

### 7.3 日常更新

1. 先执行数据库与 MinIO 备份，确认备份文件非空且可读。
2. 拉取新代码或导入新镜像。
3. 重新构建镜像。
4. 执行 `migrate`，确认迁移与种子成功。
5. 只重建应用服务（backend、worker、beat、frontend、nginx），不动数据库、Redis、MinIO。
6. 检查两个健康接口、登录、历史作品、图片下载与一次生成。
7. 出现问题时回滚镜像，并按备份恢复；恢复后复验健康与关键数据。

### 7.4 常见故障定位

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 502 Bad Gateway | backend 未启动或崩溃 | 查看 backend 日志与 `/api/health` |
| 聊天不逐字输出 | Nginx 缓冲未关闭 | 检查 `/api/v1/sessions/` 的 `proxy_buffering off` |
| 上传 413 | `client_max_body_size` 太小 | 调整为 12m 以上 |
| 生成一直排队 | worker 未启动或队列阻塞 | 检查 worker、Redis 与 `celery inspect ping` |
| 健康接口 503 | 数据库、Redis 或 MinIO 不可用 | 看 `checks` 哪项为 `error`，再查对应容器 |
| 401 频繁 | JWT 过期或 `JWT_SECRET` 变更 | 重新登录；核对 `JWT_SECRET` |
| 图片打不开 | MinIO 不可用或密钥错误 | 检查 MinIO 健康与凭据 |
| 磁盘满 | 日志、图片或备份增长 | 清理日志、扩容、核对保留天数 |
| 备份失败 | 数据库/ MinIO 不可达或权限不足 | 看备份脚本日志与退出码 |
| 恢复后数据缺失 | 恢复了错误的备份或 MinIO 目录 | 核对日期命名与 `pg_restore -l` 内容 |

