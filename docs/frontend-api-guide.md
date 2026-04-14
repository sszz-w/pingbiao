# 前端接口调取顺序指导文档

> 本文档面向前端开发者，按照业务流程的严格时序，说明每一步应调用的接口、前置条件、需要监听的 WebSocket 消息、以及何时可以进入下一步。

---

## 全局前置：WebSocket 连接管理

整个评标流程共用**一条 WebSocket 连接**，生命周期贯穿 Step 1 ~ Step 5。

```
ws://localhost:8000/api/ws/{taskId}
```

- `taskId` 由 Step 1 的 `verify-model` 接口返回
- 连接建立后，后续所有异步接口的进度和结果均通过此连接推送
- 前端需在 `onmessage` 中根据 `type` 字段分发处理

---

## 流程总览

```
Step 1: 验证模型 ──→ 获取 taskId
         │
         ▼
Step 1.5: 建立 WebSocket 连接
         │
         ▼
Step 2: 上传招标文件 (单个 PDF)
         │  等待 WS: task_done
         ▼
Step 3: 提取条款列表
         │  等待 WS: clause_list_result + clause_list_done
         ▼
Step 4: 上传投标文件 (多个 PDF)
         │  等待 WS: all_pdfs_done
         ▼
Step 5: 逐条款串行打分 (每个投标 × 每个条款)
         │  等待 WS: analysis_clause_done (逐条)
         ▼
       评审完成，前端汇总展示
```

---

## Step 1: 验证大模型配置

**触发时机**: 用户在右上角填写模型配置后点击「保存配置」

**接口**: `POST /api/verify-model`

**请求体**:
```json
{
  "base_url": "https://api.deepseek.com/v1",
  "api_token": "sk-xxx",
  "model_name": "deepseek-chat"
}
```

**响应处理**:

| 条件 | 前端行为 |
|------|---------|
| `code === 1` | 弹出绿色提示「大模型可用」，保存 `taskId` 到全局状态，解锁主界面上传区域 |
| `code === 0` | 弹出红色警告「大模型连接失败」，禁用上传区域，不允许进入 Step 2 |

**关键数据缓存**:
```typescript
// 全局状态需保存以下字段，后续所有接口复用
const globalConfig = {
  taskId: response.taskId,       // 贯穿全流程
  base_url: "https://...",       // 用户填写
  api_token: "sk-xxx",           // 用户填写
  model_name: "deepseek-chat",   // 用户填写
}
```

---

## Step 1.5: 建立 WebSocket 连接

**触发时机**: Step 1 成功后立即执行

**连接地址**: `ws://localhost:8000/api/ws/{taskId}`

```javascript
const ws = new WebSocket(`ws://localhost:8000/api/ws/${globalConfig.taskId}`)

