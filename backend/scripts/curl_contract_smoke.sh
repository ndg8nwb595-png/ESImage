#!/usr/bin/env bash
# 9 号「后端服务与接口」契约基线 curl 验收脚本。
#
# 用法（在 backend/ 目录）：
#   bash scripts/curl_contract_smoke.sh
#
# 依赖：本机 PostgreSQL（127.0.0.1:55433，共享实例）与 Python 依赖已安装。
# 脚本会：
#   1. 幂等创建超管账号 demo_super（密码 SuperAdmin123!，满足强密码策略）；
#   2. 临时启动 8011 端口的 uvicorn；
#   3. 逐条 curl 验证统一响应、错误码、JWT、权限、分页、上传、下载与 OpenAPI；
#   4. 结束后自动关闭服务。
#
# 注意：Windows Git Bash 下 `curl -d '{"中文":...}'` 会被终端按本地编码解释，
# 脚本统一用 Python 生成 UTF-8 请求体文件再 `curl --data-binary @文件`。

set -u

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://esimage:esimage@127.0.0.1:55433/esimage}"
export JWT_SECRET="${JWT_SECRET:-contract-demo-secret-0123456789abcdef}"
export PYTHONPATH=.
export DEMO_PIPELINE_STAGE_DELAY="${DEMO_PIPELINE_STAGE_DELAY:-0.02}"
export STORAGE_ROOT="${STORAGE_ROOT:-storage}"

SUPER_USER="demo_super"
SUPER_PASS="SuperAdmin123!"

PORT="${PORT:-8011}"
BASE="http://127.0.0.1:$PORT/api/v1"
TMP_DIR=".curl_contract_tmp"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

pass=0
fail_n=0

ok() {
  pass=$((pass + 1))
  echo "[契约] 通过：$1"
}

bad() {
  fail_n=$((fail_n + 1))
  echo "[契约] 失败：$1" >&2
}

# 幂等创建超管账号
python - "$SUPER_USER" "$SUPER_PASS" <<'PY'
import os, sys
os.environ.setdefault("JWT_SECRET", "contract-demo-secret-0123456789abcdef")
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import Role, User
u, p = sys.argv[1], sys.argv[2]
with SessionLocal() as db:
    role = db.scalar(select(Role).where(Role.code == "super_admin"))
    if db.scalar(select(User).where(User.username == u)) is None:
        user = User(username=u, display_name="超管", password_hash=hash_password(p), status="active", token_version=0)
        user.roles.append(role)
        db.add(user)
        db.commit()
        print(f"[契约] 已创建超管 {u}")
    else:
        print(f"[契约] 超管 {u} 已存在")
PY

# 启动服务
echo "[契约] 启动服务，端口 $PORT"
python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$TMP_DIR/uvicorn.log" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "[契约] 等待服务启动……"
READY=0
for _ in $(seq 1 60); do
  if curl -sS -o /dev/null "http://127.0.0.1:$PORT/api/openapi.json" 2>/dev/null; then
    READY=1
    break
  fi
  python -c "import time;time.sleep(0.25)"
done
if [ "$READY" -ne 1 ]; then
  echo "[契约] 服务启动失败"
  tail -40 "$TMP_DIR/uvicorn.log"
  exit 1
fi
echo "[契约] 服务已启动"

# 工具：发送 JSON 请求，返回 HTTP 状态码，响应体存 last_body.txt
req() {
  # 用法：req <METHOD> <path> <token-or-empty> [body_file]
  local method="$1" path="$2" token="$3" body_file="${4:-}"
  local -a args=(-sS -o "$TMP_DIR/last_body.txt" -w "%{http_code}" -X "$method" "$BASE$path")
  if [ -n "$token" ]; then
    args+=(-H "Authorization: Bearer $token")
  fi
  if [ -n "$body_file" ]; then
    args+=(-H "Content-Type: application/json" --data-binary "@$body_file")
  fi
  curl "${args[@]}"
}

body_code() {
  python -c "import json,sys;d=json.load(open('$TMP_DIR/last_body.txt',encoding='utf-8'));print(d.get('code'))"
}

