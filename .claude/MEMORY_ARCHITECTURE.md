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
- **会话与生图链路（2026-10-31 细化）**：首条消息建会话 Redis 幂等键 TTL 60s；`requirement_changed` 由后端判定并在 done 事件返回；assistant 消息 agent_code 记最后输出者；截断摘要不落库；修复后复检一次质量审核；示例批次产出全部 6 张计划与文案、全套批次全量复用（仅剩生图→审核→规范→合成）；重生成/重试单张完全沿用原提示词、不新建批次，成功后 completed_count+1（仅替换失败图时，重生成成功张不变）、可 partially_failed→completed。
- **接口与后端（2026-10-31 细化）**：SQLAlchemy 2.0 同步会话（FastAPI 线程池 + Celery 共用）；缩略图预签名 URL ≤5 分钟、原件鉴权流式；403 统一清 token 跳登录（20004/20005 不区分，/403 页保留不用）；批次 images 只返回当前有效（superseded 不返回）；input_full/output_full 存储前脱敏；pg_trgm 本期不启用；生成图缩略图 Worker 生成时同步生成；头像本期不做（字段/前缀预留）；retry_count=HTTP 瞬态重试、10 次指数退避为业务层；concurrency=豆包侧并发、WORKER_CONCURRENCY=worker 并发。
- **部署运维（2026-10-31 细化）**：应用侧 TimedRotatingFileHandler 按天轮转 90 天压缩；备份宿主机 cron（02:00/02:30）；仓库交付 .env.example；日志 JSON 结构化。
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

## 历史作品最小 demo（2026-10-31 用户确认）

- **文档组织**：5 号 PRD 及其实现文档统一放在 `docs/prd/5-历史作品/`，含 PRD 本体、`README.md`、`issues/`、接口文档；`docs/prd/` 顶层不再保留 `5-历史作品prd.md`。
- **引用路径**：其他文档引用该 PRD 时使用 `5-历史作品/5-历史作品prd.md`；同目录文档用相对文件名。
- **任务范围**：最小 demo 只做 5 个垂直切片——历史列表与分页、批次详情与网格、大图预览与单张下载、整组 ZIP 与 manifest、归档读取与降级。
- **阻塞关系**：1 号 demo 01~03 + 2 号 demo 06/07 → 01 → 02 → {03, 04} → 05；03 与 04 可并行，05 需两条读取路径都完成。
- **最小化取舍**：
  - 列表固定每页 20，只接受 `page`，不开放 `page_size`。
  - 不做每日归档调度与 5 年扫描；用种子模拟 `archived_at` 与 `archive/` 前缀，只验证归档后读取。
  - 部分失败批次由种子夹具提供（2 号演示管线只产出 `completed`）。
  - 归档慢读用前端 300ms 耗时判定，不新增 `archived` 字段。
  - 不做搜索、筛选、收藏、分享、删除、补生成、管理后台内容追溯、移动端。
- **权限共识**：历史列表/详情/单张下载/整组 ZIP 用 `user.history`；`/images/{id}/content` 与新增 `/images/{id}/thumbnail` 放宽为 `user.history` 或 `user.generate`，不破坏 2 号 demo 已有调用。历史接口访问他人批次按 5 号返回 403 `20005`。
- **接口增量**：
  - 新增 `GET /history`、`GET /history/{batch_id}`、`GET /images/{image_id}/thumbnail`。
  - 复用 2 号 demo 的 `GET /images/{image_id}/content` 与 `GET /images/{image_id}/download`。
  - 新增 `GET /batches/{batch_id}/download`，与 4 号 demo 08 共用同一契约与实现。
- **文件规则**：单张与 ZIP 内图片命名 `{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`，非法字符替换为下划线，时间戳取图片 `created_at`；ZIP 名取批次 `created_at`；`manifest.csv` 用 UTF-8 BOM、中文表头、`success`/`failed`，每个序号取 `attempt_no` 最大且非 `superseded` 的记录。
- **归档**：`archived_at` 非空读取 `archive/{file_path}`；缩略图始终热存；超时 `ARCHIVE_READ_TIMEOUT_SECONDS` 默认 60 秒；任一文件不可用返回 30014，ZIP 不返回残缺包。
- **待统一项**：预览权限与 2/9 号统一、缩略图接口写入 9 号、越权 403/404 全站口径、历史分页是否开放 `page_size`、归档慢读字段、归档不可用时 ZIP 行为、manifest 细节与 4 号 08 统一、封面顺延规则、文件名时间戳取用、部分失败夹具来源。

## 生图任务与结果最小 demo（2026-10-31 用户确认）

- **文档组织**：4 号 PRD 及实现文档统一放在 `docs/prd/4-生图任务与结果/`，含 PRD 本体、`README.md`、`issues/`、接口文档；`docs/prd/` 顶层不再保留 `4-生图任务与结果prd.md`。
- **引用路径**：其他文档引用该 PRD 时使用 `4-生图任务与结果/4-生图任务与结果prd.md`；文件夹内文档用 `../` 前缀。
- **定位**：本 demo 升级 2 号 demo 的占位管线（占位 PNG + 桩 Agent → 真实 8 Agent + 真实豆包 + 文字合成），**不改变 2 号 demo 的对外接口**，仅新增接口。
- **任务范围**：8 个垂直切片——01 数据模型与 Agent 运行时、02 文字留白合成、03 示例批次真实全链路、04 确认全套与详情图、05 失败重试与降级、06 取消、07 单张重试/重生成、08 整组 ZIP。
- **阻塞关系**：2 号 demo 01 → 01 → 02 → 03（另需 2 号 demo 05）→ 04（另需 2 号 demo 06）→ {05→07, 05→08, 06}；06 与 05 并行。
- **用户取舍**：
  - 只走真实豆包，不做演示桩；仅审核生成图（用户上传图不审核）。
  - 四项恢复能力全做：失败重试、取消、单张重试/重生成、整组 ZIP。
  - 生成配置只做读取与种子（模板、尺寸预设），不做后台 CRUD。
  - 不接 Celery/Redis/MinIO，用 FastAPI `BackgroundTasks` + 本地存储；单实例。
- **demo 约定（接口文档固化）**：
  - API Key 走环境变量 `DOUBAO_API_KEY`，启动校验缺失即 fail-fast。
  - 配置读取缓存 60 秒；尺寸校验 512~2048 且为 8 的倍数。
  - `completed_count` 每次图片状态变化后按成功张数重算。
  - 跳过的 Agent 在 `agent_runs` 写 `skipped` 标记。
  - ZIP 内 `manifest.csv` 用 UTF-8 带 BOM；批次超时可配置（默认 1800 秒）。
  - 故障注入开关仅测试环境可用。
- **待统一项**：README 与接口文档列出的 12 项（API Key 存放、skipped 标记、可重生成状态、`completed_count` 口径、配置接口、`template_id`、尺寸范围、幂等、批次超时、CSV 编码、审核模型、字体授权）需在正式实现前与 4/9/10 号文档统一。

## 管理后台-账号与权限最小 demo（2026-10-31 用户确认）

