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
