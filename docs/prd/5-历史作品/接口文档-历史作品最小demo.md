# 历史作品最小 demo 接口文档

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.1-demo |
| 上游依据 | `5-历史作品prd.md` §2~§9；`9-后端服务与接口prd.md` §2/§3/§5.6；`10-数据模型与存储prd.md` §4.9/§4.10/§6/§7；`2-用户端创作工作台/接口文档-创作工作台最小demo.md` §1/§6.4/§6.5；`4-生图任务与结果/README.md` 08 切片 |
| 覆盖范围 | 历史列表、批次详情、缩略图、大图预览、单张下载、整组 ZIP、归档读取 |
| 文档状态 | 最小 demo 约定；正式实现需与 9 号文档统一 |

> 本文档只描述历史作品最小 demo 需要落地的接口。会话、上传、生成、确认全套、管理后台与个人中心接口不在本次范围内；预览与单张下载复用 2 号 demo 的既有契约，本文只写历史页的差异。

---

## 1. 通用约定

### 1.1 地址与编码

| 项目 | 约定 |
| --- | --- |
| Base URL | `/api/v1` |
| 请求/响应格式 | JSON：`application/json; charset=utf-8`；文件流：`application/octet-stream` / `image/png` / `image/webp` / `application/zip` |
| 字段命名 | `snake_case` |
| ID | 整数，数据库 `BIGSERIAL` |
| 时间格式 | ISO 8601 带时区偏移，例如 `2026-10-31T10:00:00+08:00` |
| 空值 | `null`，不省略字段 |
| 时区 | 服务端统一 Asia/Shanghai；前端按浏览器本地时区展示 |

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
| `code` | int | `0` 表示成功；非 0 为业务错误码 |
| `message` | string | 面向用户的提示文案 |
| `data` | object / null | 成功时的数据；业务错误时为 `null` |

### 1.3 HTTP 状态码与业务码

| HTTP | 场景 | 业务码 |
| --- | --- | --- |
| 200 | 成功 | `0` |
| 400 | `page` 不是正整数 | `10001` |
| 401 | 未登录、token 失效 | `20002` / `20003` |
| 403 | 账号不可用 | `20004` |
| 403 | 缺少 `user.history` | `20005` |
| 403 | 访问他人批次 | `20005` |
| 404 | 批次不存在、不是 `full`、状态不在历史范围 | `30004` |
| 404 | 图片/缩略图不存在或不属于当前用户、归档不可用 | `30014` |
| 409 | 当前图片不可下载 | `30005` |
| 409 | 当前批次不可整组下载 | `30005` |
| 500 | 服务端、数据库、存储异常 | `5xxx` |

### 1.4 鉴权与权限

```http
Authorization: Bearer <jwt>
```

- 除登录接口外，所有接口必须携带 token，复用「1-登录界面」最小 demo。
- 后端每次请求校验 token 签名、过期时间、`token_version`、账号状态与接口权限。
- 历史作品权限：

| 权限码 | 用途 |
| --- | --- |
| `user.history` | 历史列表、批次详情、单张下载、整组 ZIP |
| `user.generate` | 结果区预览；历史页不作为必需权限 |

- `/images/{image_id}/content` 与 `/images/{image_id}/thumbnail` 接受 `user.history` **或** `user.generate`，用于同时兼容历史页与创作台结果区。
- 管理员/超管不通过历史页查看用户作品；仅当账号同时拥有 `user` 角色与 `user.history` 时可见。

### 1.5 分页

历史列表固定每页 20 条：

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | int | 否 | 1 | 从 1 开始；必须为正整数 |

- 不接受 `page_size`；传入时忽略，响应始终返回 `page_size=20`。
- 页码超过总页数时返回空 `items`，`total` 保持正确。

