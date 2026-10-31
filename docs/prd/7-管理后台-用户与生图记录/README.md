# 7-管理后台-用户与生图记录：最小实现 demo

| 项目 | 内容 |
| --- | --- |
| 上游 PRD | [`7-管理后台-用户与生图记录prd.md`](./7-管理后台-用户与生图记录prd.md) |
| 目标 | 用最小范围跑通「概览四卡 → Token 统计 → 用户/会话/批次/单图三层钻取 → 单图详情与下载 → 用户详情内容入口」的端到端演示 |
| 任务形式 | 6 个垂直切片，按依赖顺序编号，存放在 `issues/` |
| 接口文档 | [`接口文档-用户与生图记录最小demo.md`](./接口文档-用户与生图记录最小demo.md) |

> 本目录只覆盖 7 号 PRD 中与「概览、Token 统计、生图记录追溯、单图详情、用户详情内容入口」直接相关的最小集合，不代表 7 号 PRD 的全部验收项。数据导出（§8）、图表/排行/报表订阅、后台删除/重生成/改提示词、直连数据库不在本 demo 内。

---

## 1. 最小 demo 范围

### 1.1 做

- 概览首页四张统计卡片：用户总数、今日生成图片数、累计图片数、今日 Token；60 秒缓存；快捷入口；空状态与加载失败重试。
- 概览 Token 统计 Tab：时间范围、用户关键词、8 个 Agent 多选、模型筛选；输入/输出/总 Token 与调用次数汇总；按日期 + 用户 + Agent + 模型的明细分页；Asia/Shanghai 口径。
- 生图记录三层钻取：有生成记录的用户 → 用户会话 → 会话生成批次 → 批次图片网格 → 单图详情。
- 批次筛选：商品名称、批次类型、批次状态、批次创建时间；图片网格筛选：图片角色、图片状态。
- 单图详情：图片预览与缩放、完整参数/提示词/模型/耗时/Token/状态/快照字段、原图下载、跳转会话与用户详情。
- 归档图片：详情仍展示元数据与缩略图；大图与下载从 `archive/` 读取；慢读 loading 与不可用提示。
- 用户详情中的内容入口：启用「查看会话」「查看生图记录」，并带 `user_id` 筛选跳转；用户列表与详情的统计从 6 号 demo 的占位值升级为真实聚合。
- 权限与数据边界：管理员/超管可看概览、Token 与内容追溯；普通用户 403；管理员看不到超管账号的会话、批次与图片。
- 一份幂等的管理端演示数据种子，覆盖多用户、会话、批次、图片、Agent 调用、归档图、失败与替代图，供所有切片复用。

### 1.2 不做

- 数据导出（§8）：`POST /api/v1/admin/export`、`GET /api/v1/admin/export/{job_id}`、ZIP/CSV/manifest、24 小时下载、导出审计；内容页与用户页不展示导出按钮。
- 图表趋势、排行、报表订阅、Token 金额换算。
- 后台替用户重新生成图片、删除生图记录或图片文件、修改提示词、直连数据库执行 SQL。
- 用户详情中的账号编辑、重置密码、禁用/启用、删除/恢复（6 号 demo 范围）。
- 聊天记录页面、消息搜索、Agent 调用明细页（8 号 demo 范围）；本 demo 只提供跳转链接。
- 素材/模板、模型配置、系统提示词、操作日志页面（其他 demo 范围）。
- 归档调度与 5 年扫描；只用种子模拟 `archived_at` 与 `archive/` 前缀，验证归档后读取。
- 移动端适配；管理后台桌面优先。
- Redis、MinIO、Celery、Alembic；沿用进程内 60 秒缓存、本地存储适配层、建表 + 幂等种子。
- 真实豆包生成；本 demo 用种子数据演示，不要求配置 `DOUBAO_API_KEY`；4 号 demo 真实生成的数据同样可在后台查看。

### 1.3 相对 PRD 的最小化取舍

