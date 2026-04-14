# Pingbiao-Power 后端接口文档

## 基本信息

- **Base URL**: `http://localhost:8000`
- **API 前缀**: `/api`
- **响应格式**: `/api/run` 为 NDJSON 流式（`application/x-ndjson`），`/api/clause` 为 JSON

---

## 整体流程

评标流程拆分为两个阶段，由前端串联调用：

```
1. POST /api/run
   └─ 解析招标文件 + 投标文件 → 返回条款列表（及投标解析结果）

2. 前端循环：对每个条款调用 POST /api/clause
   └─ 输入：条款名称、条款打分要求
   └─ 输出：AI 对每个投标文件的打分结果

3. 所有条款评审完成后，前端汇总结果（或调用报告生成接口）
```

---

## POST /api/run

**职责**：解析招标文件和投标文件，返回招标文件的条款列表。不执行评审打分。

### 请求

- **Content-Type**: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `tender_file` | File | 是 | 招标 PDF 文件（单个） |
| `bid_files` | File[] | 是 | 投标 PDF 文件（一个或多个） |
| `api_base` | string | 是 | LLM API 地址，如 `https://api.openai.com/v1` |
| `api_key` | string | 是 | LLM API Key |
| `model` | string | 是 | 模型名称，如 `gpt-4o`、`deepseek-chat` |

### 请求示例

```bash
curl -N -X POST http://localhost:8000/api/run \
  -F "tender_file=@招标文件.pdf" \
  -F "bid_files=@投标A.pdf" \
  -F "bid_files=@投标B.pdf" \
  -F "api_base=https://api.openai.com/v1" \
  -F "api_key=sk-xxx" \
  -F "model=gpt-4o"
```

### 校验规则

- 所有文件必须为 `.pdf` 格式
- 非 PDF 文件返回 HTTP 400

### 错误响应（HTTP 400）

```json
{
  "detail": "招标文件必须是 PDF 格式"
}
```

---

## 响应：NDJSON 事件流（/api/run）

成功请求返回 `StreamingResponse`，`media_type="application/x-ndjson"`。

每行一个 JSON 对象，以 `\n` 分隔，按 `type` 字段区分事件类型。

### 事件时序（/api/run 仅包含解析阶段）

```
parse_tender_done    ← 招标解析完成，返回条款列表（1 次）
parse_bid_done       ← 投标解析完成（每个投标文件 1 次）
```

异常时可能出现 `error` 事件。

---

### 事件类型详解（/api/run）

#### 1. `parse_tender_done`

招标文件解析完成，返回提取到的评审条款列表。**前端据此获取条款列表，用于后续逐条调用 `/api/clause`**。

```json
{
  "type": "parse_tender_done",
  "session_id": "abc123",
  "clauses": [
    {
      "id": "1",
      "no": "1.1",
      "desc": "投标人应具备 ISO9001 质量管理体系认证",
      "score": 10.0,
      "weight": 1.0,
      "order": 1
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话标识，后续调用 `/api/clause` 时必传 |
| `clauses` | Clause[] | 评审条款数组 |

**Clause 结构**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 条款唯一标识（如 `"1"`, `"2"`） |
| `no` | string | 条款编号（如 `"1.1"`, `"2.3"`） |
| `desc` | string | 条款描述（即条款名称 + 打分要求） |
| `score` | number | 该条款满分值 |
| `weight` | number | 权重（默认 `1.0`） |
| `order` | number | 排列顺序 |

---

#### 2. `parse_bid_done`

单个投标文件解析完成。每个投标文件触发一次。后端需缓存解析结果，供后续 `/api/clause` 使用。

```json
{
  "type": "parse_bid_done",
  "bid_id": "投标A",
  "file_name": "投标A.pdf"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `bid_id` | string | 投标标识（文件名去扩展名） |
| `file_name` | string | 原始文件名 |

---

#### 3. `error`

流程中任意环节出错时触发。

```json
{
  "type": "error",
  "error": "AuthenticationError",
  "message": "Incorrect API key provided"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `error` | string | 错误类型（异常类名） |
| `message` | string | 用户可读的错误信息 |

---

## POST /api/clause

**职责**：对**单个条款**进行评审，输入条款名称和打分要求，输出 AI 对**每个投标文件**的打分结果。

前端需在 `/api/run` 完成后，对 `parse_tender_done` 返回的每个条款依次调用本接口，直到所有条款评审完成。

### 请求

- **Content-Type**: `application/json`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | string | 是 | 会话标识，与 `/api/run` 返回的会话对应，用于关联已解析的招标/投标数据 |
| `clause` | Clause | 是 | 条款对象（含条款名称、打分要求、满分等） |
| `api_base` | string | 是 | LLM API 地址 |
| `api_key` | string | 是 | LLM API Key |
| `model` | string | 是 | 模型名称 |

**Clause 请求体**（与 `parse_tender_done` 中的 Clause 结构一致）:

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 条款唯一标识 |
| `no` | string | 条款编号 |
| `desc` | string | 条款名称 + 打分要求描述 |
| `score` | number | 该条款满分值 |
| `weight` | number | 权重 |
| `order` | number | 排列顺序 |

### 请求示例

```bash
curl -X POST http://localhost:8000/api/clause \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "clause": {
      "id": "1",
      "no": "1.1",
      "desc": "投标人应具备 ISO9001 质量管理体系认证",
      "score": 10.0,
      "weight": 1.0,
      "order": 1
    },
    "api_base": "https://api.openai.com/v1",
    "api_key": "sk-xxx",
    "model": "gpt-4o"
  }'
