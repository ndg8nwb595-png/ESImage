#!/usr/bin/env bash
# 管理后台「账号与权限」最小 demo curl 验收脚本（6 号 PRD）。
#
# 用法（在 backend/ 目录）：
#   PYTHON=.venv/Scripts/python.exe bash scripts/curl_admin_smoke.sh
#
# 依赖：本机 PostgreSQL（复用 esimage-postgres:55433）与 Python 依赖已安装。
# 脚本会临时启动 8016 端口的 uvicorn，结束后自动关闭。
# 默认连接 esimage_admin 库；可用 DATABASE_URL 覆盖。
#
# 注意：Windows Git Bash 直接 `curl -d '{"中文":...}'` 可能被本地编码影响，
# 本脚本统一用 Python 生成 UTF-8 JSON 文件，再用 `curl --data-binary @文件` 发送。

set -u

PYTHON="${PYTHON:-python}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://esimage:esimage@127.0.0.1:55433/esimage_admin}"
export JWT_SECRET="${JWT_SECRET:-admin-accounts-demo-secret-0123456789abcdef}"
export PYTHONPATH=.
export STORAGE_ROOT="${STORAGE_ROOT:-storage}"

PORT="${PORT:-8016}"
BASE="http://127.0.0.1:$PORT/api/v1"
TMP_DIR=".curl_admin_tmp"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

# 每次运行使用唯一用户名，避免重复执行时命中「用户名已存在」
SUFFIX=$(date +%H%M%S)
NEW_USER="smoke_${SUFFIX}"
NEW_USER2="smoke2_${SUFFIX}"

fail() {
  echo "[curl][失败] $*" >&2
  exit 1
}

expect_http() {
  if [ "$1" != "$2" ]; then
    fail "$3：期望 HTTP $2，实际 $1；响应体 $(cat "$TMP_DIR/last_body.txt" 2>/dev/null)"
  fi
  echo "[curl] $3 -> HTTP $1"
}

expect_code() {
  local expected="$1" description="$2"
  local actual
  actual=$("$PYTHON" - "$TMP_DIR/last_body.txt" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8"))["code"])
except Exception:
    print("")
PY
)
  [ "$actual" = "$expected" ] || fail "$description：期望业务码 $expected，实际 $actual；响应体 $(cat "$TMP_DIR/last_body.txt")"
  echo "[curl] $description -> 业务码 $actual"
}

json_get() {
  "$PYTHON" - "$1" "$2" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
for part in sys.argv[2].split("."):
    data = data[int(part)] if isinstance(data, list) else data[part]
print(data)
PY
}

write_json() {
  local output="$1"
  local script="$2"
  "$PYTHON" - "$output" <<PY
import json, sys
b = {}
$script
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(b, ensure_ascii=False))
PY
}

request_json() {
  local method="$1" path="$2" token="$3" body_file="${4:-}"
  local -a args=(-sS -o "$TMP_DIR/last_body.txt" -w "%{http_code}" -X "$method" "$BASE$path" -H "Authorization: Bearer $token")
  if [ -n "$body_file" ]; then
    args+=(-H "Content-Type: application/json" --data-binary "@$body_file")
  fi
  curl "${args[@]}"
}

login() {
  local username="$1" password="$2" description="$3"
  write_json "$TMP_DIR/login.json" "b.update({'username': '$username', 'password': '$password'})"
  local code
  code=$(curl -sS -o "$TMP_DIR/login.response" -w "%{http_code}" -X POST "$BASE/auth/login" -H "Content-Type: application/json" --data-binary "@$TMP_DIR/login.json")
  cp "$TMP_DIR/login.response" "$TMP_DIR/last_body.txt"
  # 日志写 stderr，保证函数 stdout 只返回 token
  expect_http "$code" 200 "POST /auth/login（$description）" >&2
  json_get "$(cat "$TMP_DIR/login.response")" "data.token"
}

# 目标库可能是全新的 esimage_admin：脚本自行建表并写入幂等种子
echo "[curl] 初始化数据库（建表 + 幂等种子）"
"$PYTHON" scripts/init_db.py > /dev/null || fail "数据库建表失败"
"$PYTHON" scripts/seed.py > /dev/null || fail "种子写入失败"

echo "[curl] 启动服务，端口 $PORT"
"$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" > "$TMP_DIR/uvicorn.log" 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "[curl] 等待服务启动……"
READY=0
for _ in $(seq 1 60); do
  if curl -sS -o /dev/null "http://127.0.0.1:$PORT/openapi.json"; then
    READY=1
    break
  fi
  "$PYTHON" -c "import time;time.sleep(0.25)"
