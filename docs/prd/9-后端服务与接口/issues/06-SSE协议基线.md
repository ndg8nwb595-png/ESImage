# 06: SSE 协议基线

**What to build:** 聊天接口以 Server-Sent Events 流式返回，联调方按固定协议解析：连接建立先收到 `meta`，随后按真实执行顺序收到规划与商品理解两个 Agent 的 `agent_status`，正文以 `delta` 增量输出，结束收到 `done`；15 秒无事件时收到 `ping`。响应头禁止缓存与代理缓冲；客户端断开后服务端停止生成并释放资源，已产生的内容与 Agent 调用记录落库可查；流建立后的错误以 `error` 事件返回并关闭连接。

**Blocked by:** 03（权限点校验与越权语义）；2 号 demo 04（聊天 SSE 骨架）、3 号 demo 03（SSE 增量约定）

**Status:** ready-for-agent

- [ ] `POST /sessions/{id}/messages` 与 `POST /sessions/messages` 支持 `Accept: text/event-stream`；请求体含 `client_message_id`、`content`、`params`；首条消息可传 `session_id: null`。
- [ ] 响应头包含 `Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no`；不做 gzip 或响应缓冲。
- [ ] 事件类型固定为 `meta`、`agent_status`、`delta`、`done`、`error`、`ping`；`data` 为单行 UTF-8 JSON，中文不转义。
- [ ] 每个事件以 `event:` 与 `data:` 两行输出，事件之间以空行分隔；不使用 `id:` 与 `retry:` 字段。
- [ ] `meta` 首个到达，含 `message_id` 与 `session_id`；首条消息时 `session_id` 为新建会话 ID；`message_id` 指向 Agent 回复消息。
- [ ] `agent_status` 按真实顺序输出 `started` / `finished` / `skipped`；规划与商品理解两个 Agent 都不能省略状态事件。
- [ ] `delta` 只出现在需要流式输出的阶段，内容可拼接为完整回复；不把每个增量单独落成消息。
- [ ] `done` 与 `error` 互斥，二者之后不再发送任何事件并关闭连接；`done` 含 `message_id`、`token_in`、`token_out`、`requirement_summary`、`requirement_changed`。
- [ ] 连接建立后每 15 秒发送一次 `ping`，`data` 为 `{}`；`ping` 可穿插在任意事件之间，前端忽略。
- [ ] 客户端断开后停止后续 Agent 调用、释放连接与任务资源；已产生的内容、Agent 调用记录与 Token 统计在生成过程中落库，断线后可通过消息分页接口查询。
- [ ] 流建立前的参数、鉴权、权限、会话不存在错误使用普通 HTTP 状态 + 统一 JSON；流建立后的错误使用 `error` 事件，`data.code` 取 9 号错误码，随后关闭连接。
- [ ] 3 号 demo 的 `meta.duplicate`、`done.requirement_changed` 与重复消息重放约定保持不变；9 号未定义重复消息在 SSE 下的返回形式，差异记录在 README §6.2，不在本切片裁决。
- [ ] 契约回归套件捕获完整事件序列，断言顺序、心跳、响应头、断线停止与断线后可查，每个用例输出中文日志。
- [ ] 不新增聊天接口，不改变 2/3 号 demo 已定义的消息字段与 Agent 状态枚举。
