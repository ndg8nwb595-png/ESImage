#!/usr/bin/env bash
# 创作工作台最小 demo 后端 curl 验收脚本。
#
# 用法（在 backend/ 目录）：
#   bash scripts/curl_smoke.sh
#
# 依赖：本机 PostgreSQL（可用 docker compose 启动）与 Python 依赖已安装。
# 脚本会临时启动 8010 端口的 uvicorn，结束后自动关闭。
#
# 注意：Windows 下 Git Bash 直接 `curl -d '{"中文":...}'` 可能被终端按本地编码
# 解释，导致后端解析失败。本脚本统一用 Python 生成 UTF-8 JSON 文件，再用
# `curl --data-binary @文件` 发送，保证跨平台可用。

set -u

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://esimage:esimage@127.0.0.1:55433/esimage}"
export JWT_SECRET="${JWT_SECRET:-workspace-demo-secret-0123456789abcdef}"
export PYTHONPATH=.
export DEMO_PIPELINE_STAGE_DELAY="${DEMO_PIPELINE_STAGE_DELAY:-0.02}"
export STORAGE_ROOT="${STORAGE_ROOT:-storage}"
# 冒烟脚本使用独立本地目录，固定本地后端避免读取 backend/.env 的 MinIO 配置
export STORAGE_BACKEND=local
export ARCHIVE_READ_TIMEOUT_SECONDS="${ARCHIVE_READ_TIMEOUT_SECONDS:-60}"

PORT="${PORT:-8010}"
BASE="http://127.0.0.1:$PORT/api/v1"
TMP_DIR=".curl_tmp"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

# 幂等键按接口文档使用 UUID
CLIENT_MSG_ID=$(python -c "import uuid;print(uuid.uuid4())")
SAMPLE_REQ_ID=$(python -c "import uuid;print(uuid.uuid4())")
CONFIRM_REQ_ID=$(python -c "import uuid;print(uuid.uuid4())")
INVALID_REQ_ID=$(python -c "import uuid;print(uuid.uuid4())")

fail() {
  echo "[curl][失败] $*" >&2
  exit 1
}

expect_http() {
  # 用法：expect_http <实际状态码> <期望状态码> <说明>
  if [ "$1" != "$2" ]; then
    fail "$3：期望 HTTP $2，实际 $1；响应体 $(cat "$TMP_DIR/last_body.txt" 2>/dev/null)"
  fi
  echo "[curl] $3 -> HTTP $1"
}

json_get() {
  # 用法：json_get '<json 字符串>' 'data.batch_id'
  python - "$1" "$2" <<'PY'
import json
import sys

try:
    data = json.loads(sys.argv[1])
except Exception as exc:
    print(f"[json_get] 无法解析 JSON：{exc}", file=sys.stderr)
    raise SystemExit(2)
for part in sys.argv[2].split("."):
    try:
        data = data[int(part)] if isinstance(data, list) else data[part]
    except Exception as exc:
        print(f"[json_get] 缺少字段 {sys.argv[2]}：{exc}", file=sys.stderr)
        raise SystemExit(2)
print(data)
PY
}

write_json() {
  # 用法：write_json <输出文件> <python 表达式，使用变量 b>
  local output="$1"
  local script="$2"
  python - "$output" <<PY
import json, sys
b = {}
$script
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(b, ensure_ascii=False))
PY
}

request_json() {
  # 用法：request_json GET|POST|DELETE <path> <token> [body_file]
  local method="$1" path="$2" token="$3" body_file="${4:-}"
  local -a args=(-sS -o "$TMP_DIR/last_body.txt" -w "%{http_code}" -X "$method" "$BASE$path" -H "Authorization: Bearer $token")
  if [ -n "$body_file" ]; then
    args+=(-H "Content-Type: application/json" --data-binary "@$body_file")
  fi
  curl "${args[@]}"
}

