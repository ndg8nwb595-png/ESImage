# 生图任务最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `4-生图任务与结果prd.md` §2~§9；`9-后端服务与接口prd.md` §5.5/§5.6；`10-数据模型与存储prd.md` §4.8~§4.18；`2-用户端创作工作台/接口文档-创作工作台最小demo.md` |
| 覆盖范围 | 生图任务最小 demo 的配置读取、示例批次、全套批次、取消、单张重试、文字合成、单张下载与整组 ZIP |
| 文档状态 | 最小 demo 约定；正式实现需与 3、7、9、10 号文档统一 |

> 本文档只描述最小 demo 需要落地的接口与内部契约。未列出的接口（管理后台配置增删改、历史作品、个人中心、批次级重新生成等）不在本次范围内，见第 13 章。

---

## 1. 通用约定

### 1.1 地址与编码

| 项目 | 约定 |
| --- | --- |
| Base URL | `/api/v1` |
| 请求/响应格式 | JSON：`application/json; charset=utf-8`；文件：二进制流；ZIP：`application/zip` |
| 字段命名 | `snake_case` |
| ID | 整数，数据库 `BIGSERIAL` |
| 时间格式 | ISO 8601 带时区偏移，例如 `2026-10-31T10:00:00+08:00` |
| 空值 | `null`，不省略字段 |

### 1.2 统一响应

除文件流外，所有接口返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | int | `0` 成功；非 0 为业务错误码 |
| `message` | string | 面向用户的提示文案 |
| `data` | object / null | 成功数据；业务错误时为 `null` |

### 1.3 HTTP 状态码与业务码

| HTTP | 场景 | 业务码 |
| --- | --- | --- |
| 200 | 成功 | `0` |
| 400 | 参数错误、模板/尺寸不存在 | `1xxx` / `30016` |
| 401 | 未登录、token 失效 | `2xxx` |
| 403 | 无权限、账号不可用 | `2xxx` |
| 404 | 批次、图片、模板不存在或不属于当前用户 | `30004` / `30014` |
| 409 | 并发批次、批次状态不允许、重试进行中 | `30003` / `30005` |
| 500 | 服务端、数据库、存储异常 | `5xxx` |

### 1.4 鉴权与权限

```http
Authorization: Bearer <jwt>
```

- 所有接口必须携带 token；登录复用「1-登录界面」最小 demo。
- 权限码：

| 权限码 | 用途 |
| --- | --- |
| `user.generate` | 配置读取、创建批次、查询批次、确认、取消、单张重试、预览 |
| `user.history` | 单张下载、整组 ZIP 下载 |

- `demo_user` 同时具备两个权限；`demo_admin` 不具备，用于验证角色隔离。
- 越权访问他人批次、图片、配置资源统一返回 404 或 403，不泄露资源是否存在。

### 1.5 幂等

| 场景 | 幂等键 | 规则 |
| --- | --- | --- |
| 创建示例批次 | `client_request_id` | 全局唯一；重复请求返回已有批次，不重复投递 |
| 确认全套 | `client_request_id` | 全局唯一；重复请求返回已创建的全套批次 |
| 单张重试/重生成 | `client_request_id` | 全局唯一；重复请求返回已创建的新图片 |
| 取消批次 | 无 | 自然幂等：已取消返回 200 与取消态 |

### 1.6 并发限制

- 同一用户同时只允许 1 个 `queued` / `running` 批次；`sample_ready` 不计入。
- 确认全套时，被确认的 `sample_ready` 示例批次不参与并发校验。
- 单张重试/重生成不新建批次，但同一批次同时只允许 1 个重试任务。
- 超出限制返回 `30003`（批次并发）或 `30005`（单张并发）。

### 1.7 媒体访问

- 存储桶/目录不公开；所有图片经后端鉴权后流式返回。
- 响应中的 `thumbnail_url`、`content_url` 为**相对路径**；前端用 `fetch` + `Authorization` 读取后转 `blob:` URL，不得把 token 写入 `<img src>` 或 URL 查询串。
- 单张下载与整组 ZIP 使用 `Content-Disposition: attachment`，前端从响应头解析文件名。

---

## 2. 最小 demo 约定

### 2.1 运行形态

| 项目 | demo 处理 | 正式实现 |
| --- | --- | --- |
| 异步任务 | FastAPI `BackgroundTasks` + PostgreSQL 状态轮询；单实例 | Celery + Redis（11 号文档） |
| 对象存储 | 存储适配层 + 本地目录 | MinIO `esimage` 桶（10 号 §6） |
| 配置缓存 | 进程内缓存 60 秒 + 手动刷新 | Redis 缓存（9 号 §2.7） |
| 数据库迁移 | 建表脚本 + 幂等种子脚本 | Alembic（10 号 §10） |

### 2.2 真实豆包与启动校验

- 最小 demo **只走真实豆包**，不提供桩模式。
- 启动时校验 `DOUBAO_API_KEY`、`DOUBAO_BASE_URL`、`DOUBAO_TEXT_MODEL`、`DOUBAO_IMAGE_MODEL`、`DOUBAO_MODERATION_MODEL`；缺失时启动失败并提示缺失项。
- `DOUBAO_VISION_MODEL` 允许为空：质量审核跳过，`agent_runs.status=skipped`，不阻塞生成。
- API Key 只从环境变量读取；`model_configs.api_key_ciphertext` 在 demo 中留空。

### 2.3 配置读取与种子

- 建表并种入：8 条 `system_prompts`、1 条启用 `model_configs`、2 条模板、4 条素材、4 条 1000×1000 尺寸预设。
- 只读接口只返回 `status=active` 的模板、尺寸与启用的模型/提示词；素材不提供公开 HTTP 接口，由商品理解 Agent 内部读取。
- 配置缓存 60 秒；后台无增删改页面，变更通过种子脚本或数据库完成。
- 模板快照写入 `params_snapshot`，后续模板修改不影响历史批次。

### 2.4 生成链路复用

- 示例批次：规划、商品理解、文案、提示词四个 Agent 覆盖全部 6 张图；只渲染第 1 张主图。
- 全套批次：不重复调用上述四个 Agent，直接读取被确认示例批次 `agent_runs.output_full`；只对第 2~6 张执行生图、审核、规范、合成。
- 第 1 张正式图复用示例图文件，不重新生成。

### 2.5 内容审核

- 只审核**生成图**；上传商品图不审核。
- 生成图在质量审核前送豆包内容审核；被拦截时该张失败，不自动重试。
- 审核接口自身失败按生图失败处理，进入每张最多 2 次的尝试。

