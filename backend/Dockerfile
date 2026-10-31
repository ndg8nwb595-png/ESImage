# 11 号部署与运维：backend 应用镜像（worker/beat 复用）
# Python 3.11 + FastAPI + uvicorn，非 root 运行，镜像内不硬编码密钥。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先复制依赖，利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码与运维脚本
COPY app ./app
COPY scripts ./scripts

# 非 root 运行；applogs 卷挂载点预先建好并授权
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
