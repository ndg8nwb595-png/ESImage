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
- 未运行代码或测试，未创建 GitHub issue（tickets 为本地文件）。
- 2026-10-31 已提交并推送：commit `33890f1`（历史作品文档与五个记忆文档），`git push origin main` 成功，远端 main 为 `67f668d`，推送后 `HEAD...origin/main` 为 `0 0`。
- 推送时 GitHub 443 直连超时，使用 `git -c http.curloptResolve=github.com:443:140.82.112.3` 临时固定可用 IP 完成 fetch/push，未修改全局配置。

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
- 未运行代码或测试，未创建 GitHub issue（tickets 为本地文件）。

### 提交记录（2026-10-31）

- 提交 `7d34003 docs: 拆解管理后台账号与权限最小 demo 任务与接口`：新增 README、`issues/01~08`、接口文档共 10 个文件。
- 会话期间其他并行会话已提交 33890f1、1202e82，6 号引用路径与五个记忆文档的会话 10 记录已被这两次提交一并带入 HEAD；本次提交不再重复包含。
- `git push origin main` 失败两次：`Failed to connect to github.com port 443`（约 21 秒超时）；排查结果：无 http/https 代理、本机常见代理端口（7890/7897/10809/1080/8888/8080）均不可用、`~/.ssh` 无私钥，GitHub 443 不通。本地 `main` 领先 `origin/main` 3 个提交，待网络恢复后执行 `git push origin main`。
- 提交范围刻意排除了工作区中其他会话未提交的改动（1/4/6/7/8/9/11 号 PRD 的评审内容与 403 口径、三个记忆文档的后续条目）。

### 会话 4：grill-with-docs 逐份细化 12 份 PRD（2026-10-31）

- 访谈方式：AskUserQuestion 选择题面板，1~11 号子 PRD 各一轮（共 54 问 + 4 次冲突重裁决）；冲突时先引 PRD 原文再给三选项。
- 改动：1~11 号子 PRD 全部回写（待确认项就地解决、新增共识、口径统一）；同步 0 号（技术栈、头像）、9 号（上传数量/缩略图/403）、10 号（脱敏/缩略图时机/预留字段）、11 号（孤儿清理任务/日志轮转/备份/日志格式）。
- 关键结论沉淀于 `.claude/MEMORY_ARCHITECTURE.md` 三条「2026-10-31 细化」条目。
- 验证：每份 PRD 回写后按 2~6 个关键词 grep 核对（如 8~32、全量复用、requirement_changed、不含角色、created_at 倒序、HTTP 瞬态重试）；4 号一处编辑因文件并行搬移丢失，已在新路径补回并复核。
- 提交：分支 `docs/prd-refinement`——`285a2a4`（20 文件，+659/−68，含 8 号 PRD 目录迁移 rename 保留历史）+ `475cb89`（8 号 issues 跟进，6 文件）。提交后 `git status --short` 为空。
- 未推送：按分支策略待用户确认后合入 main；注意此前并行会话曾报 GitHub 443 连接失败（本地领先远程），推送前先验证网络。
- 遗留待办：各模块 demo 文档（README/issues/接口文档）与细化后 PRD 的一致性核对（demo README §6 有 12 条待统一项）；PRD 4 §9.5 completed_count 口径修正待用户复核。

## 2026-10-31 会话 11：管理后台-聊天记录最小 demo 文档拆解（to-tickets）

### 移动文件

1. `docs/prd/8-管理后台-聊天记录prd.md` → `docs/prd/8-管理后台-聊天记录/8-管理后台-聊天记录prd.md`（用户要求单独建文件夹；`git mv` 因工作区快照过期失败，使用 `mkdir -p` + `mv` 完成）。

### 修改文件

1. `docs/prd/0-系统汇总prd.md` 第 128 行索引路径改为 `8-管理后台-聊天记录/8-管理后台-聊天记录prd.md`。
2. `docs/prd/7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md` 第 11 行关联文档路径改为 `../8-管理后台-聊天记录/8-管理后台-聊天记录prd.md`。
3. `docs/prd/8-管理后台-聊天记录/README.md`：补充 `30023` 消息不存在错误码（新增错误码清单与越权拦截清单）。
4. `docs/prd/8-管理后台-聊天记录/issues/02-会话详情与消息定位.md`：补充锚点消息不存在/不属于会话返回 404 `30023`。

### 新增文件

1. `docs/prd/8-管理后台-聊天记录/README.md` —— 最小 demo 范围、做/不做、相对 PRD 取舍、前置/演示账号/种子夹具、10 个接口总览、依赖图、16 步验收脚本、13 项待确认。
2. `docs/prd/8-管理后台-聊天记录/接口文档-聊天记录最小demo.md` —— 通用约定、权限判定、种子与演示账号、数据表最小字段、模型配置 AES-GCM、Agent 字典与建议变量、聊天列表/详情/消息窗口/Agent 明细/搜索/模型配置/提示词接口、前端路由、错误码、审计动作、权限矩阵、14 项待确认。
3. `docs/prd/8-管理后台-聊天记录/issues/01-后台骨架种子与聊天记录列表.md`
4. `docs/prd/8-管理后台-聊天记录/issues/02-会话详情与消息定位.md`
5. `docs/prd/8-管理后台-聊天记录/issues/03-Agent调用明细.md`
6. `docs/prd/8-管理后台-聊天记录/issues/04-消息搜索与定位.md`
7. `docs/prd/8-管理后台-聊天记录/issues/05-模型配置读取与保存.md`
8. `docs/prd/8-管理后台-聊天记录/issues/06-系统提示词管理与版本.md`

### 验证

- `ls -la docs/prd/8-管理后台-聊天记录` 确认 PRD、README、接口文档与 `issues/01~06` 齐全。
- `grep -rn "8-管理后台-聊天记录" docs/prd/0-系统汇总prd.md docs/prd/7-管理后台-用户与生图记录` 确认外部引用已改为文件夹路径。
- `git status --short` 显示：README、issues/02 相对 HEAD 有 2 行差异（`30023`）；接口文档为未跟踪新文件；其余 issues 已被并行会话提交 `475cb89` 收入 HEAD。
- 并发情况：会话期间其他并行会话提交了 `285a2a4`（8 号目录迁移）与 `475cb89`（8 号 issues），并正在编辑 7/9/10/11 号文档与 7 号接口文档；本次未触碰这些并行改动。
- 未运行代码或测试，未 commit，未创建 GitHub issue（tickets 为本地文件）。