### 2.6 失败与重试默认值

| 环节 | 尝试次数 | 退避 | 最终失败处理 |
| --- | --- | --- | --- |
| 规划、商品理解、文案、提示词 | 10 | 1/2/4/8/16/30 秒封顶 | 批次 `failed`，记录阶段与错误 |
| 生图执行 | 2 | 无固定退避 | 批次立即 `failed`，不再生成后续张 |
| 质量审核、修复、平台规范 | 10 | 1/2/4/8/16/30 秒封顶 | 跳过并标记「未校验」「未修复」，流程继续 |
| 生成图内容审核 | 2（接口错误） | 无固定退避 | 该张 `failed`；审核拦截不重试 |
| 文字合成 | 1 | 无 | 该张 `failed` |
| 整批超时 | — | — | 未完成部分失败；生图未完成 `failed`，否则 `partially_failed` |

### 2.7 文字合成

- 使用 PRD §7.4 默认版式与内置中文字体，用户不可选字体、颜色、字号。
- 标题上方 15% 区域居中；卖点下方 20% 区域，最多 3 条；左右边距 8%。
- 超长缩字号至下限后截断并记录警告；留白不足时加半透明白底。
- 合成失败该张 `failed`，原因「文字合成失败」。

### 2.8 文件命名与 ZIP

- 单张：`{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`。
- ZIP：`{商品名称}_全套_{yyyyMMddHHmmss}.zip`。
- 非法文件名字符替换为下划线；中文文件名使用 `filename*=UTF-8''`。
- `manifest.csv` 使用 UTF-8 BOM，列：序号、文件名、状态、尺寸、生成时间、失败原因。

### 2.9 轮询与终态

- 前端每 2 秒调用 `GET /generations/{batch_id}`；页面隐藏时降为 10 秒，恢复可见立即刷新。
- 终态：`sample_ready`、`confirmed`、`completed`、`partially_failed`、`failed`、`cancelled`。
- 单张重试后批次可能从 `completed` / `partially_failed` 重新汇总；前端在重试期间继续轮询批次。

### 2.10 与 2 号 demo 的兼容性

- `POST /generations/sample`、`GET /generations/{batch_id}`、`POST /generations/{batch_id}/confirm`、`GET /images/{image_id}/content`、`GET /images/{image_id}/download` 的既有字段与错误码保持不变。
- 本 demo 只做**增量字段**（`source_sample_batch_id`、`image_type`、`attempt_no`、`is_history_visible`）与新增接口；不删除、不改名既有字段。
- `template_id` 从 2 号 demo 的「必须为 `null`」放宽为「可为空或指向启用模板」；前端仍可不展示模板入口。

---

## 3. 接口清单

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/v1/templates` | `user.generate` | 启用中的模板列表 |
| GET | `/api/v1/templates/{template_id}/thumbnail` | `user.generate` | 模板缩略图（只读） |
| GET | `/api/v1/sizes` | `user.generate` | 启用中的尺寸预设 |
| POST | `/api/v1/generations/sample` | `user.generate` | 创建示例批次 |
| GET | `/api/v1/generations/{batch_id}` | `user.generate` | 批次状态、阶段与图片 |
| POST | `/api/v1/generations/{batch_id}/confirm` | `user.generate` | 确认示例，创建全套批次 |
| POST | `/api/v1/generations/{batch_id}/cancel` | `user.generate` | 取消批次 |
| POST | `/api/v1/images/{image_id}/regenerate` | `user.generate` | 单张重试 / 重生成 |
| GET | `/api/v1/images/{image_id}/content` | `user.generate` | 大图预览 |
| GET | `/api/v1/images/{image_id}/download` | `user.history` | 下载单张 PNG |
| GET | `/api/v1/batches/{batch_id}/download` | `user.history` | 下载整组 ZIP |

---

## 4. 配置读取接口

### 4.1 模板列表

```http
GET /api/v1/templates
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "template_id": 5,
        "name": "简约白底",
        "style_text": "简洁白底，柔和棚拍光",
        "thumbnail_url": "/api/v1/templates/5/thumbnail",
        "sort_order": 0
      }
    ],
    "total": 1
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `template_id` | int | 模板 ID |
| `name` | string | 模板名称 |
| `style_text` | string / null | 默认风格文案 |
| `thumbnail_url` | string | 缩略图相对地址 |
| `sort_order` | int | 排序，越小越靠前 |

- 只返回 `status=active` 的模板；按 `sort_order ASC, id ASC` 排序；最多 50 条。
- 不返回 `prompt_template`、`layout_ref` 等内部字段。

#### 失败响应

| 场景 | HTTP | code |
| --- | --- | --- |
| 无 `user.generate` | 403 | 20005 |

### 4.2 模板缩略图

```http
GET /api/v1/templates/{template_id}/thumbnail
Authorization: Bearer <jwt>
```

HTTP 200，返回图片流：

```http
Content-Type: image/webp
Content-Disposition: inline
Cache-Control: private, max-age=3600
```

- 模板不存在或已停用返回 404 `30016`。
- 前端用 `fetch` + `Authorization` 读取后转 `blob:` URL。

### 4.3 尺寸预设

```http
GET /api/v1/sizes
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "size_id": 1,
        "platform_name": "淘宝/天猫",
        "width": 1000,
        "height": 1000,
        "sort_order": 0
      }
    ],
    "total": 1
  }
}
```

- 只返回 `status=active` 的尺寸；按 `sort_order ASC, id ASC` 排序。
- 用户端始终保留自定义宽高；自定义宽高按第 5.1 节校验。

---

## 5. 生成接口

### 5.1 创建示例批次

```http
POST /api/v1/generations/sample
Authorization: Bearer <jwt>
Content-Type: application/json
```

#### 请求体