| PRD 要求 | 最小 demo 处理 | 原因 / 影响 |
| --- | --- | --- |
| 概览卡片 Redis 缓存 60 秒 | 进程内 TTL 缓存 60 秒，单实例 | 不引入 Redis；行为与 60 秒缓存一致；正式实现换 Redis（9 号 §2.7） |
| 缩略图预签名 URL（≤5 分钟） | 新增管理端鉴权媒体接口，前端带 token 取 Blob | 本地存储无预签名能力；接口契约与正式实现可平滑替换 |
| 数据导出（ZIP + CSV） | 不做，按钮不展示，接口列入未实现 | 导出是独立的大功能；最小 demo 先保证内容追溯主链路可演示 |
| 归档任务与 5 年扫描 | 种子直接写 `archived_at` 与 `archive/` 文件 | 只验证归档后读取；调度属 10 号 §7.2 |
| 真实生成链路产出数据 | 提供幂等演示种子；4 号真实数据也可查看 | 后台演示不依赖豆包 Key，结果可复现 |
| 6 号 demo 用户详情统计返回 `0` | 改为真实聚合，`stats_available=true` | 内容表已就绪；不改变 6 号接口字段结构 |
| 6 号 demo 内容入口按钮禁用 | 启用跳转并带 `user_id` 筛选 | 7 号 PRD §5 要求；聊天页目标由 8 号 demo 提供 |
| 批次/图片分页默认 20 | 内容列表默认 20、最大 100；Token 明细固定 20 | 与 9 号分页约定一致；Token 明细按 PRD §4.3 |
| 用户列表与内容列表是否含删除/禁用用户、隐藏会话 | demo 包含并显示状态 | 内容追溯要求历史可查；待正式确认 |
| 图片网格是否展示 `superseded` 旧图 | 默认每个序号只展示最新一次尝试；`include_superseded=true` 或按 `status=superseded` 查看全部 | 避免网格重复；保留追溯能力 |
| 管理员看不到超管内容 | 列表过滤；直接访问返回 403 `20006` | 与 6 号 demo 的超管账号边界一致 |
| 导出相关审计动作 | 不做 | 导出不在本 demo 内；正式实现补 `export.*` |

### 1.4 与前后 demo 的关系

| demo | 提供的能力 | 与 7 号 demo 的边界 |
| --- | --- | --- |
| 1 号登录 | 工程骨架、登录、登录态、路由守卫 | 7 号复用，不重复 |
| 6 号管理后台-账号与权限 | `/admin` 骨架、23 个权限点、用户列表/详情、`demo_super` | 7 号新增概览与内容追溯；用户详情统计改为真实值，内容入口启用 |
| 4 号生图任务与结果 | `creative_sessions`、`generation_batches`、`generated_images`、`agent_runs` 等表与真实生成数据 | 7 号只读；不改变 4 号接口与状态机；真实生成数据可直接查看 |
| 5 号历史作品 | 归档读取、单张/整组下载、ZIP manifest | 7 号复用归档读取规则与存储适配层；不重复裁剪图片 |
| 8 号管理后台-聊天记录 | `/admin/chat` 会话详情与 Agent 明细 | 7 号只提供跳转链接；8 号未实现时链接置灰 |

---

## 2. 前置与演示配置

### 2.1 前置

本目录假定：

1. 「1-登录界面」最小 demo 的 01~03 已完成。
2. 「6-管理后台-账号与权限」最小 demo 的 01 与 06 已完成：
   - `/admin` 布局可用，23 个权限点已种入，`admin.dashboard.view`、`admin.tokens.view`、`admin.content.view` 已授予管理员；
   - `demo_super` 存在，按角色即时拥有全部权限；
   - 用户列表与用户详情可用，详情统计当前为 `0` 且 `stats_available=false`。
3. 「4-生图任务与结果」最小 demo 的 01 已完成：
   - `creative_sessions`、`generation_batches`、`generated_images`、`agent_runs` 表结构、枚举与索引就绪；
   - 存储适配层可读写 `generated/`、`thumbnails/`、`archive/`。
4. 可选：「4-生图任务与结果」03/04 已完成，用真实生成数据补充演示；本 demo 的种子不依赖真实生成。
5. 可选：「5-历史作品」05 已完成，直接复用归档读取；未完成时在 05 切片内按同一 `archived_at` 规则实现。
6. 可选：「8-管理后台-聊天记录」已完成，承接「查看会话」跳转；未完成时链接置灰。

### 2.2 演示账号

> 仅用于本地 demo，部署到任何共享环境前必须删除或改密。

| 用户名 | 密码 | 角色 | 用途 |
| --- | --- | --- | --- |
| `demo_super` | `Demo1234` | `super_admin` | 概览、Token、内容追溯；验证可看超管内容 |
| `demo_admin` | `Demo1234` | `admin` | 概览、Token、内容追溯；验证看不到超管内容 |
| `demo_user` | `Demo1234` | `user` | 内容所有者；普通用户访问管理接口应 403 |
| `demo_user2` | `Demo1234` | `user` | 本 demo 新增的第二个内容所有者，用于多用户列表与筛选 |
| `demo_dual` | `Demo1234` | `user` + `admin` | 验证双角色切换后管理端可用 |

