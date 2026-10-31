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

- 未运行代码或测试；未 commit。
