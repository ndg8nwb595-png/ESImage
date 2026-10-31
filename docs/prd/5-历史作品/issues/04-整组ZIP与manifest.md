# 04: 整组 ZIP 与 manifest.csv

**What to build:** 用户在批次详情页点击「下载整组」，后端同步打包并流式返回 ZIP。ZIP 内是全部成功图片（按序号命名），并在根目录附带 `manifest.csv`，记录全部 6 张的序号、文件名、状态、尺寸、生成时间与失败原因。部分失败批次仍可下载，ZIP 只含成功图片，manifest 对应失败行写明状态与失败原因。

**Blocked by:** 02（批次详情与图片网格）

**Status:** ready-for-agent

- [ ] `GET /api/v1/batches/{batch_id}/download` 只允许当前用户、`batch_type=full`、状态为 `completed` 或 `partially_failed` 的批次。
- [ ] 响应为 `application/zip` 流，`Content-Disposition: attachment; filename*=UTF-8''...`；ZIP 文件名为 `{商品名称}_全套_{yyyyMMddHHmmss}.zip`，商品名称按单张下载同一规则清洗。
- [ ] ZIP 内只包含成功图片，文件名与单张下载一致：`{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`；不含缩略图与其他文件。
- [ ] `manifest.csv` 按序号 1~6 各一行；每个序号取该序号下 `attempt_no` 最大的非 `superseded` 图片记录；成功行写文件名、尺寸与生成时间，失败行文件名留空、状态为 `failed`、写失败原因。
- [ ] `manifest.csv` 使用 UTF-8 BOM、中文表头「序号,文件名,状态,宽度,高度,生成时间,失败原因」；状态取 `success` / `failed`；含逗号、引号或换行的字段按 CSV 规则加引号转义。
- [ ] 部分失败批次：ZIP 只含 5 张成功图，manifest 仍有 6 行，失败行状态与失败原因正确。
- [ ] 批次详情页显示「下载整组」按钮，点击后按钮进入 loading 并禁用，完成后触发保存；失败提示「下载失败，请稍后重试」并恢复按钮。
- [ ] 批次不存在返回 404 `30004`；批次属于他人返回 403 `20005`；示例批次、失败批次或其他状态返回 409 `30005`「当前批次不可下载」；缺少 `user.history` 返回 403 `20005`。
- [ ] 同步打包，单批最多 6 张 PNG；不引入异步任务、任务表或轮询接口。
- [ ] 接口路径、响应头、manifest 列与 4 号 demo 08 保持一致；若 4 号已实现，直接复用同一实现，不另写第二套。
- [ ] 本切片不涉及归档读取；归档图片进入 ZIP 由 05 交付。