- **文档组织**：6 号 PRD 及其实现文档统一放在 `docs/prd/6-管理后台-账号与权限/`，含 PRD 本体、`README.md`、`issues/`（01~08）、`接口文档-账号与权限最小demo.md`；`docs/prd/` 顶层不再保留该 PRD。
- **引用路径**：0/7/10 号顶层文档用 `6-管理后台-账号与权限/6-管理后台-账号与权限prd.md`；1 号文件夹内文档用 `../6-管理后台-账号与权限/6-管理后台-账号与权限prd.md`。
- **任务范围**：8 个垂直切片——骨架+权限种子+用户列表、新建、编辑边界、禁用/启用/软删除/恢复、重置密码、用户详情、角色权限、操作日志。
- **依赖**：1 号 demo 01~03 → 01 → 02 → 03 → {04, 05, 06}；01 → 07；02 → 08。
- **最小化取舍**：不接 Redis（权限每请求直查 PostgreSQL）、不接 Alembic（建表+幂等种子）；用户统计返回 `0` 且 `stats_available=false`；内容追溯入口按钮禁用占位；其他管理模块与其日志不做；个人中心改密不做；角色权限 LWW。
- **演示账号**：新增 `demo_super`（`super_admin`），与 `demo_admin`、`demo_user`、`demo_dual` 密码统一 `Demo1234`，仅本地 demo 使用。
- **权限模型**：`super_admin` 不写 `role_permissions`，按角色即时授予全部 23 个权限码；其他角色取 `role_permissions` 并集；权限判定顺序为 签名/过期 → 账号状态 → `token_version` → 权限码。
- **错误码约定**：demo 新增 `30017` 用户不存在、`30018` 账号状态不允许、`30019` 日志不存在；管理员分配超管暂用 `20005`；最低权限校验暂用 `30015`。
- **审计动作码**：`account.create` / `account.update` / `account.reset_password` / `account.disable` / `account.enable` / `account.delete` / `account.restore` / `role.update`，复用 1 号 demo 的 `auth.*`。
- **待统一项**：README 与接口文档列出的 8 项（新错误码、分配超管码、最低权限码、审计动作码、统计口径、超管权限存储、操作响应结构、正式环境首个超管创建方式）需在正式实现前与 9/10 号文档统一。

## 管理后台-用户与生图记录最小 demo（2026-10-31 用户确认）

- **文档组织**：7 号 PRD 及其实现文档统一放在 `docs/prd/7-管理后台-用户与生图记录/`，含 PRD 本体、`README.md`、`issues/`（01~06）、`接口文档-用户与生图记录最小demo.md`；`docs/prd/` 顶层不再保留该 PRD。
- **引用路径**：0/8/10 号顶层文档用 `7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md`；4/6 号文件夹内文档用 `../7-管理后台-用户与生图记录/7-管理后台-用户与生图记录prd.md`。
- **任务范围**：6 个垂直切片——概览四卡与演示种子、Token 统计、用户层与会话层、批次层与图片网格、单图详情与媒体访问、用户详情真实统计与内容入口。
- **依赖**：6 号 demo 01 + 4 号 demo 01 → 01；01 → 02；01 → 03 → 04 → 05；03 + 6 号 demo 06 + 4 号 demo 01 → 06；05 与 06 互不依赖。
- **最小化取舍**：不接 Redis（概览用进程内 60 秒 TTL、权限每请求直查 PostgreSQL）、不接 MinIO（本地存储适配层 + 鉴权媒体接口）、不接 Celery/Alembic；种子模拟归档、部分失败与替代图；不调用豆包；不做数据导出。
- **权限与边界**：复用 6 号 23 个权限点，不新增；管理员看不到超管用户及其会话/批次/图片，直接访问返回 403 `20006`；普通用户访问管理接口 403 `20005`；超管可看全部。
- **统计口径**：概览四卡分别聚合；Token 只计 `success` 与有 Token 的 `failed`，`skipped` 不计；用户归属优先 `session.user_id` 再 `batch.user_id`；用户详情四项统计用真实聚合，`stats_available=true`，字段结构不变。
- **内容口径**：用户列表只含有批次的用户；会话含 `active`/`hidden`；批次图片构成按计划 1 主图 + (`total_count-1`) 详情图；图片网格默认每个序号最新尝试，`include_superseded=true` 可看全部；归档图缩略图热存、原件读 `archive/`。
- **接口增量**：新增 `/admin/content/images/{id}/thumbnail` 与 `/content`（9 号只有 `/download`）；新增错误码 `30024`（图片不存在，避开 8 号 `30020`~`30023`）；日期参数用 `start_date`/`end_date`；Token 明细固定每页 20；用户统计接口复用 6 号结构。
- **不做**：数据导出与导出审计、图表/排行、后台删除/重生成/改提示词、直连 SQL、聊天记录页（只跳转）、移动端。
- **待统一项**：README §6 与接口文档 §16 列出的 15/16 项，重点为导出延期、媒体接口与 30024、日期参数命名、内容可见性、`superseded` 默认口径、`failed_task_count` 口径、统计与 Token 归属。

## 管理后台-聊天记录最小 demo（2026-10-31 用户确认）

- **文档组织**：8 号 PRD 及其实现文档统一放在 `docs/prd/8-管理后台-聊天记录/`，含 PRD 本体、`README.md`、`issues/`（01~06）、`接口文档-聊天记录最小demo.md`；`docs/prd/` 顶层不再保留该 PRD。
- **引用路径**：0/7 号顶层文档用 `8-管理后台-聊天记录/8-管理后台-聊天记录prd.md`；文件夹内文档用相对文件名。
- **任务范围**：6 个垂直切片——01 后台骨架+种子夹具+聊天列表、02 会话详情/消息流/定位、03 Agent 调用明细、04 消息搜索、05 模型配置、06 系统提示词。
- **依赖**：1 号 demo 01~03 + 6 号 demo 01 → 01；01 → 02 → {03, 04}；01 → {05, 06}。03/04 可并行，05/06 可并行。
- **最小化取舍**：不接 Redis/Alembic/Celery/MinIO；4 张内容表 `CREATE TABLE IF NOT EXISTS` + 幂等种子；搜索用 `ILIKE` 不建索引；消息用 `before_id`/`around_id` 游标，默认 20、最大 50；「查看批次」用只读摘要抽屉代替 7 号生图详情；模型配置每次读 DB；提示词行锁 + LWW；不做归档、导出、diff、连通性测试、移动端。
- **演示数据**：`demo_user` 3 个会话（1 hidden）、`demo_super` 1 个会话；含 success/failed/skipped 调用、关联批次、可搜索关键词；模型配置 1 条默认启用；8 个 Agent 提示词与版本 1。
- **可见范围**：管理员排除 `super_admin` 账号的会话与 Agent 调用；超管看全部；管理员访问超管内容统一 403 `20005`；`full=true` 仅超管；模型配置仅超管；提示词管理员/超管均可。
- **模型配置加密**：AES-256-GCM，密钥来自 `MODEL_CONFIG_ENCRYPTION_KEY`（base64 32 字节），启动缺失即失败；存储 `base64(nonce+ciphertext+tag)`；页面只显示 `sk-****abcd` 形式脱敏值；审计只记变更字段。
- **提示词版本**：保存生成 `current_version+1` 并设为当前；回滚复制旧版本内容生成新版本，不删除历史；未知变量原样保留并告警；建议变量未引用告警但允许保存；不做 diff。
- **错误码约定**：demo 新增 `30020` Agent 调用不存在、`30021` 提示词不存在、`30022` 提示词版本不存在、`30023` 消息不存在；管理员越权统一 `20005`；不新增 `20006` 用法。
- **审计动作码**：`model_config.update`、`prompt.update`、`prompt.rollback`；需与 9/10 号统一，并同步 6 号操作日志页动作筛选。
- **待统一项**：README 与接口文档列出的 13~14 项（新错误码、管理员访问超管内容码、`full=true` 处理、消息-批次关联字段、批次跳转形态、消息游标、搜索分页/摘要、密钥环境变量与 4 号 `DOUBAO_API_KEY` 优先级、提示词并发/回滚当前版本、提示词超管隔离、已删除用户会话、审计动作码、种子表与真实表、Token 口径）需在正式实现前与 7/9/10/11 号文档统一。