```

```typescript
// 前端示例：/api/run 完成后，逐条款调用
const clauses = /* 从 parse_tender_done 获取 */;
const sessionId = /* 从 parse_tender_done.session_id 获取 */;

for (const clause of clauses) {
  const res = await fetch("/api/clause", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      clause,
      api_base,
      api_key,
      model,
    }),
  });
  const result = await res.json();
  // 处理 result.scores
}
```

### 响应（JSON）

```json
{
  "clause_id": "1",
  "clause_no": "1.1",
  "scores": [
    {
      "bid_id": "投标A",
      "bid_name": "投标A.pdf",
      "score": 7.5,
      "reason": "综合考虑，投标文件提供了认证证书但范围匹配度不足，扣 2.5 分。"
    },
    {
      "bid_id": "投标B",
      "bid_name": "投标B.pdf",
      "score": 9.0,
      "reason": "投标文件完整提供 ISO9001 认证证书，范围与项目相符。"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `clause_id` | string | 条款 ID |
| `clause_no` | string | 条款编号 |
| `scores` | ClauseScore[] | 每个投标文件的打分结果 |

**ClauseScore 结构**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `bid_id` | string | 投标标识 |
| `bid_name` | string | 投标文件名 |
| `score` | number | 该条款得分（0 ~ 条款满分） |
| `reason` | string | 评分理由 |

### 可选：NDJSON 流式响应

若需展示辩论过程（支持方/质疑方发言），`/api/clause` 可支持流式返回，事件类型与原先 `clause_start`、`debate`、`score`、`clause_end` 一致，由前端按需解析。具体是否流式由实现决定，此处以 JSON 同步响应为主。

---

## 数据模型

### Clause

```typescript
interface Clause {
  id: string;       // 唯一标识，如 "1"
  no: string;       // 条款编号，如 "1.1"
  desc: string;     // 条款描述（条款名称 + 打分要求）
  score: number;    // 满分值
  weight: number;   // 权重，默认 1.0
  order: number;    // 排列顺序
}
```

### ClauseScore（/api/clause 返回）

```typescript
interface ClauseScore {
  bid_id: string;   // 投标标识
  bid_name: string; // 投标文件名
  score: number;    // 该条款得分
  reason: string;   // 评分理由
}
```

### Chunk（内部模型，不直接暴露给前端）

```typescript
interface Chunk {
  bid_id: string;   // 投标标识
  index: number;    // 切片序号
  content: string;  // 切片文本内容
}
```

---

## 前端调用流程示意

```
1. 调用 POST /api/run
   └─ 解析 NDJSON 流，收集 clauses、session_id、bid 列表

2. for (clause of clauses) {
     调用 POST /api/clause(session_id, clause, ...)
     └─ 收集 scores，存入本地状态
   }

3. 所有条款评审完成
   └─ 前端汇总 scores，生成报告或调用 /api/report（若存在）
```

---

## CORS 配置

允许的来源：

- `http://localhost:5173`
- `http://127.0.0.1:5173`

支持所有 HTTP 方法和请求头，允许携带凭证。

---

## 内部处理流程

### /api/run

```
请求到达
  │
  ├─ 文件格式校验（非 PDF → 400）
  │
  ├─ 生成 session_id，初始化会话存储
  │
  ├─ 解析招标 PDF（PyMuPDF 提取文本 → LLM 提取条款）
  │   └─ yield parse_tender_done
  │
  └─ 解析投标 PDF（PyMuPDF 提取文本 → 按 800 字符切片，100 字符重叠）
      └─ 缓存解析结果到 session
      └─ yield parse_bid_done × N
```

### /api/clause

```
请求到达
  │
  ├─ 根据 session_id 获取已解析的招标/投标数据
  │
  ├─ 遍历每个投标：
  │   ├─ jieba 分词检索 top-5 相关切片
  │   ├─ LLM 支持方评分
  │   ├─ LLM 质疑方质疑
  │   └─ LLM 仲裁打分
  │
  └─ 返回 { clause_id, clause_no, scores }
```