# ---------------------------------------------------------------------------
echo "[契约] === 统一响应 / 错误码 ==="
# 登录成功
python - "$TMP_DIR/login.json" <<'PY'
import json, sys
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps({"username": "demo_user", "password": "Demo1234", "remember_me": False}, ensure_ascii=False))
PY
CODE=$(req POST "/auth/login" "" "$TMP_DIR/login.json")
if [ "$CODE" = "200" ] && [ "$(body_code)" = "0" ]; then ok "登录成功 code=0"; else bad "登录成功 code=0（HTTP $CODE code=$(body_code)）"; fi
TOKEN=$(python -c "import json;print(json.load(open('$TMP_DIR/last_body.txt',encoding='utf-8'))['data']['token'])")

# 密码错误 -> 401/20001
python - "$TMP_DIR/badlogin.json" <<'PY'
import json, sys
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps({"username": "demo_user", "password": "WrongPass1"}, ensure_ascii=False))
PY
CODE=$(req POST "/auth/login" "" "$TMP_DIR/badlogin.json")
if [ "$CODE" = "401" ] && [ "$(body_code)" = "20001" ]; then ok "密码错误 401/20001"; else bad "密码错误 401/20001（HTTP $CODE code=$(body_code)）"; fi

# 缺少必填参数 -> 400/10002
python - "$TMP_DIR/nouser.json" <<'PY'
import json, sys
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps({"password": "Demo1234"}, ensure_ascii=False))
PY
CODE=$(req POST "/auth/login" "" "$TMP_DIR/nouser.json")
if [ "$CODE" = "400" ] && [ "$(body_code)" = "10002" ]; then ok "缺少用户名 400/10002"; else bad "缺少用户名 400/10002（HTTP $CODE code=$(body_code)）"; fi

echo "[契约] === JWT 鉴权 ==="
CODE=$(req GET "/auth/me" "")
if [ "$CODE" = "401" ] && [ "$(body_code)" = "20003" ]; then ok "无 token 401/20003"; else bad "无 token 401/20003（HTTP $CODE code=$(body_code)）"; fi
CODE=$(req GET "/auth/me" "not-a-valid-jwt")
if [ "$CODE" = "401" ] && [ "$(body_code)" = "20003" ]; then ok "坏签名 401/20003"; else bad "坏签名 401/20003（HTTP $CODE code=$(body_code)）"; fi
CODE=$(req GET "/auth/me" "$TOKEN")
if [ "$CODE" = "200" ] && [ "$(body_code)" = "0" ]; then ok "合法 token 访问 /auth/me 通过"; else bad "合法 token 访问 /auth/me（HTTP $CODE code=$(body_code)）"; fi

echo "[契约] === 权限点 ==="
CODE=$(req GET "/users" "$TOKEN")
if [ "$CODE" = "403" ] && [ "$(body_code)" = "20005" ]; then ok "demo_user 访问管理端 403/20005"; else bad "demo_user 访问管理端 403/20005（HTTP $CODE code=$(body_code)）"; fi

# 管理员访问用户端
python - "$TMP_DIR/admin.json" <<'PY'
import json, sys
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps({"username": "demo_admin", "password": "Demo1234"}, ensure_ascii=False))
PY
CODE=$(req POST "/auth/login" "" "$TMP_DIR/admin.json")
ADMIN_TOKEN=$(python -c "import json;print(json.load(open('$TMP_DIR/last_body.txt',encoding='utf-8'))['data']['token'])")
CODE=$(req GET "/sessions" "$ADMIN_TOKEN")
if [ "$CODE" = "403" ] && [ "$(body_code)" = "20005" ]; then ok "demo_admin 访问用户端 403/20005"; else bad "demo_admin 访问用户端 403/20005（HTTP $CODE code=$(body_code)）"; fi

# 超管全量
python - "$TMP_DIR/super.json" "$SUPER_USER" "$SUPER_PASS" <<'PY'
import json, sys
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps({"username": sys.argv[2], "password": sys.argv[3]}, ensure_ascii=False))
PY
CODE=$(req POST "/auth/login" "" "$TMP_DIR/super.json")
SUPER_TOKEN=$(python -c "import json;print(json.load(open('$TMP_DIR/last_body.txt',encoding='utf-8'))['data']['token'])")
CODE=$(req GET "/users" "$SUPER_TOKEN")
if [ "$CODE" = "200" ] && [ "$(body_code)" = "0" ]; then ok "demo_super 访问管理端通过"; else bad "demo_super 访问管理端（HTTP $CODE code=$(body_code)）"; fi