### 2.3 种子数据

种子脚本必须幂等：重复执行不重复创建、不重置已有密码与已修改权限。

| 对象 | 种子内容 |
| --- | --- |
| 用户 | 创建 `demo_user2`（普通用户）；`demo_user`、`demo_super`、`demo_admin` 复用 |
| 会话 | `demo_user` 2 个（1 个 `active` 含示例+全套批次，1 个 `hidden` 含归档批次）；`demo_user2` 1 个；`demo_super` 1 个 |
| 批次 | `demo_user`：`sample_ready` 示例批次、`completed` 全套批次、`partially_failed` 全套批次、`failed` 示例批次、`cancelled` 全套批次、归档 `completed` 全套批次；`demo_user2`：1 个 `partially_failed`；`demo_super`：1 个 `completed` |
| 图片 | 覆盖 `main` / `detail`、`success` / `failed` / `cancelled` / `superseded`、`image_type=sample/final`；含 1 张 `archived_at` 非空的成功正式图 |
| Agent 调用 | 覆盖 8 个 Agent；跨 7 个自然日；2 个模型名；含 `success`、`failed`（有 Token 与 0 Token 各一条）、`skipped`（0 Token） |
| 文件 | 在 `STORAGE_DIR` 生成占位 PNG、`thumbnails/` 缩略图；归档图同时写入 `archive/`；不调用豆包 |

- 种子不修改 4 号 demo 真实生成的数据；两类数据可并存。
- 种子不写入导出任务、导出文件或 `export.*` 审计日志。
- 种子使用唯一键（用户名、`client_request_id`、固定业务标识）做幂等，不依赖固定自增 ID；测试通过查询获取 ID。

### 2.4 环境变量

| 变量 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `STORAGE_DIR` | 否 | 沿用 2/4 号 demo | 本地存储根目录 |
| `ARCHIVE_READ_TIMEOUT_SECONDS` | 否 | `60` | 归档读取超时；超时视为不可用 |
| `DASHBOARD_CACHE_TTL_SECONDS` | 否 | `60` | 概览卡片缓存 TTL；测试可调小 |
| `DOUBAO_*` | 否 | — | 本 demo 种子不调用豆包；运行 4 号真实链路时才需要 |

### 2.5 演示数据边界

- 概览「用户总数」只统计 `status != deleted`；内容追溯列表可以展示已删除/禁用用户的历史内容，并显示状态。
- 管理员看不到拥有 `super_admin` 角色的用户及其会话、批次、图片；列表过滤，直接访问返回 403 `20006`。
- 会话列表包含 `active` 与 `hidden`；批次状态包含 PRD 的 8 种；图片状态包含 `pending/generating/success/failed/cancelled/superseded`。
- 所有日期筛选与「今日」口径按 Asia/Shanghai 计算。

---

## 3. 接口总览

详细字段、错误码与统计口径见 [`接口文档-用户与生图记录最小demo.md`](./接口文档-用户与生图记录最小demo.md)。

