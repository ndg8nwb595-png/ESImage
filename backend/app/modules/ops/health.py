"""健康检测：并发检查 PostgreSQL / Redis / MinIO。

- 三项并发执行，单项超时 `HEALTH_CHECK_TIMEOUT`（默认 2 秒），整体不超 5 秒。
- 单项失败不短路其他项；失败值统一为 `error`，不返回 DSN / 上游异常等内部细节。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings


def _check_database() -> str:
    """轻量查询；使用独立短连接，避免复用引擎默认的长连接超时。"""
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(
            settings.DATABASE_URL,
            connect_args={"connect_timeout": int(settings.HEALTH_CHECK_TIMEOUT)},
        )
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        return "ok"
    except Exception:
        return "error"


def _check_redis() -> str:
    try:
        import redis

        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=settings.HEALTH_CHECK_TIMEOUT,
            socket_timeout=settings.HEALTH_CHECK_TIMEOUT,
        )
        return "ok" if client.ping() else "error"
    except Exception:
        return "error"


def _check_minio() -> str:
    try:
        from minio import Minio

        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        return "ok" if client.bucket_exists(settings.MINIO_BUCKET) else "error"
    except Exception:
        return "error"


def run_health_checks() -> dict[str, str]:
    """并发检测三项依赖，返回 `{"database": ..., "redis": ..., "minio": ...}`。"""
    results = {"database": "error", "redis": "error", "minio": "error"}
    checks = {
        "database": _check_database,
        "redis": _check_redis,
        "minio": _check_minio,
    }
    pool = ThreadPoolExecutor(max_workers=3)
    try:
        futures = {key: pool.submit(fn) for key, fn in checks.items()}
        for key, future in futures.items():
            try:
                results[key] = future.result(timeout=settings.HEALTH_CHECK_TIMEOUT)
            except Exception:
                results[key] = "error"
    finally:
        # 不等待可能仍在连接中（如防火墙丢包）的线程，避免健康检查被拖住
        pool.shutdown(wait=False)
    return results
