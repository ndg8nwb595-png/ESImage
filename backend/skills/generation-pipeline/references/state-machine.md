# 状态机、阶段与留白合成速查

> 权威依据：`docs/prd/4-生图任务与结果/4-生图任务与结果prd.md` §3、§5、§7。
> 数据表枚举已固化在 `backend/app/models/workspace.py`，写 `pipeline.py` 前先对照，勿另造。

## 批次状态（generation_batches.status）

示例批次 `sample`：

```text
queued → running → sample_ready → confirmed
                 ↘ failed
queued / running / sample_ready → cancelled
```

全套批次 `full`：

```text
queued → running → completed / partially_failed / failed
queued / running → cancelled
```

约束：

- 同一用户同时只允许 1 个 `queued`/`running` 批次；`sample_ready` 不占并发名额。
- `confirmed` 只能从 `sample_ready` 进入。
- `full` 必须 `source_sample_batch_id` 指向一个 `confirmed` 的 `sample`（DB 有 CHECK 约束）。
- `cancelled` 是终态，不可恢复。

## 单图状态（generated_images.status）

```text
pending → generating → success / failed
                    ↘ cancelled
```

- 重生成/重试：旧图 `superseded`，新图 `attempt_no + 1`，沿用原提示词，`index_no` 不变。
- 只有 `full` 批次里 `image_type=final`、`status=success`、批次 completed/partially_failed 的图才 `is_history_visible=true`。

## stage 枚举（generation_batches.stage，DB CHECK 约束）

```text
planner → product_understanding → copywriter → prompt_builder → image_generator
→ quality_reviewer → repairer → platform_rule → text_composition → done
```

前端进度映射：需求理解 → 文案生成 → 提示词构建 → 图像绘制 → 质量审核 → 文字合成。

## 全套复用细节

- 确认 `sample_ready` 示例后创建 `full`：total_count=6、completed_count=1、status=queued。
- 示例图复用为 full 第 1 张主图：新建 `generated_images`（image_type=final、image_role=main、index_no=1、source_image_id=示例图、file_path 复用），不重生成。
- planner/product_understanding/copywriter/prompt_builder 输出全量复用；full 只对 5 张详情图走 image_generator → quality_reviewer（含修复复检）→ platform_rule → text_composition。
- 同一批次内串行生成（降低供应商限流）。

## 留白合成契约

生图模型只画画面、不写中文；提示词留白 + 后端合成。

输入 `layout_instruction`：

```json
{
  "canvas": {"width": 1000, "height": 1000},
  "blocks": [
    {"type": "title", "text": "轻盈透气 一整天",
     "box": {"x": 80, "y": 70, "width": 840, "height": 120},
     "font_size": 64, "font_weight": "bold", "color": "#1A1A1A", "align": "center"}
  ]
}
```

- 输出：合成后 PNG。失败该张标记「文字合成失败」。
- 字体：后端内置 1~2 个可商用中文字体，用户不可选；可复用 `workspace/imaging.py` 的字体探测思路。
- 默认版式兜底（设计 Skill 未产出时）：标题居中上方 15%，卖点下方 20%（最多 3 条），左右边距 8%，深色字配浅底、必要时加半透明白底。
- 文案超长：自动缩字号至下限，仍超出截断并记警告，不阻塞出图。

## 已就绪的表字段（勿另造）

- `agent_runs`：session_id/message_id/batch_id/image_id、agent_code、status(success/failed/skipped)、model_name、input_summary/output_summary/input_full/output_full、prompt_tokens/completion_tokens、latency_ms、error_message、created_at。
- `generation_batches`：batch_type(sample/full)、source_sample_batch_id、product_name、style_text、width/height、template_name、total_count/completed_count、status、stage、params_snapshot、requirement_summary、error_message、client_request_id、started_at/finished_at。
- `generated_images`：image_type(sample/final)、image_role(main/detail)、index_no、attempt_no、status(pending/generating/success/failed/cancelled/superseded)、source_image_id、file_path/thumbnail_path、width/height、prompt/negative_prompt、model_name、latency_ms、prompt_tokens/completion_tokens、error_message、is_history_visible、archived_at。