ws.onopen = () => {
  console.log('WebSocket 已连接')
  // 可选：发送心跳确认
  ws.send(JSON.stringify({ action: 'ping' }))
}

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  // 根据 msg.type 分发到对应 Step 的处理函数
  handleWsMessage(msg)
}
```

**连接失败处理**:
- 如果收到 `{"type": "error", "message": "taskId 无效或未注册"}`，需回到 Step 1 重新验证

**心跳机制** (建议):
```javascript
// 每 30 秒发送一次 ping
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'ping' }))
  }
}, 30000)
```

---

## Step 2: 上传招标文件

**前置条件**: Step 1 成功 + WebSocket 已连接

**UI 状态**: 此时页面仅显示「上传招标文件」区域（单个 PDF）

**接口**: `POST /api/upload-pdf`

**请求** (multipart/form-data):
```
file:        招标文件.pdf
task_id:     ${globalConfig.taskId}
base_url:    ${globalConfig.base_url}
api_token:   ${globalConfig.api_token}
model_name:  ${globalConfig.model_name}
```

**HTTP 响应处理**:
- `result === 1`: 显示「上传成功，正在解析…」，进入等待状态
- `result === 0`: 根据 `error` 字段提示用户（如「仅支持 PDF 格式」）

**WebSocket 消息监听**:

| type | 前端行为 |
|------|---------|
| `pdf_log` | 在日志区域追加显示 `msg.message`（如「正在转换第 3 页…」） |
| `task_done` | **关键节点** — 保存 `msg.result`，记录招标文件处理目录路径（从 `ocr_done` 中获取） |
| `ocr_done` | 保存 `msg.parent_dir` 作为招标文件目录路径，后续 Step 3 使用 |
| `error` | 红色提示错误信息 |

**需要缓存的数据**:
```typescript
// 从 ocr_done 消息中获取
const tenderFolderPath = msg.parent_dir  // 招标文件处理后的目录绝对路径
```

**进入 Step 3 的条件**: 收到 `task_done` 且 `result === 1`

---

## Step 3: 提取条款列表

**前置条件**: Step 2 的 `task_done` 已收到

**触发方式**: 收到 Step 2 完成消息后**自动触发**（无需用户操作）

**接口**: `POST /api/get-clause-list`

**请求体** (JSON):
```json
{
  "folder_path": "${tenderFolderPath}",
  "task_id": "${globalConfig.taskId}",
  "base_url": "${globalConfig.base_url}",
  "api_token": "${globalConfig.api_token}",
  "model_name": "${globalConfig.model_name}"
}
```

**HTTP 响应处理**:
- `result === 1`: 显示「正在提取条款列表…」
- `result === 0`: 根据 `error` 提示（如 `summary_not_found` → 「文件解析未完成，请重试」）

**WebSocket 消息监听**:

| type | 前端行为 |
|------|---------|
| `clause_list_log` | 在日志区域追加 `msg.message`（如「条款列表精炼：第 1 轮…」） |
| `clause_list_result` | **关键节点** — 保存 `msg.data` 为条款列表数组，渲染条款表格 |
| `clause_list_done` | 确认提取完成，解锁「上传投标文件」区域 |
| `error` | 红色提示错误信息 |

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

**需要缓存的数据**:
```typescript
// 条款列表，Step 5 逐条打分时使用
const clauseList: Array<{
  条款描述: string
  评分标准: string
  其他要求: string
}> = msg.data
```

**注意事项**:
- `clause_list_result` 仅推送一次，且在两轮精炼完成后才推送
- 如果 `data` 为空数组 `[]`，说明提取失败，需提示用户检查招标文件
- 前端应允许用户手动编辑条款列表（增删改）

**进入 Step 4 的条件**: 收到 `clause_list_done` 且 `clauseList.length > 0`

---

## Step 4: 上传投标文件

**前置条件**: Step 3 的 `clause_list_done` 已收到，条款列表非空

**UI 状态**: 显示「上传投标文件」区域（支持多个 PDF），同时展示已提取的条款列表

**用户操作**: 选择多个投标 PDF → 点击「提交」

**接口**: `POST /api/upload-many-pdfs`

**请求** (multipart/form-data):
```
files:       投标文件A.pdf, 投标文件B.pdf, 投标文件C.pdf
task_id:     ${globalConfig.taskId}
base_url:    ${globalConfig.base_url}
api_token:   ${globalConfig.api_token}
model_name:  ${globalConfig.model_name}
```

**HTTP 响应处理**:
- `result === 1`: 显示「上传成功，正在解析 ${file_count} 个文件…」
- `result === 0`: 根据 `error` 提示

**WebSocket 消息监听**:

| type | 前端行为 |
|------|---------|
| `pdf_progress` | 更新进度条：「正在处理第 ${current}/${total} 个：${pdf_name}」 |
| `pdf_log` | 在日志区域追加 `msg.pdf_name`: `msg.message` |
| `ocr_done` | 记录该投标文件的处理目录路径 `{ pdf_name → parent_dir }` |
| `error` | 标记该 PDF 处理失败，红色提示 `msg.pdf_name`: `msg.message` |
| `all_pdfs_done` | **关键节点** — 全部处理完成 |

**需要缓存的数据**:
```typescript
// 从每个 ocr_done 消息中收集
const bidFolders: Map<string, string> = new Map()
// key: 投标文件名 (pdf_name)
// value: 处理后的目录绝对路径 (parent_dir)

