# Pingbiao-Power 前端开发计划

## 技术栈

- Vite + React 18 + TypeScript
- Tailwind CSS v4
- 无状态管理库，用 React useState/useReducer（单页面，状态不复杂）

---

## 前端交互流程（核心）

```
1. 用户点击「启动评审」→ 调用 POST /api/run
   └─ 解析 NDJSON 流，收集 clauses、session_id、bid 列表

2. 前端展示条款列表（ClauseListPanel）
   └─ 将 parse_tender_done 返回的 clauses 展示给用户

3. 等待 3 秒

4. 前端逐个调用 POST /api/clause（输入：条款名称、打分要求）
   └─ 每个条款调用一次，输出：AI 对每个投标文件的打分结果

5. 前端展示打分结果（ScoreCard）
   └─ 每收到一个 /api/clause 的响应，立即展示该条款的 scores

6. 重复 4～5，直到所有条款全部评审完成
```

---

## 项目结构

```
frontend/
├── index.html
├── vite.config.ts              # proxy /api → localhost:8000
├── tsconfig.json
├── package.json
├── src/
│   ├── main.tsx                # 入口
│   ├── App.tsx                 # 主布局，管理全局状态
│   ├── types.ts                # 类型定义
│   ├── hooks/
│   │   ├── useLocalStorage.ts  # localStorage 读写 hook
│   │   └── useStreamReader.ts  # NDJSON 流式读取 hook（/api/run 用）
│   ├── components/
│   │   ├── ConfigPanel.tsx     # LLM 配置区（可折叠）
│   │   ├── UploadPanel.tsx     # 文件上传区
│   │   ├── ActionBar.tsx       # 启动评审按钮
│   │   ├── ProgressBar.tsx     # 整体进度条
│   │   ├── ClauseListPanel.tsx # 条款列表展示区（核心 UI）
│   │   ├── ScoreCard.tsx       # 单条款评分卡片
│   │   ├── ReportPanel.tsx     # 报告下载区（可选）
│   │   └── ErrorToast.tsx      # 错误提示
│   └── utils/
│       └── stream.ts           # fetch + ReadableStream 工具函数
└── public/
```

---

## 开发步骤

### Step 1: 项目初始化

**目标**: 空白页面跑通，工具链正常

**任务**:
1. `npm create vite@latest frontend -- --template react-ts`
2. 安装 Tailwind CSS v4: `npm install -D tailwindcss @tailwindcss/vite`
3. 配置 `vite.config.ts`：添加 Tailwind 插件 + API 代理
4. 清理模板代码，`npm run dev` 确认启动正常

**vite.config.ts 关键配置**:
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://localhost:8000' }
  }
})
```

**产出**: 可访问 `http://localhost:5173` 的空白 React 页面

---

### Step 2: 类型定义

**目标**: 定义前后端共享的数据结构，后续所有组件基于此开发

**文件**: `src/types.ts`

```ts
// LLM 配置（存 localStorage）
export interface LLMConfig {
  apiBase: string   // 默认 https://api.openai.com/v1
  apiKey: string
  model: string     // 默认 gpt-4o
}

// 评审条款
export interface Clause {
  id: string; no: string; desc: string
  score: number; weight: number; order: number
}

// /api/run 流式事件（NDJSON 每行一个）
export type StreamEvent =
  | { type: 'parse_tender_done'; session_id: string; clauses: Clause[] }
  | { type: 'parse_bid_done'; bid_id: string; file_name: string }
  | { type: 'error'; error?: string; message: string }

// /api/clause 返回的单个投标打分
export interface ClauseScore {
  bid_id: string; bid_name: string; score: number; reason: string
}

// /api/clause 响应
export interface ClauseReviewResponse {
  clause_id: string; clause_no: string; scores: ClauseScore[]
}

// 单条款评审结果（前端汇总展示用）
export interface ClauseResult {
  clause_id: string; clause_no: string; scores: ClauseScore[]
}

// 应用阶段
export type AppPhase = 'config' | 'uploading' | 'parsing' | 'clauses_ready' | 'evaluating' | 'done'
```

**产出**: 全局类型文件，0 运行时代码

---

### Step 3: 通用 Hooks

**目标**: 封装 localStorage 和 NDJSON 流读取

#### 3a. useLocalStorage

**文件**: `src/hooks/useLocalStorage.ts`
- 泛型 hook，读写 localStorage，JSON 序列化
- 用于保存 LLM 配置（key: `pingbiao_llm_config`）

#### 3b. useStreamReader

**文件**: `src/hooks/useStreamReader.ts`

**用途**: 解析 `/api/run` 返回的 NDJSON 流