## 2026-10-31 会话 12：后端服务与接口最小实现 demo

### 新增文件

1. `docs/prd/9-后端服务与接口/README.md` —— 最小 demo 范围、做/不做、相对 PRD 取舍、前置载体、演示账号、契约载体接口表、依赖图、16 步验收脚本、9 号 §10 覆盖表、16 项待确认。
2. `docs/prd/9-后端服务与接口/接口文档-后端服务与接口最小demo.md` —— 通用约定、鉴权与权限、错误码总表、分页、幂等并发、上传、下载、SSE、OpenAPI、22 项契约覆盖矩阵、8 项待确认。
3. `docs/prd/9-后端服务与接口/issues/01-统一响应错误码与分页基线.md`
4. `docs/prd/9-后端服务与接口/issues/02-JWT鉴权与账号状态校验.md`
5. `docs/prd/9-后端服务与接口/issues/03-权限点校验与越权语义.md`
6. `docs/prd/9-后端服务与接口/issues/04-文件上传契约.md`
7. `docs/prd/9-后端服务与接口/issues/05-文件下载契约.md`
8. `docs/prd/9-后端服务与接口/issues/06-SSE协议基线.md`
9. `docs/prd/9-后端服务与接口/issues/07-幂等与并发契约.md`
10. `docs/prd/9-后端服务与接口/issues/08-OpenAPI文档与契约回归.md`

### 移动文件

1. `docs/prd/9-后端服务与接口prd.md` → `docs/prd/9-后端服务与接口/9-后端服务与接口prd.md`（`git mv`）。

### 修改文件

1. `docs/prd/0-系统汇总prd.md` 第 129 行索引路径改为 `9-后端服务与接口/9-后端服务与接口prd.md`。
2. `docs/prd/10-数据模型与存储prd.md` 第 11 行 9 号关联文档路径改为文件夹路径。
3. `docs/prd/11-部署与运维prd.md` 第 11 行 9 号关联文档路径改为文件夹路径。

### 验证

- `find docs/prd/9-后端服务与接口 -type f` 确认 PRD、README、接口文档与 `issues/01~08` 齐全。
- Python 脚本校验 README 与接口文档的 11 个相对链接全部存在。
- `git status --short` 确认 9 号目录为新增，PRD 为 rename，0/10/11 仅 9 号路径行变化。
- `ls docs/prd/9-后端服务与接口prd.md` 确认旧路径已不存在。
- 并发情况：会话期间其他并行会话正在处理 7/8 号迁移与接口文档；本次未触碰 7/8，0/10/11 的 7/8 路径改动由并行会话完成。
- 未运行代码或测试，未 commit，未创建 GitHub issue（tickets 为本地文件）。

## 2026-10-31 会话 13：管理后台-用户与生图记录最小 demo 文档拆解（to-tickets）

### 移动文件

1. `docs/prd/7-管理后台-用户与生图记录prd.md` → `docs/prd/7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md`（用户要求单独建文件夹；`git mv`；移动后状态为 `AM`，属正常“重命名 + 修改”）。

### 修改文件

1. `docs/prd/0-系统汇总prd.md` 第 127 行索引路径改为 `7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md`。
2. `docs/prd/7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md` 第 11 行关联文档改为 `../4-生图任务与结果/...`、`../6-管理后台-账号与权限/...`、`../8-管理后台-聊天记录/...`。
3. `docs/prd/4-生图任务与结果/4-生图任务与结果prd.md` 第 11 行 7 号关联文档改为 `../7-管理后台-用户与生图记录/...`。
4. `docs/prd/6-管理后台-账号与权限/6-管理后台-账号与权限prd.md` 第 11 行与第 26 行引用改为 `../7-管理后台-用户与生图记录/...`。
5. `docs/prd/8-管理后台-聊天记录/8-管理后台-聊天记录prd.md` 第 11 行 7 号关联文档改为 `../7-管理后台-用户与生图记录/...`。
6. `docs/prd/10-数据模型与存储prd.md` 第 11 行与第 692 行引用改为 `7-管理后台-用户与生图记录/...`。

### 新增文件

1. `docs/prd/7-管理后台-用户与生图记录/README.md` —— 最小 demo 范围（做/不做/取舍）、与前后 demo 边界、前置与演示账号、种子数据、环境变量、12 个接口总表、6 切片依赖图、13 步验收脚本、15 项待确认。
2. `docs/prd/7-管理后台-用户与生图记录/接口文档-用户与生图记录最小demo.md` —— 通用约定、demo 运行时、权限点与演示账号、种子、概览/Token/内容三层/单图/媒体/用户统计接口、字段与统计口径、权限与数据边界、错误码、与 9/10 差异、未实现接口、18 步验收调用序列。
3. `docs/prd/7-管理后台-用户与生图记录/issues/01-概览四卡与演示数据种子.md`
4. `docs/prd/7-管理后台-用户与生图记录/issues/02-Token统计Tab.md`
5. `docs/prd/7-管理后台-用户与生图记录/issues/03-生图记录用户层与会话层.md`
6. `docs/prd/7-管理后台-用户与生图记录/issues/04-生图记录批次层与图片网格.md`
7. `docs/prd/7-管理后台-用户与生图记录/issues/05-单图详情与媒体访问.md`
8. `docs/prd/7-管理后台-用户与生图记录/issues/06-用户详情真实统计与内容入口.md`

### 修正

- `README.md` §4 依赖图原写法把 05 连到 06，已改为：`[6 号 demo 01] + [4 号 demo 01] → 01`；`01 → 02`；`01 → 03 → 04 → 05`；`[6 号 demo 06] + [03] + [4 号 demo 01] → 06`。06 不依赖 04/05。
- 发现 `30020` 已被 8 号 demo 用作「Agent 调用不存在」，7 号原「图片不存在」改用 `30024`，同步 README §6、`issues/05` 与接口文档错误码表；8 号保留 `30020` 不变。
- 缩略图接口归属改到 04（图片网格必须用它），05 只新增大图预览与原图下载；避免 04→05 的循环依赖，README 接口表同步为 04。

