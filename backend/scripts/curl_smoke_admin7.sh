#!/usr/bin/env bash
# 7 号管理后台-用户与生图记录后端 curl 验收脚本。
#
# 用法（在 backend/ 目录）：
#   DATABASE_URL=... JWT_SECRET=... PYTHON_BIN=/path/to/python \
#     bash scripts/curl_smoke_admin7.sh
#
# 依赖：本机 PostgreSQL（复用已运行的 esimage-postgres:55433）与 Python 依赖。
# 脚本会：创建/复用 DATABASE_URL 指向的库 → 建表 → 幂等种子 → 临时启动 8017
# → 逐个 curl → 关闭。
#
# 注意：数据库连接串与 JWT 密钥只从环境变量读取，不在仓库中保存。
# 全部业务接口均为 GET，不涉及中文请求体；响应含中文时由 Python 以 UTF-8 解析。
# 脚本不会输出 JWT、密码或 API Key。

set -u

: "${DATABASE_URL:?请通过环境变量提供 DATABASE_URL}"
: "${JWT_SECRET:?请通过环境变量提供 JWT_SECRET}"
export DATABASE_URL
export JWT_SECRET
export PYTHONPATH=.
export STORAGE_ROOT="${STORAGE_ROOT:-storage}"

PYTHON_BIN="${PYTHON_BIN:-python}"
PORT="${PORT:-8017}"
BASE="http://127.0.0.1:$PORT/api/v1"
TMP_DIR=".curl_tmp_admin7"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

fail() {
  echo "[curl][失败] $*" >&2
  exit 1
}

# 在 PostgreSQL 中幂等创建开发库（假定连接账号有 CREATEDB 权限）
"$PYTHON_BIN" - <<'PY'
import re
import psycopg

url = re.sub(r"^postgresql\+psycopg://", "postgresql://", __import__("os").environ["DATABASE_URL"])
dbname = url.rsplit("/", 1)[-1]
admin_url = url.rsplit("/", 1)[0] + "/postgres"
with psycopg.connect(admin_url, autocommit=True) as conn:
    exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
    if not exists:
        conn.execute(f'CREATE DATABASE "{dbname}"')
        print(f"[curl] 已创建数据库 {dbname}")
    else:
        print(f"[curl] 复用数据库 {dbname}")
PY

echo "[curl] 建表与幂等种子"
"$PYTHON_BIN" scripts/init_db.py
"$PYTHON_BIN" scripts/seed.py > "$TMP_DIR/seed.log" 2>&1 || {
  cat "$TMP_DIR/seed.log"
  fail "种子执行失败"
}
tail -3 "$TMP_DIR/seed.log"

echo "[curl] 启动服务，端口 $PORT"
"$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$TMP_DIR/uvicorn.log" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

READY=0
for _ in $(seq 1 60); do
  if curl -sS -o /dev/null "http://127.0.0.1:$PORT/openapi.json" 2>/dev/null; then
    READY=1
    break
  fi
  "$PYTHON_BIN" -c "import time;time.sleep(0.25)"
done
if [ "$READY" -ne 1 ]; then
  tail -50 "$TMP_DIR/uvicorn.log"
  fail "服务启动失败"
fi
echo "[curl] 服务已启动"

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

json_get() {
  # 用法：json_get '<json 字符串>' 'data.items.0.user_id'
  "$PYTHON_BIN" - "$1" "$2" <<'PY'
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
if data is None:
    print("")
else:
    print(data)
PY
}

get_json() {
  # 用法：get_json <path> <token> <输出文件>；返回 HTTP 状态码
  local path="$1" token="$2" output="$3"
  local code
  code=$(curl -sS -o "$output" -w "%{http_code}" -H "Authorization: Bearer $token" "$BASE$path")
  cp "$output" "$TMP_DIR/last_body.json"
  printf '%s' "$code"
}

expect_code() {
  # 用法：expect_code <实际状态码> <期望状态码> <说明>
  if [ "$1" != "$2" ]; then
    fail "$3：期望 HTTP $2，实际 $1；响应体 $(cat "$TMP_DIR/last_body.json" 2>/dev/null)"
  fi
  echo "[curl] $3 -> HTTP $1"
}

login() {
  # 用法：login <用户名> <输出文件>；返回 token
  local username="$1" output="$2"
  curl -sS -o "$output" -w "%{http_code}" -X POST "$BASE/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$username\",\"password\":\"Demo1234\"}"
}

