#!/usr/bin/env bash
# 历史作品最小 demo 后端 curl 验收脚本。
#
# 用法（在 backend/ 目录）：
#   bash scripts/curl_history_smoke.sh
#
# 使用独立的 esimage_history_curl 数据库与 .curl_tmp/storage_history 存储目录，
# 不污染同机其他 agent 正在使用的 esimage 开发库。
# 依赖：本机 PostgreSQL（可复用 docker compose 的 esimage-postgres）与 Python 依赖。

set -u

cd "$(dirname "$0")/.." || exit 1

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-55433}"
DB_USER="${DB_USER:-esimage}"
DB_PASSWORD="${DB_PASSWORD:-esimage}"
DB_NAME="${DB_NAME:-esimage_history_curl}"
ADMIN_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/postgres"

export DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
export JWT_SECRET="${JWT_SECRET:-history-demo-secret-0123456789abcdef}"
export PYTHONPATH=.
# 避免 Windows 控制台按 GBK 解码内联 Python 脚本中的中文
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export STORAGE_ROOT=".curl_tmp/storage_history"
export ARCHIVE_READ_TIMEOUT_SECONDS="${ARCHIVE_READ_TIMEOUT_SECONDS:-60}"

PORT="${PORT:-8020}"
BASE="http://127.0.0.1:${PORT}/api/v1"
TMP_DIR=".curl_tmp/history"
# 只清理本脚本自己的目录，避免误删同机其他 agent 的 .curl_tmp 数据
rm -rf "$TMP_DIR" "$STORAGE_ROOT"
mkdir -p "$TMP_DIR"

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

expect_json() {
  # 用法：expect_json <json 字符串> <字段> <期望值> <说明>
  local actual
  actual=$(json_get "$1" "$2") || exit 1
  if [ "$actual" != "$3" ]; then
    fail "$4：字段 $2 期望 $3，实际 $actual"
  fi
  echo "[curl] $4：$2=$actual"
}

request_json() {
  # 用法：request_json GET <path> <token>
  local method="$1" path="$2" token="$3"
  curl -sS -o "$TMP_DIR/last_body.txt" -w "%{http_code}" -X "$method" "$BASE$path" \
    -H "Authorization: Bearer $token"
}

require_python() {
  python -c "import psycopg" >/dev/null 2>&1 || fail "缺少 psycopg，请先安装 backend/requirements.txt"
}

echo "[curl] 重建独立验收数据库 $DB_NAME"
require_python
python - "$ADMIN_URL" "$DB_NAME" <<'PY'
import sys

import psycopg

conn = psycopg.connect(sys.argv[1], autocommit=True)
conn.execute(f'DROP DATABASE IF EXISTS "{sys.argv[2]}" WITH (FORCE)')
conn.execute(f'CREATE DATABASE "{sys.argv[2]}"')
conn.close()
print(f"[curl] 数据库 {sys.argv[2]} 已重建")
PY

echo "[curl] 建表并写入历史种子"
python scripts/init_db.py >/dev/null || fail "建表失败"
python scripts/seed.py > "$TMP_DIR/seed.log" 2>&1 || { cat "$TMP_DIR/seed.log"; fail "种子失败"; }
tail -3 "$TMP_DIR/seed.log"

echo "[curl] 检查端口 $PORT 是否空闲"
if curl -sS -o /dev/null "http://127.0.0.1:$PORT/openapi.json" 2>/dev/null; then
  fail "端口 $PORT 已被其他服务占用，请用 PORT=<其他端口> 重试"
fi

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
for _ in $(seq 1 60); do
  if curl -sS -o /dev/null "http://127.0.0.1:$PORT/openapi.json" 2>/dev/null; then
    READY=1
    break
  fi
  python -c "import time;time.sleep(0.25)"
done
if [ "$READY" -ne 1 ]; then
  tail -40 "$TMP_DIR/uvicorn.log"
  fail "服务启动失败"
fi
echo "[curl] 服务已启动"