### 验证

- `grep -rn "7-管理后台-用户与生图记录(prd)?\.md" docs/prd` 确认 0/4/6/8/10 号引用均为文件夹路径，无旧顶层路径残留。
- 复核 `7-...prd.md` 与 `0-系统汇总prd.md` 的磁盘变更：PRD 第 11 行已使用 `../...`，0 号第 127 行为文件夹路径；未回退并行会话的改动。
- `find docs/prd/7-管理后台-用户与生图记录 -type f` 确认 PRD、README、接口文档与 `issues/01~06` 齐全。
- 未运行代码或测试；未 commit；未创建 GitHub issue（tickets 为本地文件）。
- 并发情况：会话期间其他并行会话已写入 8/9/10/11 号目录与 7 号接口文档、并更新五个记忆文档；本次只追加 7 号自身记录，未覆盖他人内容。

## 2026-10-31 会话 14：登录最小 demo 后端实现

### 新增文件

1. `docker-compose.yml` —— PostgreSQL 16（`postgres:16-alpine`，`pull_policy: never`），容器 `esimage-postgres`，宿主机端口 `55433`，含 `pg_isready` 健康检查与命名卷。
2. `backend/.env.example` —— `DATABASE_URL`、`JWT_SECRET`、`JWT_ALGORITHM` 占位。
3. `backend/requirements.txt` —— fastapi、uvicorn[standard]、SQLAlchemy、psycopg[binary]、PyJWT、bcrypt、python-dotenv、pytest、httpx。
4. `backend/pytest.ini` —— `testpaths=tests`、`pythonpath=.`、`-q`。
5. `backend/app/main.py` —— FastAPI 应用；CORS 默认放行 `http://localhost:5173` 与 `127.0.0.1:5173`；auth 路由挂在 `/api/v1`；统一异常处理（`ApiError`、`RequestValidationError` 缺字段→10002/其余→10003、兜底 500→50001）。
6. `backend/app/core/config.py` —— 读取 `backend/.env`；`JWT_SECRET` 缺失即抛 `RuntimeError`；TTL 24h/7d；时区 +08:00。
7. `backend/app/core/database.py` —— `Base`、`engine`、`SessionLocal`、`get_db`。
8. `backend/app/core/security.py` —— bcrypt cost=12 哈希/校验（密码截断到 72 字节）、签发与解析 JWT。
9. `backend/app/core/response.py` —— `ApiError`、`ok()`、`error_body()`。
10. `backend/app/core/audit.py` —— 写 `audit_logs`，IP 取 `X-Forwarded-For` 或客户端地址。
11. `backend/app/core/deps.py` —— `AuthContext`、`get_current_auth`，按 签名/过期 → 用户存在 → `token_version` → 账号状态 顺序校验，每请求查库取最新角色权限。
12. `backend/app/models/user.py` —— `users`、`roles`、`permissions`、`user_roles`、`role_permissions` 五张表（关联表用 `Column`）。
13. `backend/app/models/audit.py` —— `audit_logs`。
14. `backend/app/modules/auth/schemas.py` —— `LoginRequest`（username/password 可空 + `remember_me`）。
15. `backend/app/modules/auth/seed.py` —— 幂等种子：3 角色、4 权限点、角色权限关联、3 个演示账号。
16. `backend/app/modules/auth/router.py` —— 登录、`/me`、退出三个接口。
17. `backend/scripts/init_db.py`、`backend/scripts/seed.py` —— 建表与种子 CLI，入口加 `sys.stdout.reconfigure(encoding="utf-8")`。
18. `backend/tests/conftest.py` —— 测试库 `esimage_test`（自动建库）、`drop_all/create_all`、种子、审计与用户状态重置夹具。
19. `backend/tests/test_auth.py` —— 31 个用例。

### 修改文件

1. `backend/app/models/__init__.py` —— 由空文件改为汇总导出 `AuditLog`、`Permission`、`Role`、`User` 与两张关联表。

### 关键实现口径

- 登录：用户名去首尾空格；格式 `^[A-Za-z0-9_]{4,20}$`；密码 8~32 位且不去空格；查询精确匹配；用户不存在时也执行一次 bcrypt 校验（防时序探测）。
- 失败统一 `401 + 20001 + "用户名或密码错误"`，审计写 `result=failed`、`detail={"reason":"bad_credentials"}`。
- 成功：签发 JWT、写 `last_login_at`、审计 `auth.login`；响应 `{token, expires_at, user:{id,username,display_name,avatar_url,roles,permissions}}`。
- `/auth/me`：`{user:{id,username,display_name,avatar_url}, roles, permissions}`。
- 退出：审计 `auth.logout`，`data=null`（无状态 JWT，不做服务端吊销）。
- 角色权限：`user` → `user.workspace`/`user.history`/`user.profile`；`admin` → `admin.dashboard.view`；`super_admin` 暂不建账号。

### 前端文件（已按用户要求删除）

- 本轮曾创建 `frontend/package.json`、`frontend/tsconfig.json`、`frontend/vite.config.ts`、`frontend/index.html`、`frontend/src/test/setup.ts`，用户要求「不用开发前端」后全部删除；`frontend/` 下仅保留骨架 `.gitkeep`，未提交任何前端代码。

### 验证

- `python -c "import app.main"` 通过（重构后导入自检）。
- `pytest -q` → `31 passed`（仅 Starlette `httpx2` 弃用告警）。
- 真实服务冒烟（`uvicorn app.main:app --host 127.0.0.1 --port 8000`）：
  - 登录 `demo_user` → 200，返回 token 与 user；
  - `GET /auth/me` → 200，roles `["user"]`、权限 3 项；
  - 错误密码 → 401 `{"code":20001,"message":"用户名或密码错误"}`；
  - 无 token → 401 `{"code":20003,"message":"token 无效"}`；
  - 退出 → 200，`data=null`。
- 数据库：`docker compose up -d` 后 `esimage-postgres` healthy；`scripts/init_db.py` + `scripts/seed.py` 执行成功。

### 提交与合并

