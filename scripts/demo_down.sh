#!/usr/bin/env bash
# 停止服务，默认保留命名卷；--purge 删除卷（仅演示环境，执行前二次确认）。
# 用法：bash scripts/demo_down.sh [--purge]
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--purge" ]; then
  echo "[demo_down] 将删除全部命名卷（数据不可恢复）！" >&2
  echo "[demo_down] 生产环境禁止使用 docker compose down -v" >&2
  read -r -p "确认输入 yes 继续：" ans
  if [ "$ans" != "yes" ]; then
    echo "[demo_down] 已取消" >&2
    exit 2
  fi
  docker compose down -v
else
  docker compose down
fi

echo "[demo_down] 已停止（默认保留数据卷）"
