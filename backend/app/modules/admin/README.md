# admin 模块（6/7/8 号管理后台后端）

本目录当前只承载「7-管理后台-用户与生图记录」最小 demo 的后端实现。

## 目录规划

```text
admin/
├── router.py          # 汇总 dashboard / tokens / content / accounts 子路由
├── service.py         # 管理端公共权限、时间、分页、媒体与存储工具
├── seed.py            # 7 号幂等演示数据种子
├── dashboard/         # 概览四卡与 Token 统计
├── content/           # 内容追溯：用户 → 会话 → 批次 → 图片与媒体
└── accounts/          # 用户列表/详情（复用 6 号结构，统计改为真实值）
```

## 边界

- 只读接口，不提供导出、删除、重生成、改提示词、直连 SQL。
- 管理员看不到超管账号的内容；超管可看全部。
- 数据表复用 `app/models/workspace.py`，不新增表。
- 本地存储沿用 `app/modules/workspace/storage.py` 的适配层。
