## 前端交互流程（核心）

1. 用户首先需要配置好右上角的模型配置，点击保存配置时需要调用接口api/verify-model来验证是否可用。如果可用则上方弹出绿色框“大模型可用”，否则弹出红色警告框“大模型连接失败”。如果不可用，不允许执行主界面上传招标文件的步骤。

2. 前端此时只有上传招标文件（单个 PDF）的框。用户上传招标文件，触发接口api/upload-pdf，前后端此时要建立 websocket 连接。招标文件上传到后端配置的BASEDIR目录后，接口直接返回 0 或 1 代表是否上传成功。后端线程池异步进行将 pdf 转图片，并逐个进行 ocr 解析，直到全部解析完成后，后端通过 websocket 给前端发送解析成功的消息。

3. 前端收到第2 步的消息后，触发接口 api/get-clause-list 进行条款列表抽取。前后端此时要建立 websocket 连接。后端收到接口消息后直接返回 0 或 1 表示任务开始。后端此时对目录下的 txt 文件进行解析。解析步骤要遵循下方的**从下往上汇总**章节。因为我们需要的是条款列表，我们接下来需要用大模型对汇总内容去查询哪一组中存在条款内容，查询条款内容的方式要遵循下方的**从上往下查找**章节。初稿生成后，后端会再经**两轮大模型精炼**（过滤分值构成/基准价方法/偏差率公式等总则类非条款行，并整理字段），并对仍为空白的「评分标准」填入默认合格制文案「满足得 100 分，不满足的 0 分」。**仅在全流程结束后**通过 websocket 推送一次 `{"type":"clause_list_result","data":[...]}`：`data` 为已解析的 JSON 数组，每项为 `{"条款描述":"","评分标准":"","其他要求":""}`；解析失败时 `data` 为空数组，并可能收到 `clause_list_log` 说明原因。

4. 前端收到第 3 步的消息后，在前端渲染出上传投标文件（多个 PDF）的框。用户需上传完全部的投标文件后，点击提交触发接口 api/upload-many-pdfs前后端此时要建立websocket 连接。这些投标文件逐个上传到后端配置的BASEDIR目录后，接口直接返回 0 或 1 代表是否上传成功。后端线程池异步进行将 pdf 转图片，并逐个进行 ocr 解析，直到全部解析完成后，后端通过 websocket 给前端发送解析成功的消息。

5. 前端收到第 4 步的消息后，针对**每一条**招标条款，调用 **`POST /api/analysis-clause`** 对**当前选中的投标文件目录**做单条条款打分。前端在第 3 步收到多少条条款，本步就需调用多少次本接口；**必须串行**：待上一次评审收到结束态后再发下一次请求。调用前须已连接统一 WebSocket：`/api/ws/pdf-process/{task_id}`（`task_id` 与 `verify-model` 一致）。

   **HTTP 请求体（JSON）**

   | 字段 | 说明 |
   |------|------|
   | `folder_path` | 该投标文件 OCR 输出目录绝对路径（须含 `summary/all.txt`，与第 4 步处理结果一致） |
   | `clause_describe` | 条款描述 |
   | `score_criteria` | 评分规则 |
   | `other_requirements` | 其他要求（可无，传空字符串） |
   | `task_id` | 会话 taskId |
   | `api_token` | 大模型 API Token |
   | `base_url` | 大模型 Base URL（`http://` 或 `https://`） |
   | `model_name` | 模型名 |

   **HTTP 响应**：`{"result": 1, "task_id": "..."}` 表示后台任务已启动；`result` 为 `0` 时带 `error`（如 `invalid_folder_path`、`summary_not_found`、`invalid_task_id`、`invalid_base_url`、`empty_api_key`、`empty_model`）。**打分结果不在 HTTP 返回**，仅通过 WebSocket 推送。

   **检索与打分流程**：后端复用「从上往下查找」（见下文章节）：以 `all.txt` 与分段 summary 定位页码，合并对应 `{页码}.txt` 原文后，由大模型按上述条款与评分规则输出固定 JSON。**从下往上汇总**应在第 4 步 PDF 处理阶段已完成（`summary` 目录已存在）。

   **WebSocket 消息（`type`）**

   - `analysis_clause_log`：`{"type":"analysis_clause_log","message":"..."}` 进度日志。
   - `analysis_clause_result`：`{"type":"analysis_clause_result","data": {...} \| null}`。成功时 `data` 为对象，键名固定：`本地条款摘录`、`打分`、`思考过程`；定位或解析失败时 `data` 为 `null`。
   - `analysis_clause_done`：`{"type":"analysis_clause_done","task_id":"...","result":0|1}`，`1` 表示本条款打分流程成功结束且 `analysis_clause_result.data` 已解析成功；`0` 表示未产出有效结果。
   - `error`：未捕获异常时 `{"type":"error","message":"..."}`（通常会再跟一条 `analysis_clause_done`，`result` 为 `0`）。

## 从下往上汇总

 A 文件夹下假设有 100 个 txt 文件，分别是从“1.txt，2.txt，……100.txt”。我们需要有一定的记忆能力让大模型能更好的理解这些文档。如果后端配置的信息CHUNK_SIZE=10;CHUNK_OVERLAP=1，则表示每 10 个txt外加 1 个txt作为重叠项代表一组。如对“1.txt, 2.txt,……,10.txt,11.txt”、“11.txt, 12.txt,……,20.txt,21.txt”……以此类推直到最后“91.txt, 92.txt,……,100.txt”，把他们的每组的文字合并后发给大模型让其总结其中的内容，阐述什么内容处于哪些页码区间中，生成出 9 组汇总 txt，保存到A/summary 文件夹下，分别保存为“1～11.txt”、“11～21.txt”、……、“91～100.txt”。最后，再根据 A/summary 中的所有 txt 文件中文字合并发给大模型让他总结那几页区间的核心内容保存至 A/summary 文件夹下的 all.txt中。

## 从上往下查找

经过**从下往上汇总**章节后，A文件夹下方多了 summary 文件夹。我们先让大模型阅读 A/summary/all.txt 来获知大概哪些内容所在的页码区间。然后根据页码区间去查询对应的汇总 txt。如果后端配置的信息CHUNK_SIZE=10;CHUNK_OVERLAP=1，则表示每 10 个txt外加 1 个txt作为重叠项代表一组。那么 A/summary 文件夹下的汇总 txt 应该是“1～11.txt”、“11～21.txt”、……、“91～100.txt”格式的。如果大模型回复的页码区间在 15～25 页，那么我们需要让大模型去查询 “11～21.txt”和“21～31.txt”文件，获知组中哪些页存在需要查询的内容，如果回复的内容是 16～21 和 21～24。然后大模型根据查询的结果去定位A文件夹下的“16.txt、17.txt、……、24.txt”。最后我们把这些 txt 合并为一个去和大模型对话，让他回复我们想要查询的内容。