# 数据模型与存储（10 号）最小 demo

数据底座：18 张业务表的 Alembic 版本化迁移、幂等种子、首个超管、单桶前缀对象存储适配器、
5 年归档与归档读取、契约回归。不新增 HTTP 业务接口，通过 `esimage-data` 命令行暴露。

## 1. 命令

```bash
# 在 backend/ 目录（或 pip install -e . 后直接调用 esimage-data）
python esimage_data.py db upgrade [revision]   # 迁移到 head
python esimage_data.py db downgrade <revision> # 回滚（base 清空本 demo 对象）
python esimage_data.py db current              # 当前 revision
python esimage_data.py db verify               # 校验 18 张表 schema

python esimage_data.py seed                    # 幂等种子
python esimage_data.py init-super-admin        # 显式环境变量创建首个超管
python esimage_data.py archive run --now <ISO> # 归档任务
python esimage_data.py verify --scope all      # 契约回归
python esimage_data.py bootstrap               # 迁移 + 种子 + 首个超管
```

## 2. 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `...127.0.0.1:55433/esimage_data` | PostgreSQL 16 连接串 |
| `DATABASE_TIMEZONE` | `Asia/Shanghai` | 会话时区 |
| `STORAGE_BACKEND` | `local` | `local` / `minio`（本 demo 只验收 local） |
| `STORAGE_ROOT` | `storage` | local 后端桶根目录 |
| `ARCHIVE_RETENTION_DAYS` | `1825` | 归档保留期（demo 可调小） |
| `INITIAL_SUPER_ADMIN_USERNAME` | — | 首个超管用户名（必填） |
| `INITIAL_SUPER_ADMIN_PASSWORD` | — | 首个超管密码（必填） |

> 本模块使用独立数据库 `esimage_data`，避免与 1~9 号 demo 的迁移版本冲突。

## 3. 验收

```bash
DATABASE_URL=postgresql+psycopg://esimage:esimage@127.0.0.1:55433/esimage_data \
INITIAL_SUPER_ADMIN_USERNAME=demo_super \
INITIAL_SUPER_ADMIN_PASSWORD=Demo1234 \
python esimage_data.py bootstrap

python esimage_data.py verify --scope all
```

`verify --scope all` 覆盖 10 号 §12 中的 1、2、3、5、6、7、8、9、10、13、14 项；
4 由 6 号 demo 验收，11 由 7 号 PRD 验收，12 由 11 号 PRD 验收。
