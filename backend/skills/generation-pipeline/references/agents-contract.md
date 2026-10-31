# 8 Agent 契约速查

> 权威依据：`docs/prd/4-生图任务与结果/4-生图任务与结果prd.md` §4。写 `agents.py` 时对照本文件；
> 与本文件冲突时以 PRD 4 为准。

## 清单与失败策略

| # | agent_code | 职责 | 核心 | 重试 10 次仍失败 |
| --- | --- | --- | --- | --- |
| 1 | planner | 判断意图、拆解 1 主图 + 5 详情图、编排顺序 | 是 | 批次 failed |
| 2 | product_understanding | 推断类目/卖点/人群/场景，调用素材检索工具 | 是 | 批次 failed |
| 3 | copywriter | 生成每张图标题/卖点/说明文案 | 是 | 批次 failed |
| 4 | prompt_builder | 生成每张图生图参数与留白区 | 是 | 批次 failed |
| 5 | image_generator | 调豆包 Seedream 图生图/文生图 | 是 | 每张最多 2 次，2 次失败整批 failed |
| 6 | quality_reviewer | 文字错乱/主体变形/合规 | 否 | 跳过，标「未校验」 |
| 7 | repairer | 据审核问题修正提示词并重生成 | 否 | 跳过，标「未修复」 |
| 8 | platform_rule | 尺寸/违禁词/类目 | 否 | 跳过，标「未校验」 |

- 素材检索是 product_understanding 内部工具，不单独计为 Agent。
- 非生图 Agent 重试指数退避：1s → 2s → 4s → 8s → 16s → 30s 封顶；HTTP 瞬态错误（连接失败/429/5xx）另有 `retry_count` 立即重试，两层叠加。

## 调用顺序

```text
planner → product_understanding(含素材检索) → copywriter → prompt_builder
  → image_generator → quality_reviewer
        ├─ 通过 → platform_rule → text_composition → 输出
        └─ 不通过 → repairer → image_generator(最多 1 次) → quality_reviewer 复检
                      ├─ 通过 → platform_rule → text_composition → 输出
                      └─ 仍不通过 → 该张 failed（质量问题未通过）
```

## 各 Agent 输入/输出

### planner（输入：参数快照、需求摘要、最近 10 轮聊天摘要、聊天意图、模板信息）

`images` 固定 6 项（1 main + 5 detail），主题动态决定、符合电商场景且不重复：

```json
{
  "image_count": 6,
  "images": [
    {"index": 1, "role": "main", "theme": "白底商品主视觉", "copy_focus": "整体外观与品牌感", "layout_hint": "标题上方，卖点下方"},
    {"index": 2, "role": "detail", "theme": "核心卖点", "copy_focus": "面料与版型", "layout_hint": "左图右文"}
  ],
  "order": ["product_understanding", "copywriter", "prompt_builder", "image_generator"]
}
```

### product_understanding（输入：商品名称、上传商品图、需求摘要、聊天摘要）

```json
{"category": "服饰鞋包", "selling_points": ["透气", "不易起球", "百搭"],
 "target_audience": "25~35 岁通勤女性", "scenes": ["办公室", "周末出行"],
 "constraints": ["不要出现真人正脸"], "material_ids": [12, 18]}
```

不传商品图时仍出画像，但标注「无实物参考」。

### copywriter（输入：商品画像、每张图主题、风格、模板文案结构）

简体中文；标题 6~12 字、卖点每条 4~10 字；不生成价格/促销倒计时等未经用户提供的信息：

```json
{"index": 1, "title": "轻盈透气 一整天", "selling_points": ["冰感面料", "不易起球", "通勤百搭"],
 "body": "适合日常通勤的轻薄款", "tone": "简洁有力"}
```

### prompt_builder（输入：文案块、商品画像、风格、尺寸、模板、素材候选）

**必须显式要求留白区**；**禁止把大段中文文案写进 prompt**（否则模型画错字）：

```json
{"index": 1, "prompt": "电商主图，浅色背景，商品居中，柔和棚拍光，留出上方标题区和下方卖点区",
 "negative_prompt": "文字乱码，水印，低清晰度，主体变形",
 "whitespace": {"top_ratio": 0.18, "bottom_ratio": 0.22},
 "reference_asset_ids": [12], "model_params": {"width": 1000, "height": 1000}}
```

参考图权重、随机种子等高级参数不向用户暴露，由后端配置。

### image_generator（输入：提示词 JSON、上传商品图、参考素材；输出：基础图文件）

- 有上传图 → 图生图；无 → 文生图。
- 落库 `generated_images`：prompt、negative_prompt、model_name、latency_ms、Token、error_message。
- 单张超时 120 秒；每张最多 2 次，2 次失败整任务立即 failed。

### quality_reviewer（输入：基础图、商品画像、提示词）

用 `model_configs.vision_model`（豆包视觉模型）；未配置则跳过并标「未校验」：

```json
{"passed": true, "issues": [],
 "checks": {"product_fidelity": "pass", "deformity": "pass",
            "whitespace_available": "pass", "compliance": "pass"}}
```

文字正确性由后端合成保证，不由视觉审核负责。

### repairer（输入：审核问题、原提示词、商品画像；输出：修正后的提示词 JSON）

最多修复 1 次；修复后重走 image_generator 并复检 quality_reviewer，复检仍不通过该张失败。

### platform_rule（输入：文案、尺寸、类目、平台规范内容）

规则统一维护在 `platform_rule` 系统提示词，不单独建表：

```json
{"passed": true, "issues": [],
 "checks": {"size": "pass", "prohibited_words": "pass", "category_rules": "pass"}}
```

## 单张失败 vs 整批失败

- 生图 2 次失败 → 整批 `failed`，不再生成其他张。
- 非生图原因（内容审核/文字合成/平台规范）→ 该张 `failed`，其余继续，批次最终 `partially_failed`。
- 内容审核不过：不自动反复重试，标失败让用户调整。
- 重试/重生成：新增记录，旧图 `superseded`，不覆盖旧文件。

## 全套复用

`full` 批次不重复调用 planner/product_understanding/copywriter/prompt_builder；示例批次产出的计划 + 文案 + 提示词已覆盖全部 6 张图，全套只对 5 张详情图执行 image_generator → quality_reviewer → platform_rule → text_composition。