```json
{
  "client_request_id": "8b0f3f5a-2c4d-4f6e-9a1b-3c5d7e9f0a12",
  "session_id": 12,
  "product_name": "秋季通勤衬衫",
  "style_text": "简洁白底",
  "width": 1000,
  "height": 1000,
  "template_id": 5,
  "upload_ids": [101, 102],
  "requirement_summary": null
}
```

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `client_request_id` | string | 是 | UUID；全局唯一，用于幂等 |
| `session_id` | int / null | 否 | `null` 时后端事务内创建会话；非空时必须是当前用户的 `active` 会话 |
| `product_name` | string | 是 | 去除首尾空格后 1~60 字符；不允许纯空格 |
| `style_text` | string / null | 否 | 1~50 字符；纯空格视为 `null` |
| `width` | int / null | 否 | 省略或 `null` 默认 1000；正整数，demo 校验范围 512~2048 且为 8 的倍数 |
| `height` | int / null | 否 | 同上 |
| `template_id` | int / null | 否 | `null` 或启用中的模板；不存在/停用返回 30016 |
| `upload_ids` | int[] | 否 | 0~5 个；属于当前用户、`active`、未绑定其他会话 |
| `requirement_summary` | object / null | 否 | 省略时使用会话的 `requirement_summary`；显式传入以请求为准 |

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "batch_id": 12,
    "session_id": 12,
    "session_title": "秋季通勤衬衫",
    "batch_type": "sample",
    "status": "queued",
    "total_count": 1,
    "completed_count": 0
  }
}
```

- 响应字段与 2 号 demo 一致；新增 `stage` 不在创建响应中返回，前端通过查询接口获取。
- `total_count=1`：示例批次只渲染 1 张主图；规划与文案仍覆盖 6 张。

#### 处理流程

1. 校验 token、权限、参数、上传图归属、模板存在且启用。
2. 校验并发：当前用户无 `queued` / `running` 批次，否则 30003。
3. `session_id` 为空时，在同一事务内创建会话；标题取商品名称（截断到 50）。
4. 创建 `sample` 批次：`total_count=1`、`completed_count=0`、`status=queued`、`stage=null`；写入 `params_snapshot`、`requirement_summary`、`client_request_id`。
5. 创建 1 条 `index=1`、`image_role=main`、`image_type=sample`、`status=pending` 的图片记录。
6. 提交事务后投递生成管线。
7. 返回批次与会话信息。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 商品名称未填 | 400 | 10002 | 请先填写商品名称 |
| 商品名称超过 60 字符 | 400 | 10004 | 商品名称不能超过 60 个字符 |
| 风格超过 50 字符 | 400 | 10004 | 风格不能超过 50 个字符 |
| 宽高非正整数或超出范围 | 400 | 10003 | 宽高需为 512~2048 的正整数且为 8 的倍数 |
| 模板不存在或已停用 | 404 | 30016 | 模板/素材/尺寸不存在 |
| 上传图超过 5 张/不属于当前用户/已删除/已绑定其他会话 | 400 | 30006 | 上传文件不符合要求 |
| 会话不存在或不属于当前用户 | 404 | 30013 | 会话不存在 |
| 已有生成任务进行中 | 409 | 30003 | 已有生成任务进行中 |
| 无 `user.generate` | 403 | 20005 | 无权限 |

幂等：相同 `client_request_id` 重复提交返回已有批次，不重复创建、不重复投递。

### 5.2 查询批次状态与进度

```http
GET /api/v1/generations/{batch_id}
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200，示例批次：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "batch_id": 12,
    "batch_type": "sample",
    "source_sample_batch_id": null,
    "status": "running",
    "stage": "image_generator",
    "total_count": 1,
    "completed_count": 0,
    "images": [
      {
        "image_id": 88,
        "index": 1,
        "image_role": "main",
        "image_type": "sample",
        "attempt_no": 1,
        "status": "generating",
        "thumbnail_url": null,
        "content_url": "/api/v1/images/88/content",
        "error_message": null,
        "width": 1000,
        "height": 1000,
        "is_history_visible": false
      }
    ],
    "error_message": null,
    "created_at": "2026-10-31T10:00:00+08:00",
    "finished_at": null
  }
}
```

全套批次完成时：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "batch_id": 13,
    "batch_type": "full",
    "source_sample_batch_id": 12,
    "status": "completed",
    "stage": "done",
    "total_count": 6,
    "completed_count": 6,
    "images": [
      {
        "image_id": 88,
        "index": 1,
        "image_role": "main",
        "image_type": "final",
        "attempt_no": 1,
        "status": "success",
        "thumbnail_url": "/api/v1/images/88/thumbnail",
        "content_url": "/api/v1/images/88/content",
        "error_message": null,
        "width": 1000,
        "height": 1000,
        "is_history_visible": true
      }
    ],
    "error_message": null,
    "created_at": "2026-10-31T10:05:00+08:00",
    "finished_at": "2026-10-31T10:05:12+08:00"
  }
}
```

> 示例只展示 1 张；实际全套 `images` 按 `index` 升序返回 6 项。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | int | 批次 ID |
| `batch_type` | string | `sample` / `full` |
| `source_sample_batch_id` | int / null | `full` 批次引用的示例批次；`sample` 为 `null` |
| `status` | string | 批次状态，见 §9 |
| `stage` | string / null | 当前阶段；`queued` 时为 `null` |
| `total_count` | int | 计划张数：示例 1，全套 6 |
| `completed_count` | int | 当前非 `superseded` 的成功图数量；全套初始为 1 |
| `images` | array | 当前每个 `index` 的最新尝试，按 `index` 升序 |
| `images[].image_id` | int | 图片 ID |
| `images[].index` | int | 组内序号，1~6 |
| `images[].image_role` | string | `main` / `detail` |
| `images[].image_type` | string | `sample` / `final` |
| `images[].attempt_no` | int | 第几次尝试 |
| `images[].status` | string | `pending` / `generating` / `success` / `failed` / `cancelled` |
| `images[].thumbnail_url` | string / null | 缩略图相对地址；未生成时为 `null` |
| `images[].content_url` | string / null | 原图相对地址；未生成时为 `null` |
| `images[].error_message` | string / null | 失败原因 |
| `images[].width` / `height` | int / null | 图片尺寸 |
| `images[].is_history_visible` | bool | 是否进入历史作品；示例图、失败图、取消半成品为 `false` |
| `error_message` | string / null | 批次失败原因 |
| `created_at` | string | 创建时间 |
| `finished_at` | string / null | 结束时间 |

`stage` 取值与前端展示：

| `stage` | 前端展示 |
| --- | --- |
| `null` | 排队中 |
| `planner` | 需求理解 |
| `product_understanding` | 需求理解 |
| `copywriter` | 文案生成 |
| `prompt_builder` | 提示词构建 |
| `image_generator` | 图像绘制 |
| `quality_reviewer` | 质量审核 |
| `repairer` | 修复 |
| `platform_rule` | 平台规范 |
| `text_composition` | 文字合成 |
| `done` | 已完成 |

- `images` 只返回每个 `index` 的最新尝试；`superseded` 旧图不返回，保留在后台。
- 全套批次不经过 `planner`、`product_understanding`、`copywriter`、`prompt_builder` 阶段；这些阶段只在示例批次出现。

#### 失败响应

| 场景 | HTTP | code |
| --- | --- | --- |
| 批次不存在或不属于当前用户 | 404 | 30004 |

