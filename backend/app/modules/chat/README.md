# chat 模块（Agent 会话交互后端）

对应需求：`docs/prd/3-Agent会话交互/3-Agent会话交互prd.md` 与
`docs/prd/3-Agent会话交互/接口文档-Agent会话交互最小demo.md`。

## 模块定位

本模块只承载「3 号 Agent 会话交互最小 demo」的后端增量，统一放在
`backend/app/modules/chat/`，不修改登录模块 `backend/app/modules/auth/` 的内部实现。

## 依赖与当前状态

- 前置：2 号 demo 04（会话列表、首条消息建会话、SSE 骨架、自动命名、幂等）。
- 当前 `main` 尚无 2 号 demo 04 的可运行代码，因此本模块暂不实现业务逻辑；
  先建立目录骨架并合并到 `main`，待 `feat/workspace-backend-demo` 合并后再开发。
- 数据表、会话与消息模型由 2 号 demo 提供；本模块在其之上实现增量，避免重复建表。

## 计划接口（相对 2 号 demo 04 的增量）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/sessions` | 会话列表（沿用 2 号 04） |
| PATCH | `/api/v1/sessions/{id}` | 重命名会话（3 号新增） |
| DELETE | `/api/v1/sessions/{id}` | 软删除会话（3 号新增） |
| GET | `/api/v1/sessions/{id}/messages` | 消息分页与惰性超时（沿用并补充） |
| POST | `/api/v1/sessions/messages` | 首条消息 SSE（沿用，`done` 增加字段） |
| POST | `/api/v1/sessions/{id}/messages` | 已有会话 SSE（沿用，`done` 增加字段） |

## 计划文件

| 文件 | 职责 |
| --- | --- |
| `router.py` | 会话重命名、软删除、消息分页与聊天 SSE 路由 |
| `schemas.py` | 请求体模型 |
| `service.py` | 会话归属校验、标题校验、需求摘要合并、需求变化判定 |
| `agents.py` | 规划 / 商品理解轻链路演示桩与上下文组装 |
| `seed.py` | 演示用的隐藏会话、系统消息与已确认示例批次夹具（仅在需要时） |
