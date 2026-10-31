#!/usr/bin/env bash
# 11 号部署与运维：一键构建、迁移、启动与健康等待。
# 用法：bash scripts/demo_up.sh [--no-build]
set -euo pipefail
cd "$(dirname "$0")/.."

NO_BUILD=0
[ "${1:-}" = "--no-build" ] && NO_BUILD=1

# 前置检查
command -v docker >/dev/null 2>&1 || { echo "[demo_up] 缺少 docker" >&2; exit 3; }
docker compose version >/dev/null 2>&1 || { echo "[demo_up] 需要 Docker Compose v2" >&2; exit 3; }
[ -f .env ] || { echo "[demo_up] 缺少 .env：请复制 .env.example 并填写密钥与初始超管" >&2; exit 3; }

# 构建镜像
if [ "$NO_BUILD" -eq 0 ]; then
  docker compose build
fi

# 启动依赖并等待健康
docker compose up -d postgres redis minio
docker compose up -d --wait postgres redis minio || { echo "[demo_up] 依赖服务未就绪" >&2; exit 4; }

# 迁移 + 种子 + 初始超管（一次性）
docker compose run --rm migrate || { echo "[demo_up] 迁移/种子失败" >&2; exit 5; }

# 启动应用与网关并等待健康
docker compose up -d backend worker beat frontend nginx
docker compose up -d --wait backend nginx || { echo "[demo_up] 应用未就绪" >&2; exit 5; }

echo "[demo_up] 启动完成：http://<host>/（API http://<host>/api/health）"
echo "[demo_up] 日志卷 applogs/；备份卷 backup/（宿主机 cron 执行）"