- 提交 `f7ed1ba feat: 实现登录最小 demo 后端接口与演示账号`（21 文件，+1352）到 `feat/login-minimal-demo`。
- 记忆文档提交 `6638391`；rebase 到最新 `origin/main`（`5c4f05d`）时五个记忆文档与并行会话的会话 12/13 记录冲突，按「双方内容全部保留」解决。
- 功能分支推送 `origin/feat/login-minimal-demo`，随后 `--ff-only` 合并到 `main` 并推送。
- 未提交仓库根 `SKILL.md`（frontend-design 技能副本，用户要求安装到全局，与本需求无关）。

### 会话 14 补充：接口文档一致性校验（curl）

按 `docs/prd/1-登录界面/接口文档-登录最小demo.md` 用 curl 逐项校验三个接口，发现并修正 2 处偏差：

1. `remember_me` 非严格布尔：Pydantic 默认宽松模式会把 `"yes"` / `1` 转换为 `true`，从而签发 7 天 token；改为 `StrictBool`，非布尔值返回 400 `10003`「参数格式错误」。
2. 缺少 `50002` 数据库错误码：文档 §4 标注「本次是否使用：是」，原实现只有 50001；新增 `SQLAlchemyError` 异常处理器，返回 500 + `50002`「系统繁忙，请稍后重试」。

新增测试 4 个（`remember_me` 传 `"yes"`/`1`/`"true"` + 模拟数据库异常），`pytest` 由 31 增至 **35 passed**。

curl 校验通过项（真实服务 127.0.0.1:8000）：

- 登录成功：三个演示账号均 200；`code=0`、`message="ok"`；`data` 含 `token`/`expires_at`/`user{id,username,display_name,avatar_url:null,roles,permissions}`；用户名首尾空格被去除。
- JWT：载荷含 `sub`(string)/`iat`/`exp`/`token_version`/`roles`/`permissions`；默认 24h（86400s）、`remember_me=true` 7 天（604800s）；`expires_at` 与 `exp` 同一时刻，ISO 8601 + `+08:00`。
- 参数错误：`{}` 与全空格用户名 → 400 `10002`「请输入用户名」；缺密码/空密码 → `10002`「请输入密码」；用户名 3 位/21 位/含横线 → `10003`；密码 7 位/33 位 → `10003`；非法 JSON、`text/plain`、`remember_me` 非布尔 → `10003`「参数格式错误」；无请求体 → `10002`「缺少必填参数」。
- 凭据错误：错误密码、未知账号、禁用账号登录、密码带空格、用户名大小写不符 → 统一 401 `20001`「用户名或密码错误」。
- `/auth/me`：正常 200 且结构为 `{user{id,username,display_name,avatar_url}, roles, permissions}`；无 token / 非 Bearer / 空 Bearer / 乱码 → 401 `20003`；过期 → 401 `20002`「登录已过期」；`token_version` 不符 / 用户不存在 / `sub` 非数字 → 401 `20003`；禁用账号 → 403 `20004`「账号不可用」；token 内伪造 `super_admin` 角色不被信任，仍返回数据库中的真实角色。
- 退出登录：正常 200 `data=null`；无 token / 乱码 → `20003`；过期 → `20002`。
- 审计：登录成功/失败/退出均落 `audit_logs`；失败 `detail={"reason":"bad_credentials"}`；未知账号 `user_id` 为空；全部记录不含密码（SQL 检索 `Demo1234` 计数为 0）。
- 响应头：`content-type: application/json`（未带 `charset=utf-8`，JSON 本身固定 UTF-8，与文档的写法属等价表述）。
- 未覆盖：`50002` 无法通过 curl 安全触发，改由 pytest 依赖覆盖模拟数据库异常验证。

## 2026-10-31 会话 15：创作工作台后端最小 demo 实现

### 新增文件

1. `backend/app/models/workspace.py` —— 六张工作台表：`creative_sessions`、`chat_messages`、`agent_runs`、`generation_batches`、`generated_images`、`uploaded_assets`。
2. `backend/app/modules/workspace/router.py` —— 汇总 sessions / uploads / generations 路由。
3. `backend/app/modules/workspace/schemas.py` —— `WorkspaceParams`、`ChatMessageRequest`、`SampleGenerationRequest`、`ConfirmGenerationRequest`。
4. `backend/app/modules/workspace/service.py` —— 商品名称/风格/尺寸/模板/消息校验、UUID 幂等键、权限依赖、会话归属、进程内锁、序列化与文件名工具。
5. `backend/app/modules/workspace/sessions.py` —— 会话列表、消息分页、两个 SSE 聊天接口；幂等重放/409/失败重试；断线标记 failed。
6. `backend/app/modules/workspace/uploads.py` —— 上传、元数据、软删除、原图/缩略图读取；数量与像素边界保护。
7. `backend/app/modules/workspace/generations.py` —— 示例批次、批次查询、确认全套、图片预览/缩略图/下载；锁内幂等与并发校验。
8. `backend/app/modules/workspace/pipeline.py` —— 示例/全套演示管线，阶段推进、占位图、历史可见性原子提交。
9. `backend/app/modules/workspace/imaging.py` —— 占位 PNG、WebP 缩略图（质量 80）、像素上限校验。
10. `backend/app/modules/workspace/storage.py` —— 本地存储适配层与路径穿越防护。
11. `backend/app/modules/workspace/README.md` —— 模块目录与约定。
12. `backend/tests/test_workspace.py` —— 24 个接口用例，含并发幂等、权限、隔离、分页、校验。
13. `backend/scripts/curl_smoke.sh` —— 真实服务 curl 验收脚本。
14. `backend/README.md` —— 本地启动、演示账号、curl 验收、测试与最小 demo 限制。

### 修改文件

1. `backend/app/models/__init__.py` —— 注册六个新模型。
2. `backend/app/main.py` —— 挂载 `workspace_router`；请求校验按字段返回商品名称/消息/文件/宽高的明确文案。
3. `backend/app/core/config.py` —— 新增 `STORAGE_ROOT`、`DEMO_PIPELINE_STAGE_DELAY`。
4. `backend/app/modules/auth/seed.py` —— 新增 `user.generate` 权限并授予 `user` / `super_admin`。
5. `backend/tests/test_auth.py` —— 同步三处权限断言（加入 `user.generate`）。
6. `backend/tests/conftest.py` —— 测试期关闭管线停顿、使用独立测试存储目录。
7. `backend/requirements.txt` —— 增加 `python-multipart`、`Pillow`。
8. `backend/.env.example` —— 数据库端口修正为 55433，补充存储与管线变量。
9. `.gitignore` —— 忽略 `backend/storage/`、`backend/.pytest_storage/`、`backend/.curl_tmp/`。

