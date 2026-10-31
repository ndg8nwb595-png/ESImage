# 01: Compose 基线与依赖服务

**What to build:** 在一台干净的单机上，用一份 Compose 定义启动 PostgreSQL、Redis、MinIO 三个依赖服务；三者全部通过健康检查并持久化到命名卷；整个栈使用单一 bridge 网络，除 nginx 外不向宿主机暴露任何端口；`.env.example` 提供完整变量清单；MinIO 初始化服务幂等创建 `esimage` 桶，并验证 `uploads/`、`generated/`、`thumbnails/`、`archive/`、`exports/`、`templates/`、`materials/`、`avatars/` 前缀可写。此切片结束时，重复执行依赖启动命令都能得到健康的三依赖。

**Blocked by:** None（可立即开始）

**Status:** ready-for-agent

- [ ] `docker compose config` 校验通过；全栈只有一个 bridge 网络 `esimage_net`；所有服务可互相用服务名解析。
- [ ] 命名卷包含 `pgdata`、`redisdata`、`miniodata`、`applogs`、`nginxlogs`、`backup`，分别挂载到 PostgreSQL 数据目录、Redis `/data`、MinIO `/data`、`/app/logs`、`/var/log/nginx`、`/backup`。
- [ ] Compose 中只有 `nginx` 声明宿主机端口（80）；443 以注释模板保留；`postgres`、`redis`、`minio`、`backend`、`worker`、`beat`、`frontend` 均无 `ports` 发布。
- [ ] `.env.example` 覆盖 11 号 §6.1 全部必填变量与 §6.2 全部可选变量，包含变量名、默认值与占位说明，不含任何真实密钥；`.env` 已被 Git 忽略。
- [ ] `SECRET_KEY`、`JWT_SECRET`、`ENCRYPTION_KEY`、MinIO 访问键与密钥分列且占位不同；部署文档要求分别生成，禁止共用同一值。
- [ ] `postgres:16` 使用 `pg_isready` 健康检查；`redis:7` 使用 `redis-cli ping`；`minio` 使用 `/minio/health/live`；三者均配置 `interval`、`timeout`、`retries` 与 `start_period`。
- [ ] `minio-init` 使用 `minio/mc` 一次性运行，幂等创建 `esimage` 桶；桶不设置匿名读写策略；对 8 个前缀各写入一个临时探针对象并删除，任一前缀不可写则非 0 退出；重复执行不报错。
- [ ] 所有长驻服务设置 `restart: unless-stopped`；`migrate`、`minio-init` 设置 `restart: "no"`。
- [ ] 全部容器时区为 `Asia/Shanghai`；PostgreSQL 与 Redis 的时区/排序规则不影响后续迁移。
- [ ] `docker compose down` 后命名卷仍存在，重新启动数据不丢；README 与脚本明确警告生产禁止 `docker compose down -v`。
- [ ] 在仅启动三个依赖与 `minio-init` 的情况下，`docker compose ps` 显示三者均为 `healthy`，`minio-init` 退出码为 0。
