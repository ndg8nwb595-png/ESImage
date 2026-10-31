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

### 未改动

- `README.md`、`.vscode/settings.json` 未触碰。