## 后端服务与接口最小 demo（2026-10-31 用户确认）

- **文档组织**：9 号 PRD 及其实现文档统一放在 `docs/prd/9-后端服务与接口/`，含 PRD 本体、`README.md`、`issues/`（01~08）、`接口文档-后端服务与接口最小demo.md`；`docs/prd/` 顶层不再保留该 PRD。
- **引用路径**：0/10/11 号顶层文档用 `9-后端服务与接口/9-后端服务与接口prd.md`；文件夹内文档用 `./` 或相对文件名。
- **最小 demo 定位**：通用契约基线。只做 9 号独有的跨切面规则，业务接口沿用 1~6 号 demo，不新增业务接口；用既有接口作为契约载体。
- **任务范围**：8 个切片——01 统一响应/错误码/参数校验/分页；02 JWT 鉴权与账号状态；03 权限点与越权；04 上传契约；05 下载契约；06 SSE 协议；07 幂等与并发；08 OpenAPI 与契约回归。
- **依赖**：1 号 demo 01~03 → 01 → 02 → 03 → {04,05,06,07}；08 依赖 01~07。04 另依赖 2 号 demo 03；05 另依赖 5 号 demo 03~04；06 另依赖 2 号 demo 04 + 3 号 demo 03；07 另依赖 2 号 demo 04~05。
- **最小化取舍**：不接 Redis/Alembic/Celery/MinIO；配置缓存不做；预签名用本地 HMAC 适配器模拟；Nginx 与生产 OpenAPI 内网限制留给 11 号；导出/归档/限流不做。
- **契约口径**：统一响应 `{code,message,data}`；分页 `{items,total,page,page_size}`，`page_size` 1~100；鉴权顺序采用 6 号 demo 的「账号状态先于 `token_version`」并记录与 9 号 §2.2 的差异；权限码来自 `permissions`，超管全量；上传 `30006`、下载归档 `30014`、生成并发 `30003`。
- **待统一项**：README §6 的 16 项（6 号 8 项 + 鉴权顺序、SSE 重复消息、预览接口、缩略图访问、分页非法值、预签名细节、导出、单张下载权限码），只记录不裁决。
## 登录最小 demo 后端实现约定（2026-10-31 用户确认）

- **分支策略**：多模块目录骨架先提交并推送 `main`；业务代码提交到 `feat/login-minimal-demo`，验证后合并 `main`。
- **目录结构**：`backend/app/core/` 放配置、数据库、安全、统一响应、审计、鉴权依赖；`backend/app/models/` 放共享 ORM；`backend/app/modules/auth/` 放登录路由、请求模型、种子；`backend/scripts/` 放建表与种子 CLI；`backend/tests/` 放用例。各模块独立，路由不直接依赖其他模块内部实现。
- **配置**：`core/config.py` 从 `backend/.env` 读取，`JWT_SECRET` 缺失即 `RuntimeError` 失败退出；`.env` 已在 `.gitignore`，只提交 `.env.example`。
- **本地数据库**：Docker Compose 起 `postgres:16-alpine`，容器 `esimage-postgres`，宿主机端口 `55433`（5432 被其他项目占用）；开发库 `esimage`，测试库 `esimage_test`。
- **响应与错误**：成功 `{code:0,message:"ok",data}`；参数错误 400（10001/10002/10003/10004）、凭据错误 401 `20001`、token 过期 401 `20002`、token 无效 401 `20003`、账号不可用 403 `20004`、无权限 403 `20005`、服务端 500 `50001`。
- **鉴权顺序**：签名/格式 → 过期 → 用户存在 → `token_version` → 账号状态；每请求查库取最新角色与权限（demo 不接 Redis）。
- **JWT**：HS256，载荷 `sub`（字符串）、`exp`、`iat`、`token_version`、`roles`、`permissions`；`remember_me` 决定 24h / 7d；无 refresh token。
- **审计**：登录成功/失败、退出均写 `audit_logs`，失败原因仅记 `bad_credentials`，不落密码；IP 取 `X-Forwarded-For` 首个地址或客户端地址。
- **测试隔离**：`tests/conftest.py` 在导入应用前把 `DATABASE_URL` 指向 `esimage_test`，建库后 `drop_all/create_all` + 种子，测试不污染开发库。

## 创作工作台后端最小 demo 实现约定（2026-10-31 用户确认）

- **分支策略**：功能分支 `feat/workspace-backend-demo`；先提交模块骨架并推送，再实现并合并 `main`。并行会话会推进 `main`，提交前先 fetch/rebase。
- **复用登录**：不重复实现 1 号 demo；直接使用 `core`、`models/user`、`models/audit`、`modules/auth`。仅扩展种子权限。
- **模块位置**：`backend/app/models/workspace.py` 放六张共享 ORM；`backend/app/modules/workspace/` 放 2 号 demo 全部接口与演示管线；路由在 `main.py` 以 `/api/v1` 挂载。
- **权限**：会话/消息用 `user.workspace`；上传/批次/预览用 `user.generate`；下载用 `user.history`；缺权限统一 403 `20005`。
- **数据表**：新增 `creative_sessions`、`chat_messages`、`agent_runs`、`generation_batches`、`generated_images`、`uploaded_assets`；不建 `templates` / `size_presets` / `material_assets`。
- **对象存储**：本地目录适配器 `STORAGE_ROOT`（默认 `backend/storage`）；上传原图 `uploads/`、生成图 `generated/`、缩略图 `thumbnails/`；路径做穿越校验；`backend/storage` 与测试存储目录已忽略。路径层级是 demo 简化，正式实现再补 session/batch 层级。
- **演示管线**：`BackgroundTasks` + 轮询；示例批次 `queued→running→sample_ready`，全套 `queued→running→completed`；阶段依次写入（含 `product_understanding` / `copywriter` / `prompt_builder`）；占位 PNG 由 Pillow 生成；`DEMO_PIPELINE_STAGE_DELAY` 控制停顿；`completed` 与 `is_history_visible` 同一事务提交。
- **上传图绑定**：未绑定会话的上传图首次生成时回填 `session_id`，按 `upload_ids` 顺序写 `sort_order`；已绑定其他会话的上传图返回 30006；单张 ≤10MB、解码后 ≤4000 万像素。
- **并发与幂等**：单实例用模块级 `threading.RLock` 串行化「聊天幂等、批次并发、上传数量、确认全套」的 check-then-act；数据库唯一索引兜底。同一用户 `queued/running` 最多 1 个；`sample_ready` 不占名额；确认时对示例批次 `SELECT ... FOR UPDATE`。
- **幂等键**：`client_message_id` / `client_request_id` 必须是 UUID；聊天按 `(session_id, client_message_id)`、无会话时按 `(user_id, client_message_id)` 去重；处理中返回 409/30005，已完成重放，失败可复用原用户消息重试。
- **尺寸边界**：演示管线按请求宽高创建位图，宽高上限 4096，超出返回 10004「宽高超出范围」。
- **额外接口**：实现 `GET /images/{id}/thumbnail`，因为批次响应里的 `thumbnail_url` 需要可读取；与 5 号文档约定一致，不影响 2 号已有接口。
- **本地数据库复用**：并行开发共用已运行的 `esimage-postgres`（55433）；本模块使用独立库 `esimage_workspace`、测试库 `esimage_workspace_test`，不覆盖其他项目的库。
- **curl 编码**：Windows Git Bash 下中文 JSON 不能直接放进 `-d`；统一用 Python 生成 UTF-8 文件 + `--data-binary @文件`。

