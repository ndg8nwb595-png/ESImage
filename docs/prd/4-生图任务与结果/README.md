# 4-生图任务与结果：最小实现 demo

| 项目 | 内容 |
| --- | --- |
| 上游 PRD | [`4-生图任务与结果prd.md`](./4-生图任务与结果prd.md) |
| 目标 | 用最小范围跑通「生成示例图 → 确认示例 → 生成 1 主图 + 5 详情图 → 文字合成 → 重试/取消 → 单张/整组下载」的真实生成链路 |
| 任务形式 | 8 个垂直切片，按依赖顺序编号，存放在 `issues/` |
| 接口文档 | [`接口文档-生图任务最小demo.md`](./接口文档-生图任务最小demo.md) |

> 本目录只覆盖 4 号 PRD 中与「生图任务最小演示」直接相关的集合，不代表 4 号 PRD 的全部验收项。用户端布局、参数面板、会话与上传等交互沿用 [`../2-用户端创作工作台/README.md`](../2-用户端创作工作台/README.md)；本目录只替换其中的「演示生成管线」内部，不改动 2 号 demo 已定义的接口契约。

---

## 1. 最小 demo 范围

### 1.1 做

- 生成数据模型：`generation_batches`、`generated_images`、`agent_runs` 补齐到 10 号 §4.8~§4.10 的字段与约束。
- 生成配置的**只读消费**：`templates`、`material_assets`、`size_presets`、`model_configs`、`system_prompts` 建表并种入演示数据；不做后台增删改页面。
- 真实豆包模型：文本、视觉、图像、生成图内容审核均调用豆包；不提供桩模式。
- 8 Agent 全链路：规划 → 商品理解（含素材检索）→ 文案 → 提示词 → 生图执行 → 质量审核 → 修复（按需）→ 平台规范；文字合成作为独立后处理。
- 示例批次：生成 1 张带中文文案的示例图，阶段进度可见，可反复重新生成。
- 全套批次：复用示例图为主图，复用示例批次的规划/商品理解/文案/提示词输出，串行生成 5 张详情图。
- 文字留白与后端合成：默认版式、内置中文字体、超长缩容与截断、留白不足时半透明底。
- 失败策略：非生图 Agent 10 次指数退避（1/2/4/8/16/30 秒封顶）、生图每张 2 次、核心失败批次失败、非核心跳过并标记、非生图单张失败继续、部分失败、整批 30 分钟超时。
- 取消任务、单张重试/重生成、整组 ZIP + `manifest.csv`。
- 结果可见性与下载命名：仅 `full` 批次成功正式图进入历史；示例图确认前不可下载。

### 1.2 不做

- 模板、素材库、尺寸预设的**后台增删改、启停、排序、操作日志页面**（只建表、种子与只读接口）。
- 管理后台的生成记录、Agent 调用、Token 明细页面。
- 历史作品、个人中心、会话重命名/软删除、聊天链路改造。
- 上传商品图的内容审核（只做**生成图**审核）。
- 局部重绘、涂抹修复、在线改字、用户自定义提示词/字体/颜色。
- 一次提交多个商品、批量生成多个规格、视频与 3D 素材。
- 失败张自动补齐（只支持用户手动重试）。
- 归档与冷数据、操作审计、Token 统计报表。
- Celery + Redis、MinIO 正式接入（沿用 2 号 demo 的单实例 `BackgroundTasks` 与存储适配层）。

### 1.3 相对 PRD 的最小化取舍

| PRD 要求 | 最小 demo 处理 | 原因 / 影响 |
| --- | --- | --- |
| Celery + Redis 异步 | FastAPI `BackgroundTasks` + PostgreSQL 状态轮询；单实例 | 降低本地启动成本；并发限制仍按数据库校验；正式实现换 Celery |
| MinIO 单桶 | 沿用 2 号 demo 的存储适配层 + 本地目录 | 路径契约不变；正式实现切 MinIO（10 号 §6） |
| 模板/素材/尺寸后台管理 | 只建表、种子与只读接口，不做后台页面 | 生成链路可读取启用配置；配置变更由种子脚本完成 |
| 用户端模板卡片、尺寸下拉 | 后端接受 `template_id` 与自定义宽高；前端仍可固定 1000×1000、不发模板 | 2 号 demo 前端不改；PRD 4 后端能力先就绪 |
| 8 Agent 真实模型 | 全部调用豆包；无桩模式；缺少 Key 时启动失败 | 按用户选择执行真实全链路；质量审核在 `vision_model` 为空时按 PRD 跳过并标记 |
| 内容审核 | 只审生成图，不审上传图 | 覆盖 §8.3 的生成图拦截；上传审核留给正式实现 |
| 设计 Skill | 默认版式兜底（§7.4） | 不改变 §7.2 的输入输出契约 |
| 修复复检 | 实现「审核不通过 → 修复 1 次 → 重生图 → 复检」 | 属于 8 Agent 链路的一部分，无法省略 |
| 同批次并行生图 | 串行 | 与 PRD §13 结论一致，降低限流风险 |
| 高级生图参数（权重、种子） | 后端固定，不暴露 | PRD 本期不向用户暴露 |
| 单张失败自动补齐 | 不自动，用户手动重试 | PRD §13 结论 |
| 整批 30 分钟超时 | 实现，超时阈值可由环境变量缩短用于测试 | 便于演示超时路径，不改变正式默认值 |

