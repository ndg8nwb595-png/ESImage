# 更改记录

## 2026-10-31

### 新增文件

1. `AGENTS.md` —— 新建（仓库原先两者皆无，按用户选择创建 AGENTS.md）。内容为 `## Agent skills` 块，含 Issue tracker / Triage labels / Domain docs 三节。
2. `docs/agents/issue-tracker.md` —— 由技能种子模板 `issue-tracker-github.md` 翻译为中文，结构与命令保持一致；PR 请求面保持 `no`。
3. `docs/agents/triage-labels.md` —— 由 `triage-labels.md` 翻译；五标签映射均为同名。
4. `docs/agents/domain.md` —— 由 `domain.md` 翻译；默认单上下文布局。

### 验证

- 首次 `gh label list` → `HTTP 401: Bad credentials`；用户重新登录后 `gh auth status` 显示已登录（fine-grained PAT）。
- `gh label list` 成功，现有标签：accessibility、bug、documentation、duplicate、enhancement、good first issue、help wanted、invalid、question、wontfix。
- `gh label create` ×4 → `HTTP 403: Resource not accessible by personal access token`，因 PAT 缺 Issues 写权限，标签未创建。
- 提交 `6fc53a4`（分支 `chore/agent-skills-setup`，10 个文件）。
- `git push -u origin chore/agent-skills-setup` → `403 Permission to ndg8nwb595-png/ESImage.git denied`，PAT 缺 Contents 写权限；远程 `main` 仍为 `071fa9a`。
- 用户将 classic PAT 写入 `.env`（键名 `GITHUBTOKEN`）。用 `gh auth login --with-token` 登录成功，scopes 含 `repo`。
- `gh auth setup-git` 后 `git push -u origin chore/agent-skills-setup` 成功，远程新增分支。
- `gh label create` 创建 4 个标签成功，`gh label list` 校验五项齐全。
- 用户选择 fast-forward：`git switch main && git merge --ff-only chore/agent-skills-setup && git push origin main`，`main` 从 `071fa9a` 前进到分支顶端。

### 未改动

- `README.md`、`.vscode/settings.json` 未触碰。

## 2026-10-31 会话 2：AIGC 系统 PRD

### 新增文件

1. `docs/prd/0-系统汇总prd.md` —— 系统汇总 PRD，含定位、范围、角色权限、总体流程、8 Agent 体系、生图与文件、管理后台、数据与接口、技术架构、状态机边界、验收标准、术语、开发约束、风险与决策记录。

### 验证

- 文件由 Write 工具创建成功。
- 尚未编写子 PRD、未运行代码、未执行测试。
- 尚未 commit，等待用户评审汇总稿。

### 未改动

- 既有业务代码（仓库当前无业务代码）、`AGENTS.md`、`docs/agents/*` 未触碰。

## 2026-10-31 会话 3：12 份 PRD 交叉评审（只读）

### 未改动

- `docs/prd/*`、`GLOSSARY.md`、`AGENTS.md`、业务代码均未修改。

### 评审输出

- 通读 12 份 PRD 与术语表，发现：阻断级 12 项、设计不合理 14 项、冗余 11 项、一致性约 20 项。
- 关键冲突点已用 Grep 核对：归档桶 vs 单桶前缀、尺寸预设无表、`stage` 仅接口有、视觉模型未配置、Token 字段三处重复、`beat` 未列入汇总服务清单、DB 保留策略矛盾等。

### 验证

- 仅做文档读取与 Grep 核对，未运行代码或测试，未 commit。

### 新增文件

- `docs/reviews/PRD交叉评审-2026-10-31.md`：12 份 PRD 的交叉评审报告，含 8 个 P0、16 个 P1、19 个 P2、15 个 P3 与 10 个待拍板决策。未修改任何 PRD 原文件。

### 2026-10-31 会话 2 补充：术语表独立

#### 新增文件

1. `GLOSSARY.md` —— 仓库根目录术语表，含使用规则、20 个术语、变更记录。

#### 修改文件

1. `docs/prd/0-系统汇总prd.md` —— 第 13 章由完整术语表改为指向 `GLOSSARY.md` 的说明。
2. `AGENTS.md` —— 在「Domain docs」后新增「Domain glossary」小节，写入术语表路径、同步规则与 20 个术语。

#### 验证

- 三个文件均写入成功。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 2 补充：11 份子 PRD 完成

#### 新增文件