响应结构：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20
}
```

### 1.6 媒体文件访问

- 存储桶/目录不公开；所有图片经后端鉴权后流式返回。
- 响应中的 `cover_thumbnail_url`、`thumbnail_url`、`content_url` 均为相对路径，前端拼接 Base URL 后用 `fetch` + `Authorization` 读取，转 `blob:` URL 展示；不得把 token 写进 `<img src>` 或查询串。
- 缩略图读取接口为历史 demo 新增约定，正式实现需写入 9 号。

---

## 2. 最小 demo 约定

### 2.1 数据来源

| 项目 | demo 处理 | 正式实现 |
| --- | --- | --- |
| 批次与图片 | 读取 2 号 demo 生成的 `generation_batches` / `generated_images`；占位 PNG 即可 | 4 号真实 8 Agent 管线，字段与状态不变 |
| 部分失败批次 | 种子夹具提供 5 成功 + 1 失败 | 4 号 demo 05 真实失败降级 |
| 对象存储 | 沿用 2 号 demo 的存储适配层 + 本地目录 | MinIO `esimage` 单桶（10 号 §6） |
| 归档 | 种子模拟 `archived_at` 与 `archive/` 前缀 | 每日 03:00 归档任务（10 号 §7.2） |
| 异步任务 | 不使用；ZIP 同步流式返回 | 维持同步；单批最多 6 张 PNG |

### 2.2 历史可见性

历史接口只读取满足以下全部条件的记录：

1. `generation_batches.user_id` = 当前用户。
2. `generation_batches.batch_type = 'full'`。
3. `generation_batches.status IN ('completed','partially_failed')`。
4. `generated_images.image_type = 'final'`。
5. `generated_images.status = 'success'`。
6. `generated_images.is_history_visible = true`。

示例图（`image_type=sample`）、失败图、取消批次半成品、`superseded` 旧图一律不返回。

### 2.3 缩略图

- 缩略图始终读取 `thumbnails/` 热存储，不因归档而切换路径。
- 生成图缩略图约定为 WebP、最大宽度 400px（10 号 §6.3）；demo 占位图可为 PNG，`Content-Type` 以实际文件为准。
- 缩略图缺失时返回 404 `30014`，前端显示占位图与「图片加载失败」。

### 2.4 时间

- 列表与详情的「生成时间」统一取批次 `created_at`。
- 单张下载与 ZIP 文件名中的时间戳取图片 `created_at`，格式 `yyyyMMddHHmmss`，按 Asia/Shanghai 计算。
- ZIP 文件名中的时间戳取批次 `created_at`，格式同上。

### 2.5 归档读取

- `generated_images.archived_at` 非空时，原件路径为 `archive/{file_path}`；为空时使用 `file_path`。
- 归档读取超时由 `ARCHIVE_READ_TIMEOUT_SECONDS` 控制，默认 60 秒。
- 归档不可用统一返回 404 `30014`，`message` 为「文件归档中，请稍后重试」，并记录错误日志。
- 缩略图不走归档路径。

### 2.6 种子夹具

01 切片提供的种子至少包含：

| 夹具 | 数量 | 用途 |
| --- | --- | --- |
| `completed` 全套批次（6 张成功） | 21 | 分页、封面、详情、下载 |
| `partially_failed` 全套批次（5 成功 + 1 失败） | 1 | 部分失败展示、manifest 失败行 |
| `sample_ready` / `confirmed` 示例批次 | 1 | 验证示例不进历史 |
| `failed` 全套批次 | 1 | 验证失败批次不进历史 |
| 含 `superseded` 旧图的全套批次 | 1 | 验证旧图不展示、不上封面 |
| `archived_at` 非空的全套批次 | 1 | 归档预览、下载与 ZIP |
| 其他用户的全套批次 | 1 | 越权 403；测试脚本临时种入并清理 |

---

## 3. 接口清单

| 方法 | 路径 | 权限 | 用途 |
| --- | --- | --- | --- |
| GET | `/api/v1/history` | `user.history` | 历史批次分页 |
| GET | `/api/v1/history/{batch_id}` | `user.history` | 批次详情与成功图片列表 |
| GET | `/api/v1/images/{image_id}/thumbnail` | `user.history` 或 `user.generate` | 缩略图读取（demo 新增） |
| GET | `/api/v1/images/{image_id}/content` | `user.history` 或 `user.generate` | 大图预览（复用 2 号 demo，权限放宽） |
| GET | `/api/v1/images/{image_id}/download` | `user.history` | 单张下载（复用 2 号 demo） |
| GET | `/api/v1/batches/{batch_id}/download` | `user.history` | 整组 ZIP + `manifest.csv` |

---

## 4. 历史列表

```http
GET /api/v1/history?page=1
Authorization: Bearer <jwt>
```

### 4.1 请求参数

| 参数 | 类型 | 必填 | 默认 | 规则 |
| --- | --- | --- | --- | --- |
| `page` | int | 否 | 1 | 正整数；非正整数返回 400 `10001` |

### 4.2 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [
      {
        "batch_id": 13,
        "product_name": "秋季通勤衬衫",
        "main_count": 1,
        "detail_count": 5,
        "success_count": 6,
        "total_count": 6,
        "cover_image_id": 88,
        "cover_thumbnail_url": "/api/v1/images/88/thumbnail",
        "created_at": "2026-10-31T10:05:00+08:00"
      }
    ],
    "total": 21,
    "page": 1,
    "page_size": 20
  }
}
```