---

## 2. 前置与演示配置

### 2.1 前置

本目录假定：

1. 「1-登录界面」最小 demo 的 01~03 已完成。
2. 「2-用户端创作工作台」最小 demo 的 01~07 已完成：
   - 工作台三栏布局、参数面板、上传、会话、聊天可用；
   - `POST /generations/sample`、`GET /generations/{batch_id}`、`POST /generations/{batch_id}/confirm`、单张预览与下载可用；
   - 当前管线是「演示生成管线」（占位 PNG）。
3. 本目录的 01~08 完成后，用真实生成管线替换演示管线内部，**对外接口、批次状态、阶段枚举保持不变**。

### 2.2 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DOUBAO_API_KEY` | 是 | 火山方舟 API Key；缺失时后端启动校验失败，不进入演示 |
| `DOUBAO_BASE_URL` | 是 | 火山方舟 API 地址 |
| `DOUBAO_TEXT_MODEL` | 是 | 规划、商品理解、文案、提示词、修复、平台规范使用的文本模型名 |
| `DOUBAO_IMAGE_MODEL` | 是 | Seedream 图像模型名 |
| `DOUBAO_VISION_MODEL` | 否 | 质量审核视觉模型名；为空时质量审核跳过并标记「未校验」 |
| `DOUBAO_MODERATION_MODEL` | 是 | 生成图内容审核模型名 |
| `BATCH_TIMEOUT_SECONDS` | 否 | 整批超时，默认 `1800`；演示可缩短到 60~120 秒 |
| `STORAGE_DIR` | 否 | 本地存储根目录，沿用 2 号 demo |
| `FONT_PATH` | 否 | 中文字体文件路径；缺省使用后端内置字体 |

> 演示不使用 `model_configs.api_key_ciphertext` 存 Key，Key 只从环境变量读取；`model_configs` 只保存模型名、超时、并发等非敏感字段。正式实现再补密钥加密存储。

### 2.3 种子数据

| 表 | 种子 |
| --- | --- |
| `system_prompts` | 8 条：`planner`、`product_understanding`、`copywriter`、`prompt_builder`、`image_generator`、`quality_reviewer`、`repairer`、`platform_rule`；`platform_rule` 内容含 `{{platform_rules}}` 占位与最小演示规则 |
| `model_configs` | 1 条启用配置：`provider=volcengine_ark`，模型名来自 §2.2，`timeout_seconds=120`、`concurrency=4`、`retry_count=1` |
| `templates` | 2 条启用模板，含名称、风格文案、缩略图占位、提示词模板、版式参考 |
| `material_assets` | 4 条启用素材，覆盖「服饰/室内」「数码/白底」等标签 |
| `size_presets` | 4 条：淘宝/天猫、京东、拼多多、抖音，均为 1000×1000 |
| 权限 | `demo_user` 具备 `user.generate`、`user.history`；`demo_admin` 不具备 |

### 2.4 中文字体

- 后端内置 1 个可商用中文字体（如思源黑体 / Noto Sans SC），用户不可选。
- 字体文件缺失时启动校验失败；合成阶段字体加载失败按「文字合成失败」处理。
- 演示环境不通过网络下载字体。

### 2.5 演示账号

| 用户名 | 密码 | 角色 | 用途 |
| --- | --- | --- | --- |
| `demo_user` | `Demo1234` | `user` | 生成、确认、取消、重试、下载 |
| `demo_admin` | `Demo1234` | `admin` | 验证管理端不具备用户生成权限 |

---

## 3. 接口总览

详细字段、错误码与内部 Agent 契约见 [`接口文档-生图任务最小demo.md`](./接口文档-生图任务最小demo.md)。