1. `docs/prd/1-登录界面prd.md`
2. `docs/prd/2-用户端创作工作台prd.md`
3. `docs/prd/3-Agent会话交互prd.md`
4. `docs/prd/4-生图任务与结果prd.md`
5. `docs/prd/5-历史作品prd.md`
6. `docs/prd/6-管理后台-账号与权限prd.md`
7. `docs/prd/7-管理后台-用户与生图记录prd.md`
8. `docs/prd/8-管理后台-聊天记录prd.md`
9. `docs/prd/9-后端服务与接口prd.md`
10. `docs/prd/10-数据模型与存储prd.md`
11. `docs/prd/11-部署与运维prd.md`

#### 修改文件

1. `docs/prd/0-系统汇总prd.md`：
   - 生成批次拆为 `sample` 示例批次 / `full` 全套批次，并补充两者状态机。
   - MinIO 改为单桶 `esimage` + 前缀分区。
   - 用户端布局由左右分栏改为三栏（会话列表 / 聊天框 / 参数面板+结果区）。
   - 生成链路补充「文字合成」步骤；验收表布局描述同步。
2. `docs/prd/2-用户端创作工作台prd.md`：2.1 布局图改为三栏，2.2 宽度规则、第 10 章、验收标准同步。
3. `docs/prd/3-Agent会话交互prd.md`：会话列表位置改为页面最左侧独立栏。

#### 验证

- 已用 Glob 确认 `docs/prd/` 下 12 份文档齐全。
- 已用 Grep 检查旧布局描述，残留的「左右分栏布局」已修正为「三栏布局」。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 2 补充：参数模型调整（1 主图 + 5 详情图）

用户要求：删除参数面板的「产出类型」；只有商品名称必填，其余选填；风格改为自由文本、后台不再配置；尺寸不选默认 1:1。确认后每次生成 1 张主图 + 5 张详情图，示例图即主图。

#### 修改文件

1. `0-系统汇总prd.md`：参数面板、生成流程、张数、内容追溯、素材模板、验收、决策记录同步；删除产出类型与风格后台配置。
2. `2-用户端创作工作台prd.md`：2.1 布局、4.1 字段、4.3 风格、4.4 尺寸、4.5 图片构成、6.2/6.3 模板、7.1/7.2 校验、8.1/8.3 流程、9.2 结果、第 10 章聊天、验收与待确认同步。
3. `3-Agent会话交互prd.md`：聊天可用条件改为商品名称；风格未填时 Agent 推荐；上下文参数去掉产出类型。
4. `4-生图任务与结果prd.md`：输入、快照、校验、批次、规划 JSON、结果、下载、配置管理、验收同步；10.3 改为「风格规则（不做后台配置）」。
5. `5-历史作品prd.md`：卡片、详情、网格、验收改为 1 主图 + 5 详情图。
6. `6-管理后台-账号与权限prd.md`：权限点与审计去掉风格。
7. `7-管理后台-用户与生图记录prd.md`：筛选、批次字段、单图详情、CSV、验收改为图片角色/图片构成。
8. `9-后端服务与接口prd.md`：移除 `/styles` 与 `/admin/styles`；模板查询改 `image_role`；示例请求改 `style_text`、去 `output_type`；确认响应 `total_count=6`。
9. `10-数据模型与存储prd.md`：批次去 `output_type`、`style_name`→`style_text`；图片加 `image_role`；模板 `output_type`→`image_role`；枚举与种子同步。
10. `GLOSSARY.md` 与 `AGENTS.md`：示例图定义改为「即主图」。

#### 验证

- 已用 Grep 搜旧词（产出类型、主图 4、详情图 6、8 种、style_id、output_type、/styles、风格配置），残留仅为「不提供/不维护」类否定表述。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 2 补充：失败重试策略调整

用户要求：除生图模型外，所有 Agent 失败重试 10 次；生图模型失败 2 次则整个任务失败。

#### 修改文件

1. `4-生图任务与结果prd.md`：
   - 4.1 Agent 清单的失败策略列同步。
   - 8.1 Agent 失败：非生图 Agent 重试 10 次、指数退避；生图最多 2 次，2 次失败整批失败。
   - 8.2 单张失败：生图失败 2 次整批失败；非生图原因的单张失败可继续。
   - 8.5 超时：整批 30 分钟。
   - 验收标准同步。
