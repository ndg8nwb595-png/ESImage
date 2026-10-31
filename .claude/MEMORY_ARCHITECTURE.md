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

## 电商主图/详情图 AIGC 系统（PRD 共识）

- **产品形态**：内部工具；管理员开号；不开放注册、不计费、不做多租户。
- **用户端**：登录、创作工作台、历史作品、个人中心，共 4 页；桌面优先（≥1280px）。
- **管理后台**：6 菜单——概览、账号与权限、内容追溯、素材与模板、Agent 配置、操作日志。
- **Agent**：8 个（规划、商品理解、文案、提示词、生图执行、质量审核、修复、平台规范）；聊天只调规划+商品理解。
- **生成流程**：商品名称校验 → 1 张主图示例 → 用户确认 → 5 张详情图；合计 1 主图 + 5 详情图 = 6 张；尺寸不选默认 1:1、1000×1000。
- **风格**：自由文本；不填由对话 Agent 推荐，后台不做风格配置；尺寸不选默认 1:1。
- **失败策略**：除生图执行 Agent 外，Agent 失败重试 10 次（指数退避，封顶 30s）；生图执行每张最多尝试 2 次，2 次失败整批任务失败；整批超时 30 分钟。
- **并发口径**：同一用户同时只允许 1 个 `queued` / `running` 批次；`sample_ready` 不占名额；确认全套时被确认的示例批次不参与并发校验。
- **模板**：整套模板，定义 1 主图 + 5 详情图的视觉体系；不携带图片角色与尺寸。
- **文字渲染**：模型留白 + 后端合成；版式由后续「设计 Skill」驱动，PRD 只定契约。
- **角色**：固定普通用户/管理员/超管；账号 1~2 角色；禁止超管+管理员；超管权限包含管理员；超管可编辑权限点，管理员不可。
- **技术栈**：React 18 + TypeScript + Ant Design 5；FastAPI + Celery；PostgreSQL 16；Redis 7；MinIO；Nginx；单机 Docker Compose。
- **数据**：18 张表；热存 5 年 + `archive/` 归档前缀；每日备份保留 7 天；导出仅超管（ZIP+CSV）。
- **批次阶段**：`generation_batches.stage` 记录当前 Agent 阶段，取值见 10 号 §5；Worker 每阶段更新。
- **模型配置**：`model_configs` 分 `text_model` / `image_model` / `vision_model`；视觉模型为空时质量审核跳过并标记「未校验」。
- **平台规范**：规则（尺寸、违禁词、类目）写在 `platform_rule` Agent 的系统提示词中，通过提示词版本管理维护；不单独建规则表。
- **参数恢复**：参数与上传图 ID 只存前端 localStorage；会话不持久化参数；上传图首次用于生成时回填 `session_id`。
- **首条会话**：聊天与生成接口允许无 `session_id`，后端在同一事务内创建会话并写入首条消息/批次；用 `client_message_id` 去重。
- **接口**：`/api/v1`、JWT Bearer、统一 `{code,message,data}`、分页 `{items,total,page,page_size}`、OpenAPI。
- **登录与鉴权（2026-10-31 细化）**：密码 8~32 位无复杂度；JWT（PyJWT/HS256）载荷含 `sub`/`exp`/`iat`/`token_version`/`roles`/`permissions`，其中 roles/permissions 仅前端显示用，后端鉴权每请求查 Redis 缓存（≤30s、变更主动失效），以服务端为准；token 存 localStorage；无 refresh token（24h/7d 硬过期）；bcrypt cost=12；前端 react-router v6 + zustand + 自封装 fetch；内网 HTTP 预留 443；登录失败锁定不做。
- **工作台与上传（2026-10-31 细化）**：商品图排序仅前端维护，生成时按 `upload_ids` 顺序写回 `sort_order`；后端数量校验=该用户「未绑定会话且 `active`」上传 ≤5；孤儿上传每日 04:00 清理（30 天未绑定且未被引用 → `deleted` + 删 MinIO 对象）；参数 localStorage 按会话存 `esimage_workspace_params_{session_id}`；模板应用时覆盖风格文本、取消模板保留不回滚。
- **会话与生图链路（2026-10-31 细化）**：首条消息建会话 Redis 幂等键 TTL 60s；`requirement_changed` 由后端判定并在 done 事件返回；assistant 消息 agent_code 记最后输出者；截断摘要不落库；修复后复检一次质量审核；示例批次产出全部 6 张计划与文案、全套批次全量复用（仅剩生图→审核→规范→合成）；重生成/重试单张完全沿用原提示词、不新建批次，成功后 completed_count+1、可 partially_failed→completed。
- **文档**：12 份 PRD 存于 `docs/prd/`，命名 `数字-中文名prd.md`；例外：1 号 PRD 及其实现文档已移入 `docs/prd/1-登录界面/`（2026-10-31 用户确认）；新增后台模块按业务域并入现有文档。
- **术语表**：仓库根目录 `GLOSSARY.md` 是唯一来源；`AGENTS.md` 的「Domain glossary」小节是同步镜像。新增或修改术语时，先改 `GLOSSARY.md`，再同步 `AGENTS.md`。
- **本地评审记录**：`docs/reviews/` 已加入 `.gitignore`，不进入仓库与 `main`。