done
if [ "$READY" -ne 1 ]; then
  echo "[curl] 服务启动失败"
  tail -60 "$TMP_DIR/uvicorn.log"
  exit 1
fi
echo "[curl] 服务已启动"

# ---------------------------------------------------------------------------
# 1. 登录与权限点
# ---------------------------------------------------------------------------
SUPER_TOKEN=$(login demo_super Demo1234 "超管") || exit 1
ADMIN_TOKEN=$(login demo_admin Demo1234 "管理员") || exit 1
USER_TOKEN=$(login demo_user Demo1234 "普通用户") || exit 1
SUPER_ID=$(json_get "$(cat "$TMP_DIR/login.response")" "data.user.id" 2>/dev/null || true)

CODE=$(request_json GET "/auth/me" "$SUPER_TOKEN")
expect_http "$CODE" 200 "GET /auth/me（超管）"
cat "$TMP_DIR/last_body.txt"; echo
SUPER_ID=$("$PYTHON" - "$TMP_DIR/last_body.txt" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))["data"]
print(data["user"]["id"])
PY
)

# ---------------------------------------------------------------------------
# 2. 用户列表与筛选
# ---------------------------------------------------------------------------
CODE=$(request_json GET "/admin/users?page=1&page_size=20" "$SUPER_TOKEN")
expect_http "$CODE" 200 "GET /admin/users"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/admin/users?keyword=demo&role=admin&status=all" "$SUPER_TOKEN")
expect_http "$CODE" 200 "GET /admin/users（keyword+role 筛选）"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/admin/users" "$USER_TOKEN")
expect_http "$CODE" 403 "GET /admin/users（普通用户应 403）"
expect_code 20005 "普通用户无权限"

CODE=$(request_json GET "/admin/users?page_size=30" "$SUPER_TOKEN")
expect_http "$CODE" 400 "GET /admin/users（page_size=30 非法）"
expect_code 10003 "每页条数不合法"

# ---------------------------------------------------------------------------
# 3. 新建账号
# ---------------------------------------------------------------------------
write_json "$TMP_DIR/create.json" "b.update({'username': '$NEW_USER', 'display_name': '冒烟编辑', 'password': 'Passw0rd!', 'roles': ['user'], 'status': 'active'})"
CODE=$(request_json POST "/admin/users" "$SUPER_TOKEN" "$TMP_DIR/create.json")
expect_http "$CODE" 200 "POST /admin/users"
cat "$TMP_DIR/last_body.txt"; echo
NEW_USER_ID=$(json_get "$(cat "$TMP_DIR/last_body.txt")" "data.user_id") || exit 1

echo "[curl] 重复用户名"
CODE=$(request_json POST "/admin/users" "$SUPER_TOKEN" "$TMP_DIR/create.json")
expect_http "$CODE" 409 "POST /admin/users（用户名重复）"
expect_code 30010 "用户名已存在"

echo "[curl] 超管+管理员组合不合法"
write_json "$TMP_DIR/bad_combo.json" "b.update({'username': '${NEW_USER2}', 'display_name': '非法组合', 'password': 'Passw0rd!', 'roles': ['super_admin', 'admin']})"
CODE=$(request_json POST "/admin/users" "$SUPER_TOKEN" "$TMP_DIR/bad_combo.json")
expect_http "$CODE" 409 "POST /admin/users（超管+管理员）"
expect_code 30009 "角色组合不合法"

echo "[curl] 管理员不能创建超管"
write_json "$TMP_DIR/bad_super.json" "b.update({'username': '${NEW_USER2}', 'display_name': '超管二', 'password': 'Passw0rd!', 'roles': ['super_admin']})"
CODE=$(request_json POST "/admin/users" "$ADMIN_TOKEN" "$TMP_DIR/bad_super.json")
expect_http "$CODE" 403 "POST /admin/users（管理员建超管）"
expect_code 20005 "无权分配超管角色"

# ---------------------------------------------------------------------------
# 4. 用户详情与编辑
# ---------------------------------------------------------------------------
CODE=$(request_json GET "/admin/users/$NEW_USER_ID" "$SUPER_TOKEN")
expect_http "$CODE" 200 "GET /admin/users/{id}"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/admin/users/$SUPER_ID" "$ADMIN_TOKEN")
expect_http "$CODE" 403 "GET /admin/users/{super_id}（管理员查看超管）"
expect_code 20006 "无权操作超管账号"

