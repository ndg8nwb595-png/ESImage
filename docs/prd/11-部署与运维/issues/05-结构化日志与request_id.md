# 05: 结构化日志与 request_id

**What to build:** backend、worker、beat 的日志统一输出为 JSON 行，同时写入 stdout 与 `applogs` 卷；每个 HTTP 请求生成或复用 `X-Request-ID`，并让该 ID 出现在该请求产生的所有日志中；Worker 任务通过任务头携带同一个 ID。应用日志按天轮转、保留 90 份并压缩；Nginx 访问与错误日志由宿主机 logrotate 每日轮转；密码、JWT、API Key 等敏感信息永不落日志。

**Blocked by:** 03 应用镜像与双健康探针

**Status:** ready-for-agent

- [ ] backend、worker、beat 每条日志为一行合法 JSON，至少包含 `time`、`level`、`module`、`request_id`、`user_id`、`message`；无用户时 `user_id` 为 `null` 且字段不省略。
- [ ] `time` 为 ISO 8601 带时区（`Asia/Shanghai`）；`level` 使用 `DEBUG` / `INFO` / `WARNING` / `ERROR`；日志级别由 `LOG_LEVEL` 控制。
- [ ] 每个 HTTP 请求若携带合法的 `X-Request-ID`（`[A-Za-z0-9_-]{8,64}`）则复用，否则生成 UUIDv4；响应头返回 `X-Request-ID`；同一请求的所有日志使用同一 ID。
- [ ] 非法或超长的入站 `X-Request-ID` 被忽略并重新生成，不写入日志，避免头注入。
- [ ] Worker 任务从任务头读取 `request_id`，写入该任务的日志；缺失时生成新 ID。后端入队时把当前请求 ID 写入任务头。端到端关联由 07 的 `ops.selftest` 验证。
- [ ] 日志同时写入 stdout 与 `applogs` 下的 `backend.log`、`worker.log`、`beat.log`；同一进程不重复注册 handler，重载后不产生重复行。
- [ ] 应用日志使用按天轮转，保留份数读取 `LOG_RETENTION_DAYS`（默认 90），历史文件压缩为 `.gz`；backend、worker、beat 使用同一套轮转配置。
- [ ] 在测试中主动触发一次轮转，确认生成历史日志与压缩文件，且轮转后继续写入新的当前日志。
- [ ] Nginx 访问与错误日志写入 `nginxlogs` 卷；宿主机 logrotate 配置每日轮转、保留 90 份、压缩；`logrotate -f` 可强制轮转成功。
- [ ] 日志禁止包含密码、密码哈希、JWT、API Key、MinIO 密钥、完整身份证号与手机号；错误日志只记录错误类型、业务码与必要上下文。
- [ ] 统一响应中的错误码与 `request_id` 可在日志中检索；日志不记录完整请求体、响应体或上传文件内容。
- [ ] 容器 stdout 使用 json-file 驱动并限制单文件 10MB、保留 3 个，避免无限增长；应用文件日志仍按 90 天保留。
- [ ] `APP_ENV=production` 时不输出调试日志与详细堆栈；生产日志中不出现调试开关。
