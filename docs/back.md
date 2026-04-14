# Pingbiao-Power 后端开发计划

## 技术栈

- Python 3.11+
- FastAPI + Uvicorn
- PyMuPDF（PDF 解析）
- OpenAI Python SDK（LLM 调用，兼容 DeepSeek 等）
- jieba（中文分词，用于检索）
- SSE/NDJSON 流式响应

## 项目结构

```
backend/
├── main.py                  # FastAPI 入口，CORS，挂载路由
├── requirements.txt
├── routers/
│   └── run.py               # POST /api/run 端点
├── models/
│   └── schemas.py           # Pydantic 数据模型
├── services/
│   ├── tender_parser.py     # 招标文件解析
│   ├── bid_parser.py        # 投标文件解析 + 切片
│   ├── retriever.py         # 关键词检索
│   ├── debate.py            # AI 双代理辩论引擎
│   └── report.py            # HTML 报告生成
└── prompts/
    └── templates.py         # LLM prompt 模板
```

---

## Step 1 — 项目骨架 + 文件上传接口

### 目标

搭建 FastAPI 项目，实现文件上传端点，返回占位响应。

### 任务

1. 初始化项目目录结构
2. `requirements.txt`：fastapi, uvicorn[standard], pymupdf, openai, python-multipart, jieba
3. `main.py`：创建 FastAPI app，配置 CORS（允许 `localhost:5173`），挂载路由
4. `models/schemas.py`：定义数据模型
   - `Clause(id: str, no: str, desc: str, score: float, weight: float, order: int)`（与前端一致）
   - `Chunk(bid_id: str, index: int, content: str)`
   - `DebateEvent(type: str, role: str | None, content: str | None, score: float | None, reason: str | None)`（content 为字符串，供前端流式展示）
5. `routers/run.py`：
   - `POST /api/run` 接收：`tender_file: UploadFile`, `bid_files: list[UploadFile]`, `api_base: str`, `api_key: str`, `model: str`
   - 校验文件格式（仅 `.pdf`），非 PDF 返回 400 + `{"error": "invalid_format", "message": "仅支持 PDF 文件"}`
   - 合法请求暂时返回 `{"status": "ok"}`

### 验证

```bash
cd backend && uvicorn main:app --reload --port 8000

curl -X POST http://localhost:8000/api/run \
  -F "tender_file=@test.pdf" \
  -F "bid_files=@bid1.pdf" \
  -F "api_base=https://api.openai.com/v1" \
  -F "api_key=sk-test" \
  -F "model=gpt-4o"
# 预期：{"status": "ok"}
```

---

## Step 2 — 招标文件解析

### 目标

从招标 PDF 中提取结构化评审条款列表。

### 任务

1. `services/tender_parser.py`：实现 `async parse_tender(file_bytes, api_base, api_key, model) -> list[Clause]`
2. 解析流程：
   - PyMuPDF 提取 PDF 全文
   - 调用 LLM，prompt 要求提取评审条款，输出 JSON 数组
   - 解析返回的 JSON，映射为 `list[Clause]`
3. `prompts/templates.py`：定义招标解析 prompt
   ```
   你是招标文件分析专家。请从以下招标文件内容中提取所有评审条款。
   每个条款包含：编号(no)、描述(desc)、分值(score)、权重(weight)。
   若文件未明确权重，则 weight=1.0。
   请按出现顺序输出 JSON 数组：[{"no": "1", "desc": "...", "score": 10, "weight": 1.0}, ...]
   仅输出 JSON，不要其他内容。

   招标文件内容：
   {content}
   ```
4. 解析返回的 JSON 后，为每个条款补充 `id`（如 `id=f"c{i}"`）、`order`（如 `order=i`），与前端 Clause 结构一致。
5. 错误处理：PDF 文本为空 → `parse_failed`；LLM 返回非法 JSON → 重试一次

### 验证

```python
import asyncio
from services.tender_parser import parse_tender

async def main():
    with open("test_tender.pdf", "rb") as f:
        clauses = await parse_tender(f.read(), "https://api.openai.com/v1", "sk-xxx", "gpt-4o")
    for c in clauses:
        print(f"[{c.no}] {c.desc} — {c.score}分")

asyncio.run(main())
```

