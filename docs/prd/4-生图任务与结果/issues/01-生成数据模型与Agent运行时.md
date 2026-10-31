# 01: 生成数据模型、配置种子与 Agent 运行时

**What to build:** 在 2 号 demo 的最小数据表基础上，把生成链路需要的表补齐到 10 号 §4.8~§4.18 的字段、约束与索引；种入 8 条系统提示词、1 条启用的豆包模型配置、模板/素材/尺寸种子与生成所需权限。提供只读配置服务（只返回启用项、60 秒缓存、可手动刷新），实现真实的豆包模型适配层与 Agent 运行时：每次 Agent 调用写入 `agent_runs`，非生图 Agent 失败按 1/2/4/8/16/30 秒指数退避重试 10 次，结构化输出校验失败按 Agent 失败处理，Token 与耗时如实记录。提供批次与单图状态流转服务，统一拒绝非法流转。

**Blocked by:** 2 号 demo 01（工作台骨架与最小数据表）

**Status:** ready-for-agent

- [ ] `generation_batches`、`generated_images`、`agent_runs` 的字段、枚举、约束与索引与 10 号 §4.8~§4.10 一致；`templates`、`material_assets`、`size_presets`、`model_configs`、`system_prompts`、`prompt_versions` 建表。
- [ ] 种子脚本可重复执行：8 条 `system_prompts`（`planner`、`product_understanding`、`copywriter`、`prompt_builder`、`image_generator`、`quality_reviewer`、`repairer`、`platform_rule`）、1 条启用 `model_configs`、2 条模板、4 条素材、4 条 1000×1000 尺寸预设；`platform_rule` 提示词含 `{{platform_rules}}` 占位与最小演示规则。
- [ ] `demo_user` 具备 `user.generate`、`user.history`；`demo_admin` 不具备；种子重复执行不产生重复权限或配置。
- [ ] 豆包适配层覆盖文本、视觉、图像、生成图审核四类调用；`DOUBAO_API_KEY`、`DOUBAO_BASE_URL`、文本/图像模型名缺失时启动校验失败并给出明确提示。
- [ ] `DOUBAO_VISION_MODEL` 为空不是启动错误；质量审核调用返回 `skipped` 并记录原因「未配置视觉模型」。
- [ ] Agent 运行时按 `agent_code` 读取当前启用的系统提示词，调用文本模型，校验返回 JSON 是否符合该 Agent 的输出契约；解析失败计为一次失败并进入重试。
- [ ] 非生图 Agent 单次失败按 1、2、4、8、16、30、30、30、30、30 秒退避，共 10 次；生图 Agent 每张最多 2 次，不走该退避策略。
- [ ] 每次 Agent 调用（含每次失败重试）写入一条 `agent_runs`，记录 `session_id`、`batch_id`、`image_id`、`agent_code`、`status`、`model_name`、`input_summary`、`output_summary`、`input_full`、`output_full`、`prompt_tokens`、`completion_tokens`、`latency_ms`、`error_message`；跳过的 Agent 写 `status=skipped` 并说明原因。
- [ ] 批次状态流转服务只允许 PRD §3.3/§3.4 定义的状态迁移；`sample_ready → running`、`confirmed → running`、`cancelled → running` 等非法流转被拒绝并返回明确错误。
- [ ] 单图状态流转服务只允许 `pending → generating → success/failed/cancelled` 与 `success/failed → superseded`；`success` 不回退；非法流转被拒绝。
- [ ] 同一用户同时只允许 1 个 `queued` / `running` 批次；`sample_ready` 不计入；并发校验由状态服务统一提供。
- [ ] 只读配置服务只返回 `status=active` 的模板/素材/尺寸与启用的模型配置、提示词；缓存 60 秒，提供手动刷新入口；停用项不返回。
- [ ] 用测试命令完成一次假 Agent 编排（使用可替换的测试 provider，不访问真实豆包）：成功路径每个 Agent 一条 `agent_runs`，失败路径按 10 次退避重试且每次一条记录。
- [ ] 本切片不实现示例批次、全套批次、文字合成、取消、重试、ZIP 的 HTTP 行为；只交付可被后续切片调用的数据、配置与运行时能力。