功能：
1. 接收 fetch 返回的 Response
2. 用 ReadableStream + TextDecoder 逐行读取
3. 每行 JSON.parse 为 StreamEvent（parse_tender_done / parse_bid_done / error）
4. 通过回调通知组件
5. 处理连接中断、解析错误

关键实现思路：
```ts
const reader = response.body!.getReader()
const decoder = new TextDecoder()
let buffer = ''
while (true) {
  const { done, value } = await reader.read()
  if (done) break
  buffer += decoder.decode(value, { stream: true })
  const lines = buffer.split('\n')
  buffer = lines.pop()!  // 最后一行可能不完整
  for (const line of lines) {
    if (line.trim()) onEvent(JSON.parse(line))
  }
}
```

**产出**: 两个可复用 hook

---

### Step 4: ConfigPanel — LLM 配置区

**目标**: 用户配置大模型连接信息，持久化到 localStorage

**文件**: `src/components/ConfigPanel.tsx`

**UI**:
- 可折叠面板（默认展开，配置完成后可收起）
- 三个输入框：API Base URL / API Key（password）/ 模型名称
- 底部「保存配置」按钮
- 页面加载时从 localStorage 回填

**交互**:
- API Base placeholder: `https://api.openai.com/v1`
- Model placeholder: `gpt-4o`
- 保存时校验 API Key 非空

---

### Step 5: UploadPanel — 文件上传区

**目标**: 上传招标文件（单 PDF）和投标文件（多 PDF）

**文件**: `src/components/UploadPanel.tsx`

**UI**:
- 两个上传区域，左右排列
- 招标文件：单文件，`accept=".pdf"`，拖拽或点击
- 投标文件：多文件，`accept=".pdf"`，拖拽或点击
- 已选文件显示文件名列表，支持单个移除

**校验**:
- 仅 .pdf 文件
- 招标文件必须 1 个，投标文件至少 1 个

**状态上报**: 通过 props 回调传 `tenderFile` 和 `bidFiles` 给 App

---

### Step 6: ActionBar — 启动评审

**目标**: 触发解析流程，调用 `/api/run`，将响应交给流式读取处理

**文件**: `src/components/ActionBar.tsx`

**UI**: 单个按钮「启动评审」，点击后 disabled + loading

**核心逻辑**:
```ts
const formData = new FormData()
formData.append('tender_file', tenderFile)
bidFiles.forEach(f => formData.append('bid_files', f))
formData.append('api_base', config.apiBase)
formData.append('api_key', config.apiKey)
formData.append('model', config.model)
const res = await fetch('/api/run', { method: 'POST', body: formData })
// 将 res 交给 useStreamReader 处理，解析 parse_tender_done / parse_bid_done / error
```

**校验**: 配置已保存 + 招标文件已选 + 投标文件已选

**说明**: 本步骤仅负责调用 `/api/run`。条款列表展示、等待 3 秒、逐个调用 `/api/clause` 等逻辑在 App.tsx 中编排。

---

### Step 7: ClauseListPanel — 条款列表展示区（核心 UI）

**目标**: 展示 `/api/run` 返回的招标文件条款列表，供用户确认后进入评审

**文件**: `src/components/ClauseListPanel.tsx`

**UI 布局**:
- 标题：「评审条款列表」
- 列表：每个条款一张卡片或一行
  - 条款编号（no）
  - 条款描述（desc，含条款名称和打分要求）
  - 满分值（score）
  - 可选：评审状态（待评审 / 评审中 / 已完成）

**数据来源**: 由 App 传入 `clauses: Clause[]`（来自 `parse_tender_done`）

**显示时机**: `phase === 'clauses_ready'` 或 `phase === 'evaluating'` 时展示；`evaluating` 时可高亮当前评审中的条款

---

### Step 8: ScoreCard — 评分汇总

**目标**: 展示 `/api/clause` 返回的每个条款的打分结果

**文件**: `src/components/ScoreCard.tsx`

**UI**: 卡片列表，每个已评审条款一张卡片（ClauseResult：clause_id, clause_no, scores）
- 每张卡片显示：条款编号、该条款下每个投标的得分（bid_name、score、reason）
- 按条款分组，或按投标分组均可
- 每收到一个 `/api/clause` 响应，立即追加展示

---

### Step 9: ReportPanel — 报告下载（可选）

**目标**: 所有条款评审完成后，提供报告下载或汇总展示

**文件**: `src/components/ReportPanel.tsx`

**UI**: `phase === 'done'` 时显示「下载评标报告」或「查看汇总」按钮

**实现**: 若后端提供 `/api/report`，可调用获取 HTML；否则前端根据已收集的 `ClauseResult[]` 生成简易 HTML 或表格汇总，用 Blob URL 在新窗口打开：
```ts
const blob = new Blob([reportHtml], { type: 'text/html' })
window.open(URL.createObjectURL(blob), '_blank')
```