2. `0-系统汇总prd.md`：6.4 失败与降级同步；10.4 整批生成超时改为 30 分钟。
3. `11-部署与运维prd.md`：`BATCH_TIMEOUT_SECONDS` 由 600 改为 1800。

#### 验证

- 未运行代码或测试。
- 已提交 `b0c3575`（分支 `docs/aigc-prd`），并 fast-forward 合并到 `main` 后推送远程。

### 2026-10-31 会话 3 补充：P0-1 并发锁死修复

用户选择「只改并发口径」。

- 进行中批次仅指 `queued` / `running`；`sample_ready` 不占并发名额。
- 旧 `sample_ready` 保留原状态，仅最新一条可确认；旧示例不阻塞重新生成或确认。
- 确认全套在数据库事务中加行锁；被确认的 `sample_ready` 示例批次不参与并发校验。

#### 修改文件

1. `4-生图任务与结果prd.md`：§2.3、§3.3、§3.6.1、§5.4、§6.1、§8.6、§12。
2. `2-用户端创作工作台prd.md`：§7.3、§8.2。
3. `9-后端服务与接口prd.md`：§2.6。
4. `0-系统汇总prd.md`：10.4 单用户并发指标。

#### 验证

- 已用 Grep 确认不再存在“queued/running/sample_ready 一起限制”的旧表述。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 3 补充：P0-2 模板改为整套模板（后台任务）

- 按方案 A 落地：模板定义整套 1 主图 + 5 详情图的视觉体系，不再区分单张图片角色。
- 移除模板的 `image_role`、模板携带尺寸的表述与错误码 30012。
- 涉及 `2`、`4`、`9`、`10`、`0` 号文档；未运行测试、未 commit。

### 2026-10-31 会话 3 补充：术语一致性

- `GLOSSARY.md` 与 `AGENTS.md`：生成批次定义改为 `sample` / `full`；归档桶改为 `archive/` 归档前缀。
- `0`、`5` 号文档中的“归档桶”同步改为 `archive/` 归档前缀。

### 2026-10-31 会话 3 补充：P0-3 尺寸预设建表

用户选择「新增 `size_presets` 表」。

- `10-数据模型与存储prd.md`：新增 §4.18 `size_presets`（平台名称、宽、高、排序、状态、创建/更新时间），表数量 17→18；实体关系、枚举、种子数据、验收同步。
- `0-系统汇总prd.md`：§9.2 表清单 17→18，新增第 18 张表；文档索引同步。
- `4-生图任务与结果prd.md`：§10.4 注明尺寸预设存储于 `size_presets`。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 3 补充：P0-4 批次 stage 字段

用户选择「新增 `stage` 字段」。

- `10-数据模型与存储prd.md`：`generation_batches` 新增 `stage VARCHAR(32)`，补 `ck_batches_stage` 与 §5 阶段枚举。
- `9-后端服务与接口prd.md`：批次状态响应注明 `stage` 来自数据库字段。
- `4-生图任务与结果prd.md`：§6.4 注明阶段由 Worker 每阶段更新，前端直接读取。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 3 补充：P0-5 视觉模型配置

用户选择「新增 `vision_model`」。

- `10-数据模型与存储prd.md`：`model_configs` 新增 `vision_model`，为空时质量审核跳过并标记。
- `8-管理后台-聊天记录prd.md`：模型配置页新增“视觉模型”输入框；保存校验允许为空。
- `4-生图任务与结果prd.md`：质量审核 Agent 改为调用 `vision_model`。
- `0-系统汇总prd.md`：外部集成补“豆包视觉模型”。
- `9-后端服务与接口prd.md`：模型配置请求示例补 `vision_model`。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 3 补充：P0-6 平台规范规则来源

用户选择「写进 `system_prompts`」。

- `4-生图任务与结果prd.md`：§4.3.8 平台规范 Agent 的输入补平台规范提示词，并注明规则来源。
- `8-管理后台-聊天记录prd.md`：`{{platform_rules}}` 取自 `platform_rule` 系统提示词；Agent 列表下补说明。
- `0-系统汇总prd.md`：§6.1 输入补充；§8.6 注明平台规范规则存放在提示词中，不单独建表。
- `10-数据模型与存储prd.md`：种子数据注明 `platform_rule` 含初始规则。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 3 补充：P0-7 参数与上传图恢复

用户选择「只存前端 localStorage」。