wait_status() {
  # 用法：wait_status <batch_id> <token> <目标状态> <最大轮询次数>
  local batch_id="$1" token="$2" target="$3" limit="${4:-300}"
  local body="" status=""
  for _ in $(seq 1 "$limit"); do
    local code
    code=$(request_json GET "/generations/$batch_id" "$token")
    [ "$code" = "200" ] || fail "轮询批次 $batch_id 返回 HTTP $code"
    body=$(cat "$TMP_DIR/last_body.txt")
    status=$(json_get "$body" "data.status") || exit 1
    [ "$status" = "$target" ] && { echo "[curl] 批次 $batch_id 到达状态 $target" >&2; printf '%s' "$body"; return 0; }
    python -c "import time;time.sleep(0.05)"
  done
  fail "批次 $batch_id 未在限定次数内到达 $target，最后状态：$status"
}

echo "[curl] 启动服务，端口 $PORT"
python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$TMP_DIR/uvicorn.log" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "[curl] 等待服务启动……"
READY=0
for _ in $(seq 1 40); do
  if curl -sS -o /dev/null "http://127.0.0.1:$PORT/openapi.json"; then
    READY=1
    break
  fi
  python -c "import time;time.sleep(0.25)"
done
if [ "$READY" -ne 1 ]; then
  echo "[curl] 服务启动失败"
  tail -40 "$TMP_DIR/uvicorn.log"
  exit 1
fi
echo "[curl] 服务已启动"

# ---------------------------------------------------------------------------
# 1. 登录与当前用户
# ---------------------------------------------------------------------------
write_json "$TMP_DIR/login_user.json" 'b.update({"username": "demo_user", "password": "Demo1234", "remember_me": False})'
CODE=$(curl -sS -o "$TMP_DIR/login_user.json.response" -w "%{http_code}" -X POST "$BASE/auth/login" -H "Content-Type: application/json" --data-binary "@$TMP_DIR/login_user.json")
cp "$TMP_DIR/login_user.json.response" "$TMP_DIR/last_body.txt"
expect_http "$CODE" 200 "POST /auth/login"
LOGIN=$(cat "$TMP_DIR/login_user.json.response")
TOKEN=$(json_get "$LOGIN" "data.token") || exit 1
echo "[curl] token 长度 ${#TOKEN}"

CODE=$(request_json GET "/auth/me" "$TOKEN")
expect_http "$CODE" 200 "GET /auth/me"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/sessions" "$TOKEN")
expect_http "$CODE" 200 "GET /sessions"
cat "$TMP_DIR/last_body.txt"; echo

