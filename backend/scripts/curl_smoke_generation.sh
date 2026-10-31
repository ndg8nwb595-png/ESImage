#!/usr/bin/env bash
# 4 号 PRD「生图任务与结果」最小 demo 的 curl 验收脚本。
#
# 用法（在 backend/ 目录）：
#   bash scripts/curl_smoke_generation.sh
#
# 前置：
#   1. backend/.env 已配置 ARK_API_KEY（或 DOUBAO_API_KEY）与豆包模型名；
#   2. 已执行 python scripts/init_db.py && python scripts/seed.py；
#   3. 本机 PostgreSQL 可用（默认复用 55433 的 esimage-postgres 容器）。
#
# 脚本会临时启动 8011 端口的 uvicorn，结束后自动关闭。
# 真实模型调用会产生费用；生图模型未开通时会在示例批次阶段明确失败。

set -u

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://esimage:esimage@127.0.0.1:55433/esimage_generation}"
export STORAGE_ROOT="${STORAGE_ROOT:-storage}"
export PYTHONPATH=.
# 默认只走真实豆包；需要本地演示时可显式传 APP_ENV=test GENERATION_MODEL_PROVIDER=fake
export APP_ENV="${APP_ENV:-development}"
export GENERATION_MODEL_PROVIDER="${GENERATION_MODEL_PROVIDER:-doubao}"
unset GENERATION_FAULT_MODE

PORT="${PORT:-8011}"
BASE="http://127.0.0.1:$PORT/api/v1"
TMP_DIR=".curl_generation_tmp"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

fail() {
  echo "[curl][失败] $*" >&2
  if [ -f "$TMP_DIR/uvicorn.log" ]; then
    echo "--- uvicorn.log 末尾 ---" >&2
    tail -30 "$TMP_DIR/uvicorn.log" >&2
  fi
  exit 1
}

expect_http() {
  # 用法：expect_http <实际状态码> <期望状态码> <说明>
  if [ "$1" != "$2" ]; then
    fail "$3：期望 HTTP $2，实际 $1；响应体 $(cat "$TMP_DIR/last_body.json" 2>/dev/null)"
  fi
  echo "[curl] $3 -> HTTP $1"
}

json_get() {
  # 用法：json_get <json 文件> <点分路径>
  python - "$1" "$2" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
for part in sys.argv[2].split("."):
    if part == "":
        continue
    data = data[int(part)] if isinstance(data, list) else data[part]
print(data)
PY
}

write_json() {
  # 用法：write_json <输出文件> <python 赋值语句>
  local output="$1"
  local script="$2"
  python - "$output" <<PY
import json, sys
b = {}
$script
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(b, handle, ensure_ascii=False)
PY
}

request_json() {
  # 用法：request_json <方法> <路径> <请求体文件或 -> <期望状态码> <说明>
  local method="$1"
  local path="$2"
  local body_file="$3"
  local expected="$4"
  local title="$5"
  local response_file="$TMP_DIR/last_body.json"

  if [ "$body_file" = "-" ]; then
    code=$(curl -s -o "$response_file" -w "%{http_code}" -X "$method" "$BASE$path" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
  else
    code=$(curl -s -o "$response_file" -w "%{http_code}" -X "$method" "$BASE$path" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      --data-binary @"$body_file")
  fi
  expect_http "$code" "$expected" "$title"
}

poll_batch() {
  # 用法：poll_batch <batch_id> <超时秒数> <说明>
  local batch_id="$1"
  local timeout="$2"
  local title="$3"
  local deadline=$((SECONDS + timeout))
  while [ $SECONDS -lt $deadline ]; do
    code=$(curl -s -o "$TMP_DIR/batch.json" -w "%{http_code}" \
      "$BASE/generations/$batch_id" -H "Authorization: Bearer $TOKEN")
    expect_http "$code" "200" "$title 查询批次"
    local status stage completed total
    status=$(json_get "$TMP_DIR/batch.json" "data.status")
    stage=$(json_get "$TMP_DIR/batch.json" "data.stage")
    completed=$(json_get "$TMP_DIR/batch.json" "data.completed_count")
    total=$(json_get "$TMP_DIR/batch.json" "data.total_count")
    echo "[poll] batch=$batch_id status=$status stage=$stage progress=$completed/$total"
    case "$status" in
      sample_ready|completed|partially_failed|failed|cancelled) return 0 ;;
    esac
    sleep 3
  done
  fail "$title 超时（${timeout}s）"
}