- `2-用户端创作工作台prd.md`：参数与上传图 ID 存 localStorage；刷新/切换可恢复，换设备/清缓存丢失；待确认项补限制。
- `3-Agent会话交互prd.md`：会话不持久化参数；聊天上下文参数由前端 localStorage 读取并随请求提交。
- `9-后端服务与接口prd.md`：新增 `GET /uploads/{upload_id}`（单图元数据/缩略图）；聊天请求体补 `params`；注明会话不持久化参数。
- `10-数据模型与存储prd.md`：会话不存参数；`uploaded_assets.session_id` 首次生成时回填。
- `0-系统汇总prd.md`：布局说明、边界清单与风险表补 localStorage 限制。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 3 补充：P0-8 首条会话原子创建

用户选择「后端原子创建」。

- `3-Agent会话交互prd.md`：§2.2/§3.2 明确首条消息与生成由后端事务内创建会话，`client_message_id` 幂等。
- `9-后端服务与接口prd.md`：新增首条消息接口 `POST /sessions/messages`（`session_id` 可为空）；`POST /sessions/{id}/messages` 用于已有会话；生成接口 `session_id` 可为空；幂等表补首条消息规则；SSE 说明补 `meta` 返回新会话。
- `10-数据模型与存储prd.md`：`chat_messages` 补首条消息建会话的 Redis 幂等说明。
- 未运行代码或测试；未 commit。

### 2026-10-31 会话 3 补充：重新生成 Agent 配置

- `.gitignore` 新增 `docs/reviews/`，本地评审记录不入库。
- 按 `setup-matt-pocock-skills` 模板重写 `docs/agents/issue-tracker.md`、`triage-labels.md`、`domain.md`。
- `AGENTS.md` 的 Domain docs 行改为“单上下文（single-context）布局”；`Domain glossary` 小节保留。
- 用 `gh label list` 校验五个 triage 标签全部存在，无需新建。
- 未运行代码或测试；未 commit。

## 2026-10-31 会话 5：登录最小 demo 文档拆解（to-tickets）

### 移动文件

1. `docs/prd/1-登录界面prd.md` → `docs/prd/1-登录界面/1-登录界面prd.md`（用户确认）。

### 修改文件

1. `docs/prd/0-系统汇总prd.md` 第 121 行索引路径改为 `1-登录界面/1-登录界面prd.md`。
2. `docs/prd/6-管理后台-账号与权限prd.md` 第 11 行关联文档路径同步。

### 新增文件

1. `docs/prd/1-登录界面/README.md` —— 最小 demo 范围、演示账号、依赖图、验收口径、取舍与待确认项。
2. `docs/prd/1-登录界面/接口文档-登录最小demo.md` —— 3 个 auth 接口、JWT 规范、错误码、前端处理、审计约定、已知限制。
3. `docs/prd/1-登录界面/issues/01-工程骨架与演示账号.md`
4. `docs/prd/1-登录界面/issues/02-登录接口与登录页闭环.md`
5. `docs/prd/1-登录界面/issues/03-登录态恢复与路由守卫.md`
6. `docs/prd/1-登录界面/issues/04-角色分流与双角色切换.md`
7. `docs/prd/1-登录界面/issues/05-账号状态即时失效.md`
8. `docs/prd/1-登录界面/issues/06-退出登录与审计.md`

### 验证

- `find docs/prd/1-登录界面 -type f` 确认 9 个文件（PRD + README + 接口文档 + 6 tickets）齐全。
- `grep -rn "1-登录界面prd.md" docs` 确认旧顶层路径无残留；0/6 号引用已指向新路径。
- 未运行代码或测试，未 commit。
- 未创建 GitHub issue（用户要求输出到新文件夹，tickets 采用本地文件模板）。

## 2026-10-31 会话 6：创作工作台最小 demo 文档拆解（to-tickets）

### 移动文件

1. `docs/prd/2-用户端创作工作台prd.md` → `docs/prd/2-用户端创作工作台/2-用户端创作工作台prd.md`（用户要求单独建文件夹）。

### 修改文件

1. `docs/prd/0-系统汇总prd.md` 第 122 行索引路径改为 `2-用户端创作工作台/2-用户端创作工作台prd.md`。
2. `docs/prd/3-Agent会话交互/3-Agent会话交互prd.md` 第 11 行关联文档路径同步。
3. `docs/prd/4-生图任务与结果prd.md` 第 11 行关联文档、第 564 行引用路径同步。
4. `docs/prd/5-历史作品prd.md` 第 11 行关联文档路径同步。

