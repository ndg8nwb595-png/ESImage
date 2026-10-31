# 07: Worker/Beat 基线

**What to build:** Celery Worker 与 Beat 以真实 Redis 作为 broker 与结果后端运行：Worker 并发数读取 `WORKER_CONCURRENCY`（默认 4），Beat 使用 `Asia/Shanghai` 时区；队列连通、任务可执行、日志可关联。本切片只建立运行时基线，不注册归档、孤儿上传清理、导出清理等业务定时任务；用一个仅非生产环境可用的 `ops.selftest` 任务验证 Worker 执行与 `request_id` 透传。

**Blocked by:** 02 迁移、种子与初始超管；03 应用镜像与双健康探针

**Status:** ready-for-agent

- [ ] worker 与 beat 复用 backend 镜像，只在内网运行、不发布宿主机端口，设置 `restart: unless-stopped`。
- [ ] Worker 从 `REDIS_URL` 连接 broker 与结果后端；并发数读取 `WORKER_CONCURRENCY`，默认 4；启动日志明确输出并发数与 broker 地址（地址脱敏）。
- [ ] Beat 启动成功，时区为 `Asia/Shanghai`；调度表在本 demo 中为空，不包含归档、孤儿上传清理、导出清理等业务任务；启动日志输出时区与调度加载结果。
- [ ] `celery inspect ping` 能收到 Worker 的 pong；Redis 中存在该队列的键；停止 Worker 后 ping 失败，重启后恢复。
- [ ] 提供一个仅 `APP_ENV != production` 注册的 `ops.selftest` 任务：接受可选的 `request_id` 与 `delay_ms`，返回 `ok`、`request_id`、实际耗时；生产环境不注册该任务。
- [ ] 通过任务头传入 `request_id` 时，Worker 日志中的 `request_id` 与发起请求一致；未传入时生成新 ID；任务日志包含开始、结束、耗时与结果。
- [ ] `celery inspect registered` 在非生产环境可见 `ops.selftest`，生产环境不可见；除 `ops.selftest` 外不注册任何业务任务。
- [ ] Worker 与 Beat 的日志写入 `applogs` 下的 `worker.log`、`beat.log`，格式为 JSON，字段与 05 的日志契约一致。
- [ ] Beat 调度配置错误时启动失败并输出可读原因，不静默空转；Worker 连接 Redis 失败时按 Compose 重启策略重试，日志可定位。
- [ ] 归档、孤儿上传清理、导出清理、权限缓存刷新在本切片中明确未实现，并在接口文档的定时任务契约中标注为后续实现。
