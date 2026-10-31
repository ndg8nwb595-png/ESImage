#!/usr/bin/env bash
# 11 号部署与运维后端 curl 验收：双健康探针 + SSE 演示探针 + X-Request-ID。
#
# 用法（在 backend/ 目录）：
#   bash scripts/curl_ops_smoke.sh
#
# 说明：脚本临时启动 uvicorn，逐条 curl 三个接口后自动关闭。
# 依赖服务（PostgreSQL/Redis/MinIO）不可用时，健康接口按约定返回 503 degraded，
# 仍视为接口可用；SSE 探针不依赖外部服务，直接返回 meta -> delta -> done。
set -u

cd "$(dirname "$0")/.." || exit 1

export PYTHONPATH=.
export JWT_SECRET="${JWT_SECRET:-ops-demo-secret-0123456789abcdef}"
export APP_ENV="${APP_ENV:-development}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://esimage:esimage@127.0.0.1:55433/esimage}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export MINIO_ENDPOINT="${MINIO_ENDPOINT:-127.0.0.1:9000}"
export SSE_PROBE_INTERVAL="${SSE_PROBE_INTERVAL:-0.05}"
export LOG_DIR="${LOG_DIR:-.ops_logs}"

PORT="${PORT:-8011}"
BASE="http://127.0.0.1:$PORT"
TMP=".ops_tmp"
rm -rf "$TMP"; mkdir -p "$TMP"

fail() { echo "[ops][失败] $*" >&2; exit 1; }

echo "[ops] 启动服务，端口 $PORT"
python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$TMP/uvicorn.log" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

READY=0
for _ in $(seq 1 60); do
  if curl -sS -o /dev/null "$BASE/openapi.json"; then READY=1; break; fi
  python -c "import time;time.sleep(0.25)"
done
if [ "$READY" -ne 1 ]; then
  echo "[ops] 服务启动失败"; tail -40 "$TMP/uvicorn.log"; exit 1
fi
echo "[ops] 服务已启动"

# 1. 裸健康探针（复用入站 X-Request-ID）
CODE=$(curl -sS -D "$TMP/h.txt" -o "$TMP/h.json" -w "%{http_code}" \
  -H "X-Request-ID: ops-health-0001" "$BASE/api/health")
echo "[ops] GET /api/health -> HTTP $CODE"
case "$CODE" in 200|503) ;; *) fail "健康探针期望 200/503，实际 $CODE";; esac
python - "$TMP/h.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert set(d["checks"]) == {"database", "redis", "minio"}, d
assert d["status"] in ("ok", "degraded"), d
print(f"[ops]   status={d['status']} checks={d['checks']}")
PY
RID=$(grep -i '^x-request-id:' "$TMP/h.txt" | tr -d '\r' | awk '{print $2}')
echo "[ops]   X-Request-ID=$RID"
[ "$RID" = "ops-health-0001" ] || fail "响应未复用入站 X-Request-ID：$RID"

# 2. 统一响应健康探针
CODE=$(curl -sS -o "$TMP/hv.json" -w "%{http_code}" "$BASE/api/v1/health")
echo "[ops] GET /api/v1/health -> HTTP $CODE"
python - "$TMP/hv.json" "$CODE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
code = sys.argv[2]
if code == "200":
    assert d["code"] == 0, d
else:
    assert code == "503", code
    assert d["code"] == 50001, d
    assert d["message"] == "服务依赖不可用", d
assert set(d["data"]["checks"]) == {"database", "redis", "minio"}, d
print(f"[ops]   code={d['code']} status={d['data']['status']}")
PY

# 3. SSE 演示探针（不依赖外部服务）
CODE=$(curl -sS -N -D "$TMP/sse.h.txt" -o "$TMP/sse.txt" -w "%{http_code}" \
  "$BASE/api/v1/sessions/_probe/stream")
echo "[ops] GET /api/v1/sessions/_probe/stream -> HTTP $CODE"
[ "$CODE" = "200" ] || fail "SSE 探针期望 200，实际 $CODE"
grep -q '^event: meta' "$TMP/sse.txt" || fail "缺少 meta 事件"
grep -q '^event: delta' "$TMP/sse.txt" || fail "缺少 delta 事件"
grep -q '^event: done' "$TMP/sse.txt" || fail "缺少 done 事件"
grep -qi '^x-accel-buffering: no' "$TMP/sse.h.txt" || fail "缺少 X-Accel-Buffering: no"
echo "[ops]   SSE 帧数：$(grep -c '^event:' "$TMP/sse.txt")（含 meta/delta/done）"
head -3 "$TMP/sse.txt" | sed 's/^/[ops]     /'

echo "[ops] 全部通过"