## Agent 会话交互后端实现约定（2026-10-31 用户确认）

## 3 号 Agent 会话交互后端实现约定（2026-10-31）

- **模块位置**：3 号后端统一放在 `backend/app/modules/chat/`，不改动 `modules/auth/` 内部实现。
- **前置依赖**：3 号 demo 只做 2 号 demo 04 的增量；会话列表、首条消息建会话、SSE 骨架、自动命名、幂等由 2 号 `feat/workspace-backend-demo` 提供。
- **当前阻塞**：`main` 尚无 2 号 demo 04 的可运行代码（2 号 agent 的 `workspace/sessions.py` 等仍为同设备另一工作区的未提交改动）。用户选择「等 2 号合并后再做」，不复制、不触碰对方未提交代码。
- **合并节奏**：先提交并推送 `chat` 模块目录骨架到 `feat/agent-chat-backend-demo`，`--ff-only` 合并 `main`；业务代码待 2 号 04 合并 `main` 后再在功能分支开发并验证。
- **模型复用**：3 号不重复定义 `creative_sessions`/`chat_messages`/`agent_runs`/`generation_batches` 等表；开发时直接复用 2 号提供的 `app/models/workspace.py`，避免两套 ORM 导致建表冲突。
- **环境复用**：本地 PostgreSQL 复用并行 agent 已启动的 `esimage-postgres`（宿主端口 55433）；8000 端口被 1 号登录 demo 的 uvicorn 占用，3 号调试改用其他端口。
- **网络限制**：当前 `github.com:443` 连接超时，`git fetch/push` 失败；骨架提交已本地完成并合并 `main`，推送待网络恢复后补做。

## 10 号数据底座 demo 约定（文档提案，待用户确认）

- **迁移**：10 号 demo 必须使用 Alembic 并可正反向执行；与 2/4/6/8 号 demo 的建表脚本不同，因为「迁移可回滚」是 10 号核心验收项。
- **存储后端**：默认本地目录适配器模拟单桶 `esimage`，对象键与前缀与 MinIO 完全一致；正式实现切 MinIO 不改路径契约；不把存储根目录暴露为静态站点。
- **幂等**：不引入 Redis。消息用 `(session_id, client_message_id)` 部分唯一索引；首条消息并发建会话用数据库事务/咨询锁；批次用 `client_request_id` 部分唯一索引。
- **归档**：手动命令 + `--now` 注入时钟；`ARCHIVE_RETENTION_DAYS` 默认 1825；复制 → 校验大小 → 删除原件 → 回写 `archived_at`；缩略图不归档；单条失败不阻塞。
- **种子**：角色 3、权限 23、超管权限 23 行、尺寸 4、提示词 8 + 版本 8、模型配置 1；按唯一键判重，不覆盖已修改数据；首个超管必须显式环境变量。
- **数据边界**：所有外键 `RESTRICT`；业务数据不物理删除；`source_sample_batch_id` / `source_image_id` 暂按应用层校验，未加外键。
- **实现顺序**：01 身份/审计表 → 02 内容域表 → 03 配置域表与种子 → 04/05/06 三条数据链路 → 07 归档 → 08 回归；02 与 03 都新增迁移，必须顺序执行，避免两个 Alembic head。

## 11 号部署与运维最小 demo（2026-10-31 用户确认）

- **文档组织**：11 号 PRD 及其实现文档统一放在 `docs/prd/11-部署与运维/`，含 PRD 本体、`README.md`、`issues/`（01~08）、`接口文档-部署与运维最小demo.md`；`docs/prd/` 顶层不再保留该 PRD。
- **引用路径**：0 号索引与 9 号关联文档用 `11-部署与运维/11-部署与运维prd.md`；文件夹内文档用 `./` 或相对文件名；10 号接口文档用 `../11-部署与运维/11-部署与运维prd.md`。
- **最小 demo 定位**：部署运行壳，不是业务实现。交付 Compose 拓扑、依赖健康、迁移种子、应用镜像、双健康探针、网关、日志、备份恢复、Worker/Beat 基线与验收脚本；业务页面与接口由 1~10 号 demo 提供。
- **健康接口双路径**：`GET /api/health` 保持 11 号裸结构 `{status,checks}` 供容器/网关探活；`GET /api/v1/health` 返回 9 号统一响应 `{code,message,data}`。两者共用一次检测；降级统一 HTTP 503，`/api/v1/health` 用业务码 `50001`；该差异列入待确认。
- **任务范围**：8 个切片——01 Compose 基线与依赖服务；02 迁移/种子/初始超管；03 应用镜像与双健康探针；04 Nginx 网关与 SSE；05 结构化日志与 `request_id`；06 备份与恢复；07 Worker/Beat 基线；08 一键启动与验收。
- **依赖**：01 → 02 → 03 → {04,05,06,07}；08 依赖 04~07。06 只额外依赖 02/03；04~07 可并行。
- **最小化取舍**：只起 Worker/Beat，不注册归档/孤儿清理/导出清理等业务定时任务；审计业务写入、HTTPS/443、MinIO 控制台、Prometheus/Grafana、多机/灰度/容灾均不做；初始超管只校验创建与 bcrypt，登录闭环属 1 号 demo。
- **演示专用接口/任务**：`GET /api/v1/sessions/_probe/stream`（验证 Nginx 不缓冲）与 `ops.selftest`（验证 Worker 与 `request_id` 透传），仅 `APP_ENV != production` 启用，生产 404/不注册；是否长期保留待确认。
- **契约口径**：只有 nginx 暴露 80；`client_max_body_size 12m`；API 读超时 300s；SSE 关闭缓冲/缓存并清空 `Connection`；安全头使用 `always`；`X-Request-ID` 复用或生成 UUIDv4；日志 JSON 按天轮转 90 份压缩；备份保留 7 天。
- **待统一项**：README §6 与接口文档 §10 的 14 项，重点是双健康接口差异、健康接口鉴权、`X-Request-ID` 头名、失败值/超时、安全头取值、初始密码规则、演示专用接口、413 响应体、恢复覆盖语义、Nginx 日志轮转、MinIO 前缀、空调度、stdout 保留。

## 历史作品后端最小 demo 实现约定（2026-10-31）

