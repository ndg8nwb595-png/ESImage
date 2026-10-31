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
| P0-1 并发锁死 | 已完成（待评审） | 进行中=queued/running；sample_ready 不占名额；确认事务+行锁 |
| P0-2 模板整套化 | 已完成（待评审） | 模板定义整套 6 张视觉体系；移除 image_role 与模板尺寸 |
| P0-3 尺寸预设建表 | 已完成（待评审） | 新增 `size_presets` 表，总数 17→18，同步 0/4/10 号文档 |
| P0-4 批次 stage 字段 | 已完成（待评审） | `generation_batches.stage`，同步 4/9/10 号文档与枚举 |
| P0-5 视觉模型配置 | 已完成（待评审） | `model_configs.vision_model`；质量审核调用，未配置则跳过标记 |
| P0-6 平台规范规则来源 | 已完成（待评审） | 规则写入 `platform_rule` 系统提示词，`{{platform_rules}}` 读取，不建表 |
| P0-7 参数/上传图恢复 | 已完成（待评审） | localStorage 保存参数与上传图 ID；新增 `GET /uploads/{id}`；上传图首次生成回填 session_id |
| P0-8 首条会话创建 | 已完成（待评审） | 新增 `POST /sessions/messages`；聊天/生成无 session_id 时后端事务内创建 |
| 重新生成 Agent 配置 | 已完成 | 按技能模板重写 docs/agents；五个标签已校验；docs/reviews 已忽略 |
| 逐份细化子 PRD（grill-with-docs） | 已完成 | 1~11 号全部细化并回写（含 0 号同步）；遗留：§9.5 口径待复核、demo 文档一致性核对待定 |
| 术语表独立 | 已完成 | 根目录 `GLOSSARY.md`；`AGENTS.md` 的「Domain glossary」同步路径与内容 |

### 12 份文档清单

0. `0-系统汇总prd.md`
1. `1-登录界面/1-登录界面prd.md`
2. `2-用户端创作工作台/2-用户端创作工作台prd.md`
3. `3-Agent会话交互/3-Agent会话交互prd.md`
4. `4-生图任务与结果/4-生图任务与结果prd.md`
5. `5-历史作品/5-历史作品prd.md`
6. `6-管理后台-账号与权限/6-管理后台-账号与权限prd.md`
7. `7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md`
8. `8-管理后台-聊天记录/8-管理后台-聊天记录prd.md`
9. `9-后端服务与接口prd.md`
10. `10-数据模型与存储prd.md`
11. `11-部署与运维prd.md`

## 2026-10-31 会话 5：登录最小实现 demo

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 1 号 PRD 独立文件夹 | 完成 | 移入 `docs/prd/1-登录界面/`，同步 0/6 号引用 |
| 登录最小 demo 任务拆解 | 完成 | `docs/prd/1-登录界面/issues/01`~`06`，六个垂直切片 |
| 登录最小 demo 接口文档 | 完成 | `docs/prd/1-登录界面/接口文档-登录最小demo.md`，含 3 个 auth 接口、JWT、错误码、前端处理、审计 |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| 登录最小 demo 代码实现 | 后端完成（会话 14），前端按用户要求暂不开发 | 6 张表 + 3 个 auth 接口 + 幂等种子 + 35 个 pytest；详见文末「会话 14」 |

## 2026-10-31 PRD 交叉评审（待用户裁决）

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 审查 12 份 PRD 的模块冲突、不合理设计、冗余设计、缺失设计 | 已完成（只读） | 通读 `docs/prd/` 与 `GLOSSARY.md`，输出 P0/P1/P2/P3 清单；未改文档 |
| 输出评审报告 md | 已完成 | `docs/reviews/PRD交叉评审-2026-10-31.md`；未修改 PRD 原文件 |
| 逐项确认并修订 PRD | 未开始 | 等待用户选择先处理项；架构类改动需用户拍板 |

### 关键约束

- 产品形态：内部工具，管理员开号，不开放注册、不计费。
- 角色：固定三角色，账号 1~2 角色；禁止超管+管理员；超管权限包含管理员。
- 生成：8 Agent 全链路；聊天轻链路；示例图即主图，确认后生成 5 张详情图（合计 6 张）。
- 技术：React + FastAPI + PostgreSQL + Redis + MinIO + Docker Compose。
- 开发：AI 代码生成只用 DeepSeek，禁止 Codex/GPT；中文注释/文档/日志。

## 2026-10-31 会话 6：创作工作台最小实现 demo

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 2 号 PRD 独立文件夹 | 完成 | 移入 `docs/prd/2-用户端创作工作台/`，同步 0/3/4/5 号引用 |
| 创作工作台最小 demo 任务拆解 | 完成 | `docs/prd/2-用户端创作工作台/issues/01`~`07`，七个垂直切片 |
| 创作工作台最小 demo 接口文档 | 完成 | `docs/prd/2-用户端创作工作台/接口文档-创作工作台最小demo.md` |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| 创作工作台最小 demo 代码实现 | 未开始 | 按 01→02→03/04→05→06→07 顺序推进 |

### 最小 demo 范围

- 做：三栏布局、参数面板与商品名称校验、商品图上传与恢复、会话列表与聊天轻链路（SSE）、示例图生成与阶段进度、确认全套与 6 图网格、结果预览与单张下载、数据隔离。
- 不做：模板、尺寸预设/自定义尺寸、会话重命名/删除、取消、单张重生成/重试、ZIP 整组下载、历史/个人中心/管理后台真实页面、真实 8 Agent 链路、内容审核、Token 统计/审计、移动端。
- 前提：复用 `1-登录界面` demo 的 01~03（工程骨架、登录闭环、登录态与路由守卫）。

