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