# ---------------------------------------------------------------------------
# 1. 登录
# ---------------------------------------------------------------------------
echo "[curl] 步骤 1：登录超管 / 管理员 / 普通用户"
CODE=$(login demo_super "$TMP_DIR/login_super.json")
expect_code "$CODE" 200 "POST /auth/login（demo_super）"
SUPER=$(json_get "$(cat "$TMP_DIR/login_super.json")" "data.token") || exit 1
CODE=$(login demo_admin "$TMP_DIR/login_admin.json")
expect_code "$CODE" 200 "POST /auth/login（demo_admin）"
ADMIN=$(json_get "$(cat "$TMP_DIR/login_admin.json")" "data.token") || exit 1
CODE=$(login demo_user "$TMP_DIR/login_user.json")
expect_code "$CODE" 200 "POST /auth/login（demo_user）"
USER=$(json_get "$(cat "$TMP_DIR/login_user.json")" "data.token") || exit 1

# ---------------------------------------------------------------------------
# 2. 概览
# ---------------------------------------------------------------------------
echo "[curl] 步骤 2：概览四卡与权限"
CODE=$(get_json "/admin/dashboard/summary" "$SUPER" "$TMP_DIR/summary.json")
expect_code "$CODE" 200 "GET /admin/dashboard/summary（超管）"
cat "$TMP_DIR/summary.json"; echo
CODE=$(get_json "/admin/dashboard/summary" "$ADMIN" "$TMP_DIR/summary_admin.json")
expect_code "$CODE" 200 "GET /admin/dashboard/summary（管理员）"
CODE=$(get_json "/admin/dashboard/summary" "$USER" "$TMP_DIR/summary_user.json")
expect_code "$CODE" 403 "GET /admin/dashboard/summary（普通用户，应 403/20005）"
[ "$(json_get "$(cat "$TMP_DIR/summary_user.json")" "code")" = "20005" ] || fail "概览越权业务码不是 20005"

# ---------------------------------------------------------------------------
# 3. Token 统计
# ---------------------------------------------------------------------------
START_DATE=$("$PYTHON_BIN" -c "from datetime import datetime,timedelta;from app.core.config import settings;print((datetime.now(settings.TZ)-timedelta(days=6)).date().isoformat())")
END_DATE=$("$PYTHON_BIN" -c "from datetime import datetime;from app.core.config import settings;print(datetime.now(settings.TZ).date().isoformat())")
echo "[curl] 步骤 3：Token 统计筛选与汇总（$START_DATE ~ $END_DATE）"
CODE=$(get_json "/admin/tokens/stats?start_date=$START_DATE&end_date=$END_DATE&agent_codes=copywriter,prompt_builder&model=doubao-seed-1.6&page=1" "$SUPER" "$TMP_DIR/tokens.json")
expect_code "$CODE" 200 "GET /admin/tokens/stats"
cat "$TMP_DIR/tokens.json"; echo
CODE=$(get_json "/admin/tokens/stats?agent_codes=unknown" "$SUPER" "$TMP_DIR/tokens_bad.json")
expect_code "$CODE" 400 "GET /admin/tokens/stats（未知 Agent，应 400/10003）"

# ---------------------------------------------------------------------------
# 4. 内容用户 / 会话
# ---------------------------------------------------------------------------
echo "[curl] 步骤 4：内容用户与会话"
CODE=$(get_json "/admin/content/users?keyword=demo&page=1&page_size=20" "$ADMIN" "$TMP_DIR/content_users_admin.json")
expect_code "$CODE" 200 "GET /admin/content/users（管理员）"
ADMIN_USERS=$(cat "$TMP_DIR/content_users_admin.json")
echo "$ADMIN_USERS"
echo "$ADMIN_USERS" | "$PYTHON_BIN" -c "import sys,json;d=json.load(sys.stdin)['data'];assert all(i['username']!='demo_super' for i in d['items']);print('[curl] 管理员用户列表已过滤超管')" || fail "管理员看到了超管用户"