### 4.3 字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | int | 全套批次 ID |
| `product_name` | string | 批次商品名称快照 |
| `main_count` | int | 计划主图数；全套批次固定 1 |
| `detail_count` | int | 计划详情图数；由 `total_count - 1` 得出，固定 5 |
| `success_count` | int | 该批次历史可见的成功图数量 |
| `total_count` | int | 批次计划张数；全套批次固定 6 |
| `cover_image_id` | int | 封面图片 ID；取序号最小的成功图 |
| `cover_thumbnail_url` | string | 封面缩略图相对地址；需带 token 读取 |
| `created_at` | string | 批次生成时间，列表按此倒序 |

### 4.4 过滤与排序

- 过滤条件见 §2.2；每个批次至少有一张历史可见的成功图才会出现。
- 排序：`created_at DESC`，其次 `id DESC`。
- `total` 为符合条件的批次总数，不是图片总数。

### 4.5 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| `page` 非正整数 | 400 | 10001 | 页码参数错误 |
| 未携带或无效 token | 401 | 20003 | 请先登录 |
| token 过期 | 401 | 20002 | 登录已过期，请重新登录 |
| 缺少 `user.history` | 403 | 20005 | 无权限 |
| 账号禁用/删除 | 403 | 20004 | 账号不可用 |

---

## 5. 批次详情

```http
GET /api/v1/history/{batch_id}
Authorization: Bearer <jwt>
```

### 5.1 成功响应