write_json "$TMP_DIR/update.json" "b.update({'display_name': '冒烟编辑改', 'roles': ['admin', 'user']})"
CODE=$(request_json PATCH "/admin/users/$NEW_USER_ID" "$SUPER_TOKEN" "$TMP_DIR/update.json")
expect_http "$CODE" 200 "PATCH /admin/users/{id}"
cat "$TMP_DIR/last_body.txt"; echo

ADMIN_ID=$(request_json GET "/auth/me" "$ADMIN_TOKEN" > /dev/null; "$PYTHON" - "$TMP_DIR/last_body.txt" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["data"]["user"]["id"])
PY
)

echo "[curl] 管理员修改自己的角色应 403/20007"
write_json "$TMP_DIR/self_role.json" "b.update({'roles': ['admin', 'user']})"
CODE=$(request_json PATCH "/admin/users/$ADMIN_ID" "$ADMIN_TOKEN" "$TMP_DIR/self_role.json")
expect_http "$CODE" 403 "PATCH /admin/users/{self}（改角色）"
expect_code 20007 "不能修改自己的角色或状态"

# ---------------------------------------------------------------------------
# 5. 重置密码与旧 token 失效
# ---------------------------------------------------------------------------
OLD_TOKEN=$(login "$NEW_USER" 'Passw0rd!' "新账号") || exit 1
write_json "$TMP_DIR/reset.json" "b.update({'new_password': 'NewPass123'})"
CODE=$(request_json POST "/admin/users/$NEW_USER_ID/reset-password" "$SUPER_TOKEN" "$TMP_DIR/reset.json")
expect_http "$CODE" 200 "POST /admin/users/{id}/reset-password"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/auth/me" "$OLD_TOKEN")
expect_http "$CODE" 401 "GET /auth/me（重置密码后的旧 token）"
expect_code 20003 "旧 token 失效"

NEW_TOKEN=$(login "$NEW_USER" 'NewPass123' "重置后的新密码") || exit 1
echo "[curl] 新密码登录成功，token 长度 ${#NEW_TOKEN}"

# ---------------------------------------------------------------------------
# 6. 禁用 / 启用
# ---------------------------------------------------------------------------
CODE=$(request_json POST "/admin/users/$NEW_USER_ID/disable" "$SUPER_TOKEN")
expect_http "$CODE" 200 "POST /admin/users/{id}/disable"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/auth/me" "$NEW_TOKEN")
expect_http "$CODE" 403 "GET /auth/me（禁用后的旧 token）"
expect_code 20004 "账号不可用"

CODE=$(request_json POST "/admin/users/$NEW_USER_ID/enable" "$SUPER_TOKEN")
expect_http "$CODE" 200 "POST /admin/users/{id}/enable"
cat "$TMP_DIR/last_body.txt"; echo

# ---------------------------------------------------------------------------
# 7. 软删除 / 恢复
# ---------------------------------------------------------------------------
CODE=$(request_json DELETE "/admin/users/$NEW_USER_ID" "$SUPER_TOKEN")
expect_http "$CODE" 200 "DELETE /admin/users/{id}"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/admin/users?status=deleted&keyword=$NEW_USER" "$SUPER_TOKEN")
expect_http "$CODE" 200 "GET /admin/users（已删除筛选）"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json POST "/admin/users" "$SUPER_TOKEN" "$TMP_DIR/create.json")
expect_http "$CODE" 409 "POST /admin/users（复用已删除用户名）"
expect_code 30010 "已删除用户名不可复用"

CODE=$(request_json POST "/admin/users/$NEW_USER_ID/restore" "$SUPER_TOKEN")
expect_http "$CODE" 200 "POST /admin/users/{id}/restore"
cat "$TMP_DIR/last_body.txt"; echo

# ---------------------------------------------------------------------------
# 8. 角色与权限点
# ---------------------------------------------------------------------------
CODE=$(request_json GET "/admin/roles" "$SUPER_TOKEN")
expect_http "$CODE" 200 "GET /admin/roles"
cat "$TMP_DIR/last_body.txt"; echo
cp "$TMP_DIR/last_body.txt" "$TMP_DIR/roles_before.json"

CODE=$(request_json GET "/admin/roles" "$ADMIN_TOKEN")
expect_http "$CODE" 403 "GET /admin/roles（管理员）"
expect_code 20005 "无权限"