## 2026-10-31 会话 7：Agent 会话交互最小实现 demo

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 3 号 PRD 独立文件夹 | 完成 | 移入 `docs/prd/3-Agent会话交互/`，同步 0/2/4/8 号与 2 号接口文档引用 |
| Agent 会话交互最小 demo 任务拆解 | 完成 | `docs/prd/3-Agent会话交互/issues/01`~`04`，四个垂直切片 |
| Agent 会话交互最小 demo 接口文档 | 完成 | `docs/prd/3-Agent会话交互/接口文档-Agent会话交互最小demo.md` |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| Agent 会话交互最小 demo 代码实现 | 未开始 | 按 01/02/03 → 04 顺序推进；01/02/03 可并行 |

### 最小 demo 范围

- 做：会话重命名/软删除/切换、三类消息与 Markdown 安全渲染、消息状态与输入规则、规划 + 商品理解轻链路、需求摘要、10 轮上下文截断、`agent_runs` 调用明细、需求变化提示。
- 不做：`POST /sessions`、会话恢复、聊天导出/分享/语音/图片、聊天触发生图、后端取消消息接口、管理后台聊天页与 Agent 明细查询、真实审核、真实 Token 计费、Token 二次压缩、5 年归档、移动端。
- 前提：2 号 demo 01/02/04；04 切片额外依赖 2 号 demo 06。
- 定位：只做 2 号 demo 04 的增量，不重复会话列表、首条消息建会话、SSE 骨架、自动命名、幂等与断线重试。

## 2026-10-31 会话 8：生图任务与结果最小实现 demo

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 4 号 PRD 独立文件夹 | 完成 | `git mv` 移入 `docs/prd/4-生图任务与结果/`，同步 0/3/5/7/8/10 号与本 PRD 内部引用 |
| 生图任务最小 demo 任务拆解 | 完成 | `docs/prd/4-生图任务与结果/issues/01`~`08`，八个垂直切片 |
| 生图任务最小 demo 接口文档 | 完成 | `docs/prd/4-生图任务与结果/接口文档-生图任务最小demo.md`，含 11 个接口、Agent 内部契约、合成契约、状态机、错误码 |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| 生图任务最小 demo 代码实现 | 未开始 | 按 01→02→03→04→{05→07, 05→08, 06} 顺序推进 |

### 最小 demo 范围

- 做：真实 8 Agent 全链路、示例批次（规划 6 张仅渲染 1 张）、确认全套（复用示例核心 Agent 输出、串行生成详情图 2~6）、文字留白合成、真实豆包文本/生图/视觉/审核、失败重试与降级、取消、单张重试/重生成、单图与整组下载（ZIP + manifest.csv）、生成配置只读（模板/尺寸）。
- 不做：模板/素材/提示词/模型配置的后台 CRUD、用户上传图内容审核、历史作品页与个人中心、Celery/Redis/MinIO、多实例与异步队列。
- 前提：2 号 demo 01/05/06；内部依赖 01→02→03→04→{05→07, 05→08, 06}。
- 用户确认的取舍：只走真实豆包；四项恢复能力全做；生成配置只读取+种子；仅生成图审核。

## 2026-10-31 会话 9：历史作品最小实现 demo

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 5 号 PRD 独立文件夹 | 完成 | `git mv` 移入 `docs/prd/5-历史作品/`，同步 0 号索引与 2 号关联文档路径 |
| 历史作品最小 demo 任务拆解 | 完成 | `docs/prd/5-历史作品/issues/01`~`05`，五个垂直切片 |
| 历史作品最小 demo 接口文档 | 完成 | `docs/prd/5-历史作品/接口文档-历史作品最小demo.md`，含 6 个接口、ZIP/manifest、归档与错误码 |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| 历史作品最小 demo 代码实现 | 未开始 | 按 01→02→{03,04}→05 顺序推进 |

### 最小 demo 范围

- 做：历史列表与分页（固定每页 20）、批次详情与图片网格、大图预览、单张下载、整组 ZIP + manifest.csv、归档读取与降级、只读与权限边界。
- 不做：删除/编辑/重命名、收藏/分组/标签、搜索/筛选、分享、提示词展示、归档调度任务、异步 ZIP、管理后台内容追溯、补生成入口、移动端。
- 前提：1 号 demo 01~03；2 号 demo 06/07。
- 用户确认的取舍：5 个切片；预览/缩略图权限放宽为 `user.history` 或 `user.generate`；归档纳入；整组 ZIP 纳入。

## 2026-10-31 会话 10：管理后台-账号与权限最小实现 demo

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 6 号 PRD 独立文件夹 | 完成 | `git mv` 移入 `docs/prd/6-管理后台-账号与权限/`，同步 0/1/7/10 号引用 |
| 账号与权限最小 demo 任务拆解 | 完成 | `docs/prd/6-管理后台-账号与权限/issues/01`~`08`，八个垂直切片 |
| 账号与权限最小 demo 接口文档 | 完成 | `接口文档-账号与权限最小demo.md`，13 个接口、权限点目录、账号边界、日志动作码 |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| 账号与权限最小 demo 代码实现 | 未开始 | 按 01→02→03→{04,05,06}；01→07；02→08 顺序推进 |

### 最小 demo 范围

- 做：管理后台骨架与权限中间件、23 个权限点与三角色种子、用户列表、新建账号、编辑与角色边界、禁用/启用、软删除/恢复、重置密码、用户详情（统计占位）、角色权限配置、操作日志查询。
- 不做：Redis 缓存、Alembic、真实用户统计、内容追溯跳转、其他管理模块与对应日志、个人中心改密、日志归档/导出、并发冲突检测、移动端。
- 前提：1 号 demo 01~03（工程骨架、登录闭环、登录态与路由守卫）。
- 用户确认的取舍：8 个切片；新增 `demo_super`；统计返回 0 且 `stats_available=false`；内容入口按钮占位禁用。

