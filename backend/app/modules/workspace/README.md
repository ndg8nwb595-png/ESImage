# workspace 模块（2 号 PRD 后端最小 demo）

本目录承载「用户端创作工作台」最小 demo 的后端实现，只覆盖 2 号 PRD README 中定义的范围。

## 目录规划

```text
workspace/
├── router.py        # 汇总并挂载 sessions / uploads / generations 子路由
├── schemas.py       # 请求体模型
├── service.py       # 校验、权限依赖、序列化与文件名工具
├── sessions.py      # 会话列表、消息分页、SSE 聊天
├── uploads.py       # 商品图上传、元数据、软删除、内容读取
├── imaging.py       # 上传图解码与缩略图
└── storage.py       # 本地存储适配层（替代 MinIO）
```

约定：

- 只实现 `docs/prd/2-用户端创作工作台/接口文档-创作工作台最小demo.md` 列出的接口；额外实现 `GET /images/{id}/thumbnail`，用于让批次响应中的 `thumbnail_url` 可读取（与 5 号文档约定一致）。
- 生成相关接口（示例批次、确认全套、预览/下载、取消、单张重试、整组 ZIP）已由 4 号 PRD 的 `app/modules/generation/` 接管；本模块只保留会话、聊天与上传。
- 模块间通过 `app/core` 与 `app/models` 通信，不直接 import 其他模块的 router。
- 生成记录、上传图、会话均按 `user_id` 做数据隔离。
- 最小 demo 使用 FastAPI `BackgroundTasks` + PostgreSQL 轮询，不接 Celery / Redis / MinIO。
