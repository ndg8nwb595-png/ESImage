# 领域文档

工程技能在探索代码库时，应如何消费本仓库的领域文档。

## 探索之前先读这些

- 仓库根目录的 **`GLOSSARY.md`**；或
- 若存在仓库根目录的 **`GLOSSARY-MAP.md`**：它指向每个上下文各自的 `GLOSSARY.md`，读取与当前主题相关的那些。
- **`docs/adr/`**：读取与即将改动的区域相关的 ADR。多上下文仓库中，还要检查 `src/<context>/docs/adr/` 里上下文级的决策。

若上述文件不存在，**静默继续**。不要提示缺失，也不要主动建议预先创建。`/domain-modeling` 技能（经由 `/grill-with-docs` 与 `/improve-codebase-architecture` 触达）会在术语或决策真正确定时惰性创建它们。

## 文件结构

单上下文仓库（大多数仓库）：

```
/
├── GLOSSARY.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

多上下文仓库（根目录存在 `GLOSSARY-MAP.md`）：

```
/
├── GLOSSARY-MAP.md
├── docs/adr/                          ← 系统级决策
└── src/
    ├── ordering/
    │   ├── GLOSSARY.md
    │   └── docs/adr/                  ← 上下文级决策
    └── billing/
        ├── GLOSSARY.md
        └── docs/adr/
```

## 使用 glossary 的词汇

当你的输出需要命名某个领域概念时（issue 标题、重构提案、假设、测试名），使用 `GLOSSARY.md` 中定义的术语。不要漂移到 glossary 明确回避的同义词。

若所需概念尚未进入 glossary，这本身是个信号：要么你在创造项目不使用的语言（请重新考虑），要么存在真实缺口（记录下来，交给 `/domain-modeling`）。

## 标注 ADR 冲突

若你的输出与既有 ADR 矛盾，要显式指出，而不是悄悄推翻：

> _与 ADR-0007（event-sourced orders）冲突，但值得重开，因为……_
