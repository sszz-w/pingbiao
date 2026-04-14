# Pingbiao-Power 后端开发指南

Pingbiao-Power 评标系统的后端服务，负责招标/投标 PDF 解析、AI 双代理辩论评审、NDJSON 流式输出及 HTML 报告生成。

## 技术栈

- **Python**: 3.11+
- **框架**: FastAPI + Uvicorn
- **PDF 解析**: PyMuPDF
- **LLM**: OpenAI Python SDK（兼容 DeepSeek、Azure 等 OpenAI 兼容 API）
- **分词/检索**: jieba
- **响应格式**: NDJSON 流式（`application/x-ndjson`）

## 快速启动

```bash
cd pingbiao-back
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## 项目结构

```
pingbiao-back/
├── main.py              # FastAPI 入口、CORS、路由挂载
├── requirements.txt
├── routers/
│   └── run.py           # POST /api/run
├── models/
│   └── schemas.py       # Pydantic 数据模型
├── services/
│   ├── tender_parser.py # 招标文件解析
│   ├── bid_parser.py    # 投标解析 + 切片
│   ├── retriever.py     # 关键词检索
│   ├── debate.py        # AI 双代理辩论引擎
│   └── report.py        # HTML 报告生成
└── prompts/
    └── templates.py    # LLM prompt 模板
```

## 核心依赖

```
fastapi
uvicorn[standard]
python-multipart
pymupdf
openai
jieba
```

## API 契约

### POST /api/run

- **请求**: `multipart/form-data`
  - `tender_file`: 招标 PDF（单文件）
  - `bid_files`: 投标 PDF（多文件）
  - `api_base`: LLM API 地址（如 `https://api.openai.com/v1`）
  - `api_key`: API Key
  - `model`: 模型名称（如 `gpt-4o`、`deepseek-chat`）

- **响应**: `StreamingResponse`，`media_type="application/x-ndjson"`，每行一个 JSON 对象

- **文件校验**: 仅支持 `.pdf`，非 PDF 返回 400：
  ```json
  { "error": "invalid_format", "message": "仅支持 PDF 文件" }
  ```

### NDJSON 事件类型

| type | 含义 | 关键字段 |
|------|------|----------|
| `parse_tender_done` | 招标解析完成 | `clauses[]` |
| `parse_bid_done` | 单个投标解析完成 | `bid_id`, `file_name` |
| `clause_start` | 开始评审某条款×某投标 | `clause`（完整对象）, `bid_name` |
| `debate` | 辩论过程 | `role`(support/challenge), `content`（**字符串**） |
| `score` | 条款打分完成 | `clause_no`, `bid_name`, `score`, `reason` |
| `clause_end` | 该条款×投标评审结束 | — |
| `report` | 最终报告 | `html` |
| `error` | 错误 | `error`, `message` |

## 数据模型（与前端一致）

- **Clause**: `id`, `no`, `desc`, `score`, `weight`, `order`（招标解析时生成 `id=f"c{i}"`, `order=i`）
- **Chunk**: `bid_id`, `index`, `content`
- **DebateEvent**: `content` 必须为字符串，供前端流式展示

## 开发参考

- **详细开发步骤**: 见项目根目录 `docs/back.md`，按 Step 1～5 顺序实现
- **前后端契约**: 见 `docs/前后端对接检查报告.md`，确保事件结构与前端 types 一致
- **产品 Spec**: 见 `docs/pingbiao.md` 第 12 节

## 约定与注意点

1. **CORS**: 允许 `http://localhost:5173`、`http://127.0.0.1:5173`
2. **debate content**: LLM 返回 JSON 后，将 `reason`/`challenge` 转为字符串再 yield，前端需直接追加展示
3. **clause_start**: 必须下发完整 `clause` 对象和 `bid_name`（原始文件名），前端用于展示当前评审上下文
4. **切片参数**: `chunk_size=800`, `overlap=100`
5. **检索**: jieba 分词 + 关键词命中数排序，`top_k=5`
