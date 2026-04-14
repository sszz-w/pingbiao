# 后端变更说明：`all_pdfs_done` 事件新增 `completed_pdfs` 字段

## 变更概述

`/api/upload-many-pdfs` 批量投标文件处理完成后，WebSocket 推送的 `all_pdfs_done` 事件新增了 `completed_pdfs` 字段，携带所有成功处理的投标文件信息，以便前端自动触发后续的条款评审流程。

---

## 变更前后对比

### 变更前

```json
{
  "type": "all_pdfs_done",
  "task_id": "abc123",
  "total": 3,
  "success": 3
}
```

### 变更后

```json
{
  "type": "all_pdfs_done",
  "task_id": "abc123",
  "total": 3,
  "success": 3,
  "completed_pdfs": [
    { "pdf_name": "投标A.pdf", "parent_dir": "/abs/path/to/投标A" },
    { "pdf_name": "投标B.pdf", "parent_dir": "/abs/path/to/投标B" },
    { "pdf_name": "投标C.pdf", "parent_dir": "/abs/path/to/投标C" }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `completed_pdfs` | `Array` | 成功处理的投标文件列表，仅包含 `result == 1` 的文件 |
| `completed_pdfs[].pdf_name` | `string` | 原始文件名（与上传时一致，如 `"投标A.pdf"`） |
| `completed_pdfs[].parent_dir` | `string` | 该投标文件 OCR 输出目录的绝对路径（后续接口需要此值） |

> **向后兼容**：原有的 `task_id`、`total`、`success` 字段不变。如果前端暂时不需要自动触发后续流程，忽略 `completed_pdfs` 即可，不会有任何影响。

---

## 前端如何使用：触发条款评审

### 流程概览

```
upload-many-pdfs
  ↓ （WebSocket 推送）
all_pdfs_done.completed_pdfs
  ↓ （遍历每个投标文件）
POST /api/analysis-clause  ×  每条条款 × 每个投标文件
  ↓ （WebSocket 推送结果）
analysis_clause_result / analysis_clause_done
```

### 步骤

1. **监听 `all_pdfs_done` 事件**，从中取出 `completed_pdfs`
2. **结合已有的条款列表**（由 `clause_list_result` 事件获得），遍历调用 `/api/analysis-clause`
3. **每次调用传入一个投标文件的 `parent_dir` + 一条条款信息**

### 前端示例代码

```typescript
// types
interface CompletedPdf {
  pdf_name: string
  parent_dir: string
}

interface AllPdfsDoneEvent {
  type: 'all_pdfs_done'
  task_id: string
  total: number
  success: number
  completed_pdfs: CompletedPdf[]  // 新增
}

// WebSocket onMessage 处理
if (msg.type === 'all_pdfs_done') {
  const { completed_pdfs, task_id } = msg as AllPdfsDoneEvent

  if (completed_pdfs?.length && clauseList.length) {
    // 遍历：每条条款 × 每个投标文件
    for (const clause of clauseList) {
      for (const pdf of completed_pdfs) {
        await fetch('/api/analysis-clause', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            folder_path: pdf.parent_dir,       // ← 来自 completed_pdfs
            clause_describe: clause.条款描述,
            score_criteria: clause.评分标准,
            other_requirements: clause.其他要求 || '',
            task_id: task_id,
            base_url: savedBaseUrl,             // 与上传时相同
            api_token: savedApiToken,           // 与上传时相同
            model_name: savedModelName,         // 与上传时相同
          }),
        })
      }
    }
  }
}
```

---

## `/api/analysis-clause` 接口参考

### 请求

- **方法**: `POST`
- **Content-Type**: `application/json`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `folder_path` | `string` | 是 | 投标文件 OCR 输出目录绝对路径（即 `completed_pdfs[].parent_dir`） |
| `clause_describe` | `string` | 是 | 条款描述（来自 `clause_list_result` 的 `条款描述`） |
| `score_criteria` | `string` | 是 | 评分规则（来自 `clause_list_result` 的 `评分标准`） |
| `other_requirements` | `string` | 否 | 其他要求（来自 `clause_list_result` 的 `其他要求`，默认 `""`） |
| `task_id` | `string` | 是 | 与上传时相同的 taskId |
| `base_url` | `string` | 是 | 大模型 API 基础地址 |
| `api_token` | `string` | 是 | API Key |
| `model_name` | `string` | 是 | 模型名称 |

### 响应

```json
{ "result": 1, "task_id": "abc123" }
```

### WebSocket 推送事件

调用后，结果通过同一 WebSocket 连接推送：

| type | 说明 | 关键字段 |
|------|------|----------|
| `analysis_clause_log` | 进度日志 | `message` |
| `analysis_clause_result` | 打分结果 | `data: { "本地条款摘录", "打分", "思考过程" }` 或 `null` |
| `analysis_clause_done` | 该条款×该投标评审结束 | `task_id`, `result: 0 \| 1` |

---

## 注意事项

1. **调用时序**：`analysis-clause` 需要投标文件的 `summary/all.txt` 已生成，`all_pdfs_done` 时已经满足此条件，可以直接调用
2. **并发控制**：建议前端串行调用（逐个条款 × 逐个投标），避免同时发起大量 LLM 请求导致 API 限流
3. **错误处理**：`analysis_clause_result` 的 `data` 可能为 `null`（表示该条款在该投标文件中未匹配到内容或打分失败），前端需处理此情况
4. **条款列表来源**：`clauseList` 来自招标文件处理后 WebSocket 推送的 `clause_list_result` 事件的 `data` 字段
