# ops：部署与运维（11 号 PRD）最小 demo

与 `docs/prd/11-部署与运维/` 对应。本模块只交付部署壳与运维探针，不新增业务接口：

- `GET /api/health`：11 号 §8.3 裸结构健康探针，供容器/网关探活。
- `GET /api/v1/health`：9 号统一响应健康探针，共用同一次依赖检测。
- `GET /api/v1/sessions/_probe/stream`：演示专用 SSE 探针，仅 `APP_ENV != production` 注册。
- `X-Request-ID` 中间件、JSON 结构化日志、Celery Worker/Beat 基线（`ops.selftest`）。
- 初始超管种子与 `migrate` 入口。

依赖检测并发执行 PostgreSQL / Redis / MinIO，单项超时 2 秒、整体不超 5 秒；任一不可用返回 503 `degraded`。

## 验收（curl）

```bash
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1:8000/api/v1/health
curl -N http://127.0.0.1:8000/api/v1/sessions/_probe/stream
```

依赖未就绪时两个健康接口返回 503 `degraded` 且 `checks.*` 为 `error`；SSE 探针不依赖外部服务，直接返回 `meta → delta → done`。