### 5.3 确认示例并生成全套

```http
POST /api/v1/generations/{batch_id}/confirm
Authorization: Bearer <jwt>
Content-Type: application/json
```

#### 请求体

```json
{
  "client_request_id": "c2d4e6f8-0a1b-2c3d-4e5f-6a7b8c9d0e1f"
}
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "full_batch_id": 13,
    "total_count": 6,
    "status": "queued"
  }
}
```

#### 处理流程

1. 校验 token、权限、参数。
2. 事务内对示例批次加行锁，校验：归属、`batch_type=sample`、状态 `sample_ready`、是该用户最新可确认示例。
3. 校验并发：当前用户无其他 `queued` / `running` 批次；被确认示例不参与。
4. 创建 `full` 批次：`source_sample_batch_id` 指向示例批次，`total_count=6`、`completed_count=1`、`status=queued`、`stage=null`；复制 `params_snapshot` 与 `requirement_summary`。
5. 为示例图新建 `generated_images` 记录：`batch_id=full`、`image_type=final`、`image_role=main`、`index_no=1`、`attempt_no=1`、`status=success`、`source_image_id=示例图`，复用文件路径与尺寸；`is_history_visible=false`。
6. 创建 `index=2~6`、`image_role=detail`、`image_type=final`、`status=pending` 的图片记录。
7. 示例批次状态置 `confirmed`。
8. 提交事务后投递全套生成管线。
9. 返回全套批次 ID。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 批次不存在或不属于当前用户 | 404 | 30004 | 批次不存在 |
| 示例批次状态不是 `sample_ready` | 409 | 30005 | 当前批次状态不允许确认 |
| 不是最新可确认示例 | 409 | 30005 | 该示例不是最新示例，请确认最新示例 |
| 已有生成任务进行中 | 409 | 30003 | 已有生成任务进行中 |
| 无 `user.generate` | 403 | 20005 | 无权限 |

### 5.4 取消批次

```http
POST /api/v1/generations/{batch_id}/cancel
Authorization: Bearer <jwt>
```

#### 请求体