# ---------------------------------------------------------------------------
# 0. 读取种子夹具 ID
# ---------------------------------------------------------------------------
python - "$TMP_DIR/fixtures.json" <<'PY' || fail "读取种子夹具失败"
import json
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import GeneratedImage, GenerationBatch

with SessionLocal() as db:
    batches = list(
        db.scalars(
            select(GenerationBatch).where(
                GenerationBatch.client_request_id.like("seed-history-%")
            )
        )
    )
    out = {}
    for batch in batches:
        key = batch.client_request_id[len("seed-history-") :]
        rows = db.scalars(
            select(GeneratedImage)
            .where(GeneratedImage.batch_id == batch.id)
            .order_by(GeneratedImage.index_no.asc(), GeneratedImage.attempt_no.desc())
        )
        images = {}
        for row in rows:
            if row.status == "superseded":
                continue
            images.setdefault(row.index_no, row.id)
        out[key] = {
            "batch_id": batch.id,
            "images": {str(index): image_id for index, image_id in images.items()},
        }
    json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
print(f"[curl] 夹具已写入 {sys.argv[1]}")
PY

FIXTURES=$(cat "$TMP_DIR/fixtures.json")
COMPLETED_ID=$(json_get "$FIXTURES" "completed-01.batch_id") || exit 1
PARTIAL_ID=$(json_get "$FIXTURES" "partially-failed.batch_id") || exit 1
SAMPLE_ID=$(json_get "$FIXTURES" "sample.batch_id") || exit 1
ARCHIVED_ID=$(json_get "$FIXTURES" "archived.batch_id") || exit 1
OTHER_ID=$(json_get "$FIXTURES" "other-user.batch_id") || exit 1
ILLEGAL_ID=$(json_get "$FIXTURES" "completed-18.batch_id") || exit 1
COMPLETED_IMAGE=$(json_get "$FIXTURES" "completed-01.images.1") || exit 1
SAMPLE_IMAGE=$(json_get "$FIXTURES" "sample.images.1") || exit 1
ARCHIVED_IMAGE=$(json_get "$FIXTURES" "archived.images.1") || exit 1
ILLEGAL_IMAGE=$(json_get "$FIXTURES" "completed-18.images.1") || exit 1

# ---------------------------------------------------------------------------
# 1. 登录
# ---------------------------------------------------------------------------
echo "[curl] POST /auth/login（demo_user / demo_admin / demo_dual）"
for user in demo_user demo_admin demo_dual; do
  printf '{"username":"%s","password":"Demo1234","remember_me":false}' "$user" > "$TMP_DIR/login_$user.json"
  CODE=$(curl -sS -o "$TMP_DIR/login_$user.response" -w "%{http_code}" -X POST "$BASE/auth/login" \
    -H "Content-Type: application/json" --data-binary "@$TMP_DIR/login_$user.json")
  expect_http "$CODE" 200 "POST /auth/login（$user）"
done
TOKEN=$(json_get "$(cat "$TMP_DIR/login_demo_user.response")" "data.token") || exit 1
ADMIN_TOKEN=$(json_get "$(cat "$TMP_DIR/login_demo_admin.response")" "data.token") || exit 1
DUAL_TOKEN=$(json_get "$(cat "$TMP_DIR/login_demo_dual.response")" "data.token") || exit 1

# ---------------------------------------------------------------------------
# 2. 历史列表与分页
# ---------------------------------------------------------------------------
echo "[curl] GET /history?page=1"
CODE=$(request_json GET "/history?page=1" "$TOKEN")
expect_http "$CODE" 200 "GET /history?page=1"
BODY=$(cat "$TMP_DIR/last_body.txt")
expect_json "$BODY" "data.total" "21" "历史批次总数"
expect_json "$BODY" "data.page_size" "20" "历史分页大小"
expect_json "$BODY" "data.page" "1" "历史当前页"
ITEMS_LEN=$(json_get "$BODY" "data.items" | python -c "import sys,ast;print(len(ast.literal_eval(sys.stdin.read())))")
[ "$ITEMS_LEN" = "20" ] || fail "第 1 页应有 20 条，实际 $ITEMS_LEN"

