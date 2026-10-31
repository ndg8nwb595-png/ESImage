# 排错 Tips

- **`gh` 报 401 Bad credentials**：不是仓库问题，是本地 keyring token 失效。执行 `gh auth login -h github.com` 后重试；`gh auth status` 可确认。
- **`gh` 能读不能写、报 403 Resource not accessible**：fine-grained PAT 的仓库权限不足。需在 token 设置里勾选对应权限（如 Issues: Read and write），或改用 classic token 的 `repo` 范围。
- **`git push` 报 403 Permission denied（账号是仓库所有者）**：不是身份问题，是 PAT 缺 **Contents: Read and write**。Git 用 GCM（`credential.helper=manager`）而非 gh 的凭据；改用带 `repo` 范围的 token，或 `gh auth login -w` + `gh auth setup-git` 让 gh 接管。旧凭据可能被 GCM 缓存，必要时 `git credential-manager erase`。
- **Windows 下多行正文传给 `gh issue create`**：在 Bash 工具里用 heredoc；在 PowerShell 里用单引号 here-string（`@'...'@` 且结束符顶格）。
- **GitHub 的 issue 与 PR 共用编号**：遇到 `#42` 先 `gh pr view 42`，失败再 `gh issue view 42`。
- **子 issue 需要 gh 2.94+**：本机为 2.93，需用 `gh api` 的 `sub_issues` 端点，或在正文写 `Part of #<parent>`。
- **阻塞关系用 database id**：`gh api repos/<owner>/<repo>/issues/<n> --jq .id`，不要传 `#number` 或 `node_id`。
- **领域文档缺失不要报错**：技能约定是静默继续，避免在仓库尚未建立 glossary 时刷噪音。
