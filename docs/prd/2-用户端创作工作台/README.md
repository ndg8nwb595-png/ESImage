# 2-用户端创作工作台：最小实现 demo

| 项目 | 内容 |
| --- | --- |
| 上游 PRD | [`2-用户端创作工作台prd.md`](./2-用户端创作工作台prd.md) |
| 目标 | 用最小范围跑通「填写商品名称 → 上传商品图 → 聊天补充需求 → 生成示例图 → 确认生成全套 → 预览/下载」的端到端演示 |
| 任务形式 | 7 个垂直切片，按依赖顺序编号，存放在 `issues/` |
| 接口文档 | [`接口文档-创作工作台最小demo.md`](./接口文档-创作工作台最小demo.md) |

> 本目录只覆盖 2 号 PRD 中与「创作工作台最小演示」直接相关的最小集合，不代表 2 号 PRD 的全部验收项，也不替代 3/4/5 号 PRD 的完整实现。

---

## 1. 最小 demo 范围

### 1.1 做

- 桌面端三栏布局：会话列表 / 聊天框 / 参数面板 + 结果区，最小宽度 1280px。
- 顶部导航：创作台、历史作品、个人中心；后两者为占位页。
- 参数面板：商品名称（必填）、风格（选填自由文本）、固定尺寸 1000×1000、商品图上传、生成入口。
- 商品名称前端校验：为空或超长时弹窗提示、聚焦输入框、不发送任何网络请求。
- 商品图上传：0~5 张、JPG/PNG/WEBP、单张 ≤10MB、缩略图、删除、替换、排序；第一张为主参考图。
- 会话：新建会话草稿、首条消息或首次生成时后端原子创建会话、自动命名、会话列表、切换会话、消息分页。
- 聊天：SSE 流式输出，只展示规划 + 商品理解两个 Agent 的状态；聊天不触发生成。
- 生成示例图：创建 `sample` 批次、阶段进度、示例图展示、重新生成示例、调整参数、并发限制。
- 确认并生成全套：二次确认、创建 `full` 批次、复用示例图作为主图、生成 5 张详情图、6 张结果网格。
- 结果区：大图预览、单张 PNG 下载；示例图确认前不可下载。
- 基础数据隔离：仅普通用户可访问；只能看到自己的会话、上传图、生成记录。

### 1.2 不做

- 模板卡片与模板应用（`template_id` 固定为 `null`）。
- 尺寸预设下拉与自定义宽高（固定 1000×1000）。
- 会话重命名、软删除、恢复。
- 取消任务。
- 单张重生成、重试失败张、部分失败/全部失败的完整交互。
- 整组 ZIP 下载与 `manifest.csv`。
- 历史作品、个人中心、管理后台的实际业务页面（仅占位）。
- 真实 8 Agent 全链路、质量审核、修复、平台规范、文字合成。
- 内容审核、Token 统计、操作审计的完整实现。
- 手机端适配。

### 1.3 相对 PRD 的最小化取舍

| PRD 要求 | 最小 demo 处理 | 原因 / 影响 |
| --- | --- | --- |
| 8 Agent 全链路（规划 → 商品理解 → 文案 → 提示词 → 生图 → 质量审核 → 修复 → 平台规范 → 文字合成） | 用「演示生成管线」推进同样的阶段并产出占位 PNG；接口、批次状态机、阶段枚举不变 | PRD 4 的完整实现替换管线内部，不改本目录定义的接口 |
| Celery + Redis | FastAPI `BackgroundTasks` + PostgreSQL 状态轮询；单实例部署 | 降低本地启动成本；并发限制仍按数据库校验；正式实现换 Celery |
| MinIO 单桶 | 存储适配层 + 本地目录（可选切 MinIO） | 接口与路径契约不变；正式实现切 MinIO（10 号 §6） |
| 聊天轻链路调用真实文本模型 | 未配置模型时返回固定演示回复与最小需求摘要；配置了 `text_model` 可接真实模型 | 保证聊天面板可演示；PRD 3 的完整实现替换该桩 |
| 模板入口 | 不做 | 不建 `templates` 表、不提供 `GET /templates` |
| 尺寸预设与自定义宽高 | 固定 1000×1000 | 不建 `size_presets` 表、不提供 `GET /sizes` |
| 会话重命名 / 软删除 | 不做 | 不提供 `PATCH/DELETE /sessions/{id}` |
| 取消任务 | 不做 | 不提供 `POST /generations/{batch_id}/cancel` |
| 单张重生成 / 重试失败张 | 不做 | 不提供 `POST /images/{image_id}/regenerate` |
| 整组 ZIP | 不做 | 不提供 `GET /batches/{batch_id}/download` |
| 历史作品 / 个人中心 | 占位页 | 完整实现见 5 号 PRD 与个人中心 PRD |
| 内容审核 | 跳过 | 上传与生成不调用审核；正式实现补 30007 |
| 参数 localStorage 键 | 新增草稿键 `esimage_workspace_params_draft`，会话创建后迁移到 `esimage_workspace_params_{session_id}` | PRD 只定义了按会话的键；草稿阶段还没有 `session_id`，见待确认项 |
| 上传图 ID localStorage 键 | 新增 `esimage_workspace_upload_ids_{session_id}` 与草稿键 `esimage_workspace_upload_ids_draft` | PRD 未给键名；与参数键保持同构 |