// 示例:
// "投标文件A.pdf" → "/basedir/temp/投标文件A_abc123/..."
// "投标文件B.pdf" → "/basedir/temp/投标文件B_abc123/..."
```

**进入 Step 5 的条件**: 收到 `all_pdfs_done` 且 `success > 0`

---

## Step 5: 逐条款串行打分

**前置条件**: Step 4 的 `all_pdfs_done` 已收到

**核心规则**:
1. 对每个投标文件的每个条款调用一次 `analysis-clause`
2. **必须串行**：等上一次 `analysis_clause_done` 收到后，再发下一次请求
3. 总调用次数 = 条款数 × 投标文件数

**接口**: `POST /api/analysis-clause`

**请求体** (JSON):
```json
{
  "folder_path": "${bidFolders.get(当前投标文件名)}",
  "clause_describe": "${clauseList[i].条款描述}",
  "score_criteria": "${clauseList[i].评分标准}",
  "other_requirements": "${clauseList[i].其他要求}",
  "task_id": "${globalConfig.taskId}",
  "base_url": "${globalConfig.base_url}",
  "api_token": "${globalConfig.api_token}",
  "model_name": "${globalConfig.model_name}"
}
```

**WebSocket 消息监听**:

| type | 前端行为 |
|------|---------|
| `analysis_clause_log` | 日志区域追加 `msg.message` |
| `analysis_clause_result` | 保存打分结果到结果矩阵 |
| `analysis_clause_done` | **关键节点** — `result === 1` 表示成功，发起下一条请求 |
| `error` | 记录失败，继续下一条 |

**打分结果数据结构** (`analysis_clause_result.data`):
```json
{
  "本地条款摘录": "投标文件第3章提供了完整的技术实施方案...",
  "打分": "100",
  "思考过程": "根据评分规则，投标文件提供了完整的技术实施方案，满足条款要求..."
}
```
> `data` 为 `null` 时表示该条款打分失败

**串行调度伪代码**:
```typescript
interface ScoreResult {
  bidName: string
  clauseIndex: number
  data: {
    本地条款摘录: string
    打分: string
    思考过程: string
  } | null
}

const scoreMatrix: ScoreResult[] = []

async function runAllScoring() {
  const bidEntries = Array.from(bidFolders.entries())
  const total = bidEntries.length * clauseList.length
  let current = 0

  for (const [bidName, folderPath] of bidEntries) {
    for (let i = 0; i < clauseList.length; i++) {
      current++
      updateProgress(`正在评审 (${current}/${total}): ${bidName} - 条款 ${i + 1}`)

      // 1. 发起 HTTP 请求
      const res = await fetch('/api/analysis-clause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folder_path: folderPath,
          clause_describe: clauseList[i].条款描述,
          score_criteria: clauseList[i].评分标准,
          other_requirements: clauseList[i].其他要求 || '',
          task_id: globalConfig.taskId,
          base_url: globalConfig.base_url,
          api_token: globalConfig.api_token,
          model_name: globalConfig.model_name,
        }),
      })
      const httpResult = await res.json()

      if (httpResult.result !== 1) {
        // HTTP 层失败，记录并继续
        scoreMatrix.push({ bidName, clauseIndex: i, data: null })
        continue
      }

      // 2. 等待 WebSocket 推送 analysis_clause_done
      const wsResult = await waitForWsMessage('analysis_clause_done')

      // 3. 保存结果（analysis_clause_result 在 done 之前已推送）
      scoreMatrix.push({
        bidName,
        clauseIndex: i,
        data: latestAnalysisResult,  // 从 analysis_clause_result 消息中暂存
      })
    }
  }

  // 全部完成，渲染汇总表格
  renderScoreTable(scoreMatrix)
}
```

**等待 WebSocket 消息的工具函数**:
```typescript
function waitForWsMessage(targetType: string): Promise<any> {
  return new Promise((resolve) => {
    const handler = (event: MessageEvent) => {
      const msg = JSON.parse(event.data)
      if (msg.type === targetType) {
        ws.removeEventListener('message', handler)
        resolve(msg)
      }
    }
    ws.addEventListener('message', handler)
  })
}
```

---

## WebSocket 消息分发器（完整参考）

```typescript
let latestAnalysisResult: any = null