CODE=$(request_json GET "/history?page=2" "$TOKEN")
expect_http "$CODE" 200 "GET /history?page=2"
BODY=$(cat "$TMP_DIR/last_body.txt")
ITEMS_LEN=$(json_get "$BODY" "data.items" | python -c "import sys,ast;print(len(ast.literal_eval(sys.stdin.read())))")
[ "$ITEMS_LEN" = "1" ] || fail "第 2 页应有 1 条，实际 $ITEMS_LEN"

CODE=$(request_json GET "/history?page=999" "$TOKEN")
expect_http "$CODE" 200 "GET /history?page=999"
BODY=$(cat "$TMP_DIR/last_body.txt")
ITEMS_LEN=$(json_get "$BODY" "data.items" | python -c "import sys,ast;print(len(ast.literal_eval(sys.stdin.read())))")
[ "$ITEMS_LEN" = "0" ] || fail "越界页应为空，实际 $ITEMS_LEN"
expect_json "$BODY" "data.total" "21" "越界页 total 仍正确"

CODE=$(request_json GET "/history?page=0" "$TOKEN")
expect_http "$CODE" 400 "GET /history?page=0"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "10001" "page 非正整数业务码"

CODE=$(request_json GET "/history?page=99999999999999999999" "$TOKEN")
expect_http "$CODE" 200 "GET /history?page=超大值"
ITEMS_LEN=$(json_get "$(cat "$TMP_DIR/last_body.txt")" "data.items" | python -c "import sys,ast;print(len(ast.literal_eval(sys.stdin.read())))")
[ "$ITEMS_LEN" = "0" ] || fail "超大页码应为空，实际 $ITEMS_LEN"

# ---------------------------------------------------------------------------
# 3. 批次详情
# ---------------------------------------------------------------------------
echo "[curl] GET /history/{completed_batch_id}"
CODE=$(request_json GET "/history/$COMPLETED_ID" "$TOKEN")
expect_http "$CODE" 200 "GET /history/{completed}"
BODY=$(cat "$TMP_DIR/last_body.txt")
expect_json "$BODY" "data.status" "completed" "completed 批次状态"
expect_json "$BODY" "data.success_count" "6" "completed 成功张数"
IMAGES_LEN=$(json_get "$BODY" "data.images" | python -c "import sys,ast;print(len(ast.literal_eval(sys.stdin.read())))")
[ "$IMAGES_LEN" = "6" ] || fail "completed 详情应有 6 张图，实际 $IMAGES_LEN"

CODE=$(request_json GET "/history/$PARTIAL_ID" "$TOKEN")
expect_http "$CODE" 200 "GET /history/{partial}"
BODY=$(cat "$TMP_DIR/last_body.txt")
expect_json "$BODY" "data.status" "partially_failed" "partial 批次状态"
expect_json "$BODY" "data.success_count" "5" "partial 成功张数"
expect_json "$BODY" "data.total_count" "6" "partial 计划张数"

CODE=$(request_json GET "/history/$SAMPLE_ID" "$TOKEN")
expect_http "$CODE" 404 "GET /history/{sample}（应 404）"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "30004" "示例批次业务码"

CODE=$(request_json GET "/history/$COMPLETED_ID" "$DUAL_TOKEN")
expect_http "$CODE" 403 "GET /history/{other_user}（应 403）"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "20005" "越权业务码"

CODE=$(request_json GET "/history/$OTHER_ID" "$TOKEN")
expect_http "$CODE" 403 "GET /history/{demo_dual 的批次}（应 403）"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "20005" "反向越权业务码"