| 方法 | 路径 | 权限 | 用途 | 所在 Ticket |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/templates` | `user.generate` | 读取启用中的模板（只读） | 01 |
| GET | `/api/v1/templates/{template_id}/thumbnail` | `user.generate` | 模板缩略图（只读） | 01 |
| GET | `/api/v1/sizes` | `user.generate` | 读取启用中的尺寸预设（只读） | 01 |
| POST | `/api/v1/generations/sample` | `user.generate` | 创建示例批次（沿用 2 号 demo，升级管线） | 03 |
| GET | `/api/v1/generations/{batch_id}` | `user.generate` | 查询批次状态、阶段与图片 | 03 / 04 |
| POST | `/api/v1/generations/{batch_id}/confirm` | `user.generate` | 确认示例，创建全套批次 | 04 |
| POST | `/api/v1/generations/{batch_id}/cancel` | `user.generate` | 取消批次 | 06 |
| POST | `/api/v1/images/{image_id}/regenerate` | `user.generate` | 单张重试 / 重生成 | 07 |
| GET | `/api/v1/images/{image_id}/content` | `user.generate` | 结果区大图预览（沿用 2 号 demo） | 03 / 04 |
| GET | `/api/v1/images/{image_id}/download` | `user.history` | 下载单张 PNG | 04 / 07 |
| GET | `/api/v1/batches/{batch_id}/download` | `user.history` | 下载整套 ZIP + manifest.csv | 08 |

### 3.1 明确不提供的接口

- 全部 `/api/v1/admin/*`，包括模板、素材、尺寸、模型配置、提示词版本的后台增删改。
- `GET /api/v1/generations/{batch_id}/images`：批次状态接口已返回图片列表，最小 demo 不单独提供。
- `GET /api/v1/history`、`GET /api/v1/history/{batch_id}`、`GET/PATCH /api/v1/profile`。
- 上传图内容审核接口（不单独暴露）。
- 批次级「重新生成」接口：整批失败后按 PRD 从批次入口重新生成，最小 demo 不提供该入口。

---

## 4. 任务依赖

```text
2 号 demo 01 工作台骨架与最小数据表
        ↓
4-01 生成数据模型、配置种子与 Agent 运行时
        ↓
4-02 文字留白合成与默认版式
        ↓
4-03 示例批次真实全链路 ←────── 2 号 demo 05 生成示例图与阶段进度
        ↓
4-04 确认全套与详情图生成 ←──── 2 号 demo 06 确认全套与结果网格
        ↓
   ┌────┴─────────────┐
   ↓                  ↓
4-05 失败重试与降级   4-06 取消任务
   ↓
   ┌────┴─────────────┐
   ↓                  ↓
4-07 单张重试/重生成  4-08 整组 ZIP 与 manifest
```

| # | Ticket | 阻塞于 | 交付的可演示行为 |
| --- | --- | --- | --- |
| 01 | [生成数据模型、配置种子与 Agent 运行时](./issues/01-生成数据模型与Agent运行时.md) | 2 号 demo 01 | 表结构与种子就绪；Agent 可编排、可重试、调用落 `agent_runs`；非法状态流转被拒 |
| 02 | [文字留白合成与默认版式](./issues/02-文字留白合成与默认版式.md) | 01 | 基础图 + 文案 → 中文正确、版式正确的 1000×1000 PNG |
| 03 | [示例批次真实全链路](./issues/03-示例批次真实全链路.md) | 02、2 号 demo 05 | 8 Agent 真实调用，产出 1 张带中文文案的示例图，阶段进度可见 |
| 04 | [确认全套与详情图生成](./issues/04-确认全套与详情图生成.md) | 03、2 号 demo 06 | 示例图复用为主图，再生成 5 张详情图，1/6 → 6/6，终态正确 |
| 05 | [失败重试、降级与部分失败](./issues/05-失败重试与降级.md) | 04 | 故障注入下演示 10 次退避、生图 2 次、非核心跳过、部分失败、整批超时 |
| 06 | [取消任务](./issues/06-取消任务.md) | 04 | 生成中取消，停止创建新图，半成品不进历史 |
| 07 | [单张重试与重生成](./issues/07-单张重试与重生成.md) | 05 | 失败张沿用原提示词重试，`attempt_no+1`，旧图 `superseded`，部分失败可回升 `completed` |
| 08 | [整组 ZIP 下载与 manifest.csv](./issues/08-整组ZIP与manifest.md) | 05 | 全套 ZIP、按序号命名、manifest 列出失败张 |

> 06 与 05 可并行；07 依赖 05 的失败路径；08 依赖 05 的部分失败数据才能完整演示 manifest 的失败行。

---

## 5. 验收总口径（演示脚本）

最小 demo 完成时，至少能完整演示以下路径：

1. 配置好 §2.2 的环境变量并启动后端，种子脚本执行成功；`GET /templates`、`GET /sizes` 返回启用项。
2. `demo_user` 登录 → 在工作台填写商品名称、风格、上传 2 张商品图 → 点击「生成示例图」。
3. 结果区按阶段展示：需求理解 → 文案生成 → 提示词构建 → 图像绘制 → 质量审核 → 平台规范 → 文字合成；最终 `sample_ready`，展示 1 张带中文标题与卖点的示例图。
4. 示例图可预览、不可下载；调用下载返回 409 `30005`。
5. 点击「重新生成示例」→ 创建新的 `sample` 批次，旧批次保留；结果区只展示最新示例。
6. 点击「确认并生成全套」→ 二次确认 → 创建 `full` 批次，`completed_count=1`；第 2~6 张详情图串行生成，进度 2/6 → 6/6，终态 `completed`。
7. 全套结果 6 张：第 1 张文件复用示例图，第 2~6 张为详情图，序号与角色正确；6 张成功正式图 `is_history_visible=true`。
8. 单张下载 PNG，文件名符合 `{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`。
9. 整组下载 ZIP，解压后包含 6 张成功图与 `manifest.csv`，CSV 列与内容正确。
10. 故障注入：质量审核不通过 → 修复 → 重生图 → 复检；复检仍不通过该张失败，其余继续，批次 `partially_failed`。
11. 故障注入：生图连续 2 次失败 → 批次立即 `failed`，后续张不再生成。
12. 故障注入：`vision_model` 为空 → 质量审核 `skipped`，示例图仍可完成，`agent_runs` 标记「未校验」。
13. 生成图被内容审核拦截 → 该张失败，提示调整描述或更换商品图，不自动重试；全套批次其余张继续。
14. 生成中点击取消 → 二次确认 → 批次 `cancelled`；不再创建新图；已生成半成品不进入历史。
15. 对 `partially_failed` 批次的失败张点击「重试」→ 新建图片记录，`index` 不变、`attempt_no+1`、旧图 `superseded`；成功后批次变 `completed`。
16. 对成功张点击「重生成」→ 新图替换展示，旧图不在结果区出现，`completed_count` 不超过总数。
17. 同一用户已有 `queued` / `running` 批次时再次生成 → 409 `30003`；`sample_ready` 不阻塞。
18. 用另一个用户的 token 请求批次、图片、下载 → 404 / 403，不泄露数据；`demo_admin` 调用生成接口 → 403 `20005`。
19. 每次 Agent 调用（含重试）在 `agent_runs` 有记录，含 `agent_code`、`status`、`model_name`、Token、耗时、错误信息；8 个 Agent 顺序正确。
20. 整批超时（演示环境用短阈值）→ 未完成部分标记失败；生图未完成则 `failed`，否则 `partially_failed`。

---

## 6. 待确认项

以下事项在接口文档中给出了 demo 默认口径，正式实现前需要与 3、7、9、10 号文档统一：

1. **模型 Key 存储**：demo 从环境变量读取，`model_configs.api_key_ciphertext` 留空；正式实现需补密钥加密与后台配置。
2. **质量审核「未校验」/ 修复「未修复」的标记位置**：demo 写入 `agent_runs.status=skipped` 与 `output_summary`，不新增表字段；若结果区必须展示，需在 10 号增加 `warnings` 或等价字段。
3. **单张重生成允许的批次状态**：demo 仅允许 `completed` / `partially_failed`；`failed` 批次要求从批次入口重新生成，而该入口不在最小 demo 内。
4. **成功张重生成时的 `completed_count`**：demo 仅在替换 `failed` 图时 +1，避免超过 `total_count`；PRD §9.5「成功后加 1」需要按此口径澄清。
5. **公开只读配置接口**：2 号 demo 明确不提供 `GET /templates`、`GET /sizes`；本 demo 因「配置只做读取与种子」新增，需要正式文档确认。
6. **`template_id` 口径**：2 号 demo 要求必须为 `null`；本 demo 后端接受启用模板并写入快照，前端仍可不展示模板卡片。
7. **自定义宽高校验范围**：demo 按 `512~2048`、`8` 的倍数校验，需联调豆包后配置化并写入 9 号。
8. **取消与重生成的幂等键**：PRD 未定义；demo 为取消提供自然幂等（已取消返回 200），为重生成要求 `client_request_id`。
9. **整批超时的实现**：无 Celery 时由 Worker 自身检查已用时长；正式实现需由队列超时与补偿任务保证。
10. **ZIP 内 CSV 编码**：demo 使用 UTF-8 BOM，保证 Excel 中文正常；正式实现确认统一口径。
11. **内容审核模型与接口**：demo 使用 `DOUBAO_MODERATION_MODEL` 调用豆包审核；正式实现需确认审核接口与错误映射。
12. **字体授权**：demo 内置思源黑体 / Noto Sans SC；正式发布前需确认字体商用授权与打包方式。