---

## 2. 演示账号与前置

### 2.1 前置

本目录假定「1-登录界面」最小 demo 的 01~03 已完成：

- 前后端工程骨架可启动。
- `users`、`roles`、`permissions`、`user_roles`、`role_permissions`、`audit_logs` 六张表已存在。
- 登录、登录态恢复、请求注入、路由守卫可用。
- `demo_user` 可登录并进入 `/workspace`。

### 2.2 演示账号

| 用户名 | 密码 | 角色 | 工作台所需权限 |
| --- | --- | --- | --- |
| `demo_user` | `Demo1234` | `user` | `user.workspace`、`user.generate`、`user.history` |
| `demo_admin` | `Demo1234` | `admin` | 无工作台权限，用于验证角色隔离 |

> `demo_user` 在 1 号 demo 中已有 `user.workspace`、`user.history`、`user.profile`；本目录的 01 号任务需要补种 `user.generate`。

---

## 3. 接口总览

详细字段、错误码与 SSE 事件见 [`接口文档-创作工作台最小demo.md`](./接口文档-创作工作台最小demo.md)。

| 方法 | 路径 | 用途 | 所在 Ticket |
| --- | --- | --- | --- |
| GET | `/api/v1/auth/me` | 恢复登录态（复用 1 号 demo） | 01 |
| GET | `/api/v1/sessions` | 会话列表 | 04 |
| GET | `/api/v1/sessions/{id}/messages` | 会话消息分页 | 04 |
| POST | `/api/v1/sessions/messages` | 首条消息，SSE，可无会话 | 04 |
| POST | `/api/v1/sessions/{id}/messages` | 已有会话发消息，SSE | 04 |
| POST | `/api/v1/uploads` | 上传商品图 | 03 |
| GET | `/api/v1/uploads/{upload_id}` | 恢复上传图元数据 | 03 |
| DELETE | `/api/v1/uploads/{upload_id}` | 软删除上传图 | 03 |
| GET | `/api/v1/uploads/{upload_id}/content` | 读取上传图原图（demo 约定） | 03 |
| GET | `/api/v1/uploads/{upload_id}/thumbnail` | 读取上传图缩略图（demo 约定） | 03 |
| POST | `/api/v1/generations/sample` | 创建示例批次 | 05 |
| GET | `/api/v1/generations/{batch_id}` | 查询批次状态与进度 | 05 / 06 |
| POST | `/api/v1/generations/{batch_id}/confirm` | 确认示例，创建全套批次 | 06 |
| GET | `/api/v1/images/{image_id}/content` | 大图预览（demo 约定） | 07 |
| GET | `/api/v1/images/{image_id}/download` | 单张 PNG 下载 | 07 |

### 3.1 明确不提供的接口

`GET /sizes`、`GET /templates`、`POST /sessions`、`PATCH/DELETE /sessions/{id}`、`POST /generations/{batch_id}/cancel`、`GET /generations/{batch_id}/images`、`POST /images/{image_id}/regenerate`、`GET /batches/{batch_id}/download`、`GET /history`、`GET /profile`、全部管理端接口。

---

## 4. 任务依赖

```text
01 工作台骨架、最小数据表与演示配置
        ↓
02 参数面板、商品名称校验与参数快照
        ↓
   ┌────┴─────────────┐
   ↓                  ↓
03 商品图上传与恢复   04 会话列表与聊天轻链路
   ↓
05 生成示例图、阶段进度与示例循环
   ↓
06 确认并生成全套与结果网格
   ↓
07 结果预览与单张下载
```

> 04 与 03 可以并行；05 只被 03 阻塞。若 04 已完成，05 生成时会读取会话中由商品理解 Agent 维护的 `requirement_summary`；未完成时该字段为 `null`，不影响生成。