## 登录最小 demo（2026-10-31 用户确认）

- **文档组织**：1 号 PRD 及其实现文档统一放在 `docs/prd/1-登录界面/`，含 PRD 本体、`README.md`、`issues/`、接口文档；`docs/prd/` 顶层不再保留 `1-登录界面prd.md`。
- **引用路径**：其他文档引用该 PRD 时使用 `1-登录界面/1-登录界面prd.md`。
- **任务范围**：最小 demo 只做 6 个垂直切片——骨架+种子账号、登录闭环、登录态+守卫、角色分流、状态失效、退出+审计。
- **最小化取舍**：不接 Redis（鉴权直查 PostgreSQL）、不接 Alembic（建表+幂等种子）、只建 `users`/`roles`/`permissions`/`user_roles`/`role_permissions`/`audit_logs` 六张表、不预置超管、不做管理后台页面；仅实现 3 个 auth 接口。
- **演示账号**：`demo_user`（user）、`demo_admin`（admin）、`demo_dual`（user+admin），密码统一 `Demo1234`，仅本地 demo 使用。
- **待统一项**：接口文档中的 4 个待确认项（禁用账号响应码、审计动作码、`/auth/me` 结构、`remember_me` 必填性）需在正式实现前与 8/9 号文档统一。

## 2026-10-31 PRD 评审待裁决项（已全部随 P0 修复落地，见会话 3）

- 模板图片角色作用范围 → P0-2：整套模板，定义 1 主图 + 5 详情图视觉体系，不携带图片角色与尺寸。
- 尺寸模型 → P0-3：新增 `size_presets` 表；主图与详情图共用同一宽高。
- 商品名称与聊天先后 → 商品名称必填且由用户手填，Agent 不回填（2 号文档 4.2）。
- 平台规范检查时机 → 生图后、文字合成前（8 Agent 全链路顺序）。
- 数据库记录保留 → 永久保留，图片原件 5 年后转 `archive/`。
- 视觉模型配置 / 提示词版本 / 文字合成产物 → P0-5 `vision_model` 入模型配置；`prompt_versions` 已建表；合成产物即最终生成图。

## 创作工作台最小 demo（2026-10-31 用户确认）