function handleWsMessage(msg: any) {
  switch (msg.type) {
    // ── 心跳 ──
    case 'pong':
      break

    // ── Step 2: 招标文件上传处理 ──
    case 'pdf_log':
      if (msg.pdf_name) {
        // Step 4 批量上传的日志（带 pdf_name）
        appendLog(`[${msg.pdf_name}] ${msg.message}`)
      } else {
        // Step 2 单文件上传的日志
        appendLog(msg.message)
      }
      break
    case 'ocr_done':
      // 保存处理目录路径
      if (currentStep === 2) {
        tenderFolderPath = msg.parent_dir
      } else if (currentStep === 4) {
        bidFolders.set(msg.pdf_name, msg.parent_dir)
      }
      break
    case 'task_done':
      // Step 2 招标文件处理完成 → 自动触发 Step 3
      onTenderProcessed(msg)
      break

    // ── Step 3: 条款列表提取 ──
    case 'clause_list_log':
      appendLog(msg.message)
      break
    case 'clause_list_result':
      clauseList = msg.data
      renderClauseTable(clauseList)
      break
    case 'clause_list_done':
      onClauseListReady()
      break

    // ── Step 4: 投标文件批量处理 ──
    case 'pdf_progress':
      updateProgressBar(msg.current, msg.total, msg.pdf_name)
      break
    case 'all_pdfs_done':
      onAllBidsProcessed(msg)
      break

    // ── Step 5: 条款打分 ──
    case 'analysis_clause_log':
      appendLog(msg.message)
      break
    case 'analysis_clause_result':
      latestAnalysisResult = msg.data
      break
    case 'analysis_clause_done':
      // 由串行调度器的 waitForWsMessage 捕获
      break

    // ── 全局错误 ──
    case 'error':
      showError(msg.message)
      break
  }
}
```

---

## 状态机总结

```
┌─────────────────────────────────────────────────────────────────┐
│  状态              触发条件                  UI 表现            │
├─────────────────────────────────────────────────────────────────┤
│  INIT              页面加载                  仅显示模型配置区   │
│                                                                 │
│  MODEL_VERIFIED    verify-model code=1      解锁上传招标文件区 │
│                    + WS 连接成功                                │
│                                                                 │
│  TENDER_UPLOADING  upload-pdf result=1      显示进度日志        │
│                                                                 │
│  TENDER_DONE       WS: task_done            自动触发条款提取   │
│                                                                 │
│  CLAUSE_EXTRACTING get-clause-list result=1 显示提取进度        │
│                                                                 │
│  CLAUSE_READY      WS: clause_list_done     渲染条款表格       │
│                    + data 非空               解锁上传投标文件区 │
│                                                                 │
│  BIDS_UPLOADING    upload-many-pdfs result=1 显示批量进度条     │
│                                                                 │
│  BIDS_DONE         WS: all_pdfs_done        自动开始逐条打分   │
│                                                                 │
│  SCORING           analysis-clause 串行中    显示打分进度       │
│                                                                 │
│  COMPLETED         所有条款打分完成          渲染汇总评分表     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 接口速查表

| 步骤 | 接口 | 方法 | Content-Type | 前置条件 | 完成信号 (WS) |
|------|------|------|-------------|---------|--------------|
| 1 | `/api/verify-model` | POST | application/json | 无 | — (HTTP 直接返回) |
| 1.5 | `/api/ws/{taskId}` | WebSocket | — | Step 1 成功 | `onopen` |
| 2 | `/api/upload-pdf` | POST | multipart/form-data | WS 已连接 | `task_done` |
| 3 | `/api/get-clause-list` | POST | application/json | Step 2 完成 | `clause_list_done` |
| 4 | `/api/upload-many-pdfs` | POST | multipart/form-data | Step 3 完成 | `all_pdfs_done` |
| 5 | `/api/analysis-clause` | POST | application/json | Step 4 完成，串行调用 | `analysis_clause_done` (每条) |

---

## 异常处理与重试建议

| 场景 | 处理方式 |
|------|---------|
| WebSocket 断开 | 自动重连（最多 3 次，间隔 2s/4s/8s），重连后需重新发送 ping 确认 |
| verify-model 失败 | 提示用户检查 API 配置，不允许进入后续步骤 |
| upload-pdf HTTP 返回 0 | 提示具体错误（格式不对、文件为空等），允许重新上传 |
| task_done 未收到 | 设置超时（建议 5 分钟），超时后提示「处理超时，请重试」 |
| clause_list_result.data 为空 | 提示「未能提取到条款，请检查招标文件是否包含评审条款」 |
| upload-many-pdfs 部分失败 | `all_pdfs_done.success < total` 时提示哪些文件失败，允许重新上传失败的文件 |
| analysis_clause_done result=0 | 记录该条款打分失败，标记为「未评审」，继续下一条 |
| 全局 error 消息 | 弹出错误提示，不中断整体流程（除非是致命错误） |

---

## 前端需要维护的全局状态