# ---------------------------------------------------------------- 启动服务

echo "[curl] 启动 uvicorn :$PORT"
python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$TMP_DIR/uvicorn.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/openapi.json" || true)
  [ "$code" = "200" ] && break
  sleep 1
done
[ "$code" = "200" ] || fail "服务启动失败（检查 backend/.env 与模型配置）"

# ---------------------------------------------------------------- 登录

echo "[curl] 登录演示账号"
code=$(curl -s -o "$TMP_DIR/login.json" -w "%{http_code}" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo_user","password":"Demo1234","remember_me":false}')
expect_http "$code" "200" "demo_user 登录"
TOKEN=$(json_get "$TMP_DIR/login.json" "data.token")

curl -s -o "$TMP_DIR/admin_login.json" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo_admin","password":"Demo1234","remember_me":false}'
ADMIN_TOKEN=$(json_get "$TMP_DIR/admin_login.json" "data.token")

curl -s -o "$TMP_DIR/other_login.json" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo_dual","password":"Demo1234","remember_me":false}'
OTHER_TOKEN=$(json_get "$TMP_DIR/other_login.json" "data.token")

# ---------------------------------------------------------------- 配置读取

echo "[curl] 读取模板与尺寸"
request_json GET "/templates" "-" 200 "模板列表"
TEMPLATE_ID=$(json_get "$TMP_DIR/last_body.json" "data.items.0.template_id")
request_json GET "/sizes" "-" 200 "尺寸预设"
SIZE_COUNT=$(json_get "$TMP_DIR/last_body.json" "data.total")
[ "$SIZE_COUNT" -ge 4 ] || fail "尺寸预设数量不足：$SIZE_COUNT"
code=$(curl -s -o "$TMP_DIR/thumb.webp" -w "%{http_code}" \
  "$BASE/templates/$TEMPLATE_ID/thumbnail" -H "Authorization: Bearer $TOKEN")
expect_http "$code" "200" "模板缩略图"
[ -s "$TMP_DIR/thumb.webp" ] || fail "模板缩略图为空"

# ---------------------------------------------------------------- 权限与校验

code=$(curl -s -o "$TMP_DIR/last_body.json" -w "%{http_code}" "$BASE/templates" \
  -H "Authorization: Bearer $ADMIN_TOKEN")
expect_http "$code" "403" "管理员访问模板列表（无 user.generate）"

write_json "$TMP_DIR/bad_name.json" 'b.update({"client_request_id":"11111111-1111-4111-8111-111111111111","product_name":"   ","width":1000,"height":1000})'
request_json POST "/generations/sample" "$TMP_DIR/bad_name.json" 400 "商品名称为空"
write_json "$TMP_DIR/bad_template.json" 'b.update({"client_request_id":"22222222-2222-4222-8222-222222222222","product_name":"秋季通勤衬衫","width":1000,"height":1000,"template_id":999999})'
request_json POST "/generations/sample" "$TMP_DIR/bad_template.json" 404 "模板不存在"
write_json "$TMP_DIR/bad_size.json" 'b.update({"client_request_id":"33333333-3333-4333-8333-333333333333","product_name":"秋季通勤衬衫","width":1001,"height":1000})'
request_json POST "/generations/sample" "$TMP_DIR/bad_size.json" 400 "宽高不是 8 的倍数"

# ---------------------------------------------------------------- 上传商品图

echo "[curl] 上传两张商品图"
python - <<'PY'
from PIL import Image
Image.new("RGB", (1200, 1200), (235, 240, 245)).save(".curl_generation_tmp/goods.png")
PY
UPLOAD_IDS=""
for index in 1 2; do
  cp "$TMP_DIR/goods.png" "$TMP_DIR/goods_$index.png"
  code=$(curl -s -o "$TMP_DIR/upload_$index.json" -w "%{http_code}" -X POST "$BASE/uploads" \
    -H "Authorization: Bearer $TOKEN" -F "file=@$TMP_DIR/goods_$index.png;type=image/png")
  expect_http "$code" "200" "上传商品图 $index"
  upload_id=$(json_get "$TMP_DIR/upload_$index.json" "data.upload_id")
  if [ -z "$UPLOAD_IDS" ]; then UPLOAD_IDS="$upload_id"; else UPLOAD_IDS="$UPLOAD_IDS,$upload_id"; fi
done

# ---------------------------------------------------------------- 示例批次

echo "[curl] 创建示例批次（真实 8 Agent + 豆包）"
REQUEST_ID=$(python -c "import uuid;print(uuid.uuid4())")
write_json "$TMP_DIR/sample.json" "b.update({'client_request_id':'$REQUEST_ID','session_id':None,'product_name':'秋季通勤衬衫','style_text':'简洁白底，柔和棚拍光','width':1000,'height':1000,'template_id':$TEMPLATE_ID,'upload_ids':[$UPLOAD_IDS],'requirement_summary':None})"
code=$(curl -s -o "$TMP_DIR/last_body.json" -w "%{http_code}" -X POST "$BASE/generations/sample" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data-binary @"$TMP_DIR/sample.json")
expect_http "$code" "200" "创建示例批次"
SAMPLE_BATCH_ID=$(json_get "$TMP_DIR/last_body.json" "data.batch_id")
SESSION_ID=$(json_get "$TMP_DIR/last_body.json" "data.session_id")
SAMPLE_STATUS=$(json_get "$TMP_DIR/last_body.json" "data.status")
[ "$SAMPLE_STATUS" = "queued" ] || fail "创建示例批次状态应为 queued，实际 $SAMPLE_STATUS"

curl -s -o "$TMP_DIR/sample_replay.json" -X POST "$BASE/generations/sample" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data-binary @"$TMP_DIR/sample.json"
REPLAY_ID=$(json_get "$TMP_DIR/sample_replay.json" "data.batch_id")
[ "$REPLAY_ID" = "$SAMPLE_BATCH_ID" ] || fail "相同 client_request_id 未返回同一批次"

poll_batch "$SAMPLE_BATCH_ID" 900 "示例批次"
SAMPLE_STATUS=$(json_get "$TMP_DIR/batch.json" "data.status")
if [ "$SAMPLE_STATUS" != "sample_ready" ]; then
  echo "--- 批次错误信息 ---" >&2
  cat "$TMP_DIR/batch.json" >&2
  fail "示例批次未成功：$SAMPLE_STATUS"
fi
SAMPLE_IMAGE_ID=$(json_get "$TMP_DIR/batch.json" "data.images.0.image_id")

echo "[curl] 示例图可预览、确认前不可下载"
code=$(curl -s -o "$TMP_DIR/sample_preview.png" -w "%{http_code}" \
  "$BASE/images/$SAMPLE_IMAGE_ID/content" -H "Authorization: Bearer $TOKEN")
expect_http "$code" "200" "示例图预览"
[ -s "$TMP_DIR/sample_preview.png" ] || fail "示例图预览为空"
code=$(curl -s -o "$TMP_DIR/last_body.json" -w "%{http_code}" \
  "$BASE/images/$SAMPLE_IMAGE_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$code" "409" "示例图确认前下载被拒绝"

# 重新生成示例：创建新批次，旧批次保留
echo "[curl] 重新生成示例"
REQUEST_ID=$(python -c "import uuid;print(uuid.uuid4())")
write_json "$TMP_DIR/sample2.json" "b.update({'client_request_id':'$REQUEST_ID','session_id':$SESSION_ID,'product_name':'秋季通勤衬衫','style_text':'简洁白底，柔和棚拍光','width':1000,'height':1000,'template_id':$TEMPLATE_ID,'upload_ids':[$UPLOAD_IDS],'requirement_summary':None})"
code=$(curl -s -o "$TMP_DIR/last_body.json" -w "%{http_code}" -X POST "$BASE/generations/sample" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data-binary @"$TMP_DIR/sample2.json")
expect_http "$code" "200" "重新生成示例"
SAMPLE2_BATCH_ID=$(json_get "$TMP_DIR/last_body.json" "data.batch_id")
poll_batch "$SAMPLE2_BATCH_ID" 900 "第二个示例批次"
[ "$(json_get "$TMP_DIR/batch.json" "data.status")" = "sample_ready" ] || fail "第二个示例批次未成功"

echo "[curl] 旧示例不可确认"
write_json "$TMP_DIR/confirm_old.json" 'b.update({"client_request_id":"44444444-4444-4444-8444-444444444444"})'
code=$(curl -s -o "$TMP_DIR/last_body.json" -w "%{http_code}" -X POST \
  "$BASE/generations/$SAMPLE_BATCH_ID/confirm" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" --data-binary @"$TMP_DIR/confirm_old.json")
expect_http "$code" "409" "旧示例确认被拒绝"

# ---------------------------------------------------------------- 全套批次

echo "[curl] 确认最新示例，创建全套批次"
CONFIRM_ID=$(python -c "import uuid;print(uuid.uuid4())")
write_json "$TMP_DIR/confirm.json" "b.update({'client_request_id':'$CONFIRM_ID'})"
code=$(curl -s -o "$TMP_DIR/confirm.json.out" -w "%{http_code}" -X POST \
  "$BASE/generations/$SAMPLE2_BATCH_ID/confirm" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" --data-binary @"$TMP_DIR/confirm.json")
expect_http "$code" "200" "确认示例并生成全套"
FULL_BATCH_ID=$(json_get "$TMP_DIR/confirm.json.out" "data.full_batch_id")
FULL_TOTAL=$(json_get "$TMP_DIR/confirm.json.out" "data.total_count")
[ "$FULL_TOTAL" = "6" ] || fail "全套批次张数应为 6，实际 $FULL_TOTAL"

poll_batch "$FULL_BATCH_ID" 1800 "全套批次"
FULL_STATUS=$(json_get "$TMP_DIR/batch.json" "data.status")
if [ "$FULL_STATUS" != "completed" ]; then
  cat "$TMP_DIR/batch.json" >&2
  fail "全套批次未完成：$FULL_STATUS"
fi
[ "$(json_get "$TMP_DIR/batch.json" "data.completed_count")" = "6" ] || fail "全套完成张数不是 6"
FULL_IMAGE_ID=$(json_get "$TMP_DIR/batch.json" "data.images.1.image_id")

# ---------------------------------------------------------------- 下载

echo "[curl] 单张下载"
code=$(curl -s -o "$TMP_DIR/single.png" -D "$TMP_DIR/single_headers.txt" -w "%{http_code}" \
  "$BASE/images/$FULL_IMAGE_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$code" "200" "单张正式图下载"
grep -qi "attachment" "$TMP_DIR/single_headers.txt" || fail "单张下载缺少 attachment"
grep -qi "image/png" "$TMP_DIR/single_headers.txt" || fail "单张下载不是 PNG"

echo "[curl] 整组 ZIP 下载与 manifest"
code=$(curl -s -o "$TMP_DIR/result.zip" -D "$TMP_DIR/zip_headers.txt" -w "%{http_code}" \
  "$BASE/batches/$FULL_BATCH_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$code" "200" "整组 ZIP 下载"
python - "$TMP_DIR/result.zip" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    names = archive.namelist()
    pngs = [name for name in names if name.endswith(".png")]
    assert len(pngs) == 6, names
    assert "manifest.csv" in names, names
    text = archive.read("manifest.csv").decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines[0] == "序号,文件名,状态,尺寸,生成时间,失败原因", lines[0]
    assert len(lines) == 7, len(lines)
print("[curl] ZIP 内含 6 张 PNG 与 manifest.csv")
PY

# ---------------------------------------------------------------- 重生成

echo "[curl] 对成功正式图执行重生成"
REGEN_ID=$(python -c "import uuid;print(uuid.uuid4())")
write_json "$TMP_DIR/regen.json" "b.update({'client_request_id':'$REGEN_ID'})"
code=$(curl -s -o "$TMP_DIR/regen.out" -w "%{http_code}" -X POST \
  "$BASE/images/$FULL_IMAGE_ID/regenerate" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" --data-binary @"$TMP_DIR/regen.json")
expect_http "$code" "200" "单张重生成"
NEW_IMAGE_ID=$(json_get "$TMP_DIR/regen.out" "data.image_id")
[ "$(json_get "$TMP_DIR/regen.out" "data.attempt_no")" = "2" ] || fail "重生成 attempt_no 不是 2"
poll_batch "$FULL_BATCH_ID" 900 "重生成后的全套批次"
[ "$(json_get "$TMP_DIR/batch.json" "data.status")" = "completed" ] || fail "重生成后批次未回到 completed"
code=$(curl -s -o "$TMP_DIR/old_image.json" -w "%{http_code}" \
  "$BASE/images/$FULL_IMAGE_ID/content" -H "Authorization: Bearer $TOKEN")
expect_http "$code" "404" "旧图不再可预览"
code=$(curl -s -o "$TMP_DIR/new_image.png" -w "%{http_code}" \
  "$BASE/images/$NEW_IMAGE_ID/download" -H "Authorization: Bearer $TOKEN")
expect_http "$code" "200" "新图可下载"

# ---------------------------------------------------------------- 取消

echo "[curl] 创建并取消示例批次"
CANCEL_REQ=$(python -c "import uuid;print(uuid.uuid4())")
write_json "$TMP_DIR/cancel_sample.json" "b.update({'client_request_id':'$CANCEL_REQ','session_id':None,'product_name':'取消测试商品','style_text':None,'width':1000,'height':1000,'template_id':None,'upload_ids':[],'requirement_summary':None})"
code=$(curl -s -o "$TMP_DIR/last_body.json" -w "%{http_code}" -X POST "$BASE/generations/sample" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" --data-binary @"$TMP_DIR/cancel_sample.json")
expect_http "$code" "200" "创建取消测试批次"
CANCEL_BATCH_ID=$(json_get "$TMP_DIR/last_body.json" "data.batch_id")
code=$(curl -s -o "$TMP_DIR/cancel.out" -w "%{http_code}" -X POST \
  "$BASE/generations/$CANCEL_BATCH_ID/cancel" -H "Authorization: Bearer $TOKEN")
expect_http "$code" "200" "取消批次"
[ "$(json_get "$TMP_DIR/cancel.out" "data.status")" = "cancelled" ] || fail "取消后状态不是 cancelled"
code=$(curl -s -o "$TMP_DIR/cancel_again.out" -w "%{http_code}" -X POST \
  "$BASE/generations/$CANCEL_BATCH_ID/cancel" -H "Authorization: Bearer $TOKEN")
expect_http "$code" "200" "重复取消幂等"

# ---------------------------------------------------------------- 数据隔离

echo "[curl] 数据隔离"
code=$(curl -s -o "$TMP_DIR/last_body.json" -w "%{http_code}" \
  "$BASE/generations/$FULL_BATCH_ID" -H "Authorization: Bearer $OTHER_TOKEN")
expect_http "$code" "404" "其他用户访问批次"
code=$(curl -s -o "$TMP_DIR/last_body.json" -w "%{http_code}" \
  "$BASE/batches/$FULL_BATCH_ID/download" -H "Authorization: Bearer $ADMIN_TOKEN")
expect_http "$code" "403" "管理员下载整组 ZIP（无 user.history）"

echo "[curl] 全部生图任务接口验收通过。"
