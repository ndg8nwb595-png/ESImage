# 代码规范与架构共识

## 本仓库的 agent 配置约定

- **Agent 指令文件**：仓库根 `AGENTS.md`（本仓库不使用根 `CLAUDE.md`，避免两份并存）。后续若需改 agent 约定，编辑 `AGENTS.md`。
- **Issue 追踪**：GitHub Issues，统一 `gh` CLI；PR 不作为 triage 请求面。
- **Triage 词表**：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。
- **领域文档**：单上下文，根 `GLOSSARY.md` + `docs/adr/`；缺失时静默跳过，不预创建。
- **文档语言**：中文叙述，命令、路径、标签名、代码标识符保持原文。
- 重跑 `setup-matt-pocock-skills` 仅在需要更换追踪器或推倒重来时进行；日常直接编辑 `docs/agents/*.md`。
- **Git 凭据**：remote 为 HTTPS，凭据由 `gh auth setup-git` 接管（token 存于 gh keyring）；`.env` 中有 classic PAT，但**不要提交**，待 `.gitignore` 确认后忽略。
- **分支策略**：改动先落功能分支，经用户确认后用 `--ff-only` 合并到 `main`，再 `git push origin main`。

## 通用开发规范（来自用户全局 CLAUDE.md）

- 严格按需求文档实现，不增不减；不相关代码不触碰。
- 遵循原有边界（数据、循环/索引、资源、逻辑/状态）；与边界规范冲突时给至少三版方案由用户选择。
- 保持上下游接口与返回内容不变。
- 架构相关决定必须经用户确认。
- 中文注释；测试步骤加中文日志。