### 新增文件

1. `docs/prd/2-用户端创作工作台/README.md` —— 最小 demo 范围、演示账号、依赖图、ticket 表、验收脚本、取舍与待确认项。
2. `docs/prd/2-用户端创作工作台/接口文档-创作工作台最小demo.md` —— 通用约定、权限、分页、幂等、并发、SSE、会话/上传/生成/确认/预览/下载接口、数据结构、状态机、错误码、与 PRD 9 差异、未实现接口、验收调用序列与 curl 示例。
3. `docs/prd/2-用户端创作工作台/issues/01-工作台骨架与最小数据表.md`
4. `docs/prd/2-用户端创作工作台/issues/02-参数面板与商品名称校验.md`
5. `docs/prd/2-用户端创作工作台/issues/03-商品图上传与恢复.md`
6. `docs/prd/2-用户端创作工作台/issues/04-会话列表与聊天轻链路.md`
7. `docs/prd/2-用户端创作工作台/issues/05-生成示例图与阶段进度.md`
8. `docs/prd/2-用户端创作工作台/issues/06-确认并生成全套与结果网格.md`
9. `docs/prd/2-用户端创作工作台/issues/07-结果预览与单张下载.md`

### 验证

- `find docs/prd/2-用户端创作工作台 -type f` 确认 10 个文件（PRD + README + 接口文档 + 7 tickets）齐全。
- `grep -rn "2-用户端创作工作台prd" docs` 确认外部旧路径无残留；仅文件夹内 README/接口文档以相对名引用。
- 修正接口文档聊天 `params` 误带 `upload_ids` 的问题；`upload_ids` 仅保留在生成示例请求中。
- 修正 `30016` HTTP 状态为 404，与 PRD 9 一致。
- 修正全套批次 JSON 示例缺省说明、确认幂等返回口径，并补充与 PRD 9 的差异说明。
- 已提交 `eba6b8d`（分支 `main`）并推送 `origin/main`；推送后远程 `main` 为 `bb34985`（并行会话的 3-Agent demo 提交叠加在 `eba6b8d` 之上，我的提交仍为祖先）。
- 工作区仍有并行会话的未提交改动（5/6 号 PRD 目录迁移、7/8 号 PRD 编辑、4 号 demo 文档、记忆摘要补充），本轮未触碰、未提交。
- 未运行代码或测试；未创建 GitHub issue（tickets 为本地文件）。

## 2026-10-31 会话 7：Agent 会话交互最小 demo 文档拆解（to-tickets）

### 移动文件

1. `docs/prd/3-Agent会话交互prd.md` → `docs/prd/3-Agent会话交互/3-Agent会话交互prd.md`（用户要求单独建文件夹；使用 `git mv` 保留历史）。

### 修改文件

1. `docs/prd/0-系统汇总prd.md` 第 123 行索引路径改为 `3-Agent会话交互/3-Agent会话交互prd.md`。
2. `docs/prd/2-用户端创作工作台/2-用户端创作工作台prd.md` 关联文档与第 10 章引用改为 `../3-Agent会话交互/3-Agent会话交互prd.md`。
3. `docs/prd/2-用户端创作工作台/接口文档-创作工作台最小demo.md` 上游依据路径同步。
4. `docs/prd/4-生图任务与结果prd.md` 关联文档路径同步。
5. `docs/prd/8-管理后台-聊天记录prd.md` 关联文档路径同步。

### 新增文件

1. `docs/prd/3-Agent会话交互/README.md` —— 最小 demo 范围、前置、接口总览、依赖图、验收脚本、取舍与待确认项。
2. `docs/prd/3-Agent会话交互/接口文档-Agent会话交互最小demo.md` —— 通用约定、增量接口（重命名/软删除）、消息分页与超时、聊天 SSE 事件与字段、需求摘要、`requirement_changed`、幂等重放、断线重连、错误码、与 2/9/10 号差异、待确认项。
3. `docs/prd/3-Agent会话交互/issues/01-会话重命名与软删除.md`
4. `docs/prd/3-Agent会话交互/issues/02-消息展示与输入规则.md`
5. `docs/prd/3-Agent会话交互/issues/03-轻链路编排与上下文.md`
6. `docs/prd/3-Agent会话交互/issues/04-需求变化提示与生图衔接.md`

