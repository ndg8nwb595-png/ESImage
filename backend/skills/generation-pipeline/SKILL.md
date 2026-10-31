---
name: generation-pipeline
description: >-
  把本仓库「用户输入提示词 → 生成图片」从演示占位图升级为真实 8 Agent + 豆包 Seedream 出图的操作指引。
  保证真实出图、链路完整、失败兜底、留白合成。当用户要求实现、改造、修复或调试生图管线、示例图/全套批次、
  Agent 编排、豆包或 Seedream 接入、留白合成，或说「保证生图」「把占位图换成真出图」时使用本 skill。
---

# 生图管线：从用户提示词到真正出图

本 skill 教你在**这个仓库**里把「用户点生成」变成「真的拿到一张可上架的商品图」。
当前后端是演示桩——`backend/app/modules/workspace/pipeline.py` 只推进阶段并产 Pillow 占位 PNG；
本 skill 指导把它替换成真实 8 Agent + 豆包 Seedream 出图，落点按
`backend/app/modules/generation/README.md` 的规划（模块目录已建，文件待写）。

权威依据是 `docs/prd/4-生图任务与结果/4-生图任务与结果prd.md`（PRD 4）。本 skill **不重复 PRD**，
而是把它操作化：每一步做什么、动哪个文件、别动哪个、怎么验证、哪些判断容易做错。
需要完整字段契约时读本目录 `references/`，仍以 PRD 4 为准。

## 适用范围（别误用）

- ✅ 生成示例图、全套批次、8 Agent 全链路、豆包 Seedream 接入、留白合成、失败重试降级。
- ❌ 聊天轻链路只调 planner + product_understanding，**不出图**，不在本 skill 范围（现状见 `chat/agents.py`）。

## 八条铁律（保证生图的底线，违反任何一条都不算「生图成功」）

1. **真实出图**：`image_generator` 必须真调 Seedream 并产出图片文件。任何情况下不允许落占位图充当结果。
2. **顺序固定**：`planner → product_understanding → copywriter → prompt_builder → image_generator → quality_reviewer → (repairer → image_generator) / platform_rule → text_composition`，不重排、不跳过。
3. **每次调用落库**：每个 Agent 调用写一条 `agent_runs`（status ∈ success/failed/skipped，含 token、耗时、错误）。
4. **按规则重试降级**：非生图 Agent 失败重试 10 次（指数退避 1s→…→30s 封顶）；生图每张最多 2 次、2 次失败整任务失败；核心 Agent 失败任务失败，非核心失败跳过并标记「未校验/未修复」。
5. **留白不写字**：prompt 只描述画面 + 显式留白区；中文文案一律后端合成，绝不写进生图 prompt（否则模型画错字）。
6. **全套复用**：`full` 复用 `sample` 产出的计划/文案/提示词（已覆盖 6 张图）；示例图即主图，文件复用不重生成。
7. **状态机合法**：只走合法迁移；重生成/重试 `supersede` 旧图，绝不覆盖；`cancelled` 是终态。
8. **缺 Key 即失败**：`ARK_API_KEY` 为空时启动即校验失败，不静默回退占位图。

## 落地步骤（按顺序，每步可独立验证）

> 每步标「动哪里 / 别动哪里 / 怎么验证」。先跑通第 1 步再往下，别一次铺开。

**第 1 步 · 先验证 Seedream 能出图（最重要，别跳过）**

- 动哪里：写一个一次性脚本，用真实 `ARK_API_KEY` 调一次图生图/文生图 + 一次文本推理。
- 别动哪里：先不写编排，先确认模型名、图生图能力、留白参数到底怎么传。
- 怎么验证：拿到一张真实生成的图片文件。
- 为什么：PRD 0 §15 明确「豆包具体模型名/图生图能力/留白控制参数未实测」，这是全链路最大的不确定点，先消除它再谈编排。

**第 2 步 · doubao.py 适配层**

- 动哪里：`backend/app/modules/generation/doubao.py`。读 `backend/app/core/config.py` 里已预留的 `ARK_API_KEY / ARK_BASE_URL / ARK_TEXT_MODEL / ARK_TIMEOUT_SECONDS`。
- 别动哪里：不硬编码 Key/URL；不改 workspace 现有 HTTP 契约。
- 怎么验证：缺 `ARK_API_KEY` 时启动报错；对外提供文本/视觉/图像/审核四个方法。