CODE=$(get_json "/admin/content/users?keyword=demo&page=1&page_size=20" "$SUPER" "$TMP_DIR/content_users_super.json")
expect_code "$CODE" 200 "GET /admin/content/users（超管）"
SUPER_USERS=$(cat "$TMP_DIR/content_users_super.json")
USER_ID=$(echo "$SUPER_USERS" | "$PYTHON_BIN" -c "import sys,json;d=json.load(sys.stdin)['data'];print([i['user_id'] for i in d['items'] if i['username']=='demo_user'][0])") || exit 1
SUPER_ID=$(echo "$SUPER_USERS" | "$PYTHON_BIN" -c "import sys,json;d=json.load(sys.stdin)['data'];print([i['user_id'] for i in d['items'] if i['username']=='demo_super'][0])") || exit 1
echo "[curl] demo_user=$USER_ID demo_super=$SUPER_ID"

CODE=$(get_json "/admin/content/users/$USER_ID/sessions?page=1&page_size=20" "$SUPER" "$TMP_DIR/sessions.json")
expect_code "$CODE" 200 "GET /admin/content/users/{user_id}/sessions"
cat "$TMP_DIR/sessions.json"; echo
SESSION_ID=$(cat "$TMP_DIR/sessions.json" | "$PYTHON_BIN" -c "import sys,json;d=json.load(sys.stdin)['data'];print([i['session_id'] for i in d['items'] if i['title']=='秋季通勤衬衫'][0])") || exit 1
CODE=$(get_json "/admin/content/users/$SUPER_ID/sessions" "$ADMIN" "$TMP_DIR/sessions_denied.json")
expect_code "$CODE" 403 "GET /admin/content/users/{super}/sessions（管理员，应 403/20006）"
[ "$(json_get "$(cat "$TMP_DIR/sessions_denied.json")" "code")" = "20006" ] || fail "超管内容越权业务码不是 20006"

# ---------------------------------------------------------------------------
# 5. 批次 / 图片网格
# ---------------------------------------------------------------------------
echo "[curl] 步骤 5：批次筛选与图片网格"
CODE=$(get_json "/admin/content/sessions/$SESSION_ID/batches?batch_type=full&status=partially_failed&page=1&page_size=20" "$SUPER" "$TMP_DIR/batches.json")
expect_code "$CODE" 200 "GET /admin/content/sessions/{session_id}/batches（部分失败）"
cat "$TMP_DIR/batches.json"; echo
PARTIAL_BATCH=$(json_get "$(cat "$TMP_DIR/batches.json")" "data.items.0.batch_id") || exit 1

CODE=$(get_json "/admin/content/batches/$PARTIAL_BATCH/images?image_role=all&status=all&include_superseded=false" "$SUPER" "$TMP_DIR/images.json")
expect_code "$CODE" 200 "GET /admin/content/batches/{batch_id}/images"
cat "$TMP_DIR/images.json"; echo
IMAGE_ID=$(json_get "$(cat "$TMP_DIR/images.json")" "data.items.0.image_id") || exit 1

CODE=$(get_json "/admin/content/batches/$PARTIAL_BATCH/images?include_superseded=true" "$SUPER" "$TMP_DIR/images_all.json")
expect_code "$CODE" 200 "GET /admin/content/batches/{batch_id}/images（include_superseded=true）"

# ---------------------------------------------------------------------------
# 6. 单图详情与媒体
# ---------------------------------------------------------------------------
echo "[curl] 步骤 6：单图详情、缩略图、大图、下载"
CODE=$(get_json "/admin/content/images/$IMAGE_ID" "$SUPER" "$TMP_DIR/image_detail.json")
expect_code "$CODE" 200 "GET /admin/content/images/{image_id}"
cat "$TMP_DIR/image_detail.json"; echo

CODE=$(curl -sS -o "$TMP_DIR/thumb.webp" -w "%{http_code}" -H "Authorization: Bearer $SUPER" "$BASE/admin/content/images/$IMAGE_ID/thumbnail")
expect_code "$CODE" 200 "GET /admin/content/images/{image_id}/thumbnail"
file "$TMP_DIR/thumb.webp" 2>/dev/null || true

CODE=$(curl -sS -o "$TMP_DIR/preview.png" -w "%{http_code}" -H "Authorization: Bearer $SUPER" "$BASE/admin/content/images/$IMAGE_ID/content")
expect_code "$CODE" 200 "GET /admin/content/images/{image_id}/content"
file "$TMP_DIR/preview.png" 2>/dev/null || true