# ---------------------------------------------------------------------------
# 4. 缩略图、大图预览、单张下载
# ---------------------------------------------------------------------------
echo "[curl] GET /images/{id}/thumbnail"
CODE=$(curl -sS -o "$TMP_DIR/thumb.webp" -w "%{http_code}" "$BASE/images/$COMPLETED_IMAGE/thumbnail" \
  -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{id}/thumbnail"
file "$TMP_DIR/thumb.webp" 2>/dev/null || true

echo "[curl] GET /images/{id}/content"
CODE=$(curl -sS -o "$TMP_DIR/content.png" -w "%{http_code}" "$BASE/images/$COMPLETED_IMAGE/content" \
  -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{id}/content"
file "$TMP_DIR/content.png" 2>/dev/null || true

echo "[curl] GET /images/{id}/download"
CODE=$(curl -sS -D "$TMP_DIR/download_headers.txt" -o "$TMP_DIR/main.png" -w "%{http_code}" \
  "$BASE/images/$COMPLETED_IMAGE/download" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{id}/download"
grep -i "content-disposition" "$TMP_DIR/download_headers.txt" || fail "下载缺少 Content-Disposition"

echo "[curl] GET /images/{id}/download（商品名称含非法字符）"
CODE=$(curl -sS -D "$TMP_DIR/illegal_headers.txt" -o /dev/null -w "%{http_code}" \
  "$BASE/images/$ILLEGAL_IMAGE/download" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{id}/download（非法字符名称）"
python - "$TMP_DIR/illegal_headers.txt" <<'PY' || fail "文件名非法字符未替换"
import sys
from urllib.parse import unquote

text = open(sys.argv[1], encoding="utf-8").read()
disposition = text.lower()
# 秋季/通勤:衬衫 -> 秋季_通勤_衬衫（百分号编码后的 ASCII 形态）
expected = "%e7%a7%8b%e5%ad%a3_%e9%80%9a%e5%8b%a4_%e8%a1%ac%e8%a1%ab_%e4%b8%bb%e5%9b%be_1_"
assert expected in disposition, disposition
assert "%2f" not in disposition and "%3a" not in disposition, disposition
decoded = unquote(disposition)
assert "秋季_通勤_衬衫_主图_1_" in decoded, decoded
print("[curl] 文件名非法字符已替换为下划线")
PY

echo "[curl] GET /images/{sample}/download（应 409）"
CODE=$(request_json GET "/images/$SAMPLE_IMAGE/download" "$TOKEN")
expect_http "$CODE" 409 "GET /images/{sample}/download"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "30005" "示例图下载业务码"

# ---------------------------------------------------------------------------
# 5. 整组 ZIP
# ---------------------------------------------------------------------------
echo "[curl] GET /batches/{completed}/download"
CODE=$(curl -sS -D "$TMP_DIR/zip_headers.txt" -o "$TMP_DIR/completed.zip" -w "%{http_code}" \
  "$BASE/batches/$COMPLETED_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /batches/{completed}/download"
grep -i "content-type: application/zip" "$TMP_DIR/zip_headers.txt" || fail "ZIP Content-Type 不正确"
python - "$TMP_DIR/completed.zip" <<'PY' || fail "completed ZIP 内容校验失败"
import csv
import io
import sys
import zipfile

archive = zipfile.ZipFile(sys.argv[1])
names = archive.namelist()
assert len(names) == 7, names
raw = archive.read("manifest.csv")
assert raw.startswith(b"\xef\xbb\xbf"), "manifest 缺少 UTF-8 BOM"
rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
assert rows[0] == ["序号", "文件名", "状态", "宽度", "高度", "生成时间", "失败原因"], rows[0]
assert len(rows) == 7 and all(row[2] == "success" for row in rows[1:]), rows
print(f"[curl] completed ZIP：{len(names)} 个文件，manifest {len(rows) - 1} 行")
PY

echo "[curl] GET /batches/{partial}/download"
CODE=$(curl -sS -o "$TMP_DIR/partial.zip" -w "%{http_code}" \
  "$BASE/batches/$PARTIAL_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /batches/{partial}/download"
python - "$TMP_DIR/partial.zip" <<'PY' || fail "partial ZIP 内容校验失败"
import csv
import io
import sys
import zipfile

archive = zipfile.ZipFile(sys.argv[1])
names = archive.namelist()
assert len([name for name in names if name.endswith(".png")]) == 5, names
rows = list(csv.reader(io.StringIO(archive.read("manifest.csv").decode("utf-8-sig"))))
assert len(rows) == 7, rows
failed = rows[6]
assert failed[0] == "6" and failed[1] == "" and failed[2] == "failed", failed
assert failed[6] == "生图执行失败", failed
print(f"[curl] partial ZIP：5 张成功图，manifest 第 6 行失败原因为「{failed[6]}」")
PY

CODE=$(request_json GET "/batches/$SAMPLE_ID/download" "$TOKEN")
expect_http "$CODE" 409 "GET /batches/{sample}/download（应 409）"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "30005" "示例批次 ZIP 业务码"

# ---------------------------------------------------------------------------
# 6. 归档读取与降级
# ---------------------------------------------------------------------------
echo "[curl] 归档批次：详情、缩略图、原图、下载、ZIP"
CODE=$(request_json GET "/history/$ARCHIVED_ID" "$TOKEN")
expect_http "$CODE" 200 "GET /history/{archived}"
CODE=$(curl -sS -o "$TMP_DIR/archive_thumb.webp" -w "%{http_code}" \
  "$BASE/images/$ARCHIVED_IMAGE/thumbnail" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{archived}/thumbnail"
CODE=$(curl -sS -o "$TMP_DIR/archive_content.png" -w "%{http_code}" \
  "$BASE/images/$ARCHIVED_IMAGE/content" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{archived}/content"
CODE=$(curl -sS -o "$TMP_DIR/archive_main.png" -w "%{http_code}" \
  "$BASE/images/$ARCHIVED_IMAGE/download" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /images/{archived}/download"
CODE=$(curl -sS -o "$TMP_DIR/archive.zip" -w "%{http_code}" \
  "$BASE/batches/$ARCHIVED_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$CODE" 200 "GET /batches/{archived}/download"

echo "[curl] 临时移走归档对象，验证 30014 与错误日志"
ARCHIVE_PATH=$(python - "$ARCHIVED_IMAGE" <<'PY'
import sys

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import GeneratedImage

with SessionLocal() as db:
    image = db.get(GeneratedImage, int(sys.argv[1]))
    assert image is not None and image.file_path
    print(settings.STORAGE_ROOT / "archive" / image.file_path)
PY
) || fail "定位归档对象失败"
BACKUP_PATH="$ARCHIVE_PATH.bak"
mv "$ARCHIVE_PATH" "$BACKUP_PATH" || fail "移走归档对象失败"
restore_archive() { mv "$BACKUP_PATH" "$ARCHIVE_PATH" 2>/dev/null || true; }
trap 'restore_archive; cleanup' EXIT

CODE=$(request_json GET "/images/$ARCHIVED_IMAGE/content" "$TOKEN")
expect_http "$CODE" 404 "GET /images/{archived}/content（归档缺失）"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "message" "文件归档中，请稍后重试" "归档缺失文案"

CODE=$(request_json GET "/images/$ARCHIVED_IMAGE/download" "$TOKEN")
expect_http "$CODE" 404 "GET /images/{archived}/download（归档缺失）"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "30014" "归档缺失业务码"

CODE=$(request_json GET "/batches/$ARCHIVED_ID/download" "$TOKEN")
expect_http "$CODE" 404 "GET /batches/{archived}/download（归档缺失）"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "30014" "归档 ZIP 业务码"

restore_archive
trap cleanup EXIT
if grep -q "归档读取失败" "$TMP_DIR/uvicorn.log"; then
  echo "[curl] 服务端已记录归档读取错误日志"
else
  fail "未记录归档读取错误日志"
fi

# ---------------------------------------------------------------------------
# 7. 权限与未登录
# ---------------------------------------------------------------------------
CODE=$(request_json GET "/history" "$ADMIN_TOKEN")
expect_http "$CODE" 403 "GET /history（demo_admin）"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "20005" "管理员业务码"

echo "[curl] GET /history（不带 token）"
CODE=$(curl -sS -o "$TMP_DIR/last_body.txt" -w "%{http_code}" "$BASE/history")
expect_http "$CODE" 401 "GET /history（未登录）"
expect_json "$(cat "$TMP_DIR/last_body.txt")" "code" "20003" "未登录业务码"

echo "[curl] 全部历史作品接口验收通过；输出目录：$TMP_DIR"