无；如有请求体，忽略内容。

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "batch_id": 12,
    "status": "cancelled",
    "finished_at": "2026-10-31T10:00:30+08:00"
  }
}
```

#### 可取消状态

| 批次类型 | 可取消状态 |
| --- | --- |
| `sample` | `queued`、`running`、`sample_ready` |
| `full` | `queued`、`running` |

- 取消在事务中加行锁；`status=cancelled`、`finished_at` 写入。
- 已取消再次调用返回 200 与当前取消态，幂等。
- Worker 在下一个检查点停止创建新图片；生成中的单张允许完成，但 `is_history_visible=false`。
- 未开始的图片置 `cancelled`；已成功图片保留，但不可下载、不进历史。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 批次不存在或不属于当前用户 | 404 | 30004 | 批次不存在 |
| 批次状态不允许取消 | 409 | 30005 | 当前批次状态不允许取消 |
| 无 `user.generate` | 403 | 20005 | 无权限 |

### 5.5 单张重试 / 重生成

```http
POST /api/v1/images/{image_id}/regenerate
Authorization: Bearer <jwt>
Content-Type: application/json
```

#### 请求体

```json
{
  "client_request_id": "d3e5f7a9-1b2c-3d4e-5f6a-7b8c9d0e1f2a"
}
```

#### 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "image_id": 101,
    "batch_id": 13,
    "index": 3,
    "image_role": "detail",
    "attempt_no": 2,
    "status": "pending"
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `image_id` | int | 新创建的图片 ID |
| `batch_id` | int | 所属全套批次 |
| `index` | int | 原序号，不变 |
| `image_role` | string | `main` / `detail` |
| `attempt_no` | int | 原最大尝试号 + 1 |
| `status` | string | 初始 `pending` |

#### 允许条件

1. 图片属于当前用户。
2. 图片属于 `full` 批次，`image_type=final`。
3. 图片是该 `index` 的当前最新尝试（非 `superseded`）。
4. 批次状态为 `completed` 或 `partially_failed`。
5. 同一批次没有正在进行的重试任务。

#### 处理流程

1. 校验 token、权限、参数、图片归属与批次状态。
2. 事务内对批次/图片加锁，校验无并发重试。
3. 创建新记录：复制原图的 `batch_id`、`user_id`、`session_id`、`image_type`、`image_role`、`index_no`、`prompt`、`negative_prompt`、模型参数；`attempt_no=原最大+1`、`status=pending`、`is_history_visible=false`。
4. 旧记录置 `superseded`、`is_history_visible=false`。
5. 提交事务后投递单张管线：生图（最多 2 次）→ 内容审核 → 质量审核（含修复复检）→ 平台规范 → 文字合成。
6. 返回新图片信息。

#### 结果汇总

- 新图成功：`status=success`、`is_history_visible=true`；结果区只展示新图。
- 新图失败：`status=failed`、`is_history_visible=false`；批次按当前成功图重新汇总。
- `completed_count` 按当前非 `superseded` 成功图数量重新计算；全部成功 → `completed`，部分成功 → `partially_failed`，全部失败 → `failed`。
- 批次 `stage` 在重试期间更新为 `image_generator` / `quality_reviewer` / `platform_rule` / `text_composition`，结束回到 `done`。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 图片不存在或不属于当前用户 | 404 | 30014 | 文件不存在 |
| 图片为示例图、`superseded` 旧图或非 `full` 批次 | 409 | 30005 | 当前图片不可重试 |
| 批次状态不是 `completed` / `partially_failed` | 409 | 30005 | 请从批次入口重新生成 |
| 同一批次已有重试进行中 | 409 | 30005 | 该批次有重试任务进行中 |
| 无 `user.generate` | 403 | 20005 | 无权限 |

---

## 6. 下载接口

### 6.1 大图预览

```http
GET /api/v1/images/{image_id}/content
Authorization: Bearer <jwt>
```

HTTP 200，返回文件流：

```http
Content-Type: image/png
Content-Disposition: inline
Cache-Control: private, max-age=300
```

- 示例图与正式图、当前尝试可预览；`superseded` 旧图不提供预览。
- 失败图没有文件，返回 404 `30014`。
- 不存在或不属于当前用户返回 404 `30014`。

### 6.2 下载单张正式图

```http
GET /api/v1/images/{image_id}/download
Authorization: Bearer <jwt>
```

HTTP 200，返回 PNG 文件流：

```http
Content-Type: image/png
Content-Disposition: attachment; filename*=UTF-8''%E7%A7%8B%E5%AD%A3%E9%80%9A%E5%8B%A4%E8%A1%AC%E8%A1%AB_%E4%B8%BB%E5%9B%BE_1_20261031100512.png
```

#### 下载条件

同时满足：

1. 图片属于当前用户。
2. `image_type=final`。
3. `status=success`。
4. `is_history_visible=true`。
5. 所属批次状态为 `completed` 或 `partially_failed`。
6. 图片是该 `index` 的当前最新尝试（非 `superseded`）。

示例图、失败图、取消任务半成品、`superseded` 旧图不可下载。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 图片不存在或不属于当前用户 | 404 | 30014 | 文件不存在 |
| 示例图确认前下载 | 409 | 30005 | 示例图确认前不可下载 |
| 失败图/取消半成品/被替代旧图 | 409 | 30005 | 当前图片不可下载 |
| 无 `user.history` | 403 | 20005 | 无权限 |

### 6.3 整组 ZIP 下载

```http
GET /api/v1/batches/{batch_id}/download
Authorization: Bearer <jwt>
```

#### 成功响应

HTTP 200：

```http
Content-Type: application/zip
Content-Disposition: attachment; filename*=UTF-8''%E7%A7%8B%E5%AD%A3%E9%80%9A%E5%8B%A4%E8%A1%AC%E8%A1%AB_%E5%85%A8%E5%A5%97_20261031100512.zip
Cache-Control: private, no-store
```

ZIP 内容：

```text
秋季通勤衬衫_主图_1_20261031100512.png
秋季通勤衬衫_详情图_2_20261031100513.png
秋季通勤衬衫_详情图_3_20261031100514.png
...
manifest.csv
```

`manifest.csv` 表头与示例：

```csv
序号,文件名,状态,尺寸,生成时间,失败原因
1,秋季通勤衬衫_主图_1_20261031100512.png,success,1000x1000,2026-10-31T10:05:12+08:00,
2,秋季通勤衬衫_详情图_2_20261031100513.png,success,1000x1000,2026-10-31T10:05:13+08:00,
3,,failed,,,"质量问题未通过"
```

- 仅 `batch_type=full` 且状态 `completed` / `partially_failed` 可下载。
- ZIP 只包含当前非 `superseded`、`status=success` 的正式图。
- manifest 列出全部 6 个序号：成功张给文件名，失败张文件名为空并给出原因。
- CSV 为 UTF-8 BOM，中文表头。
- 没有任何成功图时返回 409 `30005`，不返回空 ZIP。

#### 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 批次不存在或不属于当前用户 | 404 | 30004 | 批次不存在 |
| 非 `full` 批次或状态不允许 | 409 | 30005 | 当前批次不支持整组下载 |
| 没有可下载的图片 | 409 | 30005 | 没有可下载的图片 |
| 存储读取失败 | 500 | 50003 | 存储服务错误 |
| 无 `user.history` | 403 | 20005 | 无权限 |

---

## 7. 内部 Agent 契约

> 本节定义生成管线内部的调用契约，不是公开 HTTP 接口。Agent 输出由服务端校验后落库，前端不直接读取。

### 7.1 Agent 运行时

每次调用包含：

| 字段 | 说明 |
| --- | --- |
| `agent_code` | 8 个 Agent 之一 |
| `batch_id` / `image_id` / `session_id` | 关联上下文，可空 |
| `system_prompt` | 从 `system_prompts` 读取的当前启用内容 |
| `input_payload` | 该 Agent 的输入 JSON |
| `model_name` | 文本或视觉模型名 |
| `timeout_seconds` | 默认取 `model_configs.timeout_seconds` |

返回：

| 字段 | 说明 |
| --- | --- |
| `status` | `success` / `failed` / `skipped` |
| `output` | 校验通过的 JSON 或文件元数据 |
| `model_name` | 实际模型名 |
| `prompt_tokens` / `completion_tokens` | Token；图像/审核不返回时为 0 |
| `latency_ms` | 耗时 |
| `attempts` | 本次总共尝试次数 |
| `error_message` | 失败或跳过原因 |

### 7.2 重试策略

| `agent_code` | 次数 | 退避 | 最终失败 |
| --- | --- | --- | --- |
| `planner` | 10 | 1/2/4/8/16/30 秒封顶 | 批次 `failed` |
| `product_understanding` | 10 | 同上 | 批次 `failed` |
| `copywriter` | 10 | 同上 | 批次 `failed` |
| `prompt_builder` | 10 | 同上 | 批次 `failed` |
| `image_generator` | 2 | 无固定退避 | 批次立即 `failed` |
| `quality_reviewer` | 10 | 1/2/4/8/16/30 秒封顶 | 跳过并标记「未校验」 |
| `repairer` | 10 | 同上 | 跳过并标记「未修复」 |
| `platform_rule` | 10 | 同上 | 跳过并标记「未校验」 |

- 每次尝试写一条 `agent_runs`；成功、失败、跳过都要记录。
- 跳过的 Agent 只写一条 `status=skipped`，不伪造输入输出。

### 7.3 调用顺序

```text
规划
  ↓
商品理解（含素材检索）
  ↓
文案
  ↓
提示词
  ↓
生图执行
  ↓
生成图内容审核
  ├─ 通过 → 质量审核
  │           ├─ 通过 → 平台规范 → 文字合成 → 输出
  │           └─ 不通过 → 修复 → 生图执行 → 质量审核复检
  │                          ├─ 通过 → 平台规范 → 文字合成 → 输出
  │                          └─ 仍不通过 → 该张失败
  └─ 拦截 → 该张失败