---

## Step 3 — 投标文件解析 + 切片 + 检索

### 目标

解析投标 PDF，切片存入内存，实现关键词检索。

### 任务

1. `services/bid_parser.py`：实现 `parse_bids(files: list[tuple[str, bytes]]) -> dict[str, dict]`
   - 入参：`(file_name, bytes)`，file_name 为原始文件名（如 `投标A.pdf`）
   - PyMuPDF 提取全文
   - 按字符切片：`chunk_size=800`, `overlap=100`
   - 返回 `{bid_id: {"chunks": [Chunk, ...], "file_name": "投标A.pdf"}}`，bid_id 为文件名去扩展名
2. `services/retriever.py`：实现 `retrieve(clause_desc: str, chunks: list[Chunk], top_k: int = 5) -> list[Chunk]`
   - jieba 分词提取关键词（去停用词）
   - 对每个 chunk 计算关键词命中数
   - 按命中数降序，返回 top_k

### 验证

```python
from services.bid_parser import parse_bids
from services.retriever import retrieve

bids = parse_bids([("投标A.pdf", open("bid1.pdf", "rb").read())])
results = retrieve("投标人应具备 ISO9001 质量管理体系认证", bids["投标A"]["chunks"])
for r in results:
    print(f"[chunk {r.index}] {r.content[:100]}...")
```

---

## Step 4 — AI 双代理辩论引擎

### 目标

实现支持方 → 质疑方 → 仲裁的单轮辩论，逐步 yield 事件。

### 任务

1. `prompts/templates.py` 追加三个 prompt：
   - **支持方**：根据条款和投标内容打分 → `{"score": N, "reason": "..."}`
   - **质疑方**：对支持方评分质疑 → `{"challenge": "...", "suggested_score": N}`
   - **仲裁**：综合双方给出最终分数 → `{"score": N, "reason": "..."}`
2. `services/debate.py`：实现 `async debate(clause, chunks, api_base, api_key, model) -> AsyncGenerator[DebateEvent]`
   - 构造 `AsyncOpenAI(base_url=api_base, api_key=api_key)`
   - 调用支持方 → 从 LLM 返回的 JSON 提取 `reason` 作为可读文本 → yield `DebateEvent(type="debate", role="support", content=reason_str, ...)`
   - 调用质疑方 → 从 LLM 返回的 JSON 提取 `challenge` 作为可读文本 → yield `DebateEvent(type="debate", role="challenge", content=challenge_str, ...)`
   - 调用仲裁 → yield `DebateEvent(type="score", score=N, reason="...")`
   - **重要**：`content` 必须为字符串，供前端 DebatePanel 流式追加展示
3. 错误处理：LLM 返回非 JSON → 正则提取；连续失败 → yield 错误事件

### 验证

```python
import asyncio
from services.debate import debate
from models.schemas import Clause, Chunk

clause = Clause(id="c1", no="1", desc="投标人应具备 ISO9001 认证", score=10, weight=1.0, order=1)
chunks = [Chunk(bid_id="A", index=0, content="我公司已于2023年获得ISO9001认证...")]

async def main():
    async for event in debate(clause, chunks, "https://api.openai.com/v1", "sk-xxx", "gpt-4o"):
        print(event)

asyncio.run(main())
```

---

## Step 5 — SSE 流式输出 + 报告生成

### 目标

串联 Step 2-4，NDJSON 流式推送全流程事件；生成 HTML 报告。

### 任务

1. `routers/run.py` 改造为 `StreamingResponse`，事件流程（与前端 types 一致）：
   ```
   {"type": "parse_tender_done", "clauses": [Clause, ...]}
   {"type": "parse_bid_done", "bid_id": "投标A", "file_name": "投标A.pdf"}
   {"type": "clause_start", "clause": {id, no, desc, score, weight, order}, "bid_name": "投标A.pdf"}
   {"type": "debate", "role": "support", "content": "文本内容..."}
   {"type": "debate", "role": "challenge", "content": "文本内容..."}
   {"type": "score", "clause_no": "1", "bid_name": "投标A.pdf", "score": 8, "reason": "..."}
   {"type": "clause_end"}
   ... (重复 clauses × bids)
   {"type": "report", "html": "<html>..."}
   {"type": "error", "error": "llm_error", "message": "用户可读信息"}  // 出错时
   ```