### 验证

- `find docs/prd/3-Agent会话交互 -type f` 确认 7 个文件（PRD + README + 接口文档 + 4 tickets）齐全。
- `grep -rn "3-Agent会话交互prd" docs` 确认外部旧路径无残留；仅新文件夹内以相对文件名引用。
- 未运行代码或测试，未 commit，未创建 GitHub issue（tickets 为本地文件）。

## 2026-10-31 会话 8：生图任务与结果最小 demo 文档拆解（to-tickets）

### 移动文件

1. `docs/prd/4-生图任务与结果prd.md` → `docs/prd/4-生图任务与结果/4-生图任务与结果prd.md`（用户要求单独建文件夹；使用 `git mv` 保留历史）。

### 修改文件

1. `docs/prd/4-生图任务与结果/4-生图任务与结果prd.md`：第 11 行关联文档改为 `../2-用户端创作工作台/...`、`../3-Agent会话交互/...`、`../7-...`；第 564 行引用改为 `../2-用户端创作工作台/2-用户端创作工作台prd.md`。
2. `docs/prd/0-系统汇总prd.md` 第 124 行索引路径改为 `4-生图任务与结果/4-生图任务与结果prd.md`。
3. `docs/prd/10-数据模型与存储prd.md` 第 11 行关联文档路径同步。
4. `docs/prd/3-Agent会话交互/3-Agent会话交互prd.md` 第 11 行关联文档路径同步。
5. `docs/prd/7-管理后台-用户与生图记录prd.md` 第 11 行关联文档路径同步。
6. `docs/prd/8-管理后台-聊天记录prd.md` 第 11 行关联文档路径同步。
7. `docs/prd/5-历史作品/5-历史作品prd.md` 第 11 行关联文档路径改为 `../2-...`、`../4-...`。

### 新增文件

1. `docs/prd/4-生图任务与结果/README.md` —— 最小 demo 范围（做/不做/取舍）、环境变量与种子数据、11 个接口总表、依赖图、ticket 表、20 步验收脚本、12 项待确认。
2. `docs/prd/4-生图任务与结果/接口文档-生图任务最小demo.md` —— 通用约定、demo 运行时约定、配置读取、示例/确认/取消/重生成/查询、单图与整组下载、8 个 Agent 内部契约、文字合成契约、状态机与并发、错误码、数据结构、与 PRD 9/10 及 2 号 demo 的差异、未实现接口、验收调用序列与 curl。
3. `docs/prd/4-生图任务与结果/issues/01-生成数据模型与Agent运行时.md`
4. `docs/prd/4-生图任务与结果/issues/02-文字留白合成与默认版式.md`
5. `docs/prd/4-生图任务与结果/issues/03-示例批次真实全链路.md`
6. `docs/prd/4-生图任务与结果/issues/04-确认全套与详情图生成.md`
7. `docs/prd/4-生图任务与结果/issues/05-失败重试与降级.md`
8. `docs/prd/4-生图任务与结果/issues/06-取消任务.md`
9. `docs/prd/4-生图任务与结果/issues/07-单张重试与重生成.md`
10. `docs/prd/4-生图任务与结果/issues/08-整组ZIP与manifest.md`

### 验证

- `find docs/prd/4-生图任务与结果 -type f` 确认 11 个文件（PRD + README + 接口文档 + 8 tickets）齐全。
- `grep -rn "4-生图任务与结果prd\.md" docs --include="*.md"` 确认目录外引用均为带文件夹的相对路径：0/7/8/10 号（顶层）无 `../`，2/3/5 号（文件夹内）带 `../`；无旧顶层路径残留。
- 发现未修改的问题（超出本任务范围）：6/7/10 号仍以旧顶层名引用 6 号文档，6 号自身第 11 行也未加 `../`；留待用户决定是否统一。
- 未运行代码或测试，未 commit，未创建 GitHub issue（tickets 为本地文件）。

## 2026-10-31 会话 9：历史作品最小 demo 文档拆解（to-tickets）

### 移动文件

1. `docs/prd/5-历史作品prd.md` → `docs/prd/5-历史作品/5-历史作品prd.md`（用户要求单独建文件夹；使用 `git mv` 保留历史）。

### 修改文件