## 2026-10-31 会话 11：管理后台-聊天记录最小实现 demo

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 8 号 PRD 独立文件夹 | 完成 | 移入 `docs/prd/8-管理后台-聊天记录/`，同步 0/7 号引用 |
| 聊天记录最小 demo 任务拆解 | 完成 | `docs/prd/8-管理后台-聊天记录/issues/01`~`06`，六个垂直切片 |
| 聊天记录最小 demo 接口文档 | 完成 | `接口文档-聊天记录最小demo.md`，10 个接口、种子夹具、权限矩阵、错误码、审计动作 |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| 聊天记录最小 demo 代码实现 | 未开始 | 按 01→02→{03,04}；01→{05,06} 顺序推进 |

### 最小 demo 范围

- 做：8 号后台菜单骨架、4 张内容表建表+幂等种子夹具、聊天记录列表与四类筛选、会话详情/消息流/`around_id` 定位、Agent 调用明细（摘要/超管完整输入输出）、消息搜索与高亮、模型配置读取保存（AES-GCM、脱敏、审计）、系统提示词 8 Agent 列表/保存/版本/回滚/变量告警/审计。
- 不做：Redis 缓存、Alembic、Celery、MinIO、聊天导出/编辑/删除/恢复、全文索引、模型连通性测试、提示词 diff/A-B、新建/删除 Agent、概览/Token 统计/生图三层钻取/数据导出、5 年归档、移动端。
- 前提：1 号 demo 01~03（工程骨架、登录闭环、路由守卫）+ 6 号 demo 01（管理后台骨架、权限中间件、23 个权限点）。
- 用户确认的取舍：三块全做、6 个切片；聊天数据用幂等种子夹具；「查看批次」用只读摘要抽屉；不重复 7 号生图详情。

## 2026-10-31 会话 12：后端服务与接口最小实现 demo

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 9 号 PRD 独立文件夹 | 完成 | `git mv` 到 `docs/prd/9-后端服务与接口/9-后端服务与接口prd.md`，同步 0/10/11 引用 |
| 最小 demo 任务拆解 | 完成 | `docs/prd/9-后端服务与接口/issues/01`~`08`，八个契约切片 |
| 最小 demo 接口文档 | 完成 | `接口文档-后端服务与接口最小demo.md`，契约 + 错误码 + 22 项覆盖矩阵 |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| 契约基线代码实现 | 未开始 | 按 01→02→03→{04,05,06,07}→08 顺序推进；04~07 可并行 |

### 最小 demo 范围

- 做：统一响应、错误码与参数校验、分页、JWT 鉴权与账号状态、权限点与越权、上传契约、下载契约、SSE 协议、幂等与并发、OpenAPI、契约回归套件。
- 不做：新增业务接口、登录/工作台/生成/历史/后台页面、生成管线与 8 Agent、Redis/Alembic/Celery/MinIO、导出/归档/限流、6 号待确认项裁决。
- 前提：1 号 demo 01~03；载体另需 2 号 demo 03/04/05/07、3 号 demo 03、5 号 demo 03~04、6 号 demo 01/07。
- 用户确认的取舍：通用契约基线；接口文档写契约+错误码+覆盖矩阵；8 个切片；只记录不裁决 6 号 8 项。

## 2026-10-31 会话 13：管理后台-用户与生图记录最小实现 demo

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 7 号 PRD 独立文件夹 | 完成 | `git mv` 移入 `docs/prd/7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md`，同步 0/4/6/8/10 号引用 |
| 最小 demo 任务拆解 | 完成 | `docs/prd/7-管理后台-用户与生图记录/issues/01`~`06`，六个垂直切片 |
| 最小 demo 接口文档 | 完成 | `接口文档-用户与生图记录最小demo.md`，12 个接口、统计口径、权限边界、错误码、与 9/10 差异 |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| 最小 demo 代码实现 | 未开始 | 按 01→02；01→03→04→05；03→06 顺序推进（02 与 03~05 可并行） |

### 最小 demo 范围

- 做：概览四卡与 60 秒缓存、Token 统计、用户/会话/批次/图片三层钻取、单图详情与媒体访问、用户详情真实统计与内容入口、幂等演示种子。
- 不做：数据导出、图表/排行、后台删除/重生成/改提示词、直连 SQL、Redis/MinIO/Celery/Alembic、真实豆包生成、8 号聊天页（只跳转）、移动端。
- 前提：1 号 demo 01~03；6 号 demo 01/06；4 号 demo 01；可选 4 号 demo 03/04、5 号 demo 05、8 号 demo。
- 依赖：6 号 demo 01 + 4 号 demo 01 → 01；01 → 02；01 → 03 → 04 → 05；03 + 6 号 demo 06 + 4 号 demo 01 → 06。
- 用户确认的取舍：6 个切片；不做数据导出；概览用进程内缓存；媒体走鉴权接口；种子模拟归档与失败/替代图。

## 2026-10-31 会话 14：登录最小 demo 代码实现（后端）

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 工程骨架与演示账号（ticket 01） | 完成 | `docker-compose.yml` 起 PostgreSQL 16（宿主机 55433）；`scripts/init_db.py` 建 6 张表；`modules/auth/seed.py` 幂等种子三角色、4 权限、3 个演示账号 |
| 登录接口与登录页闭环（ticket 02） | 后端完成 | `POST /api/v1/auth/login`，校验用户名/密码格式、bcrypt 校验、失败统一 401 `20001`、成功签发 JWT 并写审计 |
| 登录态恢复与路由守卫（ticket 03） | 后端完成 | `GET /api/v1/auth/me`，校验签名/过期/账号状态/`token_version` |
| 角色分流与双角色切换（ticket 04） | 后端完成 | 登录与 `/me` 返回 `roles`/`permissions`；`demo_dual` 同时具备 user+admin |
| 账号状态即时失效（ticket 05） | 完成 | 每请求查库校验 `status=active` 与 `token_version`；禁用返回 403 `20004`，版本不符返回 401 `20003` |
| 退出登录与审计（ticket 06） | 完成 | `POST /api/v1/auth/logout` 返回 `data=null`，审计 `auth.logout`；登录成功/失败均审计且不落密码 |
| 前端页面（登录页、守卫、角色落地页） | 按用户要求取消 | 已删除本轮创建的 5 个前端文件，`frontend/` 仅保留骨架 `.gitkeep` |