```typescript
interface AppState {
  // Step 1: 模型配置
  taskId: string | null
  baseUrl: string
  apiToken: string
  modelName: string

  // Step 1.5: WebSocket
  ws: WebSocket | null
  wsConnected: boolean

  // Step 2: 招标文件
  tenderFolderPath: string | null   // 从 ocr_done.parent_dir 获取

  // Step 3: 条款列表
  clauseList: Array<{
    条款描述: string
    评分标准: string
    其他要求: string
  }>

  // Step 4: 投标文件
  bidFolders: Map<string, string>   // pdf_name → parent_dir

  // Step 5: 打分结果
  scoreMatrix: Array<{
    bidName: string
    clauseIndex: number
    data: {
      本地条款摘录: string
      打分: string
      思考过程: string
    } | null
  }>

  // UI 状态
  currentStep: 'INIT' | 'MODEL_VERIFIED' | 'TENDER_UPLOADING'
    | 'TENDER_DONE' | 'CLAUSE_EXTRACTING' | 'CLAUSE_READY'
    | 'BIDS_UPLOADING' | 'BIDS_DONE' | 'SCORING' | 'COMPLETED'

  // 聊天消息列表
  chatMessages: ChatMessage[]
}
```

---

## 聊天界面设计规范

### 设计理念

前端主体界面采用**聊天对话**形式，类似微信群聊。所有 WebSocket 消息以不同「助理身份」的聊天气泡依次展示，让用户直观感受到多个 AI 角色协同工作的过程。

### 页面布局

```
┌──────────────────────────────────────────────────────┐
│  顶部栏：项目名称 + 右上角「模型配置」按钮/抽屉       │
├────────────────────────────┬─────────────────────────┤
│                            │                         │
│   聊天主区域（左侧/主体）    │   侧边栏（右侧）        │
│                            │   ┌───────────────────┐ │
│   ┌──────────────────────┐ │   │ 条款列表（可编辑） │ │
│   │ 📎 系统助理           │ │   │                   │ │
│   │ 大模型验证成功！       │ │   │ 投标文件列表      │ │
│   └──────────────────────┘ │   │                   │ │
│   ┌──────────────────────┐ │   │ 评分汇总表        │ │
│   │ 📄 文件助理           │ │   │                   │ │
│   │ 正在解析招标文件…      │ │   └───────────────────┘ │
│   └──────────────────────┘ │                         │
│   ┌──────────────────────┐ │                         │
│   │ 📋 条款助理           │ │                         │
│   │ 条款列表精炼中…       │ │                         │
│   └──────────────────────┘ │                         │
│   ...                      │                         │
│                            │                         │
├────────────────────────────┴─────────────────────────┤
│  底部操作区：上传招标文件 / 上传投标文件 / 开始评审     │
└──────────────────────────────────────────────────────┘
```

### 聊天身份定义

每个 WebSocket 消息类型对应一个固定的聊天身份，拥有独立的头像、名称和气泡颜色。

```typescript
interface ChatIdentity {
  id: string
  name: string
  avatar: string       // emoji 或图片 URL
  bubbleColor: string  // 气泡背景色
  textColor: string    // 文字颜色
}

const CHAT_IDENTITIES: Record<string, ChatIdentity> = {
  system: {
    id: 'system',
    name: '系统助理',
    avatar: '🔧',
    bubbleColor: '#E8F5E9',   // 浅绿
    textColor: '#2E7D32',
  },
  file: {
    id: 'file',
    name: '文件助理',
    avatar: '📄',
    bubbleColor: '#E3F2FD',   // 浅蓝
    textColor: '#1565C0',
  },
  clause: {
    id: 'clause',
    name: '条款助理',
    avatar: '📋',
    bubbleColor: '#FFF3E0',   // 浅橙
    textColor: '#E65100',
  },
  scorer: {
    id: 'scorer',
    name: 'AI 评审专家',
    avatar: '🧑‍⚖️',
    bubbleColor: '#F3E5F5',   // 浅紫
    textColor: '#6A1B9A',
  },
  error: {
    id: 'error',
    name: '系统警告',
    avatar: '⚠️',
    bubbleColor: '#FFEBEE',   // 浅红
    textColor: '#C62828',
  },
  user: {
    id: 'user',
    name: '我',
    avatar: '👤',
    bubbleColor: '#FFFFFF',
    textColor: '#333333',
  },
}
```

### WebSocket 消息类型 → 聊天身份映射

