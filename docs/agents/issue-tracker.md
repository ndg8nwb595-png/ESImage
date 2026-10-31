# Issue 追踪：GitHub

本仓库的 issue 与 spec 以 GitHub issue 形式存在。所有操作统一使用 `gh` CLI。

## 约定

- **创建 issue**：`gh issue create --title "..." --body "..."`。多行正文使用 heredoc。
- **读取 issue**：`gh issue view <number> --json number,title,body,labels,comments`。
- **列出 issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需加 `--label` 与 `--state` 过滤。
- **把 issue 设为父 issue 的子 issue**：`gh issue create --parent <parent> ...`，或事后 `gh issue edit <parent> --add-sub-issue <child>`（gh 2.94+）。较老的 `gh`：`gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>`（用 database id，见下文 **阻塞关系**）。若环境不支持子 issue，则在子 issue 正文顶部写 `Part of #<parent>`。
- **在 issue 下评论**：`gh issue comment <number> --body "..."`
- **添加 / 移除标签**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭**：`gh issue close <number> --comment "..."`

仓库从 `git remote -v` 推断；在克隆目录内运行 `gh` 时会自动完成。

## 以 PR 作为 triage 请求面

**PR 作为请求面：否。**（若本仓库把外部 PR 当作功能请求，改为 `是`；`/triage` 会读取此标志。）

设为 `是` 时，PR 与 issue 走相同的标签与状态流转，使用对应的 `gh pr` 命令：

- **读取 PR**：`gh pr view <number> --comments`，改动看 `gh pr diff <number>`。
- **列出待 triage 的外部 PR**：`gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '.[] | select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) | {number, title, author: .user.login, author_association, labels: [.labels[].name]}'`。
- **评论 / 打标签 / 关闭**：`gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

GitHub 的 issue 与 PR 共用一个编号空间，裸写 `#42` 可能是两者之一：先用 `gh pr view 42` 解析，失败再退回 `gh issue view 42`。

## 当技能说 "publish to the issue tracker"

创建一个 GitHub issue。

## 当技能说 "fetch the relevant ticket"

按上文 **读取 issue** 的方式读取。

## Wayfinding 操作

供 `/wayfinder` 使用。**地图（map）** 是一个带子 issue 的父 issue，**子 issue** 即票据。

- **地图**：单个 issue，标签 `wayfinder:map`，正文承载 Notes / Decisions-so-far / Fog。`gh issue create --label wayfinder:map`。
- **子票据**：以 GitHub sub-issue 形式挂到地图（见 **把 issue 设为父 issue 的子 issue**）。环境不支持子 issue 时，把子 issue 加进地图正文的任务列表，并在子 issue 正文顶部写 `Part of #<map>`。标签：`wayfinder:<type>`（`research`/`prototype`/`grilling`/`task`）。票据一旦认领，即指派给驱动的开发者。
- **阻塞关系**：使用 GitHub 原生 **issue dependencies**，这是标准且在 UI 中可见的表示。用 `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>` 添加边，其中 `<blocker-db-id>` 是阻塞者的数字 **database id**（`gh api repos/<owner>/<repo>/issues/<n> --jq .id`，注意**不是** `#number`、也不是 `node_id`）。GitHub 上报的 `issue_dependencies_summary.blocked_by` 只统计未关闭的阻塞者，是实时的门禁。环境不支持 dependencies 时，退回在子 issue 正文顶部写 `Blocked by: #<n>, #<n>`。所有阻塞者都关闭后，票据才解除阻塞。
- **前沿查询（frontier query）**：列出地图的未关闭子 issue（`gh issue list --state open`，限定在地图的 sub-issues / 任务列表内），剔除仍有未关闭阻塞者（`issue_dependencies_summary.blocked_by > 0`，或 `Blocked by` 行中仍有未关闭 issue）或已有指派者的，取地图顺序中的第一个。
- **认领**：`gh issue edit <n> --add-assignee @me`，这是本会话的第一次写入。
- **解决**：`gh issue comment <n> --body "<答案>"`，然后 `gh issue close <n>`，最后把上下文指针（摘要 + 链接）追加到地图的 Decisions-so-far。