### 验证

- `TEST_DB_NAME=esimage_workspace_test PYTHONPATH=. python -m pytest -q` → **59 passed**。
- `python -m compileall -q app scripts` → 通过。
- `bash scripts/curl_smoke.sh`（`DATABASE_URL=...55433/esimage_workspace`）逐条通过：
  - 登录 / `/auth/me` / `/auth/logout` 200；
  - 首条消息 SSE 返回 `meta` + 两个 Agent 状态 + `delta` + `done`，新建会话；
  - 会话列表与消息分页 200；
  - 两张商品图上传 200，`/content` 与 `/thumbnail` 200，元数据恢复 200；
  - 示例批次创建 200（`queued`），轮询至 `sample_ready`，示例图预览 200，下载 409/30005；
  - 确认全套 200，轮询至 `completed`，6/6 张，第 1 张主图 + 5 张详情图；
  - 主图/详情图下载 200，`Content-Disposition` 文件名符合规则；
  - 软删除上传图 200，再读 404/30014；
  - 管理员 `GET /sessions` 403/20005；商品名称为空 400/10002。
- 复用本机已运行的 `esimage-postgres`（55433），在容器内新建独立库 `esimage_workspace`；未改动其他项目的 `esimage` / `esimage_test`。

### 独立审查修复（同日）

- 聊天并发：加进程内锁；`IntegrityError` 回滚后按已保存消息重放/409；SSE 断线把 `sending` 标记 `failed`，失败可复用原用户消息重试。
- 确认并发：锁内重新做同 key 幂等判定；`db.flush()` 移入 try；并发同 key 两个请求返回同一全套批次。
- 批次/上传并发：创建示例、确认全套、上传数量都放入同一临界区，避免 check-then-act 穿透。
- 宽高上限 4096、上传解码像素上限 4000 万、`file.size` 预检，避免 OOM。
- 全套管线补齐前 3 个阶段；`completed` 与 `is_history_visible` 改为同一事务提交。
- 必填字段/类型错误的文案按字段映射；幂等键改为 UUID 校验。
- curl 脚本端口修正为 55433，幂等键改为 UUID。
- 测试补强：分页断言第一页确为最新消息；新增聊天并发、确认并发、非 UUID、缺少文件用例。

### 已知限制

- `chrome-devtools` MCP 连接超时，未使用浏览器验证；本次仅后端。
- 未配置真实文本模型与豆包生图，聊天与生图为演示桩/占位图。
- SSE 心跳 `ping` 未实现；归档下载分支未实现；`superseded` 图片默认不返回。以上均为最小 demo 取舍。

### 提交与合并

- 提交 `7595e31 feat: 实现创作工作台后端最小 demo 与 curl 验收`（28 文件，+3654）。
- 远端 `main` 在此期间前进到 `a476ac4`；功能分支 rebase 到最新 `main`，解决 `.claude/MEMORY_CHANGES.md`、`.claude/MEMORY_TIPS.md` 两处记忆文档冲突（双方内容全部保留）。
- rebase 后全量 `pytest` **59 passed**；`git push --force-with-lease origin feat/workspace-backend-demo` 成功。
- `git merge --ff-only feat/workspace-backend-demo` 合并到 `main`，推送 `a476ac4..7595e31` 成功（GitHub 443 直连超时，使用 `git -c http.curloptResolve=github.com:443:140.82.112.3` 临时固定 IP）。
- 未提交 `backend/.env`、`backend/storage/`、`backend/.curl_tmp/` 等本地文件（均已在 `.gitignore`）。

## 2026-10-31 会话 15：Agent 会话交互后端模块骨架

### 新增文件

1. `backend/app/modules/chat/README.md` —— chat 模块定位、2 号 demo 04 前置、当前阻塞、6 个计划接口与计划文件职责。

### 修改文件

- 无（只新增模块说明，不改动既有代码与路由）。

### 提交与合并

- 新分支 `feat/agent-chat-backend-demo`，基于 `main` `e6a971b`。
- 提交 `19428da chore: 建立 Agent 会话交互后端模块骨架`（1 文件，+37）。
- 本地 `--ff-only` 合并到 `main`，`main` 前进到 `19428da`。
- `git push -u origin feat/agent-chat-backend-demo` 失败：`Failed to connect to github.com port 443`；`curl https://github.com` 超时，`https://api.github.com` 可通。待网络恢复后补推分支与 main。

### 环境与并发

- 复用并行 agent 的 `esimage-postgres` 容器（healthy，宿主机 55433），未新建容器。
- 8000 端口由 `coding/1-登入界面` 的 uvicorn 占用，3 号后续联调改用 8001。
- 同设备 `coding/2-用户端创作工作台/ESImage` 的 `feat/workspace-backend-demo` 仍在开发 `workspace/sessions.py` 等未提交文件；本次未读取后复制、未修改其工作区。
- chrome-devtools MCP 已连接，`list_pages` 返回 1 个 `about:blank` 页面。

### 验证

- `git log --oneline -3`：`19428da` → `e6a971b` → `ede918e`。
- `git status --short`：干净。
- 未运行 pytest（本次无业务代码）。

## 2026-10-31 会话 14：10 号数据模型与存储最小 demo 文档

### 目录与引用

- `git mv docs/prd/10-数据模型与存储prd.md docs/prd/10-数据模型与存储/10-数据模型与存储prd.md`。
- 新建 `docs/prd/10-数据模型与存储/issues/`。
- 更新 `docs/prd/0-系统汇总prd.md` 两处路径为 `10-数据模型与存储/10-数据模型与存储prd.md`。
- 更新 `docs/prd/11-部署与运维prd.md` 关联文档路径。
- 更新 `docs/prd/7-管理后台-用户与生图记录/接口文档-用户与生图记录最小demo.md` 的 `../10-...` 相对路径。

### 新增文件