```

- 示例批次执行完整链路，只渲染 `index=1`。
- 全套批次复用前四个 Agent 输出，只对 `index=2~6` 执行生图及后续。
- 单张重试只执行生图及后续，不调用前四个 Agent。

### 7.4 规划 Agent

输入：`params_snapshot`、`requirement_summary`、最近 10 轮聊天摘要、聊天意图、模板信息。

输出：

```json
{
  "image_count": 6,
  "images": [
    {
      "index": 1,
      "role": "main",
      "theme": "白底商品主视觉",
      "copy_focus": "整体外观与品牌感",
      "layout_hint": "标题上方，卖点下方"
    }
  ],
  "order": ["product_understanding", "copywriter", "prompt_builder", "image_generator"]
}
```

- `images` 固定 6 项：1 个 `main` + 5 个 `detail`，序号 1~6。
- 主题动态生成，符合角色与电商场景，不重复。

### 7.5 商品理解 Agent

输入：商品名称、上传商品图（视觉理解）、需求摘要、聊天摘要。

输出：

```json
{
  "category": "服饰鞋包",
  "selling_points": ["透气", "不易起球", "百搭"],
  "target_audience": "25~35 岁通勤女性",
  "scenes": ["办公室", "周末出行"],
  "constraints": ["不要出现真人正脸"],
  "material_ids": [12, 18]
}
```

- 调用素材检索工具，从启用素材中选候选；检索不单独写 `agent_runs`。
- 未上传商品图时，输出需标注「无实物参考」。

### 7.6 文案 Agent

输入：商品画像、每张图主题、风格、模板文案结构。

输出 6 个文案块：

```json
{
  "index": 1,
  "title": "轻盈透气 一整天",
  "selling_points": ["冰感面料", "不易起球", "通勤百搭"],
  "body": "适合日常通勤的轻薄款",
  "tone": "简洁有力"
}
```

- 简体中文；标题 6~12 字，卖点每条 4~10 字。
- 不生成价格、促销倒计时等未提供信息。

### 7.7 提示词 Agent

输入：文案块、商品画像、风格、尺寸、模板、素材候选。

输出 6 个提示词：

```json
{
  "index": 1,
  "prompt": "电商主图，浅色背景，商品居中，柔和棚拍光，留出上方标题区和下方卖点区",
  "negative_prompt": "文字乱码，水印，低清晰度，主体变形",
  "whitespace": {
    "top_ratio": 0.18,
    "bottom_ratio": 0.22
  },
  "reference_asset_ids": [12],
  "model_params": {
    "width": 1000,
    "height": 1000
  }
}
```

- 必须显式要求留白；不把大段中文文案写入提示词。
- 高级参数由后端固定，不向用户暴露。

### 7.8 生图执行 Agent

输入：提示词 JSON、上传商品图、参考素材。

输出：基础图文件与元数据：

| 字段 | 说明 |
| --- | --- |
| `file_path` | 基础图存储路径 |
| `width` / `height` | 实际尺寸 |
| `model_name` | 图像模型名 |
| `latency_ms` | 耗时 |
| `prompt_tokens` / `completion_tokens` | 接口返回时记录，否则 0 |
| `moderation_passed` | 生成图内容审核结果 |
| `moderation_message` | 审核失败原因 |

- 有上传图走图生图，无上传图走文生图。
- 单张超时 120 秒；最多 2 次。

### 7.9 质量审核 Agent

输入：基础图、商品画像、提示词。

输出：

```json
{
  "passed": true,
  "issues": [],
  "checks": {
    "product_fidelity": "pass",
    "deformity": "pass",
    "whitespace_available": "pass",
    "compliance": "pass"
  }
}
```

- 使用 `DOUBAO_VISION_MODEL`；未配置时返回 `skipped`，原因「未配置视觉模型」。
- 文字正确性由后端合成保证，不由视觉审核负责。

### 7.10 修复 Agent

输入：审核问题、原提示词、商品画像。

输出：修正后的提示词 JSON，结构与 7.7 的单项一致。

- 最多修复 1 次；修复后重新生图并复检。
- 修复 Agent 失败跳过时标记「未修复」，该张按质量未通过处理。

### 7.11 平台规范 Agent

输入：文案、尺寸、商品类目、`platform_rule` 系统提示词中的 `{{platform_rules}}`。

输出：

```json
{
  "passed": true,
  "issues": [],
  "checks": {
    "size": "pass",
    "prohibited_words": "pass",
    "category_rules": "pass"
  }
}
```

- 规则统一维护在 `platform_rule` 提示词中，不单独建规则表。
- 不通过时该张失败，不自动重试。

### 7.12 素材检索工具

输入：类目、风格、场景关键词。

输出：候选素材 ID 与文件路径列表。

- 只检索 `material_assets.status=active` 的素材。
- 结果写入商品理解 Agent 的 `material_ids`，不单独写 `agent_runs`。
- 素材库为空时返回空列表，不阻塞生成。

### 7.13 `agent_runs` 记录

| 字段 | 说明 |
| --- | --- |
| `session_id` / `batch_id` / `image_id` | 关联上下文 |
| `agent_code` | 8 个 Agent 之一 |
| `status` | `success` / `failed` / `skipped` |
| `model_name` | 实际模型名 |
| `input_summary` / `output_summary` | 摘要 |
| `input_full` / `output_full` | 完整输入输出 |
| `prompt_tokens` / `completion_tokens` | Token |
| `latency_ms` | 耗时 |
| `error_message` | 失败/跳过原因 |

- 重试的每次尝试都写一条；成功路径的最终成功尝试 `status=success`。
- 核心 Agent 失败后批次 `failed`，失败尝试保留可追溯。
- 全套批次不新增规划、商品理解、文案、提示词记录。

### 7.14 全套批次复用契约

- 被确认示例批次的以下 `agent_runs.output_full` 必须存在且可解析：`planner`、`product_understanding`、`copywriter`、`prompt_builder`。
- 全套批次按 `agent_code` 取每条 Agent 的最后一次 `success` 记录；缺失时批次 `failed`，错误信息「示例结果不完整」。
- 复用时按 `index` 对齐：示例计划、文案、提示词的第 2~6 项用于详情图；第 1 项用于主图复用说明，不重新生图。

---

## 8. 文字合成契约

### 8.1 输入

基础图与 `layout_instruction`：

```json
{
  "canvas": { "width": 1000, "height": 1000 },
  "blocks": [
    {
      "type": "title",
      "text": "轻盈透气 一整天",
      "box": { "x": 80, "y": 70, "width": 840, "height": 120 },
      "font_size": 64,
      "font_weight": "bold",
      "color": "#1A1A1A",
      "align": "center"
    },
    {
      "type": "selling_points",
      "items": ["冰感面料", "不易起球", "通勤百搭"],
      "box": { "x": 100, "y": 760, "width": 800, "height": 160 },
      "font_size": 36,
      "color": "#333333",
      "align": "center"
    }
  ]
}
```

### 8.2 默认版式

| 区域 | 规则 |
| --- | --- |
| 画布 | 与批次 `width` × `height` 一致 |
| 标题 | 上方 15% 区域居中；左右边距 8%；字号 64，粗体 |
| 卖点 | 下方 20% 区域；左右边距 8%；最多 3 条；字号 36 |
| 颜色 | 标题 `#1A1A1A`，卖点 `#333333` |
| 对齐 | 居中 |
| 字体 | 内置可商用中文字体，用户不可选 |
| 可读性 | 背景亮度过低时加半透明白底 |

### 8.3 输出与失败

