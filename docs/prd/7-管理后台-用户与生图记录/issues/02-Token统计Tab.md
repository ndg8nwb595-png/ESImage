# 02: Token 统计 Tab

**What to build:** 在概览页新增「Token 统计」Tab，管理员或超管可按时间范围、用户关键词、多个 Agent、模型筛选，看到输入 Token、输出 Token、总 Token 与调用次数汇总，以及按日期 + 用户 + Agent + 模型聚合的明细表；明细默认按日期倒序、合计 Token 倒序，每页 20 条。只统计成功调用与失败但有 Token 返回的调用，跳过的 Agent 不计 Token。

**Blocked by:** 01（概览四卡与演示数据种子）

**Status:** ready-for-agent

- [ ] 概览页出现「统计卡片 / Token 统计」两个 Tab；Token Tab 对拥有 `admin.tokens.view` 的管理员与超管可见，普通用户 403。
- [ ] 筛选支持起止日期（默认最近 7 天，含今天，按 Asia/Shanghai）、用户关键词（用户名/显示名，可清空）、8 个 Agent 多选、模型名；筛选条件可组合，重置后回到默认 7 天。
- [ ] 汇总展示输入 Token 合计、输出 Token 合计、总 Token、调用次数；汇总口径覆盖全部筛选结果，不只当前页。
- [ ] 明细列包含日期、用户（用户名 + 显示名）、Agent 名称、模型、调用次数、输入 Token、输出 Token、合计 Token；按日期倒序、合计 Token 倒序，再按用户/Agent/模型稳定排序。
- [ ] 明细分页每页固定 20 条；页码超出范围返回空 `items` 或回到最后一页，行为在接口文档中固定。
- [ ] 统计口径：`agent_runs.status=success` 全部计入；`status=failed` 且输入 + 输出 Token > 0 计入；`status=skipped` 与 `failed` 且 0 Token 不计入；调用次数为计入的 `agent_runs` 记录数。
- [ ] 用户归属：优先 `agent_runs.session_id` 对应的 `creative_sessions.user_id`，其次 `agent_runs.batch_id` 对应的 `generation_batches.user_id`；两者都为空的记录不计入按用户明细，并在测试中断言不影响汇总。
- [ ] 日期分组按 Asia/Shanghai 的自然日；跨时区数据不会落到错误日期。
- [ ] 无数据时显示「暂无 Token 数据」；加载失败显示「加载失败，点击重试」。
- [ ] 不提供图表、导出、金额换算；不新增 Token 计费逻辑。
- [ ] 接口与页面各有可执行冒烟测试，关键步骤输出中文日志（如「[Token统计] 默认最近 7 天」「[Token统计] 汇总与明细合计一致」）。
- [ ] 本切片不实现生图记录页面与单图详情。