- 验证：`pytest` 35 passed；真实服务用 curl 按接口文档逐项校验通过（含成功、参数错误、凭据错误、token 失效/过期/版本不符/禁用、退出与审计）。
- 演示账号：`demo_user` / `demo_admin` / `demo_dual`，密码 `Demo1234`。

## 2026-10-31 会话 15：创作工作台后端最小 demo 代码实现

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 工作台最小数据表（ticket 01） | 完成 | `models/workspace.py` 六张表：`creative_sessions`、`chat_messages`、`agent_runs`、`generation_batches`、`generated_images`、`uploaded_assets`；字段、约束、索引对齐 10 号 §4.6~§4.11 |
| 演示权限（ticket 01） | 完成 | `auth/seed.py` 新增 `user.generate`，授予 `user` 与 `super_admin`；同步 `test_auth.py` 权限断言 |
| 会话列表与消息分页（ticket 04） | 完成 | `GET /sessions`（≤50、`last_message_preview`、`latest_batch_id`）、`GET /sessions/{id}/messages`（分页、页内升序、`30013`） |
| 聊天轻链路 SSE（ticket 04） | 完成 | `POST /sessions/messages`、`POST /sessions/{id}/messages`；`meta/agent_status/delta/done`；规划 + 商品理解两个 Agent；`client_message_id` 幂等；`agent_runs` 落库 |
| 商品图上传与恢复（ticket 03） | 完成 | `POST /uploads` 二次校验格式/大小/可解码/未绑定数量 ≤5；`GET/DELETE /uploads/{id}`；`/content`、`/thumbnail`；本地存储 + WebP 缩略图 |
| 示例批次与阶段进度（ticket 05） | 完成 | `POST /generations/sample`（无会话原子建会话、幂等、并发 30003、上传图绑定与排序、参数快照）；演示管线阶段推进；`GET /generations/{id}` |
| 确认全套与结果网格（ticket 06） | 完成 | `POST /generations/{id}/confirm`（行锁、最新可确认、幂等、复用示例图为主图、5 张详情图、`is_history_visible`） |
| 预览与单张下载（ticket 07） | 完成 | `GET /images/{id}/content`、`/thumbnail`、`/download`；示例图下载 409 `30005`；文件名规则与非法字符替换 |
| curl 验收脚本 | 完成 | `backend/scripts/curl_smoke.sh` 临时起服务并逐条调用全部接口；UTF-8 JSON 文件 + `--data-binary` |
| 测试 | 完成 | `tests/test_workspace.py` 20 个用例；全量 `pytest` 51 passed |
| 独立审查 | 完成 | 只读审查 agent 发现并发幂等、OOM 边界、SSE 断线、校验文案等问题；已修复并复测 |
| 提交与合并 | 完成 | 提交 `7595e31 feat: 实现创作工作台后端最小 demo 与 curl 验收`；推送功能分支并 `--ff-only` 合并到 `main`，远程 `main` 已更新 |

## 2026-10-31 会话 15：Agent 会话交互后端实现

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 新建开发分支与骨架 | 完成 | `feat/agent-chat-backend-demo`；骨架提交 `19428da` 已推送并 `--ff-only` 合并 `main`；2 号 demo 04 合并后 rebase 到 `115fb88` |
| chat 模块 | 完成 | `router.py`、`schemas.py`、`service.py`、`agents.py`、`model.py`、`stream.py`、`README.md` |
| PATCH 会话重命名 | 完成 | 去首尾空格 1~50 字；纯空格 10002、超长 10004、类型/换行 10003；不改消息/批次/摘要/last_message_at |
| DELETE 会话软删除 | 完成 | `status=hidden`；消息/批次/图片/上传图保留；重复删除 30013；用户列表立即隐藏 |
| 消息分页惰性超时 | 完成 | `sending` 超过 120 秒的 Agent 消息在查询时标记 `failed`；用户消息不参与 |
| 聊天 SSE 增量 | 完成 | `meta.duplicate`、`done.requirement_changed`、10 轮上下文与省略说明、`params.upload_ids` 校验、`agent_runs` 双 Agent 明细 |
| 豆包真实模型 | 完成 | OpenAI SDK + `ARK_API_KEY`；规划非流式、商品理解流式 + `<<<SUMMARY>>>` 摘要；Token 取 usage；无 Key/测试走演示桩 |
| 会话列表摘要清洗 | 完成 | `last_message_preview` 去换行/首尾空格后截取 30 字 |
| 测试 | 完成 | `tests/test_chat.py` + `tests/test_chat_model.py`（假客户端）；全量 `pytest` 85 passed |
| curl 联调 | 完成 | 6 个接口 + 真实豆包对话；PATCH/DELETE/隐藏 30013/管理员 403/他人会话 30013 全通过 |
| 独立审查 | 完成 | 修复重试时间戳、回复归属、隐藏会话重放、重放摘要、测试库隔离等 |
| 提交与合并 | 完成 | 提交 `6e0c96c feat: 实现 Agent 会话交互后端增量与豆包接入`；rebase 到 `4ea5d64`，推送功能分支并 `--ff-only` 合并 `main`，远程 `main` 已更新 |

- 已确认范围：只做后端；`PATCH/DELETE /sessions/{id}`、消息分页惰性超时、聊天 SSE 的 `meta.duplicate` 与 `done.requirement_changed`、轻链路与 10 轮上下文、`agent_runs` 落库、需求变化判定。
- 明确不做：`POST /sessions`、会话恢复、取消接口、`agent_runs` 查询、消息搜索/导出、管理端聊天、聊天触发生图、真实内容审核与 Token 计费。
- 环境：复用 docker `esimage-postgres`（55433）；chrome-devtools MCP 已连接（1 个 about:blank 页面），留作后端 OpenAPI/Swagger 验证。

