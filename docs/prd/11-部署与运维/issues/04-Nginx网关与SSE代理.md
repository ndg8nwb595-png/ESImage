# 04: Nginx 网关与 SSE 代理

**What to build:** 只有 nginx 向宿主机暴露 80。浏览器经网关访问静态占位页与 `/api/`；`/api/v1/sessions/` 下的 SSE 响应不缓冲、不缓存，事件逐字到达；10MB 上传不被拦截，超过 12MB 返回 413；静态资源启用 gzip 与缓存；所有响应带三项安全头；`/api/docs` 与 `/api/openapi.json` 只允许内网与回环地址访问。443 只保留注释模板，不启用。

**Blocked by:** 03 应用镜像与双健康探针

**Status:** ready-for-agent

- [ ] 只有 nginx 发布宿主机 80；backend、frontend、数据库、Redis、MinIO 均无宿主机端口；443 以注释块保留。
- [ ] `location /` 代理到 `frontend:8080`，保留 `Host`、`X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto`；`GET /` 返回 200 占位页。
- [ ] `location /api/` 代理到 `backend:8000`，使用 HTTP/1.1，保留上述转发头，`proxy_read_timeout` 为 300 秒；`GET /api/health` 经网关返回 200。
- [ ] `location /api/v1/sessions/` 匹配优先于 `/api/`，设置 `proxy_buffering off`、`proxy_cache off`、`proxy_set_header Connection ""`、读超时 300 秒；SSE 事件按服务端发送节奏到达，不出现结束后一次性输出。
- [ ] 提供一个仅非生产环境启用的 SSE 演示探针 `GET /api/v1/sessions/_probe/stream`：先发 `meta`，再以 1 秒间隔发多条 `delta`，最后发 `done`；无事件时每 15 秒发 `ping`；客户端断开后停止发送。生产环境该路径返回 404，且不进入 OpenAPI。
- [ ] SSE 响应头包含 `Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`；事件帧使用 `event:` + `data:` + 空行。
- [ ] `client_max_body_size` 为 12m；经网关发送 10MB 请求不被 413 拦截；发送超过 12MB 返回 413，且请求不会到达 backend。
- [ ] 静态资源启用 gzip（JS、CSS、JSON、SVG、字体）；带内容哈希的静态资源长缓存，`index.html` 不缓存，刷新后能拿到新入口。
- [ ] 所有响应包含 `X-Content-Type-Options: nosniff`、`X-Frame-Options: SAMEORIGIN`、`Referrer-Policy: strict-origin-when-cross-origin`；使用 `always` 保证 403、413、502、504 等错误响应也带安全头。
- [ ] `/api/docs` 与 `/api/openapi.json` 仅允许回环与 RFC1918 网段访问，其他来源返回 403；该限制在网关层完成。
- [ ] Nginx 访问日志与错误日志写入 `nginxlogs` 卷；backend 停止时返回 502，上游超时返回 504，日志可定位。
- [ ] 网关不启用 CORS；同源部署时 `CORS_ORIGINS` 留空。
