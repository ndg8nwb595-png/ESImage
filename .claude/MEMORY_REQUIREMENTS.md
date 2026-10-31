# 需求与完成状态

## 已完成

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 配置 issue 追踪器 | 完成 | `docs/agents/issue-tracker.md`：GitHub Issues + `gh` CLI，PR 请求面为 `no` |
| 配置 triage 标签词表 | 完成（文档） | `docs/agents/triage-labels.md`：五标签与角色同名 |
| 配置领域文档规则 | 完成 | `docs/agents/domain.md`：单上下文 `GLOSSARY.md` + `docs/adr/` |
| 在 agent 文件中登记 | 完成 | 仓库根新建 `AGENTS.md`，含 `## Agent skills` 三段 |

## 未完成 / 待办

- [ ] 在 GitHub 仓库创建 4 个标签：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`（`wontfix` 已存在）。当前阻塞：fine-grained PAT 缺 **Issues: Read and write**，`gh label create` 返回 403。需用户重新 `gh auth login` 换有写权限的 token，或在网页手动创建。