## 10 号数据模型与存储最小 demo（文档任务）

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| PRD 移入独立目录 | 完成 | `git mv` 到 `docs/prd/10-数据模型与存储/10-数据模型与存储prd.md` |
| 最小 demo 任务拆解 | 完成 | 8 个垂直切片，`issues/01~08` |
| 最小 demo 接口文档 | 完成 | `接口文档-数据模型与存储最小demo.md`：18 表、迁移/种子命令、存储路径、归档、验收 |
| 数据底座范围 | 已界定 | 18 表 + Alembic + 幂等种子 + 超管 + 存储路径 + 5 年归档 + 回归 |
| 明确不做 | 已记录 | 备份恢复（11 号）、导出及清理（7 号）、孤儿清理、pg_trgm、Redis、Celery、真实 MinIO、业务 HTTP |
| 待用户确认 | 17 项 | 超管权限落行、上传缩略图/未绑定路径、`source_*` 外键、`client_request_id` 跨用户、归档策略、密码策略、动作码等 |

## 2026-10-31 会话 15：11 号部署与运维最小 demo（文档任务）

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| PRD 移入独立目录 | 完成 | `git mv` 到 `docs/prd/11-部署与运维/11-部署与运维prd.md`；同步 0 号索引、9 号关联文档、10 号接口文档引用 |
| 最小 demo 任务拆解 | 完成 | 8 个垂直切片，`issues/01~08`，按依赖顺序编号 |
| 最小 demo 接口文档 | 完成 | `接口文档-部署与运维最小demo.md`：双健康探针、网关/SSE、Compose 契约、脚本 CLI、定时任务、日志、错误码、验收矩阵 |
| 发布到 GitHub issue | 未做（按用户要求输出到本地文件夹） | 如需发布可再执行 `gh issue create` |
| 最小 demo 代码实现 | 未开始 | 按 01→02→03→{04,05,06,07}→08 顺序推进；04~07 可并行 |

### 最小 demo 范围

- 做：单机 Compose 基线、依赖服务与 MinIO 桶/前缀、Alembic 迁移与幂等种子、初始超管、backend/frontend/worker/beat 镜像、双健康探针、Nginx 网关与 SSE、结构化日志与 `request_id`、备份恢复、Worker/Beat 基线、一键启动与验收脚本。
- 不做：5 年归档、孤儿上传清理、导出清理、权限缓存刷新、审计业务写入、HTTPS/443、MinIO 控制台、Prometheus/Grafana、多机/灰度/容灾、业务页面与业务接口、真实生成链路。
- 用户确认的取舍：8 个切片；只起 Worker/Beat、不做归档；健康接口双路径；PRD 移动并更新引用。
- 演示专用：`GET /api/v1/sessions/_probe/stream` 与 `ops.selftest`，仅非生产启用，待正式确认是否保留。

- 已确认范围：只做后端；重命名、软删除、消息状态、轻链路、上下文、需求摘要、需求变化提示、`agent_runs` 明细。
- 明确不做：`POST /sessions`、会话恢复、取消接口、`agent_runs` 查询、消息搜索/导出、管理端聊天、聊天触发生图、真实内容审核；生图 `doubao-seedream-5-0-pro-260628` 属于 4 号，3 号不调用。
- 环境：复用 docker `esimage-postgres`（55433）；8001 跑 3 号服务；chrome-devtools MCP 已验证 Swagger UI 与 OpenAPI。

## 2026-10-31 会话 17：6 号账号与权限后端实现（完成）

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 模块骨架与分支 | 完成 | `feat/admin-accounts-backend-demo`；`admin/accounts`、`admin/audit` README；已推送并 `--ff-only` 合并 `main` |
| 路由基线修复 | 完成 | `admin/router.py` 从 `xxx.router` 导入 router 对象；汇总路由加 `prefix="/admin"` |
| 23 权限点与 demo_super | 完成 | `auth/seed.py`：23 权限、user 4、admin 13、super_admin 不写 `role_permissions`、新增 `demo_super` |
| 超管全量权限与鉴权顺序 | 完成 | `core/deps.py`：超管读全部权限码；账号状态先于 `token_version` |
| 用户列表/新建/详情/编辑/重置密码/禁用启用/删除恢复 | 完成 | 13 个接口对齐 6 号接口文档的字段、错误码、账号边界与最后超管保护 |
| 角色与权限点 | 完成 | 固定三角色顺序、超管只读、最低权限、超管专属拒绝、返回角色对象、`role.update` 审计 |
| 操作日志 | 完成 | 文档参数 `operator/start_time/end_time` 与前端旧参数双兼容；响应同时含 `log_id` 与 `id` 等；30019 |
| 失败审计 | 完成 | 账号/角色写操作失败记录 `result=failed` 与 `detail.reason`，独立事务提交 |
| 测试与 curl | 完成 | 新增 13 个 pytest 用例；全量 **98 passed**；`curl_admin_smoke.sh` 13 接口全部通过（脚本自动建表/种子） |
| 代码审查修复 | 完成 | 已删除账号禁止 PATCH 绕过、编辑边界按值判断、纯空格密码拒绝、种子收敛权限目录、404 失败审计、统计批量聚合、无 body 返回 10002 |
| 合并最新 main | 完成 | 合并 9 号契约与 7 号管理端整合；管理端路径统一 `/api/v1/admin/*`；统计改用 `build_user_stats`；全量 **169 passed / 171**，2 个失败为 11 号 `test_ops` 既有问题（已在干净 main 复现） |
| 统计口径 | 完成（用户确认） | 内容表已接入，返回真实统计且 `stats_available=true` |
| 权限目录 | 完成（用户确认） | 名称、类型、分组按 6 号文档；分组只有用户端/管理后台 |
| Chrome MCP | 部分完成 | MCP 工具已加载；浏览器 profile 被其他 agent 占用时无法新建页面，改用 OpenAPI + curl 验证 |