---

### Step 10: ErrorToast — 错误处理

**目标**: 统一错误提示

**文件**: `src/components/ErrorToast.tsx`

**场景**:
- 非 PDF 文件 → 前端拦截
- `/api/run` 流中 `{ type: "error", message, error? }` → Toast 展示 message
- `/api/clause` 调用失败（HTTP 4xx/5xx 或 JSON 解析错误）→ Toast 展示错误信息
- 网络中断 → 提示连接失败

**UI**: 右上角浮动 Toast，3 秒自动消失

---

### Step 11: App.tsx 状态编排

**目标**: App 层管理全局状态，串联所有组件，实现完整交互流程

**状态设计**:
```ts
const [phase, setPhase] = useState<AppPhase>('config')
const [config, setConfig] = useLocalStorage<LLMConfig>(...)
const [tenderFile, setTenderFile] = useState<File | null>(null)
const [bidFiles, setBidFiles] = useState<File[]>([])
const [clauses, setClauses] = useState<Clause[]>([])
const [sessionId, setSessionId] = useState<string | null>(null)
const [results, setResults] = useState<ClauseResult[]>([])
const [currentClauseIndex, setCurrentClauseIndex] = useState(0)  // 当前评审到第几条
const [error, setError] = useState('')
```

**核心流程编排**:
```ts
// 1. 用户点击「启动评审」→ 调用 /api/run，useStreamReader 解析流
// 2. 收到 parse_tender_done：
//    setClauses(event.clauses)
//    setSessionId(event.session_id)
//    setPhase('clauses_ready')
//    → 前端展示条款列表（ClauseListPanel）
// 3. useEffect：当 phase === 'clauses_ready' 时，setTimeout 3 秒后：
//    setPhase('evaluating')
//    启动逐个调用 /api/clause 的循环
// 4. 逐个调用 /api/clause（for 循环或递归）：
for (let i = 0; i < clauses.length; i++) {
  const res = await fetch('/api/clause', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      clause: clauses[i],
      api_base: config.apiBase,
      api_key: config.apiKey,
      model: config.model,
    }),
  })
  const data: ClauseReviewResponse = await res.json()
  setResults(prev => [...prev, { clause_id: data.clause_id, clause_no: data.clause_no, scores: data.scores }])
  setCurrentClauseIndex(i + 1)
}
// 5. 全部完成后
setPhase('done')
```

**页面布局**:
```
┌─────────────────────────────┐
│ ConfigPanel（可折叠）         │
├─────────────────────────────┤
│ UploadPanel                 │
├─────────────────────────────┤
│ ActionBar                   │
├─────────────────────────────┤
│ ProgressBar                 │
├─────────────────────────────┤
│ ClauseListPanel             │  ← 条款列表展示
├─────────────────────────────┤
│ ScoreCard 打分结果列表       │  ← 逐个展示 /api/clause 返回的 scores
├─────────────────────────────┤
│ ReportPanel                 │
└─────────────────────────────┘
```

---

### Step 12: UI 打磨与收尾

**任务**:
1. 响应式布局 — 移动端条款列表、评分卡片改为上下排列
2. 加载状态 — 按钮 spinner、条款评审中的 loading 态
3. 空状态 — 未上传时的引导提示
4. 进度条 — 总条款数来自 `clauses.length`，已完成数来自 `results.length`，进度 = results.length / clauses.length
5. 等待 3 秒 — 可在条款列表展示后显示倒计时「3 秒后开始评审…」

---

## 开发顺序总结

| 顺序 | Step | 组件 | 依赖 | 可独立开发 |
|------|------|------|------|-----------|
| 1 | Step 1 | 项目初始化 | 无 | ✅ |
| 2 | Step 2 | types.ts | 无 | ✅ |
| 3 | Step 3 | hooks | Step 2 | ✅ |
| 4 | Step 4 | ConfigPanel | Step 3a | ✅ |
| 5 | Step 5 | UploadPanel | Step 2 | ✅ |
| 6 | Step 6 | ActionBar | Step 3-5 | 需后端或 mock |
| 7 | Step 7 | ClauseListPanel | Step 2 | ✅ |
| 8 | Step 8 | ScoreCard | Step 2 | ✅ |
| 9 | Step 9 | ReportPanel | Step 2 | ✅ |
| 10 | Step 10 | ErrorToast | 无 | ✅ |
| 11 | Step 11 | App.tsx 编排 | 全部 | 最后集成 |
| 12 | Step 12 | UI 打磨 | Step 11 | 最后 |

> Step 4/5/7/8/9/10 互相无依赖，可并行开发。Step 6 和 Step 11 是集成点。