**第 3 步 · agents.py（8 Agent + 契约 + 重试 + 落库）**

- 动哪里：`backend/app/modules/generation/agents.py`。契约见 `references/agents-contract.md`。
- 怎么验证：每个 Agent 输出做结构化校验，失败按铁律 4 重试/降级，成功/失败/跳过都写 `agent_runs`。

**第 4 步 · pipeline.py（sample → full 状态机）**

- 动哪里：`backend/app/modules/generation/pipeline.py`。状态机见 `references/state-machine.md`。
- 别动哪里：不改 `workspace/generations.py` 暴露的接口字段与返回结构。
- 怎么验证：走通 sample 出一张主图 → confirm → full 出 6 张。

**第 5 步 · composition.py（留白合成）**

- 动哪里：`backend/app/modules/generation/composition.py`。默认版式见 `references/state-machine.md` §留白。
- 怎么验证：基础图 + `layout_instruction` → 合成 PNG；文案超长缩字号/截断，不阻塞出图。

**第 6 步 · seed.py**

- 动哪里：`backend/app/modules/generation/seed.py`。8 条系统提示词、模型配置、模板/素材/尺寸种子。

## 几个最容易做错的判断

- **图生图还是文生图**：有上传商品图 → 图生图；没有 → 文生图。别混用。
- **复用还是重跑**：`full` 只重跑 5 张详情图的 image_generator→审核→规范→合成；planner/product_understanding/copywriter/prompt_builder 与示例图全部复用，保证风格一致。
- **单张失败 vs 整批失败**：生图本身 2 次失败 → 整批 `failed`；审核/合成/规范失败 → 只该张 `failed`、其余继续，最终 `partially_failed`。
- **审核失败不自动重试**：内容审核不过就标失败让用户调整，别循环触发审核。
- **重生成是新记录**：`supersede` 旧图、新图沿用原提示词，旧文件保留可追溯；不覆盖、不改总数。
- **并发**：同一用户同时只允许 1 个 `queued`/`running` 批次；`sample_ready` 不占名额。

## 端到端例子

商品「轻盈透气衬衫」，风格「简约白底」，尺寸 1000×1000，上传 1 张商品图。

1. 点「生成示例图」→ 建 `sample` 批次（total_count=1，status=queued）。
2. 管线走全链路：planner 出 6 张计划 → product_understanding 出画像（category=服饰鞋包、selling_points=[冰感面料, 不易起球, 通勤百搭]）→ copywriter 出 6 组文案 → prompt_builder 出带 `whitespace` 的提示词 → image_generator 调 Seedream 图生图出 1 张基础图 → quality_reviewer 通过 → platform_rule 通过 → text_composition 合成标题/卖点 → 批次 `sample_ready`。
3. 用户确认 → `sample` 置 `confirmed`，建 `full` 批次（total_count=6，completed_count=1）。
4. `full` 复用示例图作第 1 张主图（image_type=final、source_image_id 指向示例图），对 5 张详情图逐张走 image_generator→审核→规范→合成，串行推进。
5. 全部成功 → `completed`，6 张 `final` 图 `is_history_visible=true`，进入历史作品。

「完成」= 6 张真实 Seedream 图 + 合成中文，全部 `success`，能从结果区预览/下载。

## 完成自查（改完逐项过）

- [ ] 点「生成示例图」真的产出 1 张 Seedream 主图（不是占位图）。
- [ ] 8 个 Agent 按序调用，每次写 `agent_runs`。
- [ ] 除生图外 Agent 失败重试 10 次；核心失败任务失败、非核心跳过标记。
- [ ] 生图每张最多 2 次，2 次失败整批失败；非生图单张失败其余继续。
- [ ] prompt 含留白要求，图上中文由后端合成且正确。
- [ ] 确认后 full 出 6 张，示例图即主图不重生成。
- [ ] 同一用户同时只有 1 个 `queued`/`running` 批次；`sample_ready` 不占名额。
- [ ] 缺 `ARK_API_KEY` 时启动失败。

## 需要细节时读

- `references/agents-contract.md` —— 8 Agent 的输入/输出 JSON、顺序、重试降级细节。
- `references/state-machine.md` —— 批次/单图状态、stage 枚举、全套复用、留白合成契约。
- 权威口径仍以 `docs/prd/4-生图任务与结果/4-生图任务与结果prd.md` 为准；本 skill 是操作化，不替代 PRD。