## 2026-10-31 会话 17：5 号历史作品后端最小 demo 实现

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 分支与骨架 | 完成 | `feat/history-backend-demo`；`4ea5d64` 建 `history/README.md` 骨架，push 后 ff 合并 `main` |
| 历史列表与分页 | 完成 | `GET /history`：本人 `full`、`completed`/`partially_failed`、final+success+visible；固定 20 条，`page` 非法返回 10001 |
| 批次详情与网格 | 完成 | `GET /history/{batch_id}`：不存在 404/30004、越权 403/20005、非历史范围 404/30004；图片按序号升序 |
| 大图预览与单张下载 | 完成 | 复用 `/images/{id}/content`、`/download`；预览/缩略图权限放宽为 `user.history` 或 `user.generate`；下载限 `full + final + success + visible` |
| 整组 ZIP 与 manifest | 完成 | `GET /batches/{batch_id}/download`，同步流式 ZIP；manifest UTF-8 BOM、中文表头、成功/失败行、失败原因 |
| 归档读取与降级 | 完成 | `archived_at` 非空读 `archive/{file_path}`；缩略图始终热存；`ARCHIVE_READ_TIMEOUT_SECONDS` 默认 60；缺失/超时 404/30014 并写错误日志 |
| 种子夹具 | 完成 | `history/seed.py` 幂等写入 21 个历史可见批次 + 示例/失败批次 + demo_dual 其他用户批次；接入 `scripts/seed.py` |
| 自动化测试 | 完成 | `tests/test_history.py` 8 用例；合并最新 `main` 后全量 `pytest` 93 用例通过 |
| curl 验收 | 完成 | `scripts/curl_history_smoke.sh`，独立库/存储，覆盖接口文档 §16 全部调用 |
| 待用户裁决 | 待确认 | 种子计数口径（21 可见 vs 文档“21 completed + partial”）；manifest 宽度/高度分列与 4 号“尺寸”单列差异 |

## 2026-10-31 会话 18：本地 MinIO 存储接入

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| `backend/.env` 本地启动配置 | 完成 | 以 `.env.example` 为模板生成；数据库 55433、Redis 6379、MinIO 127.0.0.1:9002；JWT_SECRET 随机；`.env` gitignored |
| Docker 依赖端口暴露 | 完成 | `docker-compose.yml` 增加 Redis 6379、MinIO 9002/9003；MinIO 密码默认改 `esimage123` |
| 业务文件真实入 MinIO | 完成 | 完整实现 `MinioStorageAdapter`；`workspace.storage.Storage` 统一门面委托 `get_storage()` |
| 全量读写统一 | 完成 | 上传/生成/缩略图/管理端素材/历史归档读取均走门面；热下载由 `FileResponse` 改缓冲 `Response` |
| 错误契约保持 | 完成 | 对象缺失→404/30014；存储异常→500/50003；归档超时语义不变 |
| 测试隔离 | 完成 | `tests/conftest.py` 强制 `STORAGE_BACKEND=local`；真实 MinIO 测试需显式环境变量才运行 |
| 自动化测试 | 完成 | 13 个存储单元测试 + 2 个真实 MinIO 集成测试通过；全量仅 2 个既有 `test_ops` 失败 |
| 端到端验证 | 完成 | 真实 MinIO：登录→上传→原图→缩略图→`/api/health`；对象落在 `uploads/`、`thumbnails/` |
| 待用户裁决 | 已裁决 | 用户选择方案 C：旧卷 `esimage_esimage_pgdata` 复制到新卷 `esimage_pgdata`，旧卷保留；库内 18 张表、4 个用户 |
| 提交/合并 | 完成 | 已推送 `feat/minio-storage-local`；`main` 以 `--ff-only` 从 `3878e33` 快进到 `a21dc5a` 并推送 |
| 独立审查修复 | 完成 | 本地 FileResponse 兼容、async 上传线程池、compose 存储配置、脚本本地隔离、StorageError 全局映射、端口绑定、响应关闭测试 |
| MinIO Range/ETag | 已知取舍 | MinIO 后端使用缓冲 Response，不支持 Range；本地后端保持原 FileResponse 行为 |
| 归档超时连接池 | 待后续 | MinIO SDK 默认超时/重试较长；极端卡顿可能占用连接池，后续可配置短超时 PoolManager |
## 2026-10-31 会话 17：8 号管理后台-聊天记录（后端）

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 分支与模块目录 | 完成 | `feat/admin-chat-records-backend-demo`；新建 `modules/admin/chat_records/`，骨架提交 `1624922` 并推送分支与 `main` |
| 聊天会话列表 | 完成 | `GET /admin/chat/sessions`：用户/标题关键词（ILIKE 转义）、最后消息日期范围、状态、20/50/100 分页；管理员排除超管账号；聚合消息数、Token、批次数 |
| 会话详情与消息窗口 | 完成 | `GET /admin/chat/sessions/{id}`：默认最新、`before_id`、`around_id` 锚点；`has_older/has_newer`；Agent 名称、调用摘要、关联批次；`sending` 超时惰性标记 failed |
| Agent 调用明细 | 完成 | `GET /admin/agent-runs/{id}`：完整字段、`token_usage`、`full_available`；管理员 `full=true` 403；超管可看已脱敏完整输入/输出；权限经 session/batch 推导 |
| 消息搜索 | 完成 | `GET /admin/chat/messages/search`：`keyword` 1~100、固定每页 20、大小写不敏感、通配符转义、约 120 字符纯文本摘要、可见范围过滤 |
| 模型配置 | 完成 | `GET/PUT /admin/model-config`：仅超管；AES-256-GCM 加密、`sk-****abcd` 脱敏、范围/步长/URL 校验、单启用行、审计不含明文 |
| 系统提示词 | 完成 | 8 Agent 固定顺序列表、详情、保存新版本、回滚生成新版本；`{{变量}}` 识别、未知/缺失建议变量告警；行锁；审计 |
| 加密密钥启动校验 | 完成 | `MODEL_CONFIG_ENCRYPTION_KEY` 为主、`ENCRYPTION_KEY` 回退；缺失或非 32 字节启动失败；`.env.example` 与测试 conftest 提供演示密钥 |
| 演示种子 | 完成 | `chat_records/seed.py` 4 会话/消息/调用/批次幂等夹具；auth 种子新增 `demo_super`；config 种子补版本 1 与默认模型配置 |
| 自动化测试 | 完成 | `tests/test_admin_chat_records.py` 7 用例通过；合并后全量 178 collected / 176 passed，2 个 `test_ops` 既有环境失败 |
| curl 验收 | 完成 | `.smoke/curl_module8.sh` 覆盖 8 组接口，合并前后均全部通过 |
| 既有缺陷修复 | 完成 | `admin/router.py` 显式导入子模块 `APIRouter`；管理后台路由补 `/admin` 前缀 |

