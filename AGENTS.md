## Agent skills

### Issue tracker

Issue 与需求文档（spec）以 GitHub issue 形式存放在 `ndg8nwb595-png/ESImage`，统一通过 `gh` CLI 读写。详见 `docs/agents/issue-tracker.md`。

### Triage labels

沿用五个规范标签，标签名与角色名一致：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。详见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文布局：仓库根目录的 `GLOSSARY.md` + `docs/adr/`。详见 `docs/agents/domain.md`。

### Domain glossary

术语表位于仓库根目录 `GLOSSARY.md`，是本项目领域术语的**唯一来源**。编写 PRD、接口、数据库字段、测试用例、issue 与代码注释时，必须使用下表中的术语，不得自造同义词；新增或修改术语时，先改 `GLOSSARY.md`，再同步本节。

| 术语 | 说明 |
| --- | --- |
| AIGC | AI Generated Content，AI 生成内容 |
| Agent | 承担单一职责的 AI 调用单元，本系统共 8 个 |
| 轻链路 | 聊天消息只调用规划 + 商品理解两个 Agent |
| 全链路 | 生成示例图/正式图时调用的完整 8 Agent 流程 |
| 示例图 | 确认风格用的第一张图（即主图），计入最终张数 |
| 图片角色 | 每张图在整套结果中的角色：`main` 主图 / `detail` 详情图 |
| 正式图 | 用户确认示例后批量生成的结果图 |
| 生成批次 | 一次生成动作：`sample` 示例批次或 `full` 全套批次 |
| 会话 | 一个商品项目的创作上下文，对应一个 `creative_session` |
| 商品图 | 用户上传的 1~5 张商品实拍图，可选 |
| 留白合成 | 生图时留出文字区，后端叠加中文文案 |
| 设计 Skill | 后续产出的版式设计能力，驱动文字合成 |
| 豆包 | 火山方舟提供的大模型服务，本系统用于文本、图像与审核 |
| Seedream | 豆包图像生成模型 |
| 平台规范 | 尺寸、违禁词、类目规则等电商平台要求 |
| Token | 大模型调用的计费/计量单位；本系统统计输入与输出 Token |
| 归档前缀 | MinIO `esimage` 桶的 `archive/` 前缀，存放满 5 年的冷数据 |
| RBAC | 基于角色的访问控制 |
| SSE | Server-Sent Events，服务端推送，用于聊天流式输出 |
| JWT | JSON Web Token，登录凭证 |
| MinIO | 自建对象存储服务 |