- **目录与职责**：`backend/app/modules/history/` 放 `router.py`（列表/详情/ZIP）、`service.py`（可见性/分页/序列化）、`zip_export.py`（ZIP+manifest）、`seed.py`（夹具）；路由在 `main.py` 统一挂载，不修改 auth/workspace 路由结构。
- **复用而非重写**：单张预览与下载继续用 2 号 workspace 的 `/images/{id}/content`、`/download`；历史模块只补权限放宽、`full + final` 校验、归档读取与更严格文件名规则。ZIP 实现集中在 history `zip_export.build_batch_zip`，4 号 demo 08 接入时调用同一函数。
- **权限**：列表/详情/单张下载/整组 ZIP 用 `user.history`；预览与缩略图接受 `user.history` 或 `user.generate`。`app/core/deps.py` 提供 `require_permission` / `require_any_permission`，`workspace.service` 重新导出以兼容 2 号已有调用。
- **越权口径**：历史聚合接口按 5 号返回 403/20005；媒体接口仍按 2 号“不泄露存在性”返回 404/30014。该差异保留为待统一项。
- **归档**：`archived_at` 非空时原件路径为 `archive/{file_path}`，缩略图始终读热存 `thumbnail_path`；`ARCHIVE_READ_TIMEOUT_SECONDS` 默认 60；归档缺失/超时/存储异常统一 404/30014「文件归档中，请稍后重试」并写 `esimage.storage` 错误日志（image_id/batch_id/archive_path/reason）。
- **ZIP 契约**：仅 `full` 且 `completed`/`partially_failed`；按 `index_no` 1..total_count 取 `attempt_no` 最大、非 `superseded` 的记录；manifest UTF-8 BOM、中文表头、`success`/`failed`、失败原因；任一成功图不可读则整体失败，不返回残缺包；构建到 `SpooledTemporaryFile` 后分块流式输出。
- **文件名**：`{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`；商品名称非法字符、控制字符、结尾点/空格替换为下划线；时间戳取图片 `created_at`，ZIP 名取批次 `created_at`，均按 Asia/Shanghai。
- **种子口径**：demo_user 21 个历史可见批次（18 completed + 1 含 superseded + 1 归档 + 1 partial），另 1 个示例批次与 1 个失败批次不进历史；demo_dual 另有 1 个全套批次用于跨用户 403，不进入 demo_user 列表；重复执行按 `client_request_id=seed-history-*` 跳过。
- **查询与分页**：历史列表先用「可见图片按 batch 聚合」的子查询，子查询内同时按 `GeneratedImage.user_id` 与批次 user/type/status 过滤；先算 total，`offset >= total` 直接返回空 items，避免超大页码溢出 bigint。
- **命名与可见性单一来源**：`history.service` 提供 `HISTORY_BATCH_STATUSES`、`visible_image_filters`、`is_visible_image`；`zip_export` 复用，不再各自维护。单张下载与 ZIP 图片名共用 `workspace.service.image_download_filename`。
- **归档超时**：线程池读取必须 `shutdown(wait=False, cancel_futures=True)`，不能用 `with ThreadPoolExecutor`（退出会等待线程导致超时失效）；已补 0.1 秒慢读用例。
- **种子自愈**：种子启动时校验批次图片记录与 file/thumbnail 文件（归档件校验 `archive/` 路径），缺失则删除 `seed-history-*` 批次并重建，避免数据库保留而存储丢失时整页 404。
- **日志命名**：归档/热存储读取错误使用 `esimage.storage` logger，包含 image_id/batch_id/path/reason，不含 token。
- **待用户/跨模块确认**：
  1. 种子计数与文档“21 个 completed + 1 partial”不一致，当前以接口验收 `total=21` 为准。
  2. manifest 的「宽度/高度」分列与 4 号「尺寸」单列冲突，需与 4 号 demo 08 统一。
  3. 示例图下载 409 文案沿用 2 号「示例图确认前不可下载」，5 号 §8.4 写「当前图片不可下载」；为保护 2 号已有调用暂未改。
  4. 归档读取与文件名工具暂放 `workspace/service.py`（history 反向 import）；权限依赖已上移 `app/core/deps.py`。若后续 chat/generation 也复用归档工具，需确认是否再上移。
  5. `GET /batches/{batch_id}/download` 在 4 号生成模块中也会出现；合并分支时需改为只保留一份实现，避免 FastAPI 重复路由。
## 3 号 Agent 会话交互后端最终实现（2026-10-31）

- **模块位置**：3 号后端统一放在 `backend/app/modules/chat/`，不改动 `modules/auth/` 内部实现；会话/消息/AgentRun 表复用 2 号 `app/models/workspace.py`，不重复建表。
- **复用 2 号基线**：会话列表、首条消息建会话、SSE 骨架、自动命名、幂等由 2 号 demo 04 提供；3 号增加重命名、软删除、惰性超时、`meta.duplicate`、`done.requirement_changed`、10 轮上下文、上传图校验与 `agent_runs` 明细。
- **合并节奏**：骨架先提交并推送 `feat/agent-chat-backend-demo`，`--ff-only` 合并 `main`；业务代码在功能分支开发，验证后再合并。2 号 demo 04 合并 main 后才开始 3 号实现。
- **真实模型**：
  - 文本模型走火山方舟 OpenAI 兼容接口：`ARK_API_KEY`、`ARK_BASE_URL` 默认 `https://ark.cn-beijing.volces.com/api/v3`、`ARK_TEXT_MODEL` 默认 `doubao-seed-character-260628`。
  - 规划 Agent 非流式、商品理解 Agent 流式；流式正文结束后用 `<<<SUMMARY>>>` 哨兵 + 摘要 JSON，哨兵与 JSON 不下发前端。
  - Token 取接口 usage；助手消息与 done 事件记两个 Agent 合计；`agent_runs` 分 Agent 记 Token、模型名、耗时。
  - `ARK_API_KEY` 为空或 `CHAT_USE_STUB=true` 时使用确定性演示桩，Token 记 0；测试由 `tests/conftest.py` 强制 `CHAT_USE_STUB=1`。
  - 生图模型 `doubao-seedream-5-0-pro-260628` 与生文共用同一 Key，但属于 4 号 PRD，3 号不调用。
- **调用时序**：模型调用放在 SSE 流内、`workspace_lock` 之外；`meta → planner started/finished → product started → delta → finished → done` 与实际调用一致；15 秒心跳由 `stream.py` 包装。
- **边界修复（代码审查后）**：失败重试刷新 `created_at`，避免被超时规则立即标记；按“下一条用户消息”定位回复，避免重试覆盖后一条消息；首条消息去重只查 active 会话；重放 done 返回该条回复保存时的摘要；测试库改用 `esimage_chat_test` 隔离并行 agent。
- **环境**：复用 `esimage-postgres`（55433）；8000 被 1 号登录 demo 占用，3 号联调用 8001；chrome-devtools MCP 已用于 Swagger UI 验证。
- **实现状态**：业务代码提交 `6e0c96c`，rebase 到 `4ea5d64` 后推送 `feat/agent-chat-backend-demo` 并 `--ff-only` 合并 `main`；全量 `pytest` **85 passed**；真实豆包联调通过。
- **已知 demo 边界**：参数校验先于幂等重放（已删除上传图的极端重试会返回 30006）；真实模型措辞需联调抽检；接口不返回 usage 时 Token 记 0。

## 8 号管理后台-聊天记录（2026-10-31 用户确认）