HTTP 200：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "batch_id": 13,
    "product_name": "秋季通勤衬衫",
    "style_text": "简洁白底",
    "width": 1000,
    "height": 1000,
    "main_count": 1,
    "detail_count": 5,
    "success_count": 5,
    "total_count": 6,
    "status": "partially_failed",
    "created_at": "2026-10-31T10:05:00+08:00",
    "images": [
      {
        "image_id": 88,
        "index": 1,
        "image_role": "main",
        "width": 1000,
        "height": 1000,
        "thumbnail_url": "/api/v1/images/88/thumbnail",
        "content_url": "/api/v1/images/88/content",
        "created_at": "2026-10-31T10:05:12+08:00"
      },
      {
        "image_id": 89,
        "index": 2,
        "image_role": "detail",
        "width": 1000,
        "height": 1000,
        "thumbnail_url": "/api/v1/images/89/thumbnail",
        "content_url": "/api/v1/images/89/content",
        "created_at": "2026-10-31T10:05:14+08:00"
      }
    ]
  }
}
```

> 示例只展示前 2 张；实际 `completed` 批次返回 6 张，`partially_failed` 返回全部成功图。

### 5.2 字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `batch_id` | int | 批次 ID |
| `product_name` | string | 商品名称快照 |
| `style_text` | string / null | 风格文本快照；未填写为 `null` |
| `width` / `height` | int | 批次尺寸 |
| `main_count` / `detail_count` | int | 计划主图数 / 详情图数 |
| `success_count` | int | 历史可见成功图数量 |
| `total_count` | int | 计划张数 |
| `status` | string | `completed` 或 `partially_failed` |
| `created_at` | string | 批次生成时间 |
| `images` | array | 成功图片列表，按 `index` 升序 |
| `images[].image_id` | int | 图片 ID |
| `images[].index` | int | 组内序号，从 1 开始 |
| `images[].image_role` | string | `main` / `detail` |
| `images[].width` / `height` | int / null | 图片尺寸；未生成为 `null` |
| `images[].thumbnail_url` | string | 缩略图相对地址 |
| `images[].content_url` | string | 原图相对地址 |
| `images[].created_at` | string | 图片生成时间 |

- 不返回 `prompt`、`negative_prompt`、`model_name`、Token、`params_snapshot`。
- 部分失败批次不返回失败图，也不返回失败占位项。

### 5.3 处理规则

1. 校验 token、权限与 `user.history`。
2. 查询批次；不存在返回 404 `30004`。
3. 批次 `user_id` 不是当前用户返回 403 `20005`。
4. 批次不是 `full`，或状态不是 `completed` / `partially_failed`，返回 404 `30004`。
5. 按 §2.2 查询成功图片，按 `index` 升序返回。

### 5.4 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 批次不存在 | 404 | 30004 | 批次不存在 |
| 批次属于其他用户 | 403 | 20005 | 无权限 |
| 示例批次、失败批次或其他状态 | 404 | 30004 | 批次不存在 |
| 缺少 `user.history` | 403 | 20005 | 无权限 |
| 未登录 / token 失效 | 401 | 20002 / 20003 | 登录已过期，请重新登录 |

---

## 6. 缩略图读取（demo 约定）

```http
GET /api/v1/images/{image_id}/thumbnail
Authorization: Bearer <jwt>
```

### 6.1 权限与范围

- 当前用户本人图片；接受 `user.history` 或 `user.generate`。
- 可读取本人任意状态的生成图缩略图（结果区也需要读取示例图缩略图）；历史页只会请求历史可见图片。
- 缩略图始终从 `thumbnails/` 读取，不进入 `archive/`。

### 6.2 成功响应

HTTP 200，返回文件流：

```http
Content-Type: image/webp
Content-Disposition: inline
Cache-Control: private, max-age=3600
```

> demo 占位缩略图可能为 `image/png`，以实际存储的 MIME 为准。

### 6.3 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 图片不存在、不属于当前用户、缩略图缺失 | 404 | 30014 | 文件不存在 |
| 缺少 `user.history` 与 `user.generate` | 403 | 20005 | 无权限 |
| 未登录 / token 失效 | 401 | 20002 / 20003 | 登录已过期，请重新登录 |

---

## 7. 大图预览（复用）

```http
GET /api/v1/images/{image_id}/content
Authorization: Bearer <jwt>
```

### 7.1 与 2 号 demo 的差异

| 项目 | 2 号 demo | 历史 demo |
| --- | --- | --- |
| 权限 | `user.generate` | `user.history` 或 `user.generate` |
| 归档路径 | 未定义 | `archived_at` 非空时读取 `archive/{file_path}` |
| 响应 | `image/png` 文件流，`Content-Disposition: inline` | 不变 |
| 错误 | 404 `30014` | 不变；归档不可用同样 30014 |

- 响应头、缓存策略、所有权校验沿用 2 号 demo §6.4。
- 历史页只对详情接口返回的图片 ID 发起请求。

### 7.2 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 图片不存在或不属于当前用户 | 404 | 30014 | 文件不存在 |
| 归档文件暂不可用 | 404 | 30014 | 文件归档中，请稍后重试 |
| 缺少 `user.history` 与 `user.generate` | 403 | 20005 | 无权限 |
| 未登录 / token 失效 | 401 | 20002 / 20003 | 登录已过期，请重新登录 |

---

## 8. 单张下载（复用）

```http
GET /api/v1/images/{image_id}/download
Authorization: Bearer <jwt>
```

### 8.1 下载条件

同时满足：

1. 图片属于当前用户。
2. `image_type=final`。
3. `status=success`。
4. `is_history_visible=true`。
5. 所属批次 `batch_type=full`，状态为 `completed` 或 `partially_failed`。

示例图、失败图、取消半成品、`superseded` 旧图不可下载。

### 8.2 成功响应

HTTP 200，返回 PNG：

```http
Content-Type: image/png
Content-Disposition: attachment; filename*=UTF-8''%E7%A7%8B%E5%AD%A3%E9%80%9A%E5%8B%A4%E8%A1%AC%E8%A1%AB_%E4%B8%BB%E5%9B%BE_1_20261031100512.png
Cache-Control: no-store
```

### 8.3 文件命名

- 格式：`{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`。
- 商品名称取批次快照。
- 非法字符替换：`/ \ : * ? " < > |`、控制字符（`0x00`~`0x1F`）、结尾的点与空格，统一替换为 `_`。
- 时间戳取图片 `created_at`，按 Asia/Shanghai 格式化。
- `Content-Disposition` 使用 RFC 5987 `filename*=UTF-8''` 编码；前端解析失败时按同一规则自行拼装。

### 8.4 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 图片不存在或不属于当前用户 | 404 | 30014 | 文件不存在 |
| 示例图确认前下载、失败图、取消半成品、被替代旧图 | 409 | 30005 | 当前图片不可下载 |
| 归档文件暂不可用 | 404 | 30014 | 文件归档中，请稍后重试 |
| 缺少 `user.history` | 403 | 20005 | 无权限 |
| 未登录 / token 失效 | 401 | 20002 / 20003 | 登录已过期，请重新登录 |

---

## 9. 整组 ZIP 下载

```http
GET /api/v1/batches/{batch_id}/download
Authorization: Bearer <jwt>
```

### 9.1 允许的批次

- 当前用户本人。
- `batch_type=full`。
- 状态为 `completed` 或 `partially_failed`。

### 9.2 成功响应

HTTP 200，同步流式返回：

```http
Content-Type: application/zip
Content-Disposition: attachment; filename*=UTF-8''%E7%A7%8B%E5%AD%A3%E9%80%9A%E5%8B%A4%E8%A1%AC%E8%A1%AB_%E5%85%A8%E5%A5%97_20261031100500.zip
Cache-Control: no-store
```

- ZIP 文件名：`{商品名称}_全套_{yyyyMMddHHmmss}.zip`。
- 商品名称按 §8.3 同一规则清洗；时间戳取批次 `created_at`。

### 9.3 ZIP 结构

```text
秋季通勤衬衫_主图_1_20261031100512.png
秋季通勤衬衫_详情图_2_20261031100514.png
秋季通勤衬衫_详情图_3_20261031100516.png
秋季通勤衬衫_详情图_4_20261031100518.png
秋季通勤衬衫_详情图_5_20261031100520.png
秋季通勤衬衫_详情图_6_20261031100522.png
manifest.csv
```

- 只包含成功图片，不包含缩略图、提示词或其他文件。
- 图片按 `index` 升序写入；`manifest.csv` 位于 ZIP 根目录。
- 部分失败时，缺少的序号不产生图片文件，但 manifest 仍保留该行。
- 单个图片从热存储或 `archive/` 读取，规则见 §11。

### 9.4 manifest.csv

编码 UTF-8 BOM；首行为中文表头；字段含逗号、引号或换行时按 CSV 规则加引号并转义。

```csv
序号,文件名,状态,宽度,高度,生成时间,失败原因
1,秋季通勤衬衫_主图_1_20261031100512.png,success,1000,1000,2026-10-31T10:05:12+08:00,
2,秋季通勤衬衫_详情图_2_20261031100514.png,success,1000,1000,2026-10-31T10:05:14+08:00,
6,,failed,,,,生图执行失败
```

| 列 | 类型 | 说明 |
| --- | --- | --- |
| 序号 | int | 1~`total_count` |
| 文件名 | string | 成功行与 ZIP 内文件名一致；失败行为空 |
| 状态 | string | `success` / `failed` |
| 宽度 / 高度 | int | 成功行为图片尺寸；失败行为空 |
| 生成时间 | string | 成功行为 ISO 8601 时间；失败行为空 |
| 失败原因 | string | 失败行取 `error_message`；成功行为空 |

### 9.5 行选取规则

1. 对 `index_no` 1~`total_count` 逐一处理。
2. 取该序号下 `attempt_no` 最大、且 `status != 'superseded'` 的记录；`attempt_no` 相同取 `id` 最大。
3. 该记录满足 §2.2 的历史可见条件时写入图片文件与成功行；否则写失败行，状态 `failed`，失败原因取该记录 `error_message`（为空时写「生成失败」）。

### 9.6 失败响应

| 场景 | HTTP | code | message |
| --- | --- | --- | --- |
| 批次不存在 | 404 | 30004 | 批次不存在 |
| 批次属于其他用户 | 403 | 20005 | 无权限 |
| 示例批次、失败批次或其他状态 | 409 | 30005 | 当前批次不可下载 |
| 任一图片归档不可用 | 404 | 30014 | 文件归档中，请稍后重试 |
| 缺少 `user.history` | 403 | 20005 | 无权限 |
| 未登录 / token 失效 | 401 | 20002 / 20003 | 登录已过期，请重新登录 |

- 归档不可用时不返回残缺 ZIP；整个请求失败。
- 流开始前发生的鉴权、归属、状态、归档校验错误返回上述 JSON；流开始后的存储异常直接中断连接，前端按下载失败处理。

---

## 10. 错误响应示例

```json
{
  "code": 30005,
  "message": "当前图片不可下载",
  "data": null
}
```

---

## 11. 归档读取规则

| 场景 | 路径 | 失败返回 |
| --- | --- | --- |
| `archived_at IS NULL` | `generated_images.file_path` | 404 `30014` 文件不存在 |
| `archived_at IS NOT NULL` | `archive/{file_path}` | 404 `30014` 文件归档中，请稍后重试 |
| 缩略图 | `generated_images.thumbnail_path`（始终热存储） | 404 `30014` 文件不存在 |

- 读取超时：`ARCHIVE_READ_TIMEOUT_SECONDS`，默认 60。
- 归档不可用时记录错误日志：`image_id`、`batch_id`、`archive_path`、错误类型与原因；不得记录 token。
- 归档不影响列表可见性、排序、详情展示、单张下载权限与 ZIP 生成。

---

## 12. 错误码（最小集）

| code | HTTP | 含义 | 本 demo 使用场景 |
| --- | --- | --- | --- |
| 0 | 200 | 成功 | 全部 |
| 10001 | 400 | 参数错误 | `page` 非正整数 |
| 20002 | 401 | 登录已过期 | token 过期 |
| 20003 | 401 | token 无效 | 未携带、签名错误、版本不符 |
| 20004 | 403 | 账号不可用 | 账号禁用/删除 |
| 20005 | 403 | 无权限 | 缺少 `user.history`；访问他人批次 |
| 30004 | 404 | 批次不存在 | 不存在、不是 `full`、状态不在历史范围 |
| 30005 | 409 | 当前操作不允许 | 单张不可下载；整组批次不可下载 |
| 30014 | 404 | 文件不存在或归档不可用 | 图片、缩略图、归档读取 |
| 50001 | 500 | 系统内部错误 | 兜底 |
| 50002 | 500 | 数据库错误 | 兜底 |
| 50003 | 500 | 存储服务错误 | 兜底 |

---

## 13. 前端约定

### 13.1 路由与守卫

| 路由 | 页面 | 守卫 |
| --- | --- | --- |
| `/history?page={n}` | 历史列表 | 登录 + `user.history` |
| `/history/{batch_id}` | 批次详情 | 登录 + `user.history` |

- 未登录跳转 `/login?redirect=当前路径`。
- 401 `20002` / `20003` 清除 token 与用户状态后跳登录。
- 403 `20005` 跳 `/403`。
- 列表页码写入 URL 查询参数，刷新与浏览器回退可恢复原页。

### 13.2 列表与卡片

- 每页固定 20 条；分页器显示总页数，切换后回到列表顶部。
- 卡片展示：封面缩略图、商品名称、「1 主图 + 5 详情图」、成功张数、生成时间。
- 成功张数文案：`success_count == total_count` 显示「6 张」，否则显示「5/6 张」。
- 时间按浏览器本地时区格式化到分钟。
- 首次加载显示骨架屏；失败显示「加载失败，点击重试」。
- 空数据显示「还没有作品，去创作台生成第一组图吧」与「去创作」按钮，跳转 `/workspace`。

### 13.3 图片读取与加载态

- 缩略图与原图均通过 `fetch` + `Authorization` 读取，转 `URL.createObjectURL`；组件卸载或替换时 `URL.revokeObjectURL`。
- 缩略图加载失败显示占位图与「图片加载失败」。
- 封面加载超过 300ms 显示占位图与「加载中」。
- 大图请求超过 300ms 未返回时显示「正在从归档读取…」；返回后正常展示。

### 13.4 大图预览

- 点击缩略图打开弹层，默认适应屏幕。
- 支持适应屏幕 / 100% 切换；100% 时容器可滚动。
- 上一张/下一张只在成功图片间切换，边界禁用；Esc 关闭并回到网格。
- 显示当前序号、图片尺寸与「下载这张」。

### 13.5 下载

- 单张与整组均用 `fetch` + `Authorization` 获取文件流。
- 从 `Content-Disposition` 解析文件名；解析失败时分别按 §8.3、§9.2 规则在前端拼装。
- 使用临时 `<a download>` 触发保存，保存后释放 blob URL。
- 按钮在请求中进入 loading 并禁用；失败提示「下载失败，请稍后重试」。

### 13.6 错误处理

| 场景 | 前端行为 |
| --- | --- |
| 401（`20002` / `20003`） | 清除登录态，跳 `/login?redirect=当前路径` |
| 403（`20004`） | 清除登录态，跳 `/login` |
| 403（`20005`） | 跳 `/403` |
| 404（`30004`） | 详情页显示「批次不存在」，提供返回历史列表 |
| 404（`30014`） | 图片占位并提示；下载 Toast「文件归档中，请稍后重试」或「下载失败，请稍后重试」 |
| 409（`30005`） | Toast 返回的 `message` |
| 5xx | Toast「系统繁忙，请稍后重试」，不自动登出 |
| 网络异常 | Toast「网络异常，请稍后重试」；列表提供重试 |

---

## 14. 与正式文档的差异与待统一项

| 项目 | 本文 demo 口径 | 正式依据 / 待确认 |
| --- | --- | --- |
| 预览与缩略图权限 | `user.history` 或 `user.generate` | 5 号用 `user.history`，2 号 demo 用 `user.generate`；需统一或拆分为预览/下载两个权限 |
| 缩略图接口 | 新增 `GET /images/{id}/thumbnail` | 9 号未定义路径；需补入 9 号 §8 |
| 越权响应 | 历史接口返回 403 `20005` | 5 号要求 403；2 号 demo 用 404 不泄露存在性，需统一全站口径 |
| 分页 | 固定每页 20，不开放 `page_size` | 9 号通用分页允许 `page_size`；需确认历史页是否允许调整 |
| 归档慢读提示 | 前端按 300ms 耗时判断 | 精确提示需详情响应增加 `archived` / `archived_at` 字段 |
| 归档件不可用时的 ZIP | 整体返回 30014 | 需确认是否改为跳过失败文件并在 manifest 标注 |
| manifest.csv | UTF-8 BOM、中文表头、`success`/`failed`、ISO 8601 | 需与 4 号 demo 08 统一 |
| 封面选择 | 序号最小的成功图 | 首张失败时封面顺延，需产品确认 |
| 文件名时间戳 | 图片 `created_at`；ZIP 名取批次 `created_at` | 需与 4 号示例统一 |
| 部分失败夹具 | 种子数据 | 正式由 4 号 demo 05 产生 |
| ZIP 实现 | 与 4 号 demo 08 共用契约与实现 | 避免两个 demo 分叉 |
| 归档调度 | 不实现，仅种子模拟 | 正式按 10 号 §7.2 每日 03:00 执行 |

---

## 15. 未实现接口

| 方法 | 路径 / 能力 | 说明 |
| --- | --- | --- |
| DELETE | `/api/v1/history/{batch_id}` | 历史作品只读，不提供删除 |
| PATCH | `/api/v1/history/{batch_id}` | 不支持重命名/编辑 |
| GET | `/api/v1/history?q=` | 不支持关键词搜索与筛选 |
| — | 收藏、分组、标签、分享 | 5 号 PRD 明确不做 |
| GET | `/api/v1/history/{batch_id}/images` | 详情已返回图片列表 |
| POST | `/api/v1/batches/{batch_id}/retry` | 历史页不提供补生成入口 |
| — | 归档调度、归档恢复 | 正式实现属于 10 号 §7.2 |
| — | 下载任务查询、异步 ZIP | 单批最多 6 张，同步返回 |
| — | `/api/v1/admin/*` | 管理后台内容追溯属于 7 号 PRD |

---

## 16. 验收调用序列

| 步骤 | 调用 | 期望 |
| --- | --- | --- |
| 1 | `POST /auth/login`（复用 1 号 demo） | 返回 token，`user.permissions` 含 `user.history` |
| 2 | `GET /history?page=1` | 200，`page_size=20`，`items` 20 条，按时间倒序 |
| 3 | `GET /history?page=2` | 200，`items` 1 条，`total=21` |
| 4 | `GET /history?page=999` | 200，`items=[]`，`total=21` |
| 5 | `GET /history/{completed_batch_id}` | 200，`status=completed`，`images` 6 张，序号升序 |
| 6 | `GET /history/{partial_batch_id}` | 200，`status=partially_failed`，`success_count=5`，`images` 5 张 |
| 7 | `GET /history/{sample_batch_id}` | 404 `30004` |
| 8 | `GET /history/{other_user_batch_id}` | 403 `20005` |
| 9 | `GET /images/{image_id}/thumbnail` | 200，返回缩略图流 |
| 10 | `GET /images/{image_id}/content` | 200，返回原图流 |
| 11 | `GET /images/{image_id}/download` | 200，PNG，文件名符合 §8.3 |
| 12 | `GET /images/{sample_image_id}/download` | 409 `30005` |
| 13 | `GET /batches/{completed_batch_id}/download` | 200，ZIP 含 6 张图与 `manifest.csv` |
| 14 | `GET /batches/{partial_batch_id}/download` | 200，ZIP 含 5 张图；manifest 6 行，失败行状态与原因正确 |
| 15 | `GET /batches/{sample_batch_id}/download` | 409 `30005` |
| 16 | `GET /history/{archived_batch_id}` 及对应预览、下载 | 200；原件从 `archive/` 读取 |
| 17 | 将归档对象移走后再请求预览/下载 | 404 `30014`「文件归档中，请稍后重试」，服务端有错误日志 |
| 18 | 用 `demo_admin` 的 token 调用 `GET /history` | 403 `20005` |
| 19 | 不带 token 调用 `GET /history` | 401 `20003` |
