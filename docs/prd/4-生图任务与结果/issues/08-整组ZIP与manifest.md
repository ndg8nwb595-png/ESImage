# 08: 整组 ZIP 下载与 manifest.csv

**What to build:** 用户可以对 `completed` 或 `partially_failed` 的全套批次下载整组 ZIP。ZIP 包含全部当前成功的正式图，按序号命名为 `{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`，并附带 `manifest.csv`，列出序号、文件名、状态、尺寸、生成时间与失败原因。部分失败时仍可下载成功图片，manifest 需要列出失败张及其原因。ZIP 命名为 `{商品名称}_全套_{yyyyMMddHHmmss}.zip`；示例批次、非全套批次、取消或失败的批次不可整组下载。

**Blocked by:** 05（失败重试、降级与部分失败）

**Status:** ready-for-agent

- [ ] `GET /api/v1/batches/{batch_id}/download` 仅允许当前用户下载自己的批次；不存在或不属于当前用户返回 404 `30004`。
- [ ] 仅 `batch_type=full` 且状态为 `completed` / `partially_failed` 的批次可下载；示例批次、`queued`、`running`、`confirmed`、`failed`、`cancelled` 返回 409 `30005`，并给出明确提示。
- [ ] ZIP 包含该批次当前非 `superseded`、`status=success` 的全部正式图；第 1 张主图与第 2~6 张详情图均按 `index_no` 升序排列。
- [ ] 单张文件名规则：`{商品名称}_{主图|详情图}_{序号}_{yyyyMMddHHmmss}.png`；商品名称中的文件名非法字符替换为下划线；主图序号为 1，详情图序号为 2~6。
- [ ] `manifest.csv` 至少包含列：序号、文件名、状态、尺寸、生成时间、失败原因；失败张的状态为 `failed`，文件名为空或按规则生成，失败原因为该张 `error_message`；成功张的失败原因为空。
- [ ] `manifest.csv` 使用 UTF-8 BOM 编码，中文在 Excel 中正常显示；表头为中文。
- [ ] 部分失败批次：ZIP 只包含成功图，manifest 同时列出成功张与失败张；不因存在失败张而拒绝下载。
- [ ] 全部失败或没有成功图的批次不生成空 ZIP，返回 409 `30005`，提示「没有可下载的图片」。
- [ ] ZIP 文件名：`{商品名称}_全套_{yyyyMMddHHmmss}.zip`；响应头使用 `Content-Type: application/zip` 与 `Content-Disposition: attachment; filename*=UTF-8''...`。
- [ ] 下载使用流式响应，不把整个 ZIP 加载进内存；文件从存储适配层读取，读取失败返回 500 `50003`，不返回半截 ZIP。
- [ ] 权限为 `user.history`；缺少权限返回 403 `20005`。
- [ ] 单张成功正式图仍可通过既有 `GET /api/v1/images/{image_id}/download` 下载，命名规则与 ZIP 内一致；示例图、失败图、`superseded` 旧图、取消任务产物不可下载。
- [ ] 本切片不实现历史作品列表、归档文件读取与下载任务排队；只交付当前批次的整组 ZIP。