- **模块边界**：聊天记录独立到 `backend/app/modules/admin/chat_records/`；模型配置与系统提示词继续留在 `admin/prompts/`（均属「Agent 配置」）。聊天接口从 `admin/content/router.py` 迁出，URL 不变，7 号内容追溯不受影响。
- **路由前缀（合并后最终口径）**：`admin/router.py` 使用 `APIRouter()`；`dashboard` / `tokens` / `content` 子路由自带 `/admin` 前缀；`accounts`、`assets`、`prompts`、`audit`、`chat_records` 在 `include_router` 时加 `prefix="/admin"`。禁止在汇总层再加 `prefix`，否则会出现 `/admin/admin`。导入必须显式写 `from app.modules.admin.xxx.router import router`。
- **重复实现处理**：并行 agent 曾把旧聊天实现放在 `content/chat_router.py` 并与 `chat_records` 同时挂载；合并后只挂载 `chat_records`，旧文件保留但不注册，避免同一路径被先注册的旧实现覆盖。
- **加密密钥**：`MODEL_CONFIG_ENCRYPTION_KEY` 为 base64 编码的 32 字节；与 11 号部署模板的 `ENCRYPTION_KEY` 双名兼容（优先前者、回退后者）；两者都缺失或长度不符时应用启动失败。测试与 `.env.example` 使用固定演示密钥；生产必须替换。
- **模型配置**：AES-256-GCM，存储 `base64(12 字节 nonce + ciphertext + tag)`；只返回 `sk-****abcd` 脱敏值；省略/空 `api_key` 表示不修改；审计只记录 `changed_fields` 与 `api_key_changed`。
- **聊天可见范围**：管理员在接口层排除拥有 `super_admin` 角色的账号；越权统一 403 `20005`（不用 `20006`）；聊天记录任何角色只读，不提供发送/编辑/删除/导出/恢复入口。
- **游标与搜索**：消息窗口用 `id` 游标（默认 20、最大 50），`before_id` 与 `around_id` 互斥；`around_id` 取锚点前 `floor((limit-1)/2)` 条、后 `limit-1-已取` 条，不向另一侧扩张。搜索用 `ILIKE` + 通配符转义，固定每页 20，摘要约 120 字符纯文本。
- **提示词版本**：保存 `current_version+1` 并设为当前；回滚复制目标版本内容再生成新版本，不删除历史；行锁 + 后保存者覆盖；变量语法 `{{变量名}}`，允许两侧空格，区分大小写。
- **种子**：以 `(user_id, title)` 识别会话，已存在则跳过其子数据；8 Agent 种子补版本 1；默认模型配置 1 条；`demo_super` 为演示超管。
- **环境复用**：复用 `esimage-postgres`（55433）；8000 被 DynamoDB Local 占用，本模块联调使用 8010。共享库存在同名旧会话时，种子按约定跳过，不覆盖他人数据。
## 管理后台-账号与权限后端实现约定（2026-10-31 用户确认）

- **模块位置**：账号与角色放 `backend/app/modules/admin/accounts/`，操作日志放 `backend/app/modules/admin/audit/`；复用已有骨架，不新增顶层模块。
- **路由前缀**：汇总路由 `backend/app/modules/admin/router.py` 使用 `APIRouter(prefix="/admin")`，`main.py` 挂 `/api/v1`；子模块 `__init__.py` 为空，必须从 `xxx.router` 导入 router 对象。
- **种子**：`modules/auth/seed.py` 是 23 个权限点的唯一来源；`user` 4 个、`admin` 13 个、`super_admin` 不写 `role_permissions`；新增 `demo_super`。重复执行不覆盖已有数据。
- **鉴权**：`core/deps.py` 中超管按角色即时授予全部权限码；校验顺序为签名 → 过期 → 用户存在 → 账号状态（20004）→ `token_version`（20003）→ 权限码（20005）。
- **统计口径**：内容表已接入，用户统计返回真实值且 `stats_available=true`（用户选择，覆盖 6 号 demo 文档的 0/false 初值）。
- **权限目录**：名称、类型、分组按 6 号接口文档；`group_name` 只有「用户端 / 管理后台」，角色管理页平铺展示。
- **操作日志双兼容**：请求同时接受文档参数与前端旧参数；响应同时返回文档字段与旧字段，避免破坏已合并的前端。
- **审计**：账号写操作必须带 `target_type=account`/`target_id=用户名`；角色权限带 `role`/角色 code；编辑记录 before/after；失败操作独立事务写 `result=failed` 与 `detail.reason`；不记录密码。
- **本地环境**：复用并行 agent 的 `esimage-postgres`（55433）；本模块使用 `esimage_admin` 开发库、`esimage_admin_test` 测试库；8001 被 3 号占用，6 号 curl 用 8016。
- **分支**：`feat/admin-accounts-backend-demo`；骨架先推送并 `--ff-only` 合并 `main`，业务代码验证后再合并。
- **编辑边界按值判断**：前端编辑弹窗总是提交 `display_name/roles/status`；后端只在角色集合或状态值真正变化时触发 20007/20005，避免「原样提交」被误拦。
- **已删除账号**：`PATCH /admin/users/{id}` 一律 409 `30018`，必须走 restore；禁止出现 `status=active` 但 `deleted_at` 非空的中间态。
- **统计查询**：列表按当前页 user_id 批量聚合（4 条 SQL），详情复用同一函数；Token 归属优先 `session.user_id`，其次 `batch.user_id`。
- **种子收敛**：权限点/角色名称、类型、分组、`is_super_only` 属于系统目录，重跑种子会更新；密码与 `role_permissions` 仍不覆盖。
- **失败审计**：404 与账号/角色业务失败都写 `result=failed` + `detail.reason`；`require_permission` 的 20005 不另加未定义动作码，避免超出文档动作清单。
- **无请求体**：新建/编辑/重置密码无 body 时返回 10002，而不是框架 422。
- **冒烟脚本**：`curl_admin_smoke.sh` 自带建表与幂等种子，新环境可直接运行。
- **路由前缀（合并后最终口径）**：`admin/router.py` 使用 `APIRouter()`；`dashboard` / `tokens` / `content` 子路由自带 `/admin` 前缀，其余（accounts、assets、prompts、audit、chat_content、chat_records）在 `include_router` 时加 `prefix="/admin"`。禁止在汇总层再加 `prefix`，否则出现 `/admin/admin`。
- **统计复用**：用户列表/详情统一调用 `modules/admin/accounts/service.py::build_user_stats`（批量聚合，Token 口径 success + 有 Token 的 failed），不再在 router 内联聚合。
- **9 号契约**：`modules/contract/openapi.py::PERMISSION_MAP` 的管理端路径必须与 `/api/v1/admin/*` 一致；`demo_super` 统一密码 `Demo1234`。
- **测试库**：本模块用 `TEST_DB_NAME=esimage_admin_test`；上游 conftest 默认库为 `esimage_admin7_test`，并行运行时用环境变量覆盖。
- **已知非本模块失败**：11 号 `tests/test_ops.py` 的 2 个用例在干净 `origin/main` 也失败（httpx2 中文头、`delay_ms` monkeypatch），不修改。

## 2026-10-31 存储架构共识（MinIO 统一门面）

