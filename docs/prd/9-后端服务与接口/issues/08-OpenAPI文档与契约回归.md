# 08: OpenAPI 文档与契约回归

**What to build:** 联调方打开 `/api/docs` 就能看到完整、可执行的接口契约：Bearer 鉴权、统一响应 `{ code, message, data }`、分页 `{ items, total, page, page_size }`、9 号错误码表、每个接口的权限码、上传的 `multipart/form-data`、下载的二进制响应与 `Content-Disposition`、SSE 的事件表与心跳说明。`/api/openapi.json` 可被工具读取。契约回归套件覆盖 01~07 的验收项，逐条输出中文日志并全部通过。

**Blocked by:** 01~07（统一响应、鉴权、权限、上传、下载、SSE、幂等与并发）

**Status:** ready-for-agent

- [ ] `/api/docs` 可访问并渲染 Swagger UI；`/api/openapi.json` 返回 OpenAPI 3.0 文档；本地 demo 不限制访问，生产仅内网限制留给 11 号部署文档。
- [ ] OpenAPI 包含 Bearer 安全方案，声明 `Authorization: Bearer <jwt>`；登录接口标注无需鉴权。
- [ ] 所有 JSON 接口引用统一响应结构 `{ code, message, data }`；成功、参数错误、鉴权失败、无权限、业务错误、系统错误都有可读示例。
- [ ] 登录接口与所有分页接口引用统一分页结构 `{ items, total, page, page_size }`，并标注 `page` 默认 1、`page_size` 默认 20、最大 100。
- [ ] OpenAPI 的接口描述中包含 9 号 §3.1 错误码表与含义；不出现 9 号总表之外的 demo 私有错误码作为正式契约。
- [ ] 每个非登录接口都能看到所需权限码（如 `admin.accounts.view`、`user.generate`）；「登录即可」的接口明确标注。
- [ ] 上传接口文档包含 `multipart/form-data`、字段名 `file`、允许格式、10MB 限制与 `30006`。
- [ ] 下载接口文档包含 `image/png` / `application/zip` 响应、`Content-Disposition` 的 RFC 5987 规则与 `30014`。
- [ ] SSE 接口文档标注 `text/event-stream`、`meta` / `agent_status` / `delta` / `done` / `error` / `ping` 事件、15 秒心跳与断线行为。
- [ ] OpenAPI 只包含本 demo 实际实现或作为载体的接口，不出现「文档有、接口无」的接口；未实现的 9 号接口不出现在文档中。
- [ ] 契约回归套件覆盖 01~07 的全部验收项，至少包含：统一响应、参数校验、分页边界、JWT 五类失败、权限与越权、上传八类场景、下载八类场景、SSE 事件与断线、消息/批次幂等、生成并发。
- [ ] 契约回归套件每个用例输出中文日志：用例名、请求、预期 HTTP、预期业务码、实际 HTTP、实际业务码、耗时、结论；失败时输出可定位的请求 ID。
- [ ] 契约回归套件读取 `/api/openapi.json`，断言 Bearer 方案、统一响应、分页结构、错误码说明与至少 3 个接口的权限码标注存在。
- [ ] 不新增业务接口，不改变 1~7 号切片与 1~6 号 demo 已定义的契约。
