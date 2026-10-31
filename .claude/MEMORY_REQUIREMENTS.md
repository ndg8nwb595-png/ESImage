# 需求与完成状态

## 已完成

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 配置 issue 追踪器 | 完成 | `docs/agents/issue-tracker.md`：GitHub Issues + `gh` CLI，PR 请求面为 `no` |
| 配置 triage 标签词表 | 完成（文档） | `docs/agents/triage-labels.md`：五标签与角色同名 |
| 配置领域文档规则 | 完成 | `docs/agents/domain.md`：单上下文 `GLOSSARY.md` + `docs/adr/` |
| 在 agent 文件中登记 | 完成 | 仓库根新建 `AGENTS.md`，含 `## Agent skills` 三段 |

- [x] 在 GitHub 仓库创建 4 个标签：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`（`wontfix` 已存在）。已于 2026-10-31 用 classic PAT 创建并校验通过。

## 未完成 / 待办

- [x] 分支 `chore/agent-skills-setup` 已按用户要求 fast-forward 合并到 `main` 并推送。
- [ ] 仓库无 `.gitignore`，`.env`（含 token）处于未跟踪状态，建议加入忽略列表（待用户确认）。

## 电商主图/详情图 AIGC 生成系统（PRD）

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 系统汇总 PRD | 已完成（待评审） | `docs/prd/0-系统汇总prd.md` |
| 11 份模块子 PRD | 已完成（待评审） | `docs/prd/1`~`11`，按 0 号文档第 2.5 节索引 |
| 工作台三栏布局 | 已完成（待评审） | 会话列表 / 聊天框 / 参数面板+结果区；已同步 0、2、3 号文档 |
| 参数面板简化 | 已完成（待评审） | 仅商品名称必填；风格自由文本、后台不配置；尺寸默认 1:1；1 主图 + 5 详情图 |
| 失败重试策略 | 已完成（待评审） | 除生图外 Agent 重试 10 次；生图最多 2 次，2 次失败整批失败；整批超时 30 分钟 |
| 术语表独立 | 已完成 | 根目录 `GLOSSARY.md`；`AGENTS.md` 的「Domain glossary」同步路径与内容 |

### 12 份文档清单

0. `0-系统汇总prd.md`
1. `1-登录界面prd.md`
2. `2-用户端创作工作台prd.md`
3. `3-Agent会话交互prd.md`
4. `4-生图任务与结果prd.md`
5. `5-历史作品prd.md`
6. `6-管理后台-账号与权限prd.md`
7. `7-管理后台-用户与生图记录prd.md`
8. `8-管理后台-聊天记录prd.md`
9. `9-后端服务与接口prd.md`
10. `10-数据模型与存储prd.md`
11. `11-部署与运维prd.md`

## 2026-10-31 PRD 交叉评审（待用户裁决）

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 审查 12 份 PRD 的模块冲突、不合理设计、冗余设计、缺失设计 | 已完成（只读） | 通读 `docs/prd/` 与 `GLOSSARY.md`，输出 P0/P1/P2/P3 清单；未改文档 |
| 逐项确认并修订 PRD | 未开始 | 等待用户选择先处理项；架构类改动需用户拍板 |

### 关键约束

- 产品形态：内部工具，管理员开号，不开放注册、不计费。
- 角色：固定三角色，账号 1~2 角色；禁止超管+管理员；超管权限包含管理员。
- 生成：8 Agent 全链路；聊天轻链路；示例图即主图，确认后生成 5 张详情图（合计 6 张）。
- 技术：React + FastAPI + PostgreSQL + Redis + MinIO + Docker Compose。
- 开发：AI 代码生成只用 DeepSeek，禁止 Codex/GPT；中文注释/文档/日志。