- `docs/prd/10-数据模型与存储/README.md`
- `docs/prd/10-数据模型与存储/issues/01-迁移骨架与身份审计表.md`
- `docs/prd/10-数据模型与存储/issues/02-内容域六表与数据约束.md`
- `docs/prd/10-数据模型与存储/issues/03-配置域六表幂等种子与初始超管.md`
- `docs/prd/10-数据模型与存储/issues/04-会话消息与Agent调用数据链路.md`
- `docs/prd/10-数据模型与存储/issues/05-生成批次与图片数据链路.md`
- `docs/prd/10-数据模型与存储/issues/06-上传图与对象存储路径.md`
- `docs/prd/10-数据模型与存储/issues/07-五年归档与归档读取.md`
- `docs/prd/10-数据模型与存储/issues/08-数据底座验收与契约回归.md`
- `docs/prd/10-数据模型与存储/接口文档-数据模型与存储最小demo.md`

### 内容要点

- README：最小范围、做/不做、相对 PRD 取舍、环境前置、契约总览、依赖图、13 步验收脚本、10 号 §12 覆盖表、17 项待确认。
- 接口文档：18 张表字段与约束、枚举、迁移与 schema 校验、种子清单与幂等规则、首个超管、脱敏、存储适配器操作与路径、归档算法与读取降级、验收命令、16 项待确认。
- 未运行代码或测试；未 commit；未创建 GitHub issue。

### 验证命令

- 仅使用 `find`、`grep`、`git mv`、`git status` 类只读/文件操作；未执行迁移、种子或回归。

## 2026-10-31 会话 15：11 号部署与运维最小 demo 文档

### 目录与引用

- `git mv docs/prd/11-部署与运维prd.md docs/prd/11-部署与运维/11-部署与运维prd.md`。
- 新建 `docs/prd/11-部署与运维/issues/`。
- 更新 `docs/prd/0-系统汇总prd.md` 索引为 `11-部署与运维/11-部署与运维prd.md`。
- 更新 `docs/prd/9-后端服务与接口/9-后端服务与接口prd.md` 关联文档为 `10-数据模型与存储/10-数据模型与存储prd.md`、`11-部署与运维/11-部署与运维prd.md`。
- 更新移动后 `11-部署与运维prd.md` 头部引用为 `../0-系统汇总prd.md`、`../9-后端服务与接口/...`、`../10-数据模型与存储/...`、`../../GLOSSARY.md`。
- 更新 `docs/prd/10-数据模型与存储/接口文档-数据模型与存储最小demo.md` 的上游引用为 `../11-部署与运维/11-部署与运维prd.md`。

### 新增文件

- `docs/prd/11-部署与运维/README.md`
- `docs/prd/11-部署与运维/issues/01-Compose基线与依赖服务.md`
- `docs/prd/11-部署与运维/issues/02-迁移种子与初始超管.md`
- `docs/prd/11-部署与运维/issues/03-应用镜像与双健康探针.md`
- `docs/prd/11-部署与运维/issues/04-Nginx网关与SSE代理.md`
- `docs/prd/11-部署与运维/issues/05-结构化日志与request_id.md`
- `docs/prd/11-部署与运维/issues/06-备份与恢复.md`
- `docs/prd/11-部署与运维/issues/07-Worker-Beat基线.md`
- `docs/prd/11-部署与运维/issues/08-一键启动与验收脚本.md`
- `docs/prd/11-部署与运维/接口文档-部署与运维最小demo.md`

### 内容要点

- README：最小范围、做/不做、相对 PRD 取舍、前置与演示配置、接口总览、依赖图、16 步验收脚本、11 号 §14 覆盖表、14 项待确认、快速开始/日常更新/排障。
- 接口文档：`GET /api/health` 裸结构、`GET /api/v1/health` 统一响应、演示 SSE 探针、Nginx 路由/SSE/413/安全头/文档内网限制、Compose 服务/网络/卷/环境变量/启动顺序、6 个运维脚本 CLI、cron 与 Celery 契约、日志与 `request_id`、错误码与退出码、验收矩阵、14 项待确认。
- 用户确认的取舍：8 个切片；只起 Worker/Beat、不做归档；健康接口双路径；移动 PRD 并更新引用。
- 明确不做：5 年归档、孤儿上传清理、导出清理、权限缓存刷新、审计业务写入、HTTPS/443、MinIO 控制台、Prometheus/Grafana、多机/灰度/容灾、业务页面与接口。
- 演示专用：`/api/v1/sessions/_probe/stream`、`ops.selftest`，仅非生产启用，已列待确认。

### 验证命令

- `find "docs/prd/11-部署与运维" -type f`：确认 11 个文件（PRD、README、8 issues、接口文档）。
- `grep -o "issues/[^)]*" docs/prd/11-部署与运维/README.md`：确认 8 个 issue 链接与文件名一致。
- `grep -rn "11-部署与运维prd.md" docs --include=*.md`：确认无旧顶层路径残留（文件夹内裸文件名与 `./` 链接属正常）。
- `git status --short`：提交前确认移动为 rename、新增文件为 untracked，提交后已全部纳入；未执行代码、迁移、种子或回归。
- 文档生成时未提交；随后提交到 `docs/deploy-ops-minimal-demo` 并合并 `main`；未创建 GitHub issue。

## 2026-10-31 会话 17：历史作品后端最小 demo 实现

### 分支与提交

- 从 `main` 创建 `feat/history-backend-demo`。
- 骨架提交 `4ea5d64 chore: 建立历史作品后端模块骨架`：新增 `backend/app/modules/history/README.md`；push 后 `git merge --ff-only` 到 `main` 并 push。
- 业务实现提交 `afbdc18 feat: 实现历史作品后端最小 demo`。
- 合并最新 `origin/main`（`6db0259`）解决冲突后，提交合并结果并推送功能分支。

### 新增文件

