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