echo "[契约] === 分页边界 ==="
# 先造一个带消息的会话
python - "$TMP_DIR/chat.json" <<'PY'
import json, sys, uuid
body = {"client_message_id": str(uuid.uuid4()), "content": "帮我做一套图", "params": {"product_name": "秋季通勤衬衫", "width": 1000, "height": 1000}, "session_id": None}
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(body, ensure_ascii=False))
PY
curl -sS -o "$TMP_DIR/sse.txt" -N -X POST "$BASE/sessions/messages" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: text/event-stream" --data-binary "@$TMP_DIR/chat.json" > /dev/null 2>&1
SESSION_ID=$(python - "$TMP_DIR/sse.txt" <<'PY'
import json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    if line.startswith("data:"):
        d = json.loads(line[5:])
        if "session_id" in d:
            print(d["session_id"]); break
PY
)
if [ -z "$SESSION_ID" ]; then bad "未能从 SSE 解析 session_id"; else ok "聊天 SSE 返回 session_id=$SESSION_ID"; fi

CODE=$(req GET "/sessions/$SESSION_ID/messages?page=0" "$TOKEN")
if [ "$CODE" = "400" ] && [ "$(body_code)" = "10001" ]; then ok "page<1 400/10001"; else bad "page<1 400/10001（HTTP $CODE code=$(body_code)）"; fi
CODE=$(req GET "/sessions/$SESSION_ID/messages?page_size=101" "$TOKEN")
if [ "$CODE" = "400" ] && [ "$(body_code)" = "10004" ]; then ok "page_size>100 400/10004"; else bad "page_size>100 400/10004（HTTP $CODE code=$(body_code)）"; fi
CODE=$(req GET "/sessions/$SESSION_ID/messages?page_size=abc" "$TOKEN")
if [ "$CODE" = "400" ] && [ "$(body_code)" = "10003" ]; then ok "page_size 非整数 400/10003"; else bad "page_size 非整数 400/10003（HTTP $CODE code=$(body_code)）"; fi
CODE=$(req GET "/sessions/$SESSION_ID/messages?page=1&page_size=20" "$TOKEN")
if [ "$CODE" = "200" ] && [ "$(body_code)" = "0" ]; then ok "正常分页 200 统一结构"; else bad "正常分页 200（HTTP $CODE code=$(body_code)）"; fi

echo "[契约] === 文件上传校验 ==="
python - "$TMP_DIR" <<'PY'
import sys
from pathlib import Path
from PIL import Image
Image.new("RGB", (900, 900), (70, 110, 190)).save(Path(sys.argv[1]) / "ok.png")
Path(sys.argv[1], "bad.gif").write_bytes(b"GIF89a")
PY
CODE=$(curl -sS -o "$TMP_DIR/upload.json" -w "%{http_code}" -X POST "$BASE/uploads" -H "Authorization: Bearer $TOKEN" -F "file=@$TMP_DIR/ok.png;type=image/png")
if [ "$CODE" = "200" ]; then ok "上传合法 PNG 200"; else bad "上传合法 PNG（HTTP $CODE）"; fi
CODE=$(curl -sS -o "$TMP_DIR/last_body.txt" -w "%{http_code}" -X POST "$BASE/uploads" -H "Authorization: Bearer $TOKEN" -F "file=@$TMP_DIR/bad.gif;type=image/gif")
if [ "$CODE" = "400" ] && [ "$(body_code)" = "30006" ]; then ok "上传 GIF 400/30006"; else bad "上传 GIF 400/30006（HTTP $CODE code=$(body_code)）"; fi

echo "[契约] === OpenAPI 契约标注 ==="
curl -sS -o "$TMP_DIR/openapi.json" "http://127.0.0.1:$PORT/api/openapi.json"
python - "$TMP_DIR/openapi.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
assert "BearerAuth" in s.get("components", {}).get("securitySchemes", {}), "缺 Bearer 方案"
assert "UnifiedResponse" in s["components"]["schemas"], "缺统一响应"
assert "PaginatedResponse" in s["components"]["schemas"], "缺分页结构"
assert s.get("x-error-codes"), "缺错误码表"
assert s["paths"]["/api/v1/users"]["get"]["x-permission"] == "admin.accounts.view"
print("OpenAPI 契约标注齐全")
PY
if [ "$?" = "0" ]; then ok "OpenAPI 含 Bearer/统一响应/分页/错误码/权限码"; else bad "OpenAPI 契约标注不完整"; fi

echo ""
echo "[契约] 结果：通过 $pass，失败 $fail_n"
[ "$fail_n" -eq 0 ]