- `backend/app/modules/history/router.py`：`GET /history`、`GET /history/{batch_id}`、`GET /batches/{batch_id}/download`。
- `backend/app/modules/history/service.py`：历史可见性查询、分页、封面、详情序列化、`page` 校验。
- `backend/app/modules/history/zip_export.py`：整组 ZIP 与 `manifest.csv`，与 4 号 demo 08 共用契约。
- `backend/app/modules/history/seed.py`：幂等演示夹具（demo_user 21 个历史可见批次 + 示例/失败批次 + demo_dual 其他用户批次）。
- `backend/tests/test_history.py`：7 个历史接口用例，含分页、详情、权限、媒体、ZIP、归档降级。
- `backend/scripts/curl_history_smoke.sh`：独立数据库/存储的 curl 验收脚本。

### 修改文件

- `backend/app/main.py`：挂载 history router。
- `backend/app/core/config.py`：新增 `ARCHIVE_READ_TIMEOUT_SECONDS`（默认 60）。
- `backend/.env.example`：补充 `ARCHIVE_READ_TIMEOUT_SECONDS`。
- `backend/scripts/seed.py`：登录种子后调用 `seed_history`。
- `backend/scripts/curl_smoke.sh`：补充 `ARCHIVE_READ_TIMEOUT_SECONDS` 导出。
- `backend/app/modules/workspace/service.py`：
  - 新增 `require_any_permission`（预览/缩略图双权限）。
  - `safe_filename_part` 按 5 号 §8.3 收紧：控制字符、结尾点与空格替换为下划线。
  - 新增 `archive_relative_path`、`read_image_bytes`、归档错误日志；归档读取超时用线程池。
- `backend/app/modules/workspace/generations.py`：
  - `/images/{id}/content`、`/thumbnail` 权限放宽为 `user.history` 或 `user.generate`。
  - 单张下载增加 `batch_type=full`、`image_type=final` 校验；归档件走 `read_image_bytes`；下载 `Cache-Control: no-store`。

### 验证命令与结果

- `python -m pytest tests/test_history.py -q`：8 passed。
- `python -m pytest -q`：合并 main 前 67 passed；合并后 93 passed。
- `python -m compileall -q app tests scripts`：通过。
- `bash scripts/curl_history_smoke.sh`：通过；覆盖列表/分页、详情、404/403、缩略图、内容、单张下载、非法文件名、示例下载 409、整组 ZIP（completed/partial/sample）、归档读取与缺失降级 30014、管理员 403、未登录 401。
- 复用 docker `esimage-postgres`（55433）；curl 使用独立库 `esimage_history_curl`，未干扰其他 agent。

### 合并最新 main 的集成处理

- `origin/main` 已由其他 agent 合入一版 history 内联实现（仅 `router.py`）、workspace 归档路径与 `app/core/deps.py` 的权限依赖。合并时以本分支的 `service.py` + `zip_export.py` + `seed.py` 为唯一实现，`router.py` 保留本分支版本并改为从 `app.core.deps` 引入 `require_permission`；main 的内联 ZIP/查询代码不再保留。
- main 的 `workspace/generations.py` 已有归档路径与权限放宽；合并时保留该结构，把归档读取替换为 `read_image_bytes`（超时/日志），并补 `full + final` 下载校验与共享文件名。
- main 的 `workspace/service.py` 从 core 重新导出 `require_permission`；合并时补充 `require_any_permission` 重导出，并加入本分支的归档读取、文件名函数与更严格清洗。
- main 的 `scripts/seed.py` 已调用 `seed_config`；合并后同时调用 `seed_history`。
- 修复 main 既有启动 bug：`backend/app/modules/admin/router.py` 把子模块当 `APIRouter`，改为从 `admin.<domain>.router` 导入实例，否则整个 app 无法启动。
- 修复 main 既有测试口径：`tests/test_auth.py` 的双角色权限断言改为从 `ROLE_PERMISSIONS` 派生，适配 admin 权限扩展。
- 合并后 `pytest -q` 93 passed；`curl_history_smoke.sh` 全部通过；前端 `frontend/src/modules/history/api.ts` 的字段契约与本实现兼容。

### 独立代码审查与修复（code-review，10 条）

已修复：

- 超大 `page` 导致 offset 溢出 PostgreSQL bigint：先算 total，`offset >= total` 直接返回空 `items`；补超大页码用例与 curl 断言。
- `/history` 聚合子查询未按用户收窄：子查询内加 `GeneratedImage.user_id`、批次 user/type/status 过滤，避免全站扫描。
- ZIP 与单张下载文件名重复实现：抽出 `workspace.service.image_download_filename`，两处共用；补 ZIP 条目名与单张下载名一致性断言。
- 历史可见状态/判定重复：集中到 `history.service.HISTORY_BATCH_STATUSES`、`is_visible_image`，`zip_export` 复用。
- 归档超时无效：`with ThreadPoolExecutor` 退出会等待线程，改为 `shutdown(wait=False, cancel_futures=True)`；补慢读超时用例（0.1 秒内返回 30014）。
- 种子只按批次幂等：新增 `_seed_artifacts_missing` / `_reset_seed_batches`，数据库保留但存储丢失时自动清理并重建；已手工验证「删 storage 后重跑种子」。
- curl 脚本 `rm -rf .curl_tmp` 误删共享目录：只清理 `.curl_tmp/history` 与 `.curl_tmp/storage_history`。
- 归档错误日志 logger 从 `esimage.history` 改为中性的 `esimage.storage`，并同步测试。

保留待用户裁决：

- 种子计数：文档表格写「21 个 completed + 1 partial」，但接口文档 §16 验收写 `total=21`；实现取 21 个历史可见批次（18 completed + superseded + archived + partial），以便验收脚本 `total=21` 成立。
- `manifest.csv`：按 5 号列「宽度/高度」分开；4 号接口文档用单列「尺寸」（`1000x1000`），需与 4 号 demo 08 统一。
- 示例图下载 409 文案：沿用 2 号「示例图确认前不可下载」，5 号 §8.4 写「当前图片不可下载」；为不破坏 2 号已有调用暂未改。
- 归档读取/文件名工具仍在 `workspace/service.py`（history 反向 import），未迁移到 `app/core`；架构归属需用户确认。
## 2026-10-31 会话 16：Agent 会话交互后端实现与豆包接入

### 新增文件

