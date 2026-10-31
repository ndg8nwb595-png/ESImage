# history 模块（5 号 PRD 历史作品后端最小 demo）

对应需求：

- `docs/prd/5-历史作品/5-历史作品prd.md`
- `docs/prd/5-历史作品/接口文档-历史作品最小demo.md`
- `docs/prd/5-历史作品/issues/01` ~ `05`

## 模块定位

本模块只承载「历史作品」最小 demo 的后端读取能力：历史列表、批次详情、
缩略图与归档读取、单张下载、整组 ZIP 与 `manifest.csv`。
历史页只读，不提供删除、编辑、重命名、搜索、收藏、分享与补生成。

## 依赖与边界

- 数据表复用 `app/models/workspace.py` 的 `generation_batches` / `generated_images`。
- 生成侧数据由 2 号工作台 demo 或 4 号生图 demo 提供，本模块不写生成记录。
- 对象存储沿用 `app/modules/workspace/storage.py` 的本地适配层。
- 单张预览与下载复用 2 号 demo 的 `/images/{image_id}/content` 与
  `/images/{image_id}/download`，本模块只补充归档路径与权限放宽。
- 整组 ZIP 与 4 号 demo 08 共用同一契约；实现集中在 `zip_export.py`，
  4 号模块接入时直接复用，避免两套逻辑分叉。
- 权限：列表/详情/单张下载/整组 ZIP 用 `user.history`；
  预览与缩略图接受 `user.history` 或 `user.generate`。

## 文件规划

| 文件 | 职责 |
| --- | --- |
| `router.py` | 历史列表、批次详情、整组 ZIP 路由 |
| `service.py` | 历史可见性查询、序列化、分页、文件名与归档读取工具 |
| `zip_export.py` | 整组 ZIP 与 `manifest.csv` 构建（与 4 号 demo 08 共用） |
| `seed.py` | 可重复执行的演示夹具（completed / partial / sample / failed / superseded / archived） |
| `README.md` | 模块说明 |

## 接口清单

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| GET | `/api/v1/history` | `user.history` |
| GET | `/api/v1/history/{batch_id}` | `user.history` |
| GET | `/api/v1/images/{image_id}/thumbnail` | `user.history` 或 `user.generate` |
| GET | `/api/v1/images/{image_id}/content` | `user.history` 或 `user.generate` |
| GET | `/api/v1/images/{image_id}/download` | `user.history` |
| GET | `/api/v1/batches/{batch_id}/download` | `user.history` |

## 状态

- [x] 模块目录骨架
- [ ] 历史列表与分页
- [ ] 批次详情与图片网格
- [ ] 缩略图、预览与单张下载（含归档）
- [ ] 整组 ZIP 与 manifest.csv
- [ ] 种子夹具与 curl 验收