## 2026-11-01 会话 19：修复 test_ops 过期用例

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 非法 X-Request-ID 用例可执行 | 完成 | 测试头值改为 ASCII `"bad id!"`，仍覆盖非法值重新生成分支 |
| selftest 纯函数用例可执行 | 完成 | 删除对不存在的 `ops_tasks.delay_ms` 的 monkeypatch，直接验证 `selftest(request_id, delay_ms)` |
| 回归验证 | 完成 | `tests/test_ops.py` 22 passed；全量 192 passed、2 skipped |
| 分支与合并 | 完成 | 分支 `fix/test-ops-stale-cases` 已推送；`main` 以 `--ff-only` 从 `c8f073e` 快进到 `c7b5b01` 并推送 |

## 2026-11-01 会话 20：记忆文件推送与根 `.env`

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 推送记忆文件 | 完成 | 五个 `.claude/MEMORY_*.md` 独立提交并推送 `main` |
| 补齐根 `.env` | 完成 | 按根 `.env.example` 补齐 31 个 compose 变量，保留原 `GITHUBTOKEN`；随机生成密钥与初始超管密码 |
| 配置校验 | 完成 | `docker compose config -q` 通过；`.env` 被 `.gitignore` 忽略，未入库 |
| 后端本地配置 | 无需改动 | `backend/.env` 已包含宿主机启动所需全部键，本次未改 || 既有缺陷修复 | 完成 | `admin/router.py` 显式导入子模块 `APIRouter`；管理后台路由补 `/admin` 前缀 || 待用户裁决 | 待确认 | 种子计数口径（21 可见 vs 文档“21 completed + partial”）；manifest 宽度/高度分列与 4 号“尺寸”单列差异 |- 已确认范围：只做后端；重命名、软删除、消息状态、轻链路、上下文、需求摘要、需求变化提示、`agent_runs` 明细。
- 明确不做：`POST /sessions`、会话恢复、取消接口、`agent_runs` 查询、消息搜索/导出、管理端聊天、聊天触发生图、真实内容审核；生图 `doubao-seedream-5-0-pro-260628` 属于 4 号，3 号不调用。
- 环境：复用 docker `esimage-postgres`（55433）；8001 跑 3 号服务；chrome-devtools MCP 已验证 Swagger UI 与 OpenAPI。## 2026-10-31 会话 16：4 号生图任务与结果后端最小 demo（代码实现）

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 模块目录与骨架 | 完成 | `backend/app/modules/generation/`；先推分支再合并 main |
| 生成数据模型 | 完成 | 复用 `generation_batches/generated_images/agent_runs`；新增 `templates/material_assets/model_configs/system_prompts/prompt_versions/size_presets` |
| 8 条系统提示词与种子 | 完成 | `generation/seed.py`，幂等；2 模板、4 素材、4 尺寸、1 模型配置 |
| 只读配置接口 | 完成 | `GET /templates`、`/templates/{id}/thumbnail`、`/sizes`；60 秒缓存 + 手动刷新 |
| 豆包适配层 | 完成 | 文本/视觉 `chat/completions`、生图 `images/generations`、生成图审核（视觉模型结构化判定）；Key 支持 `ARK_API_KEY` |
| 8 Agent 运行时 | 完成 | 结构化输出校验、10 次指数退避、每次尝试写 `agent_runs`、跳过写 `skipped` |
| 文字留白合成 | 完成 | Pillow + 默认版式；标题上方 15%、卖点下方 20%、边距 8%；缩字号/截断/半透明白底 |
| 示例批次真实全链路 | 完成（真实生图待额度） | 规划→商品理解→文案→提示词→生图→审核→质量→修复→规范→合成 |
| 确认全套与详情图 | 完成（真实生图待额度） | 复用示例图与四类核心 Agent 输出，串行生成 2~6 |
| 失败重试与降级 | 完成 | 核心失败批次 failed、生图 2 次失败立即 failed、非核心跳过、非生图单张失败继续、30 分钟超时、测试故障注入 |
| 取消任务 | 完成 | 行锁 + 状态机；pending 置 cancelled、成功图不进历史、重复取消幂等 |
| 单张重试/重生成 | 完成 | 新记录 attempt+1、旧图 superseded、`completed_count` 重算、单批次单重试 |
| 整组 ZIP + manifest | 完成 | 临时文件流式返回；UTF-8 BOM CSV；部分失败仍可下载成功图 |
| curl 验收 | 完成（替身）；真实待额度 | `scripts/curl_smoke_generation.sh` 覆盖全部接口；真实示例批次已跑通四个核心 Agent |
| pytest | 完成 | 75 passed；生成链路使用确定性替身，不访问外网 |
| 真实 Seedream 验收 | 阻塞 | 账号安全体验模式额度用尽（429 SetLimitExceeded），待用户在控制台调整 |