1. `docs/prd/0-系统汇总prd.md`：5 号索引路径改为 `5-历史作品/5-历史作品prd.md`。
2. `docs/prd/2-用户端创作工作台/2-用户端创作工作台prd.md`：关联文档路径改为 `../4-生图任务与结果/4-生图任务与结果prd.md`、`../5-历史作品/5-历史作品prd.md`。

### 新增文件

1. `docs/prd/5-历史作品/README.md` —— 最小 demo 范围（做/不做/取舍）、前置与种子、接口总表、依赖图、14 步验收脚本、11 项待确认。
2. `docs/prd/5-历史作品/接口文档-历史作品最小demo.md` —— 通用约定、历史可见性、缩略图与归档约定、列表/详情/缩略图/预览/单张下载/整组 ZIP、manifest.csv、错误码、前端约定、与正式文档差异、未实现接口、19 步验收序列。
3. `docs/prd/5-历史作品/issues/01-历史列表与分页.md`
4. `docs/prd/5-历史作品/issues/02-批次详情与图片网格.md`
5. `docs/prd/5-历史作品/issues/03-大图预览与单张下载.md`
6. `docs/prd/5-历史作品/issues/04-整组ZIP与manifest.md`
7. `docs/prd/5-历史作品/issues/05-归档图片读取与降级.md`

### 验证

- `find docs/prd/5-历史作品 -type f` 确认 8 个文件（PRD + README + 接口文档 + 5 tickets）齐全。
- `grep -rn "5-历史作品prd\.md" docs` 确认外部引用均带文件夹路径，无旧顶层路径残留。
- 未运行代码或测试，未 commit，未创建 GitHub issue（tickets 为本地文件）。

## 2026-10-31 会话 10：管理后台-账号与权限最小 demo 文档拆解（to-tickets）

### 移动文件

1. `docs/prd/6-管理后台-账号与权限prd.md` → `docs/prd/6-管理后台-账号与权限/6-管理后台-账号与权限prd.md`（用户要求单独建文件夹；使用 `git mv`）。

### 修改文件

1. `docs/prd/0-系统汇总prd.md` 第 126 行索引路径改为 `6-管理后台-账号与权限/6-管理后台-账号与权限prd.md`。
2. `docs/prd/1-登录界面/1-登录界面prd.md` 第 39 行引用改为 `../6-管理后台-账号与权限/6-管理后台-账号与权限prd.md`。
3. `docs/prd/7-管理后台-用户与生图记录prd.md` 第 11/26/129 行引用改为带文件夹路径。
4. `docs/prd/10-数据模型与存储prd.md` 第 11/729 行引用改为带文件夹路径。

### 新增文件

1. `docs/prd/6-管理后台-账号与权限/README.md` —— 最小 demo 范围、做/不做、相对 PRD 取舍、前置与演示账号、14 个接口总览、依赖图、16 步验收脚本、8 项待确认。
2. `docs/prd/6-管理后台-账号与权限/接口文档-账号与权限最小demo.md` —— 通用约定与权限判定顺序、种子与 23 个权限点、用户列表/新建/详情/编辑/重置密码/状态操作、角色权限、操作日志、数据结构、账号边界与状态机、错误码、前端约定、与 9/10 号差异、未实现接口、24 步验收序列与 curl 示例。
3. `docs/prd/6-管理后台-账号与权限/issues/01-管理后台骨架与用户列表.md`
4. `docs/prd/6-管理后台-账号与权限/issues/02-新建账号与角色组合校验.md`
5. `docs/prd/6-管理后台-账号与权限/issues/03-编辑账号与角色边界.md`
6. `docs/prd/6-管理后台-账号与权限/issues/04-禁用启用软删除与恢复.md`
7. `docs/prd/6-管理后台-账号与权限/issues/05-重置密码与旧Token失效.md`
8. `docs/prd/6-管理后台-账号与权限/issues/06-用户详情与统计占位.md`
9. `docs/prd/6-管理后台-账号与权限/issues/07-角色管理与权限点配置.md`
10. `docs/prd/6-管理后台-账号与权限/issues/08-操作日志查询.md`

### 验证

- `find docs/prd/6-管理后台-账号与权限 -type f` 确认 11 个文件（PRD + README + 接口文档 + 8 tickets）齐全。
- `grep -rnP "(^|[^/])6-管理后台-账号与权限prd\.md" docs` 只剩文件夹内 README/接口文档的相对文件名引用，外部无旧路径。
- 未运行代码或测试，未 commit，未创建 GitHub issue（tickets 为本地文件）。
