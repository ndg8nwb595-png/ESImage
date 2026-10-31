# chat 模块（Agent 会话交互后端）

对应需求：`docs/prd/3-Agent会话交互/3-Agent会话交互prd.md` 与
`docs/prd/3-Agent会话交互/接口文档-Agent会话交互最小demo.md`。

## 模块定位

本模块承载「3 号 Agent 会话交互最小 demo」的后端增量，放在
`backend/app/modules/chat/`。会话列表、首条消息建会话、SSE 骨架、自动命名与幂等
复用 2 号 `modules/workspace/` 的实现，不重复建表。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `router.py` | `PATCH /sessions/{id}` 重命名、`DELETE /sessions/{id}` 软删除 |
| `schemas.py` | 重命名请求体 |
| `service.py` | 标题校验、软删除、消息惰性超时、上传图校验、需求变化判定 |
| `agents.py` | 上下文组装（10 轮截断、已确认示例描述）、演示桩提示词、摘要合并 |
| `model.py` | 豆包（火山方舟）真实模型接入、流式输出、摘要哨兵解析、演示桩回退 |
| `stream.py` | SSE 事件输出与 15 秒心跳包装 |
| `backend/app/modules/workspace/sessions.py` | 复用并集成：消息分页、聊天 SSE、幂等重放/失败重试 |

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/sessions` | 会话列表（2 号基线，3 号补充摘要清洗） |
| PATCH | `/api/v1/sessions/{id}` | 重命名会话（3 号新增） |
| DELETE | `/api/v1/sessions/{id}` | 软删除会话（3 号新增） |
| GET | `/api/v1/sessions/{id}/messages` | 消息分页与惰性超时（3 号补充） |
| POST | `/api/v1/sessions/messages` | 首条消息 SSE（可无会话） |
| POST | `/api/v1/sessions/{id}/messages` | 已有会话 SSE |

SSE 增量：`meta.duplicate`、`done.requirement_changed`、`done.requirement_summary`、
`done.token_in/token_out`；事件顺序仍为 `meta → planner → product_understanding → done`。

## 豆包真实模型配置

`backend/.env`（不提交）或部署环境变量：

```dotenv
ARK_API_KEY=你的火山方舟 API Key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_TEXT_MODEL=doubao-seed-character-260628
ARK_TIMEOUT_SECONDS=60
CHAT_USE_STUB=false
```

行为：

- `ARK_API_KEY` 非空且 `CHAT_USE_STUB=false`：走真实模型。
  - 规划 Agent：非流式调用，输出 intent / 是否追问 / 风格建议 JSON。
  - 商品理解 Agent：流式调用，正文实时下发；正文结束后输出 `<<<SUMMARY>>>`
    哨兵与需求摘要 JSON，后端缓冲解析，不把哨兵与 JSON 发给前端。
  - Token 取接口返回的 usage；助手消息与 `done` 事件记两个 Agent 的合计。
- `ARK_API_KEY` 为空或 `CHAT_USE_STUB=true`：使用确定性演示桩，Token 记 0。
- 测试环境由 `tests/conftest.py` 强制 `CHAT_USE_STUB=1`，不会产生真实调用费用。

> 生图与生文共用同一个火山方舟 API Key；生图属于 4 号 PRD，本模块只接文本模型。

## 本地验证

```bash
cd backend
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

完整 curl 示例见本次实现记录；OpenAPI：`http://127.0.0.1:8001/docs`。

## demo 已知边界

- 参数校验先于幂等重放：已完成消息重放时若当前参数（如已删除的上传图）失效，
  会返回参数错误而不是重放；前端自动重试使用的是同一份有效参数，正常路径不受影响。
- 真实模型回复的措辞由模型决定；提示词已禁止承诺直接生图，但仍需联调时抽检。
- 真实模型流式输出依赖 `stream_options.include_usage`；接口不返回 usage 时 Token 记 0。
- 聊天不触发生图；生成必须走 2 号/4 号的生成接口。