# ---------------------------------------------------------------------------
# 2. 聊天 SSE（无会话 -> 自动建会话）
# ---------------------------------------------------------------------------
echo "[curl] POST /sessions/messages（SSE，无会话）"
python - "$TMP_DIR/chat.json" "$CLIENT_MSG_ID" <<'PY'
import json, sys
body = {
    "client_message_id": sys.argv[2],
    "content": "帮我做一套通勤风的图",
    "params": {
        "product_name": "秋季通勤衬衫",
        "style_text": "简洁白底",
        "width": 1000,
        "height": 1000,
        "template_id": None,
    },
    "session_id": None,
}
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(body, ensure_ascii=False))
PY
CODE=$(curl -sS -o "$TMP_DIR/chat_sse.txt" -w "%{http_code}" -N -X POST "$BASE/sessions/messages" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: text/event-stream" \
  --data-binary "@$TMP_DIR/chat.json")
cp "$TMP_DIR/chat_sse.txt" "$TMP_DIR/last_body.txt"
expect_http "$CODE" 200 "POST /sessions/messages"
head -c 900 "$TMP_DIR/chat_sse.txt"; echo
SESSION_ID=$(python - "$TMP_DIR/chat_sse.txt" <<'PY'
import json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    if line.startswith("data:"):
        data = json.loads(line[5:])
        if "session_id" in data:
            print(data["session_id"])
            break
PY
)
[ -n "$SESSION_ID" ] || fail "未能从 SSE meta 事件解析 session_id"
echo "[curl] 新建会话 session_id=$SESSION_ID"

CODE=$(request_json GET "/sessions/$SESSION_ID/messages?page=1&page_size=20" "$TOKEN")
expect_http "$CODE" 200 "GET /sessions/{id}/messages"
cat "$TMP_DIR/last_body.txt"; echo

# ---------------------------------------------------------------------------
# 3. 上传商品图
# ---------------------------------------------------------------------------
echo "[curl] 生成两张测试图片"
python - "$TMP_DIR" <<'PY'
import sys
from pathlib import Path
from PIL import Image
out = Path(sys.argv[1])
Image.new("RGB", (900, 900), (70, 110, 190)).save(out / "a.png")
Image.new("RGB", (800, 1000), (190, 120, 70)).save(out / "b.png")
PY

echo "[curl] POST /uploads（两张）"
CODE=$(curl -sS -o "$TMP_DIR/upload1.json" -w "%{http_code}" -X POST "$BASE/uploads" \
  -H "Authorization: Bearer $TOKEN" -F "file=@$TMP_DIR/a.png;type=image/png")
expect_http "$CODE" 200 "POST /uploads（第 1 张）"
cat "$TMP_DIR/upload1.json"; echo
UPLOAD_ID=$(json_get "$(cat "$TMP_DIR/upload1.json")" "data.upload_id") || exit 1

CODE=$(curl -sS -o "$TMP_DIR/upload2.json" -w "%{http_code}" -X POST "$BASE/uploads" \
  -H "Authorization: Bearer $TOKEN" -F "file=@$TMP_DIR/b.png;type=image/png")
expect_http "$CODE" 200 "POST /uploads（第 2 张）"
cat "$TMP_DIR/upload2.json"; echo
UPLOAD_ID2=$(json_get "$(cat "$TMP_DIR/upload2.json")" "data.upload_id") || exit 1

CODE=$(request_json GET "/uploads/$UPLOAD_ID" "$TOKEN")
expect_http "$CODE" 200 "GET /uploads/{id}"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(curl -sS -o "$TMP_DIR/upload_content.png" -w "%{http_code}" "$BASE/uploads/$UPLOAD_ID/content" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /uploads/{id}/content"
file "$TMP_DIR/upload_content.png" 2>/dev/null || true

CODE=$(curl -sS -o "$TMP_DIR/upload_thumb.webp" -w "%{http_code}" "$BASE/uploads/$UPLOAD_ID/thumbnail" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /uploads/{id}/thumbnail"
file "$TMP_DIR/upload_thumb.webp" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 4. 创建示例批次、轮询、预览
# ---------------------------------------------------------------------------
echo "[curl] POST /generations/sample"
python - "$TMP_DIR/sample.json" "$SESSION_ID" "$UPLOAD_ID" "$UPLOAD_ID2" "$SAMPLE_REQ_ID" <<'PY'
import json, sys
body = {
    "client_request_id": sys.argv[5],
    "session_id": int(sys.argv[2]),
    "product_name": "秋季通勤衬衫",
    "style_text": "简洁白底",
    "width": 1000,
    "height": 1000,
    "template_id": None,
    "upload_ids": [int(sys.argv[3]), int(sys.argv[4])],
    "requirement_summary": None,
}
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(body, ensure_ascii=False))
PY
CODE=$(request_json POST "/generations/sample" "$TOKEN" "$TMP_DIR/sample.json")
expect_http "$CODE" 200 "POST /generations/sample"
cat "$TMP_DIR/last_body.txt"; echo
BATCH_ID=$(json_get "$(cat "$TMP_DIR/last_body.txt")" "data.batch_id") || exit 1

BATCH=$(wait_status "$BATCH_ID" "$TOKEN" "sample_ready")
SAMPLE_IMAGE_ID=$(json_get "$BATCH" "data.images.0.image_id") || exit 1
echo "$BATCH" | python -c "import sys,json;d=json.load(sys.stdin);print('[curl] 示例批次：',d['data']['status'],d['data']['stage'],[(i['index'],i['image_role'],i['status']) for i in d['data']['images']])"

CODE=$(curl -sS -o "$TMP_DIR/sample.png" -w "%{http_code}" "$BASE/images/$SAMPLE_IMAGE_ID/content" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{id}/content"
file "$TMP_DIR/sample.png" 2>/dev/null || true

CODE=$(curl -sS -o "$TMP_DIR/sample_thumb.webp" -w "%{http_code}" "$BASE/images/$SAMPLE_IMAGE_ID/thumbnail" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{id}/thumbnail"
file "$TMP_DIR/sample_thumb.webp" 2>/dev/null || true

echo "[curl] GET /images/{sample}/download（示例图，应 409/30005）"
CODE=$(curl -sS -o "$TMP_DIR/last_body.txt" -w "%{http_code}" "$BASE/images/$SAMPLE_IMAGE_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 409 "GET /images/{sample}/download"
cat "$TMP_DIR/last_body.txt"; echo

# ---------------------------------------------------------------------------
# 5. 确认全套、轮询、下载
# ---------------------------------------------------------------------------
echo "[curl] POST /generations/{batch_id}/confirm"
printf '{"client_request_id":"%s"}' "$CONFIRM_REQ_ID" > "$TMP_DIR/confirm.json"
CODE=$(request_json POST "/generations/$BATCH_ID/confirm" "$TOKEN" "$TMP_DIR/confirm.json")
expect_http "$CODE" 200 "POST /generations/{batch_id}/confirm"
cat "$TMP_DIR/last_body.txt"; echo
FULL_ID=$(json_get "$(cat "$TMP_DIR/last_body.txt")" "data.full_batch_id") || exit 1

FULL=$(wait_status "$FULL_ID" "$TOKEN" "completed")
MAIN_IMAGE_ID=$(json_get "$FULL" "data.images.0.image_id") || exit 1
DETAIL_IMAGE_ID=$(json_get "$FULL" "data.images.1.image_id") || exit 1
echo "$FULL" | python -c "import sys,json;d=json.load(sys.stdin);print('[curl] 全套批次：',d['data']['status'],d['data']['stage'],d['data']['completed_count'],'/',d['data']['total_count'],[(i['index'],i['image_role'],i['status']) for i in d['data']['images']])"

CODE=$(curl -sS -D "$TMP_DIR/download_headers.txt" -o "$TMP_DIR/main.png" -w "%{http_code}" "$BASE/images/$MAIN_IMAGE_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{main}/download"
grep -i "content-disposition" "$TMP_DIR/download_headers.txt" || true
file "$TMP_DIR/main.png" 2>/dev/null || true

CODE=$(curl -sS -o "$TMP_DIR/detail.png" -w "%{http_code}" "$BASE/images/$DETAIL_IMAGE_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{detail}/download"
file "$TMP_DIR/detail.png" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 6. 软删除上传图
# ---------------------------------------------------------------------------
CODE=$(request_json DELETE "/uploads/$UPLOAD_ID" "$TOKEN")
expect_http "$CODE" 200 "DELETE /uploads/{id}"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/uploads/$UPLOAD_ID" "$TOKEN")
expect_http "$CODE" 404 "GET /uploads/{id}（已删除）"
cat "$TMP_DIR/last_body.txt"; echo

# ---------------------------------------------------------------------------
# 7. 权限与参数校验
# ---------------------------------------------------------------------------
write_json "$TMP_DIR/login_admin.json" 'b.update({"username": "demo_admin", "password": "Demo1234"})'
CODE=$(curl -sS -o "$TMP_DIR/login_admin.response" -w "%{http_code}" -X POST "$BASE/auth/login" -H "Content-Type: application/json" --data-binary "@$TMP_DIR/login_admin.json")
expect_http "$CODE" 200 "POST /auth/login（demo_admin）"
ADMIN_TOKEN=$(json_get "$(cat "$TMP_DIR/login_admin.response")" "data.token") || exit 1

CODE=$(request_json GET "/sessions" "$ADMIN_TOKEN")
expect_http "$CODE" 403 "GET /sessions（管理员，应 403/20005）"
cat "$TMP_DIR/last_body.txt"; echo

python - "$TMP_DIR/invalid_sample.json" "$INVALID_REQ_ID" <<'PY'
import json, sys
body = {
    "client_request_id": sys.argv[2],
    "product_name": "   ",
    "width": 1000,
    "height": 1000,
    "upload_ids": [],
}
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(body, ensure_ascii=False))
PY
CODE=$(request_json POST "/generations/sample" "$TOKEN" "$TMP_DIR/invalid_sample.json")
expect_http "$CODE" 400 "POST /generations/sample（商品名称为空，应 400/10002）"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json POST "/auth/logout" "$TOKEN")
expect_http "$CODE" 200 "POST /auth/logout"
cat "$TMP_DIR/last_body.txt"; echo

echo "[curl] 全部接口调用结束；文件输出目录：$TMP_DIR"