- 输出：合成后的 PNG，尺寸与画布一致。
- 失败原因：字体缺失、图片损坏、画布非法、写文件失败、渲染异常。
- 失败时该张 `status=failed`、`error_message="文字合成失败"`，不产出半成品。

### 8.4 超长处理

- 标题字号可自动缩小，下限 40px；卖点字号下限 24px。
- 仍超出则截断并加省略号，在合成结果中记录 `warnings`。
- 卖点超过 3 条只渲染前 3 条并记录警告。
- 超长不阻塞出图。

---

## 9. 状态机与并发

### 9.1 示例批次

```text
queued → running → sample_ready → confirmed
                 ↘ failed
queued / running / sample_ready → cancelled
```

### 9.2 全套批次

```text
queued → running → completed / partially_failed / failed
queued / running → cancelled
```

### 9.3 单图

```text
pending → generating → success / failed / cancelled
success / failed → superseded
```

### 9.4 迁移约束

1. `confirmed` 只能从 `sample_ready` 进入。
2. `full` 必须引用一个 `confirmed` 的 `sample` 批次。
3. `cancelled` 是终态，不允许恢复。
4. `success` 的单图不允许回退；重生成另建记录。
5. 单张重试成功后，批次可由 `partially_failed` 置为 `completed`。
6. 单张重生成失败时，批次可由 `completed` 置为 `partially_failed`。

### 9.5 并发与可确认示例

1. 同一用户同时只允许 1 个 `queued` / `running` 批次；`sample_ready` 不计入。
2. 只有该用户最近创建的、仍为 `sample_ready` 的示例批次可确认；旧示例返回 30005。
3. 确认时对示例批次加行锁；重复确认或状态不符返回 30005。
4. `sample_ready` 不阻塞重新生成示例或确认最新示例。
5. 单张重试不新建批次；同一批次同时只允许 1 个重试任务。

### 9.6 取消与重试的交互

- 取消后批次为 `cancelled`，单张重试返回 30005。
- 重试进行中取消：取消优先；新图允许完成但 `is_history_visible=false`，批次保持 `cancelled`。
- 取消与确认并发：以行锁后的最终状态为准，非法操作返回 30005。

### 9.7 `completed_count` 口径

- `sample`：成功为 1，否则 0。
- `full`：初始为 1（复用示例图）；按当前非 `superseded` 的成功图数量重新计算。
- 失败张重试成功后 +1；成功张重生成成功不变；成功张重生成失败 -1。
- 不小于 0，不大于 `total_count`。

---

## 10. 错误码

| code | HTTP | 含义 | 本 demo 使用场景 |
| --- | --- | --- | --- |
| 0 | 200 | 成功 | 全部 |
| 10001 | 400 | 参数错误 | 通用 |
| 10002 | 400 | 缺少必填参数 | 商品名称、批次 ID |
| 10003 | 400 | 参数格式错误 | 宽高非正整数/超出范围 |
| 10004 | 400 | 参数超出范围 | 商品名称、风格超长 |
| 20002 | 401 | 登录已过期 | token 过期 |
| 20003 | 401 | token 无效 | 未携带/签名错误/版本不符 |
| 20004 | 403 | 账号不可用 | 账号禁用/删除 |
| 20005 | 403 | 无权限 | 缺少 `user.generate` / `user.history` |
| 30001 | — | 模型调用失败 | 写入批次/图片错误与 `agent_runs`，不直接返回 HTTP |
| 30003 | 409 | 已有生成任务进行中 | 创建示例/确认全套 |
| 30004 | 404 | 批次不存在 | 查询/确认/取消/整组下载 |
| 30005 | 409 | 批次或图片状态不允许该操作 | 确认非 `sample_ready`、取消、重试、示例图下载 |
| 30006 | 400 | 上传文件不符合要求 | 上传图归属/数量/状态 |
| 30007 | — | 内容未通过审核 | 生成图失败原因，写入图片错误信息 |
| 30013 | 404 | 会话不存在 | 创建示例 |
| 30014 | 404 | 文件不存在或归档不可用 | 图片预览/下载/重试 |
| 30016 | 404 | 模板/素材/尺寸不存在 | 模板不存在或停用 |
| 50001 | 500 | 系统内部错误 | 兜底 |
| 50002 | 500 | 数据库错误 | 兜底 |
| 50003 | 500 | 存储服务错误 | 图片读写、ZIP 生成 |

错误响应统一为：

```json
{
  "code": 30005,
  "message": "当前批次状态不允许取消",
  "data": null
}
```

---

## 11. 数据结构

### 11.1 批次

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | int | `generation_batches.id` |
| `batch_type` | string | `sample` / `full` |
| `source_sample_batch_id` | int / null | `full` 引用的示例批次 |
| `status` | string | 批次状态 |
| `stage` | string / null | 当前阶段 |
| `total_count` | int | 计划张数 |
| `completed_count` | int | 当前成功张数 |
| `images` | array | 当前最新尝试的图片 |
| `error_message` | string / null | 批次失败原因 |
| `created_at` / `finished_at` | string / null | 时间 |

### 11.2 图片

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `image_id` | int | `generated_images.id` |
| `index` | int | 序号 1~6 |
| `image_role` | string | `main` / `detail` |
| `image_type` | string | `sample` / `final` |
| `attempt_no` | int | 尝试号 |
| `status` | string | 图片状态 |
| `thumbnail_url` / `content_url` | string / null | 媒体相对地址 |
| `error_message` | string / null | 失败原因 |
| `width` / `height` | int / null | 尺寸 |
| `is_history_visible` | bool | 是否进入历史作品 |

### 11.3 Agent 调用

字段见 §7.13；公开接口不返回 `agent_runs`，由后台追溯。

### 11.4 配置

| 实体 | 主要字段 |
| --- | --- |
| 模板 | `template_id`、`name`、`style_text`、`thumbnail_url`、`sort_order` |
| 尺寸 | `size_id`、`platform_name`、`width`、`height`、`sort_order` |
| 素材（内部） | `material_id`、`name`、`file_path`、`tags`、`style_tags`、`sort_order` |

### 11.5 参数快照

```json
{
  "product_name": "秋季通勤衬衫",
  "style_text": "简洁白底",
  "width": 1000,
  "height": 1000,
  "template_id": 5,
  "template_name": "简约白底",
  "upload_ids": [101, 102],
  "image_composition": "1 main + 5 detail",
  "requirement_summary": {
    "product_name": "秋季通勤衬衫",
    "category": null,
    "selling_points": [],
    "target_audience": null,
    "scenes": [],
    "tone": null,
    "constraints": []
  },
  "created_at": "2026-10-31T10:00:00+08:00"
}
```