- **唯一业务读写入口**：业务代码只依赖 `app.modules.workspace.storage.Storage`（`storage` 单例）；禁止在新代码里直接拼 `STORAGE_ROOT` 或调用本地文件 API。
- **后端选择**：`Storage` 委托 `app.modules.data.storage.get_storage()`；`STORAGE_BACKEND=local` → `LocalStorageAdapter`，`minio` → `MinioStorageAdapter`，未知值直接 50003。
- **对象键规范**：始终使用桶内相对键（`uploads/...`、`generated/...`、`thumbnails/...`、`archive/...`），与本地目录结构完全一致；本地与 MinIO 可互换。
- **本地路径边界**：`storage.path()` 只允许本地后端；MinIO 后端显式抛 50003，禁止调用方假设有本地文件。
- **HTTP 媒体响应**：本地后端继续使用 `FileResponse`，保留 `ETag/Last-Modified/Accept-Ranges` 与 Range 206；MinIO 后端使用缓冲 `Response(content=bytes)`。禁止对 MinIO 对象调用 `FileResponse`；MinIO 暂不支持 Range。
- **async 路由中的存储调用**：`storage.save/delete` 是同步网络调用，必须用 `run_in_threadpool` 包裹，禁止直接阻塞事件循环。
- **存储异常兜底**：`app/main.py` 统一处理 `ObjectNotFound → 404/30014` 与 `StorageError → 500/50003`；写接口无需各自捕获。
- **本地脚本隔离**：所有 `curl_*_smoke.sh` 与 `verify_archive_scope()` 显式固定 `STORAGE_BACKEND=local`，避免读取开发者 `.env` 的 MinIO 配置。
- **错误映射**：对象缺失 → 404 / 30014（归档文案按场景）；存储/网络异常 → 500 / 50003。归档读取仍受 `ARCHIVE_READ_TIMEOUT_SECONDS` 线程池超时约束。
- **配置来源**：`app.core.config.settings` 负责 `load_dotenv(backend/.env)`；`app.modules.data.config.config` 直接读环境变量。应用启动必须先导入 core 配置；测试必须在导入 app 前覆盖环境变量。
- **测试隔离**：`tests/conftest.py` 强制 `STORAGE_BACKEND=local`；真实 MinIO 集成测试用 `MINIO_TEST_ENDPOINT` 显式开启，默认跳过。
- **本地 Docker 端口**：Redis 6379；MinIO API 9002、控制台 9003（避开并行项目的 9000/9001）；PostgreSQL 55433 保持不变。
- **MinIO 初始化**：`minio-init` 复用 `minio/minio` 镜像内置 `mc`，不依赖 `minio/mc` 镜像；根密码必须 ≥8 位。
- **Compose 卷风险**：本项目卷键为 `pgdata`，历史容器可能使用 `esimage_esimage_pgdata`；执行 `docker compose up` 前必须确认卷名，避免重建 Postgres 并切到空库。

## 2026-11-01 测试用例维护共识

- **过期测试单独修**：`test_ops.py` 两条失败属于测试自身过期，不夹带在生产功能提交中；使用独立分支与提交，便于回溯。
- **HTTP 头测试值必须 ASCII**：httpx2 在发送前按 ASCII 编码头值；测试非法头时用空格/标点等 ASCII 字符，不要用中文制造“非法”。
- **monkeypatch 只补真实存在的属性**：补丁目标必须与当前模块/函数签名一致；`selftest` 的延时是参数，不应再补模块级 `delay_ms`。

## 2026-11-01 本地环境变量文件共识

- **两份 `.env` 分工**：根 `.env` 供 Docker Compose 插值与容器 `env_file`；`backend/.env` 供宿主机 uvicorn 启动。两者都被 `.gitignore` 忽略，禁止提交。
- **根 `.env` 只追加不覆盖**：该文件可能包含用户自己的 `GITHUBTOKEN`，补齐配置时必须保留原行且不得打印其值。
- **Compose 内网地址**：根 `.env` 的 `DATABASE_URL`、`REDIS_URL`、`MINIO_ENDPOINT` 使用容器服务名（`postgres`、`redis`、`minio:9000`）；宿主机 `backend/.env` 使用 `127.0.0.1` 映射端口。
- **密钥生成**：`SECRET_KEY`、`JWT_SECRET`、`ENCRYPTION_KEY`、初始超管密码使用随机值；`ENCRYPTION_KEY` 必须为 32 字节 Base64。
- **验证方式**：改完根 `.env` 用 `docker compose config -q` 校验插值，不输出具体值；再用 `git check-ignore` 确认文件仍被忽略。- **Compose 卷风险**：本项目卷键为 `pgdata`，历史容器可能使用 `esimage_esimage_pgdata`；执行 `docker compose up` 前必须确认卷名，避免重建 Postgres 并切到空库。- **已知非本模块失败**：11 号 `tests/test_ops.py` 的 2 个用例在干净 `origin/main` 也失败（httpx2 中文头、`delay_ms` monkeypatch），不修改。- **已知 demo 边界**：参数校验先于幂等重放（已删除上传图的极端重试会返回 30006）；真实模型措辞需联调抽检；接口不返回 usage 时 Token 记 0。## 4 号生图任务与结果最小 demo（2026-10-31 实现共识）

- **模块边界**：生成相关接口统一放 `backend/app/modules/generation/`；`workspace` 只保留会话/聊天/上传。生成路由接管 `POST /generations/sample`、`GET /generations/{id}`、`POST /confirm`、`GET /images/{id}/content|thumbnail|download`，并新增取消、单张重试、模板/尺寸、整组 ZIP。对外字段只做增量（`source_sample_batch_id`、`image_type`、`attempt_no`、`is_history_visible`），不删不改既有字段。
- **数据模型**：`generation_batches`、`generated_images`、`agent_runs` 复用 `app/models/workspace.py`；配置表放 `app/models/generation.py`。为满足单张重试幂等，`generated_images` 增加内部列 `client_request_id`（10 号文档未列出，向后兼容，部分唯一索引）；正式实现前需与 10 号统一。
- **共享基础设施**：`app/core/storage.py` 与 `app/core/media.py` 提供跨模块存储、缩略图、PNG 编码与缩放；不改动 `workspace` 的既有 `storage.py`/`imaging.py`。
- **配置**：60 秒进程内缓存 + `refresh()`；只返回 `active` 模板/尺寸/素材与启用的提示词/模型配置。种子幂等，已存在的模型配置不覆盖；本次本地库通过一次性更新把 image_model 改为 `doubao-seedream-5-0-pro-260628`。
- **模型接入**：Key 优先 `DOUBAO_API_KEY`，兼容 `ARK_API_KEY`；文本 `doubao-seed-character-260628`、视觉/审核 `doubao-seed-2-1-lite-260915`、生图 `doubao-seedream-5-0-pro-260628`。真实模式启动强校验；`APP_ENV=test` + `GENERATION_MODEL_PROVIDER=fake` 才允许替身。
- **生图参数**：Seedream 5.0 Pro 不接受 `sequential_image_generation` / `stream`，适配层只发送 `model/prompt/size/response_format/watermark`；目标尺寸小于 100 万像素时按整数倍放大后再生成，最终缩放回批次尺寸。
- **Agent 运行时**：非生图 10 次、退避 1/2/4/8/16/30 秒封顶；生图每张 2 次；每次尝试写 `agent_runs`；跳过的 Agent 只写一条 `skipped`。结构化输出校验失败按一次失败处理。
- **文字合成**：默认版式标题上方 15%、卖点下方 20%、左右边距 8%；标题/卖点字号随画布缩放；超长缩到下限后截断并记录 warnings；深色底加半透明白底。字体优先 `FONT_PATH`，其次 Windows/Noto/文泉驿候选；生产缺失 fail-fast，测试环境降级默认字体。
- **状态机**：批次与单图迁移集中在 `state.py`；`sample_ready → running`、`cancelled → running` 等非法迁移被拒绝。重生成允许 `completed → partially_failed` / `partially_failed → completed`。
- **管线**：示例批次调用四个核心 Agent（覆盖 6 张）但只渲染第 1 张；全套批次读取示例批次四类 `agent_runs.output_full`，不重复调用核心 Agent，串行生成 2~6；单张重试只走生图及后续。每个阶段更新 `generation_batches.stage`；取消/超时在每个检查点读取最新状态。
- **失败策略**：核心 Agent 10 次失败 → 批次 failed；生图 2 次失败 → 批次立即 failed，后续 pending 置「批次已失败，未生成」；非核心 Agent 10 次失败 → skipped 并继续；非生图单张失败 → 该张 failed，批次最后按成功数汇总；整批 30 分钟超时，`BATCH_TIMEOUT_SECONDS` 可缩短。
- **重试/重生成**：事务内加锁，复制原图提示词/角色/序号，`attempt_no+1`，旧图 `superseded`；同批次只允许一个 generating 重试；`completed_count` 按当前非 superseded 成功图重算。
- **ZIP**：临时文件 + `FileResponse` 流式返回；manifest 用 UTF-8 BOM、中文表头；只包含当前成功正式图；部分失败仍可下载。
- **已注意的兼容取舍**：宽高校验改为 512~2048 且 8 的倍数，但超过 4096 仍返回既有 10004，避免破坏 2 号 demo 的错误码断言；其余越界返回 10003。现有测试全部保留并通过。
- **测试**：生成链路统一用 `FakeGateway`；故障注入 `GENERATION_FAULT_MODE`（core/image/quality/platform/moderation/timeout）仅 `APP_ENV=test` 生效；测试退避缩放为 0。
- **已知外部阻塞**：Seedream 5.0 Pro 已开通但账号「安全体验模式」额度用尽（429 SetLimitExceeded），真实全链路验收待用户调整额度。

