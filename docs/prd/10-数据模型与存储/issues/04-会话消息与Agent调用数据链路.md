# 04: 会话、消息与 Agent 调用数据链路

**What to build:** 在内容域表之上跑通聊天写入链路：创建会话、写入用户/助手/系统消息、更新会话最后消息时间、记录每次 Agent 调用的状态、Token、耗时与输入输出摘要。重复发送同一 `client_message_id` 不产生重复消息；并发发送首条消息只创建一个会话；消息按稳定顺序读出；Agent 输入输出落库前完成敏感字段脱敏。本切片不实现 HTTP 与 SSE，只交付可被 2/3 号 demo 调用的数据层能力与用例。

**Blocked by:** 03 配置域六表、幂等种子与初始超管

**Status:** ready-for-agent

- [ ] 创建会话后，`user_id`、`title`、`status=active` 正确；`last_message_at` 在写入首条消息前为空，写入后更新为该会话最新消息时间。
- [ ] 写入用户消息时校验 `role=user`、`content` 非空、`content_type` 为 `text`/`markdown`；写入助手消息时允许 `agent_code`，Token 默认 0；`status` 仅 `sending`/`done`/`failed`。
- [ ] 同一 `(session_id, client_message_id)` 重复写入时返回已存在消息，不新增行、不改变原消息内容；`client_message_id` 为空的消息不受该唯一约束影响。
- [ ] 并发发送同一用户的同一条首条消息（相同 `user_id + client_message_id`）时，只创建一个会话和一条消息；未引入 Redis，使用数据库事务与咨询锁完成去重，并在用例中并发触发验证。
- [ ] 消息按 `(created_at, id)` 稳定排序；同一时间戳下按 `id` 升序，不重复、不遗漏。
- [ ] 会话 `status=hidden` 可正常写入与读取；本切片不物理删除会话或消息，隐藏状态由调用方决定是否在用户端列表过滤。
- [ ] 每次 Agent 调用写入一条 `agent_runs`：`agent_code`、`status`（`success`/`failed`/`skipped`）、`model_name`、`prompt_tokens`、`completion_tokens`、`latency_ms`、`error_message` 正确；跳过的调用记录原因。
- [ ] `agent_runs` 的 `session_id`、`message_id`、`batch_id`、`image_id` 按调用场景写入或留空；关联对象不存在时外键拒绝。
- [ ] `input_summary`、`output_summary`、`input_full`、`output_full` 按 10 号 §4.8 落库；写入前调用 03 切片的共享脱敏函数，密码、API Key、JWT、`Authorization` 不得以明文出现在上述字段。
- [ ] 会话、消息与 Agent 调用均不提供物理删除；删除仍有消息的会话时数据库外键拒绝。
- [ ] 用例覆盖成功、失败、跳过三类 Agent 调用，覆盖重复消息、并发首条消息、稳定排序与脱敏；每步输出中文日志（操作、预期、实际、结论）。
- [ ] 本切片不实现聊天 HTTP 接口、SSE、需求摘要生成、`agent_runs` 的查询接口或管理后台展示；这些分别属 2/3/8 号 demo。