# 保存去掉 admin.accounts.view 的管理员权限
"$PYTHON" - "$TMP_DIR/roles_before.json" "$TMP_DIR/role_perms.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))["data"]
admin = next(role for role in data["roles"] if role["code"] == "admin")
codes = [code for code in admin["permissions"] if code != "admin.accounts.view"]
json.dump({"permissions": codes}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PY
CODE=$(request_json PUT "/admin/roles/admin/permissions" "$SUPER_TOKEN" "$TMP_DIR/role_perms.json")
expect_http "$CODE" 200 "PUT /admin/roles/admin/permissions"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/admin/users" "$ADMIN_TOKEN")
expect_http "$CODE" 403 "GET /admin/users（权限移除后）"
expect_code 20005 "管理员失去用户管理权限"

echo "[curl] 超管专属权限点不能授予管理员"
"$PYTHON" - "$TMP_DIR/roles_before.json" "$TMP_DIR/role_perms_bad.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))["data"]
admin = next(role for role in data["roles"] if role["code"] == "admin")
codes = list(admin["permissions"]) + ["admin.audit.view"]
json.dump({"permissions": codes}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PY
CODE=$(request_json PUT "/admin/roles/admin/permissions" "$SUPER_TOKEN" "$TMP_DIR/role_perms_bad.json")
expect_http "$CODE" 409 "PUT /admin/roles/admin/permissions（超管专属）"
expect_code 30015 "超管专属权限点不能授予该角色"

# 恢复管理员默认权限
"$PYTHON" - "$TMP_DIR/roles_before.json" "$TMP_DIR/role_perms_restore.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))["data"]
admin = next(role for role in data["roles"] if role["code"] == "admin")
json.dump({"permissions": admin["permissions"]}, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PY
CODE=$(request_json PUT "/admin/roles/admin/permissions" "$SUPER_TOKEN" "$TMP_DIR/role_perms_restore.json")
expect_http "$CODE" 200 "PUT /admin/roles/admin/permissions（恢复）"

# ---------------------------------------------------------------------------
# 9. 操作日志（文档参数 + 旧前端参数双兼容）
# ---------------------------------------------------------------------------
START_TIME=$("$PYTHON" -c "from datetime import datetime,timezone,timedelta;print((datetime.now(timezone.utc)-timedelta(hours=1)).astimezone(timezone(timedelta(hours=8))).isoformat())")
END_TIME=$("$PYTHON" -c "from datetime import datetime,timezone,timedelta;print((datetime.now(timezone.utc)+timedelta(hours=1)).astimezone(timezone(timedelta(hours=8))).isoformat())")

# URL 中 +08:00 的加号必须编码为 %2B，否则会被解析成空格
START_TIME_URL=${START_TIME//+/%2B}
END_TIME_URL=${END_TIME//+/%2B}
CODE=$(request_json GET "/admin/audit-logs?action=account.create&result=success&operator=demo_super&start_time=$START_TIME_URL&end_time=$END_TIME_URL&page=1&page_size=20" "$SUPER_TOKEN")
expect_http "$CODE" 200 "GET /admin/audit-logs（文档参数）"
cat "$TMP_DIR/last_body.txt"; echo
LOG_ID=$(json_get "$(cat "$TMP_DIR/last_body.txt")" "data.items.0.log_id") || exit 1

CODE=$(request_json GET "/admin/audit-logs?keyword=account.create&created_from=2026-01-01&created_to=2099-12-31" "$SUPER_TOKEN")
expect_http "$CODE" 200 "GET /admin/audit-logs（旧前端参数）"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/admin/audit-logs/$LOG_ID" "$SUPER_TOKEN")
expect_http "$CODE" 200 "GET /admin/audit-logs/{id}"
cat "$TMP_DIR/last_body.txt"; echo

CODE=$(request_json GET "/admin/audit-logs/999999" "$SUPER_TOKEN")
expect_http "$CODE" 404 "GET /admin/audit-logs/{id}（不存在）"
expect_code 30019 "操作日志不存在"

CODE=$(request_json GET "/admin/audit-logs" "$ADMIN_TOKEN")
expect_http "$CODE" 403 "GET /admin/audit-logs（管理员）"
expect_code 20005 "无权限"

# ---------------------------------------------------------------------------
# 10. 越权与最后超管保护
# ---------------------------------------------------------------------------
echo "[curl] 管理员不能禁用超管"
CODE=$(request_json POST "/admin/users/$SUPER_ID/disable" "$ADMIN_TOKEN")
expect_http "$CODE" 403 "POST /admin/users/{super_id}/disable（管理员）"
expect_code 20006 "无权操作超管账号"

echo "[curl] 超管不能禁用自己"
CODE=$(request_json POST "/admin/users/$SUPER_ID/disable" "$SUPER_TOKEN")
expect_http "$CODE" 403 "POST /admin/users/{super_id}/disable（自己）"
expect_code 20007 "不能对自己执行该操作"

echo "[curl] 全部接口调用结束；输出目录：$TMP_DIR"
