# Pingbiao-Power 前端开发指南

Pingbiao-Power 评标系统的前端应用，单页 SPA，负责 LLM 配置、文件上传、评审进度与 AI 辩论展示、报告下载。

## 技术栈

- **构建**: Vite
- **框架**: React 18 + TypeScript
- **样式**: Tailwind CSS v4
- **状态**: useState/useReducer（无 Redux 等，单页状态不复杂）

## 快速启动

```bash
cd pingbiao-front
npm install
npm run dev
```

默认访问 `http://localhost:5173`，API 请求通过 Vite proxy 转发到 `http://localhost:8000`。

## 项目结构

```
pingbiao-front/
├── index.html
├── vite.config.ts           # Tailwind 插件 + proxy /api → localhost:8000
├── tsconfig.json
├── package.json
├── src/
│   ├── main.tsx
│   ├── App.tsx              # 主布局，全局状态
│   ├── types.ts             # 类型定义（与后端契约一致）
│   ├── hooks/
│   │   ├── useLocalStorage.ts   # localStorage 读写
│   │   └── useStreamReader.ts   # NDJSON 流式读取（核心）
│   ├── components/
│   │   ├── ConfigPanel.tsx     # LLM 配置区（可折叠）
│   │   ├── UploadPanel.tsx     # 文件上传
│   │   ├── ActionBar.tsx       # 启动评审按钮
│   │   ├── ProgressBar.tsx     # 进度条
│   │   ├── DebatePanel.tsx     # 辩论展示（核心 UI）
│   │   ├── ScoreCard.tsx       # 评分卡片
│   │   ├── ReportPanel.tsx     # 报告下载
│   │   └── ErrorToast.tsx      # 错误提示
│   └── utils/
│       └── stream.ts
└── public/
```

## Vite 配置要点

```ts
// vite.config.ts
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://localhost:8000' }
  }
})
```

## 类型定义（与后端一致）

- **LLMConfig**: `apiBase`, `apiKey`, `model`，存 localStorage key `pingbiao_llm_config`
- **Clause**: `id`, `no`, `desc`, `score`, `weight`, `order`
- **StreamEvent**: 按 `type` 分发，见下表
- **ClauseResult**: `clause_no`, `bid_name`, `score`, `reason`（由 score 事件归档）

### StreamEvent 类型

| type | 关键字段 |
|------|----------|
| `parse_tender_done` | `clauses: Clause[]` |
| `parse_bid_done` | `bid_id`, `file_name` |
| `clause_start` | `clause`, `bid_name` |
| `debate` | `role`(support/challenge), `content`（字符串） |
| `score` | `clause_no`, `bid_name`, `score`, `reason` |
| `clause_end` | — |
| `report` | `html` |
| `error` | `error?`, `message` |

## 核心流程

1. **ConfigPanel** → 配置 LLM，保存到 localStorage
2. **UploadPanel** → 选择招标 PDF（1 个）、投标 PDF（≥1 个）
3. **ActionBar** → 点击「启动评审」，组装 FormData 调用 `POST /api/run`
4. **useStreamReader** → 读取 NDJSON 流，按 type 分发事件
5. **DebatePanel** → 展示 clause_start、debate、score、clause_end
6. **ReportPanel** → 收到 report 后显示下载按钮，Blob URL 新窗口打开 HTML

## 开发参考

- **详细开发步骤**: 见项目根目录 `docs/front.md`，按 Step 1～12 顺序实现
- **前后端契约**: 见 `docs/前后端对接检查报告.md`
- **产品 Spec**: 见 `docs/pingbiao.md` 第 12 节

## 约定与注意点

1. **debate content**: 后端保证为字符串，前端直接追加展示，无需解析 JSON
2. **clause_start**: 含完整 `clause` 和 `bid_name`，用于展示当前评审上下文
3. **文件校验**: 前端 `accept=".pdf"`，非 PDF 拦截；后端也会校验，返回 400 时 ErrorToast 展示 `message`
4. **响应式**: 辩论区移动端改为上下排列（支持方上、质疑方下）
5. **进度计算**: `parse_tender_done` 得总条款数，`clause_end` 计数，进度 = 已完成 / (条款数 × 投标数)