2. 主循环伪代码：
   ```python
   async def event_generator():
       clauses = await parse_tender(...)  # 每个 Clause 含 id, no, desc, score, weight, order
       yield ndjson({"type": "parse_tender_done", "clauses": [c.dict() for c in clauses]})

       # bids: {bid_id: {"chunks": [...], "file_name": "xxx.pdf"}}
       bids = parse_bids([(f.filename, await f.read()) for f in bid_files])
       for bid_id, data in bids.items():
           yield ndjson({"type": "parse_bid_done", "bid_id": bid_id, "file_name": data["file_name"]})

       results = []
       for clause in clauses:
           for bid_id, data in bids.items():
               bid_name = data["file_name"]
               chunks = data["chunks"]
               yield ndjson({"type": "clause_start", "clause": clause.dict(), "bid_name": bid_name})
               relevant = retrieve(clause.desc, chunks)
               async for event in debate(clause, relevant, ...):
                   yield ndjson(event.dict())  # content 为字符串
                   if event.type == "score":
                       results.append({"clause_no": clause.no, "bid_name": bid_name, "score": event.score, "reason": event.reason})
               yield ndjson({"type": "clause_end"})

       html = generate_report(clauses, bids, results)
       yield ndjson({"type": "report", "html": html})

   return StreamingResponse(event_generator(), media_type="application/x-ndjson")
   ```
3. `services/report.py`：实现 `generate_report(clauses, bids, results) -> str`
   - 生成 HTML 表格：投标文件 × 条款 → 得分 + 理由（results 含 clause_no, bid_name, score, reason）
   - 底部汇总每个投标的总分（bids 结构：`{bid_id: {"chunks": [...], "file_name": "xxx.pdf"}}`）

### 验证

```bash
curl -N -X POST http://localhost:8000/api/run \
  -F "tender_file=@tender.pdf" \
  -F "bid_files=@bid1.pdf" \
  -F "bid_files=@bid2.pdf" \
  -F "api_base=https://api.openai.com/v1" \
  -F "api_key=sk-xxx" \
  -F "model=gpt-4o"
# 预期：逐行输出 JSON 事件，最后输出 report 事件
```

---

## 前后端对接契约

前端只需消费 `POST /api/run` 返回的 NDJSON 流，每行一个 JSON，按 `type` 字段分发。与 `front.md` 中 `StreamEvent` 类型一致：

| type | 含义 | 关键字段 |
|------|------|----------|
| `parse_tender_done` | 招标解析完成 | `clauses[]`（含 id, no, desc, score, weight, order） |
| `parse_bid_done` | 单个投标解析完成 | `bid_id`, `file_name` |
| `clause_start` | 开始评审某条款×某投标 | `clause`（完整 Clause 对象）, `bid_name`（原始文件名） |
| `debate` | 辩论过程 | `role`(support/challenge), `content`（字符串） |
| `score` | 条款打分完成 | `clause_no`, `bid_name`, `score`, `reason` |
| `clause_end` | 该条款×投标评审结束 | — |
| `report` | 最终报告 | `html` |
| `error` | 错误 | `error`（错误码）, `message`（用户可读信息） |

---

## 开发顺序与时间估算

| 步骤 | 依赖 | 预计工作量 |
|------|------|-----------|
| Step 1 骨架 + 上传 | 无 | 0.5h |
| Step 2 招标解析 | Step 1 | 1h |
| Step 3 投标切片 + 检索 | Step 1 | 1h |
| Step 4 辩论引擎 | Step 2, 3 | 1.5h |
| Step 5 流式串联 + 报告 | Step 1-4 | 1h |

Step 2 和 Step 3 可并行开发，Step 4 依赖两者的输出。