1. `backend/app/modules/chat/router.py` —— `PATCH /sessions/{id}` 重命名、`DELETE /sessions/{id}` 软删除。
2. `backend/app/modules/chat/schemas.py` —— `RenameSessionRequest`（`title: Any`，由路由区分 10002/10003/10004）。
3. `backend/app/modules/chat/service.py` —— 标题校验、软删除、消息惰性超时、上传图归属校验、需求变化判定、最近已确认示例查询。
4. `backend/app/modules/chat/agents.py` —— 10 轮上下文组装、系统提示词、演示桩规划/回复、需求摘要合并与类型归一。
5. `backend/app/modules/chat/model.py` —— 豆包 OpenAI 兼容接入：规划非流式、商品理解流式、`<<<SUMMARY>>>` 摘要解析、usage Token、演示桩回退。
6. `backend/app/modules/chat/stream.py` —— SSE 事件输出与 15 秒心跳包装（后台线程 + 队列）。
7. `backend/tests/test_chat.py` —— 22 个 3 号接口/行为用例。
8. `backend/tests/test_chat_model.py`、`backend/tests/chat_model_fakes.py` —— 豆包接入假客户端单测，不产生真实调用。

### 修改文件

1. `backend/app/modules/workspace/sessions.py` —— 复用并集成 3 号增量：`meta.duplicate`、`done.requirement_changed`、惰性超时、上传图参数、10 轮上下文、Agent 调用明细、失败重试复用原消息、`last_message_preview` 去换行/首尾空格。
2. `backend/app/modules/workspace/schemas.py` —— `WorkspaceParams` 增加可选 `upload_ids`。
3. `backend/app/main.py` —— 挂载 chat 路由。
4. `backend/app/core/config.py` —— 新增 `CHAT_MESSAGE_TIMEOUT_SECONDS`、`CHAT_CONTEXT_ROUNDS`、`SSE_HEARTBEAT_SECONDS`、`ARK_API_KEY`、`ARK_BASE_URL`、`ARK_TEXT_MODEL`、`ARK_TIMEOUT_SECONDS`、`CHAT_USE_STUB`。
5. `backend/.env.example` —— 补充 3 号聊天配置与豆包文本模型配置；记录生图模型 `doubao-seedream-5-0-pro-260628` 留给 4 号。
6. `backend/requirements.txt` —— 增加 `openai>=1.0,<4.0`。
7. `backend/tests/conftest.py` —— 测试库默认改为 `esimage_chat_test`，并强制 `CHAT_USE_STUB=1`，避免并行 agent 清表与真实调用费用。
8. `backend/app/modules/chat/README.md` —— 更新为最终模块说明、豆包配置与已知边界。

### 实现口径

- 重命名：去首尾空格 1~50 字；纯空格/未传 10002、超长 10004、非字符串/换行控制字符 10003；只更新 `title` 与 `updated_at`。
- 软删除：只把 `status` 置 `hidden`，保留消息/批次/图片/上传图，不更新 `last_message_at`；重复删除 30013。
- 消息超时：分页与重复请求前，把超过 120 秒仍为 `sending` 的 Agent 消息标记 `failed`；用户消息不参与。
- 幂等：已完成重放 `meta.duplicate=true` + 一条完整 delta + done；处理中 409/30005；失败复用原 Agent 消息并刷新 `created_at`，不新增用户/回复消息。
- 需求变化：最近一个 `sample + confirmed` 批次，比较风格、尺寸、卖点集合；无已确认示例始终 false；重放按当前状态重算。
- 上下文：系统提示词、当前参数、需求摘要、最近 10 轮（20 条非 system 消息）、已确认示例描述；超限注入省略说明，只进入上下文与 `agent_runs.input_full`，不写 `chat_messages`。
- 豆包：规划非流式 JSON；商品理解流式正文 + `<<<SUMMARY>>>` + 摘要 JSON；Token 取 usage，助手消息与 done 记两 Agent 合计；无 Key 或 `CHAT_USE_STUB=true` 走演示桩。

### 代码审查修复

- 失败重试刷新 `created_at`，避免被超时规则立即标记。
- 回复归属改为「该用户消息之后、下一条用户消息之前」的最新 assistant，避免重试重放/覆盖后一条消息。
- 首条消息去重只查 `active` 会话，已隐藏会话不可再重放或写回。
- 重放 `done.requirement_summary` 优先读该条回复的 `agent_runs.output_full` 快照，`requirement_changed` 仍按当前状态重算。
- 模型调用移入 SSE 流内、`workspace_lock` 之外；失败在流内标记 failed 并返回 error。
- 需求变化查询与上下文共用 `latest_confirmed_sample`。
- 新增测试用中文步骤日志；测试库改用 `esimage_chat_test`。

### 测试与验证

- 全量 `pytest -q`：**85 passed**（`test_auth`、`test_chat`、`test_chat_model`、`test_workspace`）。
- `test_chat.py` 覆盖：重命名成功/校验/权限/归属、软删除与数据保留、消息惰性超时、重放 duplicate、失败重试复用、隐藏会话重放、需求变化（风格/尺寸/卖点/重放）、10 轮上下文与省略说明、摘要保留、`agent_runs`、上传图校验、聊天不建批次、心跳、真实模型集成（假客户端）。
- curl 真实服务（8001）：6 个会话接口全部通过；PATCH 成功与 10002/10003/10004；DELETE 与重复删除 30013；隐藏/他人会话 30013；管理员 403/20005；上传图 30006。
- 真实豆包：4 次对话成功（约 3~4 秒）；Token 419/119、521/160、513/175 等；摘要含类目、卖点、目标人群、场景、语气、限制；有风格时确认并追问场景，无风格时列 4 个风格建议；提示词已禁止“我会直接生图”。

### 提交与合并

- 提交 `6e0c96c feat: 实现 Agent 会话交互后端增量与豆包接入`（23 文件，+2625/-167）。
- 提交前 rebase 到最新 `origin/main` `4ea5d64`（生图/历史/部署骨架），解决五个记忆文档冲突（双方内容全部保留）；rebase 后全量 `pytest` **85 passed**。
- 推送 `feat/agent-chat-backend-demo`，`--ff-only` 合并 `main` 并推送 `4ea5d64..6e0c96c`，远程 `main` 已更新。
- `.smoke/` 为临时 curl 产物，已删除并加入 `.gitignore`；`backend/.env` 含真实 Key，已被 `.gitignore` 忽略，禁止提交。