| 方法 | 路径 | 权限 | 用途 | 所在 Ticket |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/dashboard/summary` | `admin.dashboard.view` | 概览四张统计卡片 | 01 |
| GET | `/api/v1/admin/tokens/stats` | `admin.tokens.view` | Token 统计汇总与明细 | 02 |
| GET | `/api/v1/admin/content/users` | `admin.content.view` | 有生成记录的用户列表 | 03 |
| GET | `/api/v1/admin/content/users/{user_id}/sessions` | `admin.content.view` | 用户会话列表 | 03 |
| GET | `/api/v1/admin/content/sessions/{session_id}/batches` | `admin.content.view` | 会话批次列表 | 04 |
| GET | `/api/v1/admin/content/batches/{batch_id}/images` | `admin.content.view` | 批次图片列表 | 04 |
| GET | `/api/v1/admin/content/images/{image_id}` | `admin.content.view` | 单图详情 | 05 |
| GET | `/api/v1/admin/content/images/{image_id}/thumbnail` | `admin.content.view` | 图片网格缩略图 | 04 / 05 |
| GET | `/api/v1/admin/content/images/{image_id}/content` | `admin.content.view` | 单图大图预览 | 05 |
| GET | `/api/v1/admin/content/images/{image_id}/download` | `admin.content.view` | 下载单张原图 | 05 |
| GET | `/api/v1/admin/users` | `admin.accounts.view` | 用户列表；统计改为真实值（复用 6 号） | 06 |
| GET | `/api/v1/admin/users/{id}` | `admin.accounts.view` | 用户详情；统计改为真实值（复用 6 号） | 06 |

### 3.1 明确不提供的接口

- `POST /api/v1/admin/export`、`GET /api/v1/admin/export/{job_id}`、导出文件下载接口。
- `GET /api/v1/admin/chat/*`、`GET /api/v1/admin/agent-runs/{run_id}`（8 号 demo）。
- `GET/PUT /api/v1/admin/model-config`、`/api/v1/admin/prompts/*`、`/api/v1/admin/templates/*`、`/api/v1/admin/materials/*`、`/api/v1/admin/sizes/*`、`/api/v1/admin/audit-logs*`（其他 demo）。
- 批次/图片的删除、重新生成、修改提示词接口。
- 直连数据库或 SQL 查询接口。

---

## 4. 任务依赖

```text
6 号 demo 01（管理后台骨架、权限点、用户列表）
        │
4 号 demo 01（生成数据模型与 Agent 运行时）
        ↓
01 概览四卡与演示数据种子
        ├──────────────────────────┐
        ↓                          ↓
02 Token 统计 Tab         03 生图记录：用户层与会话层
                                   ↓
                          04 生图记录：批次层与图片网格
                                   ↓
                          05 单图详情与媒体访问
                                   │
                    ┌──────────────┘
                    ↓
              （03 → 06，见下）
06 用户详情真实统计与内容入口
```

> 02 与 03~05 在 01 完成后可并行；06 依赖 03 的 `user_id` 筛选入口与 6 号 demo 06 的用户详情；05 的归档读取可复用 5 号 demo 05。

| # | Ticket | 阻塞于 | 交付的可演示行为 |
| --- | --- | --- | --- |
| 01 | [概览四卡与演示数据种子](./issues/01-概览四卡与演示数据种子.md) | 6 号 demo 01、4 号 demo 01 | `/admin/dashboard` 四卡、60 秒缓存、快捷入口、点击跳转内容页并带当天筛选；幂等演示数据种子 |
| 02 | [Token 统计 Tab](./issues/02-Token统计Tab.md) | 01 | 时间/用户/Agent/模型筛选；汇总与明细分页；跳过的 Agent 不计 Token |
| 03 | [生图记录：用户层与会话层](./issues/03-生图记录用户层与会话层.md) | 01 | 三栏骨架；用户列表关键词与最后生成时间排序；选中用户加载会话，默认展开最近会话；管理员过滤超管 |
| 04 | [生图记录：批次层与图片网格](./issues/04-生图记录批次层与图片网格.md) | 03 | 展开会话显示批次与构成；商品/类型/状态/时间筛选；图片网格与角色/状态筛选、缩略图 |
| 05 | [单图详情与媒体访问](./issues/05-单图详情与媒体访问.md) | 04 | 单图详情全字段；缩略图/预览/下载；归档读取与降级；跳转会话与用户详情 |
| 06 | [用户详情真实统计与内容入口](./issues/06-用户详情真实统计与内容入口.md) | 6 号 demo 06、03、4 号 demo 01 | 用户列表/详情统计改为真实聚合；启用两个内容入口并带 `user_id` 跳转 |

---

## 5. 验收总口径（演示脚本）

最小 demo 完成时，至少能完整演示以下路径：

1. 执行种子脚本两次，用户、会话、批次、图片、Agent 调用数量不变；不调用豆包也能得到可展示数据。
2. `demo_super` 登录 → 进入 `/admin/dashboard`，四张卡片数字与种子一致；60 秒内重复进入数字不变；缓存过期或清缓存后按最新数据重算。
3. 点击「今日生成图片数」与「累计图片数」→ 均跳转 `/admin/content` 并带当天日期筛选；快捷入口分别跳用户管理、生图记录、Token Tab。
4. Token Tab 选择最近 7 天、指定用户、多个 Agent、指定模型 → 汇总与明细合计一致；`skipped` 不计 Token；失败但有 Token 的调用计入；无数据时显示空状态。
5. 生图记录左侧用户列表按最后生成时间倒序；输入关键词过滤；选择 `demo_user` 加载会话；默认展开最近会话。
6. 展开会话查看批次：类型、状态、商品名称、图片构成、张数、创建时间正确；按商品名称、批次类型、状态、时间筛选后结果正确；无结果显示「没有符合条件的记录」。
7. 选择全套批次 → 图片网格显示 1 主图 + 5 详情图（或失败/替代状态）；按图片角色、图片状态筛选；缩略图加载失败显示占位。
8. 点击图片 → 单图详情抽屉展示预览、图片 ID、用户、会话、批次、序号、状态、商品、风格、尺寸、角色、模板、提示词、负面提示词、模型、耗时、Token、错误、创建时间、文件路径、是否历史可见；可缩放、下载原图、跳转会话/用户详情。
9. 打开归档图片 → 元数据与缩略图正常；大图/下载显示「正在从归档读取…」，成功后返回；归档不可用返回 404 `30014` 并提示「文件归档中，请稍后重试」。
10. `demo_admin` 登录 → 内容追溯用户列表不含 `demo_super`；直接请求 `demo_super` 的会话/批次/图片返回 403 `20006`；`demo_user` 调用管理接口返回 403 `20005`。
11. 打开用户详情 → 累计生成图片数、累计会话数、累计 Token、失败任务数与种子一致，`stats_available=true`；点击「查看生图记录」跳转内容页并按该用户筛选；「查看会话」跳转 8 号聊天页（未实现时置灰）。
12. 概览/内容页均无导出按钮；调用导出接口不在本 demo 接口清单内；无删除、重新生成、修改提示词、直连 SQL 入口。
13. 接口与页面各有可执行冒烟测试，关键步骤输出中文日志。

---

## 6. 待确认项

以下事项在接口文档中给出了 demo 默认口径，正式实现前需要与 4、6、8、9、10 号文档统一：

1. **「累计图片数」点击也带当天日期筛选**：PRD §3.1 原文如此，demo 照做；但累计数配当天筛选在交互上可能反直觉，待产品确认是否改为不带日期。
2. **内容追溯是否包含已删除/禁用用户与 `hidden` 会话**：demo 包含并显示状态，便于历史追溯；PRD 未明确。
3. **图片网格默认是否展示 `superseded` 旧图**：demo 默认每个序号只展示最新尝试，提供 `include_superseded=true` 与 `status=superseded` 查看全部；PRD 只要求状态筛选包含 superseded。
4. **`agent_runs` 的用户归属**：demo 优先取 `creative_sessions.user_id`，其次 `generation_batches.user_id`；两者都为空的记录不计入按用户明细。需 4 号运行时保证每次调用至少关联会话或批次。
5. **Token 统计的失败调用口径**：demo 只计入 `success`，以及 `failed` 且输入+输出 Token > 0 的记录；`failed` 且 0 Token 不计入。
6. **新增错误码 `30020`（图片不存在）**：9 号未定义；demo 暂用 `30020`，与 6 号 demo 的 `30017`~`30019` 连续。
7. **新增管理端媒体接口**：`/thumbnail`、`/content` 在 9 号只有 `/download`；demo 新增，需与 9 号统一。
8. **管理员下载文件名**：demo 复用用户端 `{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`；PRD 未单独定义后台命名。
9. **归档读取复用**：demo 复用 5 号 demo 05 的 `archived_at` + `archive/` 规则与 `30014`；正式实现需统一超时阈值与错误文案。
10. **概览缓存实现**：demo 用进程内 60 秒 TTL，单实例；正式实现按 9 号 §2.7 使用 Redis 并支持主动失效。
11. **`failed_task_count` 口径**：demo 统计批次状态为 `failed` 或 `partially_failed` 的数量；是否把 `cancelled` 计入待确认。
12. **「查看会话」依赖 8 号聊天页**：demo 链接到 `/admin/chat?user_id=...`；8 号未实现时按钮置灰，不阻塞本 demo 验收。
13. **数据导出未实现**：PRD §1.2/§8 的导出能力与验收项 9/10/12/13 延期；本 demo 不展示入口，接口列入未实现。
14. **时间筛选参数命名**：demo 内容/Token 用 `start_date`/`end_date`（`YYYY-MM-DD`），9 号导出用 `start_time`/`end_time`（ISO 8601）；正式实现需统一。
15. **超管内容越权的错误码**：demo 用 `20006`（无权操作超管账号）并返回「无权查看超管账号内容」；9 号未区分查看与操作。