### 4 号复审后的实现调整（2026-10-31）

- **共享工具落点**：`app/core/common.py` 承载 workspace 与 generation 共用的权限、校验、时间、URL、文件名函数；两个模块只 import，不再各写一份。
- **重试并发口径**：`pending` 与 `generating` 都算“重试进行中”。新图先 pending 落库，后台再置 generating，只看 generating 会留下请求/Worker 之间的并发窗口。
- **取消与在途图**：取消只阻止创建新的图片任务；已经进入生图流程的当前张允许完成后续审核/合成并落库，但 `is_history_visible=false`，批次保持 cancelled。示例批次在图片流程结束后再检查一次取消。
- **重试提示词**：`generated_images.prompt/negative_prompt` 保存的是最终（可能修复后）提示词；重试优先使用这两列，示例批次的 `prompt_builder` 输出只用于补齐 whitespace、reference_asset_ids 等未落库参数。
- **批次错误清理**：重试汇总为 completed 时必须把 `batch.error_message` 清空；partially_failed / failed 分别写入对应摘要。
- **参考图上限**：用户上传图 0~5 张全部参与商品理解与生图；上传图 + 素材合计最多送 6 张参考图，单张压缩到 1024px JPEG。
- **审查结论**：两轴审查的功能问题已修复；剩余外部阻塞仍是 Seedream 账号额度（429），以及 AGENTS.md 要求的 GitHub issue 尚未创建（本地 tickets 为现状）。

## 4 号 skill 接入与主分支集成（2026-10-31 会话 17）

- **Skill 定位**：`backend/skills/generation-pipeline/` 是操作指引而非运行时代码；generation README 与 backend README 引用它，管线按其八条铁律实现。
- **数据模型归属**：生成配置表（templates/material_assets/model_configs/system_prompts/prompt_versions/size_presets）统一归 10 号 `app/models/config.py`；4 号不再维护自己的副本。`generated_images.client_request_id` 是 4 号内部幂等列，通过 Alembic 0004 落地。
- **路由边界**：用户端只读配置保持 `/api/v1/templates`、`/sizes`、`/templates/{id}/thumbnail`；管理端素材/模板/尺寸统一在 `/api/v1/admin/...`，与 6 号契约一致，避免 FastAPI 同路径先注册者胜出。
- **共享 ZIP**：整组 ZIP 以 5 号 `history/zip_export.py` 为唯一实现；4 号不再写第二套。manifest 表头统一为 4 号口径 `序号,文件名,状态,尺寸,生成时间,失败原因`；越权返回 403，符合 4 号“404 或 403”口径。
- **媒体读取**：预览/下载使用 `workspace.service.read_image_bytes`，统一处理热存储与 `archive/` 前缀、超时与错误码；content/thumbnail 允许 `user.generate` 或 `user.history`；单张下载 `Cache-Control: no-store`。
- **种子策略**：10/6 号种子写入的 <80 字占位提示词会被升级为 4 号详细提示词；已有长提示词不覆盖。quality_reviewer/prompt_builder 通过 revision marker 定向升级。demo/空模型名会同步为真实环境模型名。
- **留白策略**：生图 prompt 追加显式 top/bottom 留白比例；质量审核仅 `whitespace_available=fail` 时降级为 warning，由 `compose_text(force_panel=True)` 加半透明底兜底；其他硬性项失败仍走修复/失败。
- **取消与并发**：沿用复审结论——重试并发覆盖 `pending + generating`；生图开始后在途图允许完成；取消只阻止新图。
- **测试环境**：主分支 160 项测试全部通过；两个 ops 测试问题属于主分支既有环境问题，已做最小修复（ASCII 无效 header、移除不存在的 delay_ms monkeypatch）。
- **环境**：复用 `esimage-postgres` 55433，独立库 `esimage_generation` / `esimage_generation_test`；真实模型 `doubao-seed-character-260628` / `doubao-seed-2-1-lite-260915` / `doubao-seedream-5-0-pro-260628`。

### 会话 17 补充：管理端前缀归属

- 管理端子路由统一由 `app/modules/admin/router.py` 加 `/admin` 前缀；`admin/assets/router.py` 只定义 `/templates|/materials|/sizes`，不要再自带 `/admin`，否则会变成 `/api/v1/admin/admin/...`。
- 用户端只读配置仍为 `/api/v1/templates|/sizes|/templates/{id}/thumbnail`，由 generation `config_router` 提供；两条路径互不冲突。
- 真实全套批次在被系统终止前已完成 6/6；重生成完成验证受外部内存终止影响，不是代码缺陷，已把本地残留状态收敛为合法终态。

### 会话 17 补充：存储迁移等待

- 共享存储将由并行 agent 统一改为 Docker MinIO（`STORAGE_BACKEND=minio`，宿主 9002）。
- 4 号 generation 的存储落点最终应改为 `app.modules.data.storage.get_storage()`，不再直接使用 `app.core.storage` / `workspace.storage`；在对方分支合并前不改，避免冲突。
- 数据库与对象存储都是并行 agent 共享的本地基础设施；容器重建会丢失模块库，验收前需重新建库/种子。