CODE=$(curl -sS -D "$TMP_DIR/download_headers.txt" -o "$TMP_DIR/download.png" -w "%{http_code}" -H "Authorization: Bearer $SUPER" "$BASE/admin/content/images/$IMAGE_ID/download")
expect_code "$CODE" 200 "GET /admin/content/images/{image_id}/download"
grep -i "content-disposition" "$TMP_DIR/download_headers.txt" || fail "下载响应缺少 Content-Disposition"

# 归档图片：取隐藏会话下的归档批次
CODE=$(get_json "/admin/content/users/$USER_ID/sessions" "$SUPER" "$TMP_DIR/sessions_all.json")
expect_code "$CODE" 200 "GET /admin/content/users/{user_id}/sessions（全部）"
HIDDEN_SESSION=$(cat "$TMP_DIR/sessions_all.json" | "$PYTHON_BIN" -c "import sys,json;d=json.load(sys.stdin)['data'];print([i['session_id'] for i in d['items'] if i['status']=='hidden'][0])") || exit 1
CODE=$(get_json "/admin/content/sessions/$HIDDEN_SESSION/batches" "$SUPER" "$TMP_DIR/batches_hidden.json")
expect_code "$CODE" 200 "GET /admin/content/sessions/{hidden}/batches"
ARCHIVED_BATCH=$(json_get "$(cat "$TMP_DIR/batches_hidden.json")" "data.items.0.batch_id") || exit 1
CODE=$(get_json "/admin/content/batches/$ARCHIVED_BATCH/images" "$SUPER" "$TMP_DIR/images_archived.json")
expect_code "$CODE" 200 "GET /admin/content/batches/{archived}/images"
ARCHIVED_IMAGE=$(cat "$TMP_DIR/images_archived.json" | "$PYTHON_BIN" -c "import sys,json;d=json.load(sys.stdin)['data'];print([i['image_id'] for i in d['items'] if i['archived_at']][0])") || exit 1
echo "[curl] 归档图片 image_id=$ARCHIVED_IMAGE"
CODE=$(curl -sS -o "$TMP_DIR/archive_preview.png" -w "%{http_code}" -H "Authorization: Bearer $SUPER" "$BASE/admin/content/images/$ARCHIVED_IMAGE/content")
expect_code "$CODE" 200 "GET /admin/content/images/{archived}/content（从 archive/ 读取）"

echo "[curl] 步骤 7：媒体缺失与越权"
CODE=$(curl -sS -o "$TMP_DIR/missing.json" -w "%{http_code}" -H "Authorization: Bearer $SUPER" "$BASE/admin/content/images/999999/content")
expect_code "$CODE" 404 "GET /admin/content/images/999999/content（应 404/30024）"
[ "$(json_get "$(cat "$TMP_DIR/missing.json")" "code")" = "30024" ] || fail "图片不存在业务码不是 30024"

# ---------------------------------------------------------------------------
# 8. 用户列表 / 详情统计
# ---------------------------------------------------------------------------
echo "[curl] 步骤 8：用户列表与详情真实统计"
CODE=$(get_json "/admin/users?keyword=demo&status=all&page=1&page_size=20" "$SUPER" "$TMP_DIR/users.json")
expect_code "$CODE" 200 "GET /admin/users"
cat "$TMP_DIR/users.json"; echo
CODE=$(get_json "/admin/users/$USER_ID" "$SUPER" "$TMP_DIR/user_detail.json")
expect_code "$CODE" 200 "GET /admin/users/{id}"
cat "$TMP_DIR/user_detail.json"; echo
echo "$(cat "$TMP_DIR/user_detail.json")" | "$PYTHON_BIN" -c "import sys,json;s=json.load(sys.stdin)['data']['stats'];assert s['stats_available'] is True;print('[curl] 用户统计 stats_available=true',s)" || fail "用户统计未启用"

CODE=$(get_json "/admin/users/$SUPER_ID" "$ADMIN" "$TMP_DIR/user_denied.json")
expect_code "$CODE" 403 "GET /admin/users/{super}（管理员，应 403/20006）"
CODE=$(get_json "/admin/users" "$USER" "$TMP_DIR/users_denied.json")
expect_code "$CODE" 403 "GET /admin/users（普通用户，应 403/20005）"

echo "[curl] 全部 7 号管理后台接口调用结束；文件输出目录：$TMP_DIR"