| WS `type` | 聊天身份 | 气泡内容示例 |
|-----------|---------|-------------|
| `pong` | — (不展示) | — |
| `pdf_log` | 📄 文件助理 | `正在将 PDF 转换为图片（第 3/20 页）…` |
| `ocr_done` | 📄 文件助理 | `✅ 「招标文件.pdf」解析完成` |
| `task_done` | 📄 文件助理 | `✅ 招标文件处理完毕，即将提取条款…` |
| `pdf_progress` | 📄 文件助理 | `正在处理第 2/5 个投标文件：投标文件B.pdf` |
| `all_pdfs_done` | 📄 文件助理 | `✅ 全部 5 个投标文件处理完成（成功 5 个）` |
| `clause_list_log` | 📋 条款助理 | `条款列表精炼：第 1 轮（过滤总则类条目）…` |
| `clause_list_result` | 📋 条款助理 | `✅ 已提取 12 条评审条款，请在右侧面板查看和编辑` |
| `clause_list_done` | 📋 条款助理 | `条款列表提取完成，请上传投标文件` |
| `analysis_clause_log` | 🧑‍⚖️ AI 评审专家 | `正在定位投标文件中与「技术方案完整性」相关的内容…` |
| `analysis_clause_result` | 🧑‍⚖️ AI 评审专家 | 渲染为结构化卡片（见下方「特殊气泡」） |
| `analysis_clause_done` | 🧑‍⚖️ AI 评审专家 | `✅ 「投标文件A」×「技术方案完整性」评审完成，得分：100` |
| `error` | ⚠️ 系统警告 | `处理失败：summary/all.txt 未找到` |

### 聊天消息数据结构

```typescript
interface ChatMessage {
  id: string                // 唯一 ID（uuid 或自增）
  identity: ChatIdentity    // 聊天身份
  content: string           // 文本内容
  timestamp: number         // 时间戳
  extra?: {                 // 附加结构化数据（用于特殊气泡渲染）
    type: 'clause_table' | 'score_card' | 'progress' | 'file_upload'
    data: any
  }
}
```

### 特殊气泡类型

除了普通文本气泡外，以下消息需要渲染为特殊卡片：

#### 1. 条款列表卡片 (`clause_list_result`)

```
┌─ 📋 条款助理 ──────────────────────────────────┐
│  ✅ 已提取 12 条评审条款                         │
│  ┌────────────────────────────────────────────┐ │
│  │ 序号 │ 条款描述         │ 评分标准          │ │
│  │  1   │ 技术方案完整性   │ 满足100/不满足0   │ │
│  │  2   │ 项目经验         │ 3个10分/2个6分…  │ │
│  │ ...  │ ...              │ ...              │ │
│  └────────────────────────────────────────────┘ │
│  [在右侧面板查看完整列表 →]                       │
└─────────────────────────────────────────────────┘
```

#### 2. 打分结果卡片 (`analysis_clause_result`)

```
┌─ 🧑‍⚖️ AI 评审专家 ─────────────────────────────┐
│  投标文件A × 条款「技术方案完整性」               │
│  ┌────────────────────────────────────────────┐ │
│  │ 打分：100                                   │ │
│  │ ──────────────────────────────              │ │
│  │ 摘录：投标文件第3章提供了完整的技术实施方案…  │ │
│  │ ──────────────────────────────              │ │
│  │ 思考过程：根据评分规则，投标文件提供了完整的  │ │
│  │ 技术实施方案，满足条款要求，因此得 100 分。   │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

打分失败时（`data === null`）：

```
┌─ 🧑‍⚖️ AI 评审专家 ─────────────────────────────┐
│  ❌ 投标文件A × 条款「技术方案完整性」            │
│  未能产出有效评审结果，已标记为「未评审」          │
└─────────────────────────────────────────────────┘
```

#### 3. 用户操作气泡

用户的上传操作也以聊天气泡形式展示（靠右对齐）：

```
                    ┌─ 👤 我 ──────────────────┐
                    │  📎 已上传招标文件：       │
                    │  某某项目招标文件.pdf       │
                    └──────────────────────────┘

                    ┌─ 👤 我 ──────────────────┐
                    │  📎 已上传 3 个投标文件：  │
                    │  · 投标文件A.pdf           │
                    │  · 投标文件B.pdf           │
                    │  · 投标文件C.pdf           │
                    └──────────────────────────┘