### 明确不做

- 模板/素材/尺寸/提示词/模型配置的后台 CRUD（只读 + 种子）。
- 上传图内容审核、历史作品页、个人中心、管理后台页面。
- Celery/Redis/MinIO/Alembic；多实例与批次级重新生成。

### 会话 16 复审补充

| 复审项 | 状态 | 处理 |
| --- | --- | --- |
| 共享工具重复 | 已修复 | 新增 `app/core/common.py`，workspace/generation 共用 |
| 单张重试并发窗口 | 已修复 | `pending` + `generating` 都计入，新增测试 |
| 取消丢弃在途图 | 已修复 | 生图开始后允许当前张完成，完成后再检查取消 |
| 重试忽略修复后提示词 | 已修复 | 优先使用 `image.prompt`，示例输出只补 whitespace/reference |
| completed 后残留 error_message | 已修复 | 重试汇总按终态清空/设置 |
| 上传图只传 2 张 | 已修复 | 最多 5 张上传 + 素材，参考图上限 6 |
| pytest | 完成 | **76 passed** |
| 真实 Seedream 验收 | 阻塞 | 429 SetLimitExceeded，待控制台调整额度 |

### 会话 16 收尾决定（2026-10-31）

- 用户选择：真实 Seedream 额度恢复前**不合并 main**，保留 `feat/generation-backend-demo` 分支；额度调整后先跑 `bash backend/scripts/curl_smoke_generation.sh`，真实通过再合并。
- 分支已 rebase 到 `origin/main`（`fcc1fde`，含 3 号聊天后端与管理后台骨架），解决 `config.py` / `main.py` / `.env.example` / 5 个 Memory 文档冲突后，全量 **102 passed**，替身 curl 全接口通过，已 force-push 到 `4d392a8`。
- 当前唯一未完成项：真实生图模型调用仍返回 429 `SetLimitExceeded`（账号安全体验模式额度），不是代码缺陷。

## 2026-10-31 会话 17：skill 接入与主分支集成

| 需求 | 状态 | 实现手段 |
| --- | --- | --- |
| 加载 `backend/skills/generation-pipeline` | 完成 | generation README 与 backend README 引用；按八条铁律调整管线 |
| rebase 最新 main | 完成 | 9ea5316；解决 config/main/models/seed/test/gitignore/memory 冲突 |
| 复用 10 号配置表 | 完成 | 删除 `models/generation.py`，统一 `models/config.py` |
| 6 号管理端路由隔离 | 完成 | admin assets 移到 `/api/v1/admin/templates|materials|sizes`；contract map 同步 |
| 5 号共享 ZIP | 完成 | 4 号 `/batches/{id}/download` 使用 `history/zip_export.py`；manifest 统一 4 号表头 |
| 归档媒体读取 | 完成 | 预览/下载走 `read_image_bytes`；单张下载 `no-store` |
| 重试幂等列迁移 | 完成 | Alembic `0004_image_client_request` |
| 留白兜底优化 | 完成 | prompt 追加比例；仅留白失败转 warning + 强制半透明底；质量提示词校准 |
| pytest | 完成 | **160 passed**（含主分支模块） |
| 替身 curl | 完成 | 全部接口通过 |
| 真实 Seedream 全链路 | 复验中 | 安全体验模式已关闭；真实单图/示例已成功 |

### 会话 17 收尾

| 项 | 状态 | 说明 |
| --- | --- | --- |
| rebase 最新 main（74f37c4） | 完成 | 解决 README/contract/Memory 冲突 |
| 管理端素材路由前缀 | 完成 | 移除 assets router 的重复 `/admin`；主分支 admin router 已统一加 |
| pytest | 完成 | **191 passed** |
| 替身 curl | 完成 | 全部接口通过 |
| 真实全套 6/6 | 完成 | 批次 48 在被系统终止前 completed 6/6；单张/ZIP 200 |
| 真实重生成完成 | 未完成（外部） | 服务进程被系统因内存不足终止，新图停在 generating；已收敛为 partial |

### 会话 17 新增待办：MinIO 存储

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 并行 MinIO 迁移 | 进行中（其他 agent） | `feat/minio-storage-local`，容器 9002/9003，`STORAGE_BACKEND=minio` |
| 4 号 generation 存储适配 | 待办 | 等该分支合并后 rebase，改用共享 `get_storage()` |
| 合并 main | 暂缓 | 用户选择等 MinIO 分支合并后再处理 |
| 真实重生成验收 | 暂缓 | 共享库重建导致批次 48 丢失；待存储稳定后重跑 |

### 会话 18：MinIO 适配

| 项 | 状态 | 说明 |
| --- | --- | --- |
| generation 存储切统一门面 | 完成 | `workspace.storage` + `media_response` + `read_image_bytes` |
| 删除本地存储适配层 | 完成 | `app/core/storage.py` 删除 |
| 本地 env | 完成 | MinIO 9002 + 加密密钥 |
| 全量测试 | 完成 | 191 passed（2 skipped） |
| 替身 curl（local/MinIO） | 完成 | 均全接口通过 |
| 真实 MinIO 重生成 | 完成 | fake 全套 6/6 + 真实重生成 success；下载/ZIP 200 |
| 合并 main | 待做 | 真实验收通过后合并 |

### 会话 18 收尾

| 项 | 状态 | 说明 |
| --- | --- | --- |
| MinIO 适配 | 完成 | 统一存储门面 + media_response |
| pytest | 完成 | 191 passed（2 skipped） |
| 替身 curl（local/MinIO） | 完成 | 全接口通过 |
| MinIO 真实重生成 | 完成 | fake 全套 6/6 + 真实新图 success；下载/ZIP 200 |
| 合并 main | 完成 | `487dd47` |