- 写入 `generation_batches.params_snapshot`；生成过程中修改前端参数不影响已创建批次。
- 后台追溯以快照为准。

---

## 12. 与 9 / 10 号文档的差异与待统一项

| 项目 | 本文 demo 口径 | 9 / 10 号或 2 号 demo | 处理建议 |
| --- | --- | --- | --- |
| 模型 Key | 环境变量读取，`api_key_ciphertext` 留空 | 10 号定义密文列 | 正式实现补加密与后台配置 |
| 质量审核跳过标记 | `agent_runs.status=skipped` + `output_summary` | 10 号无 `warnings` 字段 | 若需结果区展示，增加字段后再统一 |
| 单张重试允许状态 | 仅 `completed` / `partially_failed` | PRD §8.2 提到失败批次从批次入口 | 正式实现补批次级重新生成 |
| 成功张重生成后的计数 | 按当前成功图重新计算 | PRD §9.5「成功后加 1」 | 明确按当前成功图口径 |
| 公开配置接口 | 新增 `GET /templates`、`/sizes`、模板缩略图 | 2 号 demo 明确不提供 | 正式文档确认是否保留 |
| `template_id` | 可为 `null` 或启用模板 | 2 号 demo 要求必须为 `null` | 前端仍可不展示模板入口 |
| 自定义宽高 | 512~2048、8 的倍数 | 9 号未给范围 | 联调豆包后配置化 |
| 素材接口 | 不提供公开 HTTP，内部服务读取 | 9 号列出 `GET /materials` | 正式实现确认是否需要 HTTP |
| 取消/重试幂等 | 取消自然幂等；重试要求 `client_request_id` | 9 号未定义 | 正式实现统一幂等口径 |
| 整批超时 | Worker 自检 `BATCH_TIMEOUT_SECONDS` | 11 号建议队列超时 | 正式实现用 Celery 超时与补偿 |
| ZIP CSV 编码 | UTF-8 BOM | 9 号未定义 | 正式实现统一 |
| 生成图审核 | 只审生成图 | PRD §8.3 含上传图 | 正式实现补上传审核 |
| 单图列表 | 只返回每个 `index` 最新尝试 | 10 号保留 `superseded` 记录 | 后台查询保留全部，公开接口不返回旧图 |

---

## 13. 未实现接口

以下接口明确不在最小 demo 内，调用方不得依赖：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/generations/{batch_id}/images` | 批次状态接口已含图片列表 |
| GET | `/api/v1/materials` | 素材仅内部检索使用 |
| POST | `/api/v1/generations/{batch_id}/retry` | 批次级重新生成 |
| GET | `/api/v1/history` | 历史作品列表 |
| GET | `/api/v1/history/{batch_id}` | 历史批次详情 |
| GET / PATCH | `/api/v1/profile` | 个人中心 |
| — | `/api/v1/admin/*` | 全部管理端接口，含模板/素材/尺寸/模型配置/提示词版本 |
| POST | `/api/v1/uploads` 审核相关 | 上传图内容审核 |

---

## 14. 验收调用序列

| 步骤 | 调用 | 期望 |
| --- | --- | --- |
| 1 | `POST /auth/login`（复用 1 号 demo） | 返回 token 与 `user.generate`、`user.history` |
| 2 | `GET /templates` | 返回启用模板；停用模板不出现 |
| 3 | `GET /sizes` | 返回 4 条 1000×1000 预设 |
| 4 | `POST /generations/sample` | 返回 `batch_id`、`status=queued`、`total_count=1` |
| 5 | `GET /generations/{batch_id}` 轮询 | `stage` 依次推进，最终 `sample_ready`，1 张示例图 |
| 6 | `GET /images/{sample_image_id}/content` | 可预览带中文文案的示例图 |
| 7 | `GET /images/{sample_image_id}/download` | 409 `30005`，示例图确认前不可下载 |
| 8 | `POST /generations/sample`（新 `client_request_id`） | 创建新示例批次，旧批次保留 |
| 9 | `POST /generations/{latest_sample_batch_id}/confirm` | 返回 `full_batch_id`、`total_count=6`、`status=queued` |
| 10 | `GET /generations/{full_batch_id}` 轮询 | `completed_count` 1→6，`status=completed`，6 张图 |
| 11 | `GET /images/{full_image_id}/download` | 200，PNG，文件名符合规则 |
| 12 | `GET /batches/{full_batch_id}/download` | 200，ZIP；解压含 6 图 + manifest.csv |
| 13 | 故障注入：生图连续失败 | 批次 `failed`，后续张不再生成 |
| 14 | 故障注入：平台规范不通过 | 该张 `failed`，其余继续，批次 `partially_failed` |
| 15 | `POST /generations/{running_batch_id}/cancel` | 200，`status=cancelled`；再调用仍 200 |
| 16 | `POST /images/{failed_image_id}/regenerate` | 返回新 `image_id`、`attempt_no+1`、`pending` |
| 17 | `GET /generations/{batch_id}` | 新图替换旧图，旧图不返回；批次可能回到 `completed` |
| 18 | 已有 `queued` / `running` 批次时再次创建 | 409 `30003` |
| 19 | 用另一个用户 token 请求批次/图片/ZIP | 404 或 403 |
| 20 | `demo_admin` token 调生成接口 | 403 `20005` |

### 14.1 创建示例批次

```bash
curl -X POST http://localhost:8000/api/v1/generations/sample \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "client_request_id": "8b0f3f5a-2c4d-4f6e-9a1b-3c5d7e9f0a12",
    "session_id": 12,
    "product_name": "秋季通勤衬衫",
    "style_text": "简洁白底",
    "width": 1000,
    "height": 1000,
    "template_id": 5,
    "upload_ids": [101, 102]
  }'
```

### 14.2 确认全套

```bash
curl -X POST http://localhost:8000/api/v1/generations/12/confirm \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_request_id":"c2d4e6f8-0a1b-2c3d-4e5f-6a7b8c9d0e1f"}'
```

### 14.3 取消

```bash
curl -X POST http://localhost:8000/api/v1/generations/12/cancel \
  -H "Authorization: Bearer $TOKEN"
```

### 14.4 单张重试

```bash
curl -X POST http://localhost:8000/api/v1/images/88/regenerate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"client_request_id":"d3e5f7a9-1b2c-3d4e-5f6a-7b8c9d0e1f2a"}'
```

### 14.5 整组下载

```bash
curl -L -o "result.zip" \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/batches/13/download
```