```

### WebSocket 消息 → 聊天消息转换器

```typescript
function wsMessageToChatMessage(msg: any): ChatMessage | null {
  const id = generateId()
  const timestamp = Date.now()

  switch (msg.type) {
    // ── 不展示 ──
    case 'pong':
      return null

    // ── 文件助理 ──
    case 'pdf_log':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.file,
        content: msg.pdf_name
          ? `[${msg.pdf_name}] ${msg.message}`
          : msg.message,
      }

    case 'ocr_done':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.file,
        content: `✅「${msg.pdf_name}」解析完成`,
      }

    case 'task_done':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.file,
        content: msg.result === 1
          ? '✅ 招标文件处理完毕，即将自动提取条款列表…'
          : '❌ 招标文件处理失败',
      }

    case 'pdf_progress':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.file,
        content: `正在处理第 ${msg.current}/${msg.total} 个投标文件：${msg.pdf_name}`,
        extra: {
          type: 'progress',
          data: { current: msg.current, total: msg.total, name: msg.pdf_name },
        },
      }

    case 'all_pdfs_done':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.file,
        content: `✅ 全部 ${msg.total} 个投标文件处理完成（成功 ${msg.success} 个）`,
      }

    // ── 条款助理 ──
    case 'clause_list_log':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.clause,
        content: msg.message,
      }

    case 'clause_list_result':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.clause,
        content: msg.data.length > 0
          ? `✅ 已提取 ${msg.data.length} 条评审条款，请在右侧面板查看和编辑`
          : '⚠️ 未能提取到评审条款，请检查招标文件内容',
        extra: msg.data.length > 0
          ? { type: 'clause_table', data: msg.data }
          : undefined,
      }

    case 'clause_list_done':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.clause,
        content: '条款列表提取完成，请上传投标文件继续评审',
      }

    // ── AI 评审专家 ──
    case 'analysis_clause_log':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.scorer,
        content: msg.message,
      }

    case 'analysis_clause_result': {
      if (msg.data) {
        return {
          id, timestamp,
          identity: CHAT_IDENTITIES.scorer,
          content: `评审完成，得分：${msg.data.打分}`,
          extra: { type: 'score_card', data: msg.data },
        }
      }
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.scorer,
        content: '❌ 未能产出有效评审结果，已标记为「未评审」',
      }
    }

    case 'analysis_clause_done':
      // 不单独展示气泡，由 analysis_clause_result 已覆盖
      // 仅用于串行调度器的流程控制
      return null

    // ── 系统警告 ──
    case 'error':
      return {
        id, timestamp,
        identity: CHAT_IDENTITIES.error,
        content: msg.message,
      }

    default:
      return null
  }
}
```

### 消息分发器（聊天版）

替换原有的 `handleWsMessage`，在分发业务逻辑的同时将消息追加到聊天列表：

```typescript
function handleWsMessage(msg: any) {
  // 1. 转换为聊天消息并追加到列表
  const chatMsg = wsMessageToChatMessage(msg)
  if (chatMsg) {
    appState.chatMessages.push(chatMsg)
    scrollToBottom()  // 自动滚动到最新消息
  }

  // 2. 业务逻辑处理（数据缓存、状态流转）
  switch (msg.type) {
    case 'ocr_done':
      if (appState.currentStep === 'TENDER_UPLOADING') {
        appState.tenderFolderPath = msg.parent_dir
      } else if (appState.currentStep === 'BIDS_UPLOADING') {
        appState.bidFolders.set(msg.pdf_name, msg.parent_dir)
      }
      break

    case 'task_done':
      if (msg.result === 1) {
        appState.currentStep = 'TENDER_DONE'
        autoTriggerClauseExtraction()
      }
      break

    case 'clause_list_result':
      appState.clauseList = msg.data
      break

    case 'clause_list_done':
      appState.currentStep = 'CLAUSE_READY'
      break

    case 'all_pdfs_done':
      appState.currentStep = 'BIDS_DONE'
      break

    case 'analysis_clause_result':
      latestAnalysisResult = msg.data
      break
  }
}
```

### 用户操作也生成聊天气泡

用户的关键操作需要以「我」的身份插入聊天流：

```typescript
// Step 1 验证成功时
function onModelVerified(taskId: string) {
  appState.chatMessages.push({
    id: generateId(),
    timestamp: Date.now(),
    identity: CHAT_IDENTITIES.system,
    content: '🟢 大模型连接验证成功，WebSocket 已建立',
  })
}

// Step 2 用户上传招标文件时
function onTenderFileSelected(file: File) {
  appState.chatMessages.push({
    id: generateId(),
    timestamp: Date.now(),
    identity: CHAT_IDENTITIES.user,
    content: `📎 已上传招标文件：${file.name}`,
    extra: { type: 'file_upload', data: { files: [file.name] } },
  })
}

