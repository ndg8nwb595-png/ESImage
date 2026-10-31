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

- [ ] 分支 `chore/agent-skills-setup` 尚未合并到 `main`（待用户选择 fast-forward 还是 PR）。
- [ ] 仓库无 `.gitignore`，`.env`（含 token）处于未跟踪状态，建议加入忽略列表（待用户确认）。