| # | Ticket | 阻塞于 | 交付的可演示行为 |
| --- | --- | --- | --- |
| 01 | [工作台骨架、最小数据表与演示配置](./issues/01-工作台骨架与最小数据表.md) | 1 号 demo 的 01~03 | 登录后进入三栏工作台，空状态可见，普通用户可访问、管理员被拦截 |
| 02 | [参数面板、商品名称校验与参数快照](./issues/02-参数面板与商品名称校验.md) | 01 | 商品名称必填校验、聊天/生成入口联动、参数按会话保存并提交快照 |
| 03 | [商品图上传、恢复与排序](./issues/03-商品图上传与恢复.md) | 02 | 0~5 张商品图上传、缩略图、删除、排序、刷新恢复 |
| 04 | [会话列表与聊天轻链路](./issues/04-会话列表与聊天轻链路.md) | 02 | 新建/切换会话、首条消息建会话、SSE 流式回复、自动命名 |
| 05 | [生成示例图、阶段进度与示例循环](./issues/05-生成示例图与阶段进度.md) | 03 | 点击生成、阶段进度、示例图展示、重新生成示例、并发拦截 |
| 06 | [确认并生成全套与结果网格](./issues/06-确认并生成全套与结果网格.md) | 05 | 二次确认、`full` 批次、1 主图 + 5 详情图、6 张网格 |
| 07 | [结果预览与单张下载](./issues/07-结果预览与单张下载.md) | 06 | 大图预览、正式图单张下载、示例图确认前不可下载 |

---

## 5. 验收总口径（演示脚本）

最小 demo 完成时，至少能完整演示以下路径：

1. `demo_user` 登录 → 进入 `/workspace`，三栏布局在 1280px 下可见且无横向滚动。
2. 结果区空状态显示「填写参数后生成示例图」；商品名称未填时聊天输入框禁用、生成按钮不可用。
3. 商品名称留空点击生成 → 弹窗「请先填写商品名称」并聚焦输入框，网络面板无请求。
4. 填写商品名称 → 聊天输入框与生成按钮同时可用；填写风格；上传 2 张商品图，第一张显示「主参考图」。
5. 发送聊天消息 → 用户气泡立即上屏，Agent 回复流式展示；会话自动命名并出现在左侧列表。
6. 点击「生成示例图」→ 结果区按阶段展示进度 → 生成 1 张示例图；示例图可预览、不可下载。
7. 点击「重新生成示例」→ 创建新的 `sample` 批次，旧批次保留；结果区只展示最新示例。
8. 点击「确认并生成全套」→ 二次确认 → 结果区展示 2/6、3/6… → 最终 6 张网格，第 1 张为主图，2~6 为详情图。
9. 点击任一张正式图 → 大图预览；下载单张 PNG，文件名为 `{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`。
10. 刷新页面 → 参数、上传图、当前会话与最近批次结果恢复。
11. 在已有 `queued` / `running` 批次时再次点击生成 → 按钮禁用或返回 30003，提示「已有生成任务进行中」。
12. `demo_admin` 登录后访问 `/workspace` → 被路由守卫拦截或返回 403。
13. 用 `demo_user` 的 token 请求另一个用户的批次 / 上传图 / 图片 → 404 或 403，不泄露数据。

---

## 6. 待确认项

以下事项在接口文档中给出了 demo 默认口径，正式实现前需要与 9 号、10 号文档统一：

1. **创建示例批次的响应是否返回 `session_id`**：2 号与 9 号未定义创建响应；demo 约定返回 `batch_id`、`session_id`、`session_title`、`status`，否则前端无法把批次挂到会话列表。
2. **草稿阶段的 localStorage 键名**：PRD 只定义 `esimage_workspace_params_{session_id}`；demo 增加 `_draft` 键，会话创建后迁移。
3. **结果区大图预览接口**：9 号只定义下载接口，未定义「只预览、不允许下载」的读取接口；demo 增加 `GET /images/{image_id}/content`，示例图可读、下载接口仍拦截。
4. **上传图/缩略图读取接口**：9 号只给 `file_url` / `thumbnail_url`，未定义具体路径；demo 增加 `/uploads/{id}/content` 与 `/uploads/{id}/thumbnail`。
5. **会话列表的 `latest_batch_id` 与 `last_message_preview`**：9 号未定义；demo 为支持「切换会话恢复最近结果」和列表摘要而增加，正式实现需确认是否由会话详情接口承担。
6. **预览接口的权限码**：demo 统一用 `user.generate`；PRD 5 的历史作品预览/下载用 `user.history`，正式实现需统一。
7. **示例图确认的「最新可确认」判定**：demo 以「该用户最近创建的 `sample` 批次且状态为 `sample_ready`」为准；正式实现需明确是否按会话维度。
8. **聊天桩回复**：未配置文本模型时返回固定回复与最小需求摘要；若要求真实模型，需并入 3 号 PRD 的任务，不属于本最小 demo。