// Step 4 用户上传投标文件时
function onBidFilesSelected(files: File[]) {
  const names = files.map(f => f.name)
  appState.chatMessages.push({
    id: generateId(),
    timestamp: Date.now(),
    identity: CHAT_IDENTITIES.user,
    content: `📎 已上传 ${files.length} 个投标文件：\n${names.map(n => `· ${n}`).join('\n')}`,
    extra: { type: 'file_upload', data: { files: names } },
  })
}
```

### 前端全局状态（完整版）

```typescript
interface AppState {
  // ── Step 1: 模型配置（必须持久化，所有接口复用） ──
  taskId: string | null
  baseUrl: string          // 大模型 API 基础地址
  apiToken: string         // API Key
  modelName: string        // 模型名称

  // ── Step 1.5: WebSocket ──
  ws: WebSocket | null
  wsConnected: boolean

  // ── Step 2: 招标文件 ──
  tenderFileName: string | null      // 招标文件原始文件名
  tenderFolderPath: string | null    // 招标文件 OCR 输出目录（从 ocr_done.parent_dir 获取）

  // ── Step 3: 条款列表 ──
  clauseList: Array<{
    条款描述: string
    评分标准: string
    其他要求: string
  }>

  // ── Step 4: 投标文件（文件名与工作目录一一对应） ──
  bidFolders: Map<string, string>
  // key:   投标文件原始文件名 (pdf_name)，如 "投标文件A.pdf"
  // value: OCR 输出目录绝对路径 (parent_dir)，如 "/basedir/temp/投标文件A_abc123"
  //
  // 示例:
  //   "投标文件A.pdf" → "/basedir/temp/投标文件A_abc123"
  //   "投标文件B.pdf" → "/basedir/temp/投标文件B_abc123"
  //   "投标文件C.pdf" → "/basedir/temp/投标文件C_abc123"
  //
  // ⚠️ 该映射由 ocr_done 消息逐条构建：
  //   msg.pdf_name → msg.parent_dir
  //   后续 analysis-clause 接口的 folder_path 参数从此处取值

  // ── Step 5: 打分结果矩阵 ──
  scoreMatrix: Array<{
    bidName: string        // 投标文件名（与 bidFolders 的 key 一致）
    clauseIndex: number    // 条款在 clauseList 中的索引
    data: {
      本地条款摘录: string
      打分: string
      思考过程: string
    } | null               // null 表示打分失败
  }>

  // ── UI 状态 ──
  currentStep: 'INIT' | 'MODEL_VERIFIED' | 'TENDER_UPLOADING'
    | 'TENDER_DONE' | 'CLAUSE_EXTRACTING' | 'CLAUSE_READY'
    | 'BIDS_UPLOADING' | 'BIDS_DONE' | 'SCORING' | 'COMPLETED'

  // ── 聊天消息列表 ──
  chatMessages: ChatMessage[]
}
```

### 关键数据流转总结

下表说明每个接口调用时，参数从全局状态的哪个字段取值：

| 接口 | 参数 | 取值来源 |
|------|------|---------|
| `verify-model` | `base_url`, `api_token`, `model_name` | 用户输入 → 存入 `appState.baseUrl` 等 |
| `ws/{taskId}` | `taskId` | `appState.taskId`（verify-model 返回） |
| `upload-pdf` | `task_id` | `appState.taskId` |
| | `base_url`, `api_token`, `model_name` | `appState.baseUrl` 等 |
| `get-clause-list` | `folder_path` | `appState.tenderFolderPath`（ocr_done 写入） |
| | `task_id` | `appState.taskId` |
| | `base_url`, `api_token`, `model_name` | `appState.baseUrl` 等 |
| `upload-many-pdfs` | `task_id` | `appState.taskId` |
| | `base_url`, `api_token`, `model_name` | `appState.baseUrl` 等 |
| `analysis-clause` | `folder_path` | `appState.bidFolders.get(当前投标文件名)` |
| | `clause_describe` | `appState.clauseList[i].条款描述` |
| | `score_criteria` | `appState.clauseList[i].评分标准` |
| | `other_requirements` | `appState.clauseList[i].其他要求` |
| | `task_id` | `appState.taskId` |
| | `base_url` → `api_token` → `model_name` | `appState.baseUrl` 等 |
