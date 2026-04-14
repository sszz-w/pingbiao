# Pingbiao-Power 后端 API 接口文档

## 项目概述

**技术栈**
- **语言**: Python 3.11+
- **框架**: FastAPI + Uvicorn
- **PDF 解析**: PyMuPDF, PaddleOCR
- **LLM**: OpenAI Python SDK (兼容 DeepSeek, Azure, 阿里云等)
- **分词**: jieba
- **响应格式**: NDJSON 流式 (`application/x-ndjson`) 或 WebSocket

**基础地址**: `http://localhost:8000/api`

**CORS 配置**: 允许 `http://localhost:5173`, `http://127.0.0.1:5173`

---

## 目录

1. [模型验证接口](#1-模型验证接口)
2. [PDF 上传与处理接口](#2-pdf-上传与处理接口)
3. [条款提取与评审接口](#3-条款提取与评审接口)
4. [WebSocket 实时通信](#4-websocket-实时通信)
5. [数据模型](#5-数据模型)
6. [错误处理](#6-错误处理)

---

## 1. 模型验证接口

### 1.1 验证大模型可用性

**端点**: `POST /api/verify-model`

**描述**: 验证大模型 API 是否可用，成功时返回 `taskId` 用于后续 WebSocket 连接。

**请求体** (JSON):
```json
{
  "base_url": "https://api.openai.com/v1",
  "api_token": "sk-xxx",
  "model_name": "gpt-4o"
}
```

**支持的 API 提供商**:
- **OpenAI**: `https://api.openai.com/v1` (模型: `gpt-4o`, `gpt-4-turbo`, `gpt-3.5-turbo`)
- **DeepSeek**: `https://api.deepseek.com/v1` (模型: `deepseek-chat`)
- **阿里云 Qwen**: `https://coding.dashscope.aliyuncs.com/v1` (模型: `qwen3.5-plus`, `qwen-max`)

**响应体** (JSON):

成功时:
```json
{
  "status": "success",
  "available": true,
  "code": 1,
  "message": "大模型可用",
  "taskId": "a1b2c3d4e5f6..."
}
```

失败时:
```json
{
  "status": "failed",
  "available": false,
  "code": 0,
  "message": "大模型连接失败：Invalid API key",
  "taskId": null
}
```

**重要说明**:
- 成功时返回的 `taskId` 用于后续建立 WebSocket 连接
- 前端需连接 `ws://host/api/ws/{taskId}` 建立统一 WebSocket
- 该 WebSocket 连接供后续所有接口复用

---

## 2. PDF 上传与处理接口

### 2.1 上传单个 PDF 文件

**端点**: `POST /api/upload-pdf`

**描述**: 上传单个 PDF 文件进行 OCR 处理，后台异步执行，通过 WebSocket 推送进度和结果。

**请求体** (multipart/form-data):
- `file`: PDF 文件
- `task_id`: 由 `verify-model` 返回的 taskId
- `base_url`: 大模型 API 基础地址
- `api_token`: API Key
- `model_name`: 模型名称

**响应体** (JSON):

成功时:
```json
{
  "result": 1,
  "task_id": "a1b2c3d4..."
}
```

失败时:
```json
{
  "result": 0,
  "error": "invalid_pdf"
}
```

**错误码**:
- `invalid_pdf`: 文件不是 PDF 格式
- `invalid_task_id`: taskId 无效
- `invalid_base_url`: base_url 格式错误
- `empty_api_token`: API token 为空
- `empty_model_name`: 模型名称为空
- `empty_file`: 文件内容为空
- `upload_failed`: 上传失败

**WebSocket 消息类型**:
- `{"type": "pdf_log", "message": "..."}` — 处理日志
- `{"type": "ocr_done", "pdf_name": "...", "parent_dir": "/abs/path"}` — OCR 完成
- `{"type": "task_done", "task_id": "...", "result": 1}` — 任务完成
- `{"type": "error", "message": "..."}` — 错误

**处理流程**:
1. PDF → JPG 图片 (pdf2jpg)
2. JPG → OCR 文本 (PaddleOCR)
3. 文本汇总 (down_to_up)

---

### 2.2 批量上传多个投标 PDF

**端点**: `POST /api/upload-many-pdfs`

**描述**: 批量上传多个投标 PDF 文件，后台逐个处理，通过 WebSocket 推送进度。

**请求体** (multipart/form-data):
- `files`: 多个 PDF 文件
- `task_id`: 由 `verify-model` 返回的 taskId
- `base_url`: 大模型 API 基础地址
- `api_token`: API Key
- `model_name`: 模型名称

**响应体** (JSON):

成功时:
```json
{
  "result": 1,
  "task_id": "a1b2c3d4...",
  "file_count": 3
}
```

失败时:
```json
{
  "result": 0,
  "error": "invalid_pdf",
  "file": "document.pdf"
}
```

**WebSocket 消息类型**:
- `{"type": "pdf_progress", "current": 1, "total": 3, "pdf_name": "..."}` — 当前处理进度
- `{"type": "pdf_log", "pdf_name": "...", "message": "..."}` — 单个 PDF 的处理日志
- `{"type": "ocr_done", "pdf_name": "...", "parent_dir": "/abs/path"}` — 单个 PDF OCR 完成
- `{"type": "error", "pdf_name": "...", "message": "..."}` — 单个 PDF 处理失败
- `{"type": "all_pdfs_done", "task_id": "...", "total": 3, "success": 3}` — 全部完成

---

## 3. 条款提取与评审接口

### 3.1 获取条款列表

**端点**: `POST /api/get-clause-list`

**描述**: 从已处理的招标文件目录中提取评审条款列表，后台异步执行，通过 WebSocket 推送结果。

**请求体** (JSON):
```json
{
  "folder_path": "/abs/path/to/processed/folder",
  "task_id": "a1b2c3d4...",
  "base_url": "https://api.openai.com/v1",
  "api_token": "sk-xxx",
  "model_name": "gpt-4o"
}
```

**响应体** (JSON):

成功时:
```json
{
  "result": 1,
  "task_id": "a1b2c3d4..."
}
```

失败时:
```json
{
  "result": 0,
  "error": "invalid_folder_path"
}
```

**错误码**:
- `invalid_folder_path`: 文件夹路径无效
- `summary_not_found`: 未找到 summary/all.txt，需先运行 PDF 处理
- `invalid_task_id`: taskId 未注册
- `invalid_base_url`: base_url 格式错误
- `empty_api_token`: API token 为空
- `empty_model_name`: 模型名称为空

**WebSocket 消息类型**:
- `{"type": "clause_list_log", "message": "..."}` — 进度日志（含精炼阶段、解析/精炼失败说明）
- `{"type": "clause_list_result", "data": [...]}` — 条款列表（**仅在初稿解析成功并完成精炼后推送一次**）
- `{"type": "clause_list_done", "task_id": "...", "result": 1}` — 任务完成
- `{"type": "error", "message": "..."}` — 错误

**条款列表数据结构** (`clause_list_result.data`):
```json
[
  {
    "条款描述": "技术方案完整性：需提供完整的技术实施方案，包括系统架构、技术路线等",
    "评分标准": "满足得 100 分，不满足得 0 分",
    "其他要求": "需提供详细的技术文档"
  },
  {
    "条款描述": "项目经验：近三年内完成过类似项目",
    "评分标准": "3个及以上得10分，2个得6分，1个得3分，0个得0分",
    "其他要求": ""
  }
]
```

**精炼流程**:
1. 初稿提取：从 summary/all.txt 中提取所有评审条款
2. 第 1 轮精炼：过滤总则类条目（分值构成、基准价计算方法、偏差率公式等）
3. 第 2 轮精炼：字段整理，确保格式统一
4. 默认评分：若「评分标准」为空，填充默认合格制「满足得 100 分，不满足得 0 分」

---

### 3.2 条款打分（针对单个投标文件）

**端点**: `POST /api/analysis-clause`

**描述**: 对单个投标文件的某条款进行打分评审，后台异步执行，通过 WebSocket 推送结果。

**请求体** (JSON):
```json
{
  "folder_path": "/abs/path/to/bid/folder",
  "clause_describe": "技术方案完整性：需提供完整的技术实施方案",
  "score_criteria": "满足得 100 分，不满足得 0 分",
  "other_requirements": "需提供详细的技术文档",
  "task_id": "a1b2c3d4...",
  "base_url": "https://api.openai.com/v1",
  "api_token": "sk-xxx",
  "model_name": "gpt-4o"
}
```

**响应体** (JSON):

成功时:
```json
{
  "result": 1,
  "task_id": "a1b2c3d4..."
}
```

失败时:
```json
{
  "result": 0,
  "error": "invalid_folder_path"
}
```

**WebSocket 消息类型**:
- `{"type": "analysis_clause_log", "message": "..."}` — 进度日志
- `{"type": "analysis_clause_result", "data": {...} | null}` — 打分结果
- `{"type": "analysis_clause_done", "task_id": "...", "result": 0|1}` — 任务结束
- `{"type": "error", "message": "..."}` — 未捕获异常

**打分结果数据结构** (`analysis_clause_result.data`):
```json
{
  "本地条款摘录": "投标文件第3章提供了完整的技术实施方案，包括系统架构图、技术路线说明...",
  "打分": "100",
  "思考过程": "根据评分规则，投标文件提供了完整的技术实施方案，满足条款要求，因此得 100 分。"
}
```

失败或未产出时 `data` 为 `null`。

---

### 3.3 单条款评审（旧版接口，已废弃）

**端点**: `POST /api/clause`

**描述**: 对单条款进行评审，返回所有投标的评分结果（同步接口，不推荐使用）。

**请求体** (JSON):
```json
{
  "session_id": "session_xxx",
  "clause": {
    "id": "c1",
    "no": "1.1",
    "desc": "技术方案完整性",
    "score": 10.0,
    "weight": 0.1,
    "order": 1
  },
  "api_base": "https://api.openai.com/v1",
  "api_key": "sk-xxx",
  "model": "gpt-4o"
}
```

**响应体** (JSON):
```json
{
  "clause_id": "c1",
  "clause_no": "1.1",
  "scores": [
    {
      "bid_id": "bid_1",
      "bid_name": "投标文件A.pdf",
      "score": 8.5,
      "reason": "技术方案较完整，但缺少部分细节说明"
    },
    {
      "bid_id": "bid_2",
      "bid_name": "投标文件B.pdf",
      "score": 9.0,
      "reason": "技术方案完整，文档齐全"
    }
  ]
}
```

---

### 3.4 解析阶段接口（旧版接口，已废弃）

**端点**: `POST /api/run`

**描述**: 解析招标文件和投标文件，返回 NDJSON 流（旧版接口，不推荐使用）。

**请求体** (multipart/form-data):
- `tender_file`: 招标 PDF 文件
- `bid_files`: 投标 PDF 文件（多个）
- `api_base`: LLM API URL
- `api_key`: API Key
- `model`: 模型名称
- `chunk_size`: 切片大小（可选，默认 800）
- `chunk_overlap`: 切片重叠大小（可选，默认 100）

**响应**: `StreamingResponse`, `media_type="application/x-ndjson"`

**NDJSON 事件类型**:
- `progress_update`: 进度更新
- `parse_tender_done`: 招标文件解析完成
- `parse_bid_done`: 投标文件解析完成
- `error`: 错误

---

## 4. WebSocket 实时通信

### 4.1 统一 WebSocket 端点

**端点**: `ws://host/api/ws/{task_id}`

**描述**: 统一 WebSocket 端点，供所有接口复用，用于实时推送日志、进度和结果。

**连接流程**:
1. 调用 `POST /api/verify-model` 获取 `taskId`
2. 连接 `ws://host/api/ws/{taskId}`
3. 连接成功后，调用其他接口（如 `upload-pdf`, `get-clause-list` 等）
4. 通过 WebSocket 接收实时消息

**前端 → 后端消息格式** (JSON):
```json
{
  "action": "ping"
}
```

**后端 → 前端消息格式** (JSON):
```json
{
  "type": "pong"
}
```

**连接验证**:
- 仅当 `taskId` 已通过 `verify-model` 注册时才接受连接
- 否则返回错误并关闭连接：
```json
{
  "type": "error",
  "message": "taskId 无效或未注册"
}
```

**消息类型汇总**:

| 消息类型 | 来源接口 | 说明 |
|---------|---------|------|
| `pong` | WebSocket | 心跳响应 |
| `pdf_log` | upload-pdf | PDF 处理日志 |
| `ocr_done` | upload-pdf | OCR 完成 |
| `task_done` | upload-pdf | 任务完成 |
| `pdf_progress` | upload-many-pdfs | 批量处理进度 |
| `all_pdfs_done` | upload-many-pdfs | 批量处理完成 |
| `clause_list_log` | get-clause-list | 条款列表提取日志 |
| `clause_list_result` | get-clause-list | 条款列表结果 |
| `clause_list_done` | get-clause-list | 条款列表提取完成 |
| `analysis_clause_log` | analysis-clause | 条款打分日志 |
| `analysis_clause_result` | analysis-clause | 条款打分结果 |
| `analysis_clause_done` | analysis-clause | 条款打分完成 |
| `error` | 所有接口 | 错误消息 |

---

## 5. 数据模型

### 5.1 Clause (招标评审条款)

```python
{
  "id": str,          # 条款 ID，格式: "c{i}"
  "no": str,          # 条款编号，如 "1.1"
  "desc": str,        # 条款描述
  "score": float,     # 分值
  "weight": float,    # 权重
  "order": int        # 排序序号
}
```

### 5.2 Chunk (投标文件切片)

```python
{
  "bid_id": str,      # 投标 ID
  "index": int,       # 切片索引
  "content": str      # 切片内容
}
```

### 5.3 ClauseScore (条款评分结果)

```python
{
  "bid_id": str,      # 投标 ID
  "bid_name": str,    # 投标文件名
  "score": float,     # 得分
  "reason": str       # 评分理由
}
```

### 5.4 ClauseListItem (条款列表项)

```python
{
  "条款描述": str,    # 条款编号、名称及要点概述
  "评分标准": str,    # 分值、权重、打分规则、计算公式等
  "其他要求": str     # 资格、形式、响应性等其他说明
}
```

### 5.5 ProgressEvent (进度事件)

```python
{
  "type": "progress_update",
  "stage": str,       # pdf_parse, clause_extract, debate, report
  "current": int,     # 当前进度
  "total": int,       # 总数
  "message": str      # 进度消息（可选）
}
```

---

## 6. 错误处理

### 6.1 HTTP 错误码

| 状态码 | 说明 |
|-------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在（如 session_id 无效） |
| 500 | 服务器内部错误 |

### 6.2 业务错误码

**verify-model 接口**:
- `code: 0` — 模型不可用
- `code: 1` — 模型可用

**upload-pdf / upload-many-pdfs 接口**:
- `result: 0` — 失败
- `result: 1` — 成功

**错误消息格式** (JSON):
```json
{
  "result": 0,
  "error": "error_code",
  "message": "详细错误信息"
}
```

**WebSocket 错误消息**:
```json
{
  "type": "error",
  "message": "错误描述"
}
```

---

## 7. 完整使用流程示例

### 7.1 招标文件条款提取流程

```
1. POST /api/verify-model
   → 获取 taskId

2. WebSocket 连接 ws://host/api/ws/{taskId}
   → 建立实时通信

3. POST /api/upload-pdf (上传招标文件)
   → 后台 OCR 处理
   → WebSocket 推送: pdf_log, ocr_done, task_done

4. POST /api/get-clause-list (提取条款列表)
   → 后台 LLM 提取并精炼
   → WebSocket 推送: clause_list_log, clause_list_result, clause_list_done
```

### 7.2 投标文件批量处理与打分流程

```
1. POST /api/verify-model
   → 获取 taskId

2. WebSocket 连接 ws://host/api/ws/{taskId}
   → 建立实时通信

3. POST /api/upload-many-pdfs (批量上传投标文件)
   → 后台逐个 OCR 处理
   → WebSocket 推送: pdf_progress, pdf_log, ocr_done, all_pdfs_done

4. 对每个投标文件的每个条款调用 POST /api/analysis-clause
   → 后台 LLM 打分
   → WebSocket 推送: analysis_clause_log, analysis_clause_result, analysis_clause_done
```

---

## 8. 配置说明

### 8.1 环境变量

| 变量名 | 默认值 | 说明 |
|-------|-------|------|
| `BASEDIR` | `.` | 基础目录，用于保存生成的文件 |
| `CHUNK_SIZE` | `10` | PDF 文本切片大小（字符数） |
| `CHUNK_OVERLAP` | `2` | 切片重叠大小（字符数） |
| `TOP_K` | `5` | 检索的最相关切片数量 |
| `DOWN_TO_UP_CHUNK_SIZE` | `10` | down_to_up 每组文件数 |
| `DOWN_TO_UP_CHUNK_OVERLAP` | `1` | down_to_up 重叠文件数 |

### 8.2 CORS 配置

允许的源:
- `http://localhost:5173`
- `http://127.0.0.1:5173`

---

## 9. 注意事项

1. **文件格式**: 仅支持 PDF 文件，非 PDF 文件将返回 400 错误
2. **taskId 生命周期**: taskId 在 verify-model 成功后生成，需在后续所有接口中使用
3. **WebSocket 连接**: 必须先建立 WebSocket 连接，再调用需要实时推送的接口
4. **异步处理**: upload-pdf, get-clause-list, analysis-clause 均为异步接口，立即返回，结果通过 WebSocket 推送
5. **精炼流程**: get-clause-list 会自动进行两轮精炼，删除总则类条目，填充默认评分标准
6. **打分格式**: analysis-clause 返回的「打分」字段可能是数字、等级或简短文字
7. **错误处理**: 所有接口均会通过 WebSocket 推送 error 类型消息，前端需监听处理

---

## 10. API 测试示例

### 10.1 使用 curl 测试 verify-model

```bash
curl -X POST http://localhost:8000/api/verify-model \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "https://api.openai.com/v1",
    "api_token": "sk-xxx",
    "model_name": "gpt-4o"
  }'
```

### 10.2 使用 curl 测试 upload-pdf

```bash
curl -X POST http://localhost:8000/api/upload-pdf \
  -F "file=@/path/to/document.pdf" \
  -F "task_id=a1b2c3d4..." \
  -F "base_url=https://api.openai.com/v1" \
  -F "api_token=sk-xxx" \
  -F "model_name=gpt-4o"
```

### 10.3 使用 JavaScript 连接 WebSocket

```javascript
const taskId = 'a1b2c3d4...'; // 从 verify-model 获取
const ws = new WebSocket(`ws://localhost:8000/api/ws/${taskId}`);

ws.onopen = () => {
  console.log('WebSocket 连接成功');
  // 发送心跳
  ws.send(JSON.stringify({ action: 'ping' }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('收到消息:', data);
  
  switch (data.type) {
    case 'pong':
      console.log('心跳响应');
      break;
    case 'pdf_log':
      console.log('PDF 处理日志:', data.message);
      break;
    case 'clause_list_result':
      console.log('条款列表:', data.data);
      break;
    case 'error':
      console.error('错误:', data.message);
      break;
  }
};

ws.onerror = (error) => {
  console.error('WebSocket 错误:', error);
};

ws.onclose = () => {
  console.log('WebSocket 连接关闭');
};
```

---

## 附录

### A. 项目目录结构

```
pingbiao-back/
├── main.py              # FastAPI 入口，CORS，路由注册
├── config.py            # 全局配置
├── routers/
│   ├── verify_model.py  # 模型验证接口
│   ├── upload.py        # PDF 上传接口
│   ├── clause.py        # 条款提取与评审接口
│   ├── ws.py            # WebSocket 接口
│   └── run.py           # 旧版解析接口（已废弃）
├── models/
│   └── schemas.py       # Pydantic 数据模型
├── services/
│   ├── verify_model.py  # 模型验证服务
│   ├── deal_pdf.py      # PDF 处理服务
│   ├── pdf2jpg.py       # PDF 转 JPG
│   ├── down_to_up.py    # 文本汇总（自下而上）
│   ├── up_to_down.py    # 文本查询（自上而下）
│   ├── clause_list_refine.py  # 条款列表精炼
│   ├── ws_manager.py    # WebSocket 连接管理
│   ├── session_store.py # 会话存储（旧版）
│   ├── tender_parser.py # 招标文件解析（旧版）
│   ├── bid_parser.py    # 投标文件解析（旧版）
│   ├── retriever.py     # 关键词检索（旧版）
│   ├── debate.py        # AI 辩论引擎（旧版）
│   └── report.py        # HTML 报告生成（旧版）
└── prompts/
    └── templates.py     # LLM Prompt 模板
```

### B. 依赖包

```
fastapi
uvicorn
python-multipart
pydantic
openai
PyMuPDF
paddlepaddle
paddleocr
jieba
Pillow
PyYAML
```

---

**文档版本**: v1.0  
**最后更新**: 2025-03-XX  
**维护者**: Pingbiao-Power Team