- **文档组织**：2 号 PRD 及其实现文档统一放在 `docs/prd/2-用户端创作工作台/`，含 PRD 本体、`README.md`、`issues/`、接口文档；`docs/prd/` 顶层不再保留 `2-用户端创作工作台prd.md`。
- **引用路径**：其他文档引用该 PRD 时使用 `2-用户端创作工作台/2-用户端创作工作台prd.md`。
- **任务范围**：最小 demo 只做 7 个垂直切片——骨架+最小数据表、参数面板+商品名称校验、商品图上传+恢复、会话列表+聊天轻链路、示例图+阶段进度、确认全套+结果网格、结果预览+单张下载。
- **阻塞关系**：01 → 02 → {03, 04}；03 → 05 → 06 → 07；04 与 05 并行且不阻塞。01 依赖 1 号登录 demo 的 01~03。
- **最小化取舍**：
  - 后端用 FastAPI `BackgroundTasks` 跑 demo 管线，不接 Celery/Redis。
  - 图片用本地存储适配器 + 占位 PNG，不接 MinIO。
  - 无文本模型时聊天走桩；演示管线固定 6 个阶段。
  - 尺寸固定 1000×1000，不做尺寸预设与自定义尺寸。
  - 不做模板、取消、单张重生成/重试、ZIP 整组下载。
  - 不做历史作品、个人中心、管理后台真实页面；不做内容审核、Token 统计、审计。
  - 参数与上传图 ID 仅存 localStorage：草稿键 `esimage_workspace_params_draft` / `esimage_workspace_upload_ids_draft`，会话键 `esimage_workspace_params_{session_id}` / `esimage_workspace_upload_ids_{session_id}`。
- **演示账号**：`demo_user` / `Demo1234`，权限 `user.workspace`、`user.generate`、`user.history`；`demo_admin` 访问用户端接口返回 403 `20005`。
- **接口约定**：
  - 会话列表 `GET /sessions` 增加 `last_message_preview`、`latest_batch_id`。
  - 创建示例批次响应增加 `session_id`、`session_title`，允许 `session_id` 为空时后端建会话。
  - 新增 `GET /images/{image_id}/content` 用于预览；下载接口仅正式图可用，示例图返回 409 `30005`。
  - 新增 `GET /uploads/{id}/content`、`GET /uploads/{id}/thumbnail` 用于恢复。
  - 聊天请求 `params` 只含参数，不含 `upload_ids`。
- **待统一项**：接口文档中列出的待确认项（草稿键命名、预览接口、上传内容接口、`latest_batch_id`、预览权限、最近可确认示例的维度、聊天桩行为）需在正式实现前与 3/4/9/10 号文档统一。

## Agent 会话交互最小 demo（2026-10-31 用户确认）

- **文档组织**：3 号 PRD 及其实现文档统一放在 `docs/prd/3-Agent会话交互/`，含 PRD 本体、`README.md`、`issues/`、接口文档；`docs/prd/` 顶层不再保留 `3-Agent会话交互prd.md`。
- **引用路径**：其他文档引用该 PRD 时使用 `3-Agent会话交互/3-Agent会话交互prd.md`；同目录文档用相对文件名。
- **定位**：只做 2 号 demo 04 的增量，不重复会话列表、首条消息建会话、SSE 骨架、自动命名、幂等与断线重试。
- **任务范围**：最小 demo 只做 4 个垂直切片——重命名/软删除/切换、消息展示/状态/输入规则、轻链路/上下文/调用明细、需求变化提示与生图衔接（2026-10-31 用户确认保持 4 个，不合并、不拆分、不砍 04）。
- **阻塞关系**：2 号 demo 04 → {01, 02, 03}；03 + 2 号 demo 06 → 04。
- **最小化取舍**：
  - 进程内锁 + 数据库唯一约束替代 Redis 幂等键。
  - 未配置 `text_model` 时使用确定性演示桩；事件与落库结构不变。
  - 只做 10 轮截断，不做 Token 上限二次压缩。
  - 不做内容审核、真实 Token 计费、消息后端取消状态、管理端聊天页与 `agent_runs` 查询接口。
  - 需求变化只比对风格、卖点、尺寸三类字段。
- **接口增量**：
  - 新增 `PATCH /sessions/{id}`、`DELETE /sessions/{id}`。
  - 聊天 SSE `meta` 增加 `duplicate`（demo 约定），`done` 增加 `requirement_changed`。
  - 已隐藏会话统一 404 `30013`；重复删除由前端按成功处理。
  - 消息分页查询时惰性将超过 120 秒的 `sending` Agent 消息标记为 `failed`。
- **待统一项**：重复消息在 SSE 下的重放形式、已隐藏会话的 PATCH/DELETE 语义、需求变化比对字段、已确认示例图描述来源、消息超时阈值、系统通知写入方、消息中止状态、`requirement_summary` 合并规则，需在正式实现前与 3/4/8/9/10 号文档统一。
