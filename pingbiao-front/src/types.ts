// ── 状态机步骤 ──
export type AppStep =
  | 'INIT'
  | 'MODEL_VERIFIED'
  | 'TENDER_UPLOADING'
  | 'TENDER_DONE'
  | 'CLAUSE_EXTRACTING'
  | 'CLAUSE_READY'
  | 'BIDS_UPLOADING'
  | 'BIDS_DONE'
  | 'SCORING'
  | 'COMPLETED'

// ── LLM 配置（存 localStorage，所有接口复用） ──
export interface LLMConfig {
  baseUrl: string
  apiToken: string
  modelName: string
}

// ── 条款（从 clause_list_result 获取） ──
export interface ClauseItem {
  条款描述: string
  评分标准: string
  其他要求: string
}

// ── 打分结果 ──
export interface ScoreResult {
  bidName: string
  clauseIndex: number
  data: {
    本地条款摘录: string
    打分: string
    思考过程: string
  } | null
}

// ── 聊天身份 ──
export interface ChatIdentity {
  id: string
  name: string
  avatar: string
  bubbleColor: string
  textColor: string
}

export const CHAT_IDENTITIES: Record<string, ChatIdentity> = {
  system: {
    id: 'system',
    name: '系统助理',
    avatar: '🔧',
    bubbleColor: '#E8F5E9',
    textColor: '#2E7D32',
  },
  file: {
    id: 'file',
    name: '文件助理',
    avatar: '📄',
    bubbleColor: '#E3F2FD',
    textColor: '#1565C0',
  },
  clause: {
    id: 'clause',
    name: '条款助理',
    avatar: '📋',
    bubbleColor: '#FFF3E0',
    textColor: '#E65100',
  },
  scorer: {
    id: 'scorer',
    name: 'AI 评审专家',
    avatar: '🧑‍⚖️',
    bubbleColor: '#F3E5F5',
    textColor: '#6A1B9A',
  },
  support: {
    id: 'support',
    name: '支持方 AI',
    avatar: '✅',
    bubbleColor: '#E8F5E9',
    textColor: '#2E7D32',
  },
  challenge: {
    id: 'challenge',
    name: '质疑方 AI',
    avatar: '❓',
    bubbleColor: '#FFF3E0',
    textColor: '#F57C00',
  },
  arbitrator: {
    id: 'arbitrator',
    name: '仲裁方 AI',
    avatar: '⚖️',
    bubbleColor: '#E1F5FE',
    textColor: '#0277BD',
  },
  error: {
    id: 'error',
    name: '系统警告',
    avatar: '⚠️',
    bubbleColor: '#FFEBEE',
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

// ── 聊天消息 ──
export interface ChatMessage {
  id: string
  identity: ChatIdentity
  content: string
  timestamp: number
  extra?: {
    type: 'clause_table' | 'score_card' | 'progress' | 'file_upload' | 'debate_card'
    data: any
  }
}

// ── 投标文件完成信息（all_pdfs_done 事件携带） ──
export interface CompletedPdf {
  pdf_name: string
  parent_dir: string
}

// ── WebSocket 消息（后端推送） ──
export interface WsMessage {
  type: string
  message?: string
  result?: number
  data?: any
  parent_dir?: string
  pdf_name?: string
  current?: number
  total?: number
  success?: number
  error?: string
  completed_pdfs?: CompletedPdf[]
  role?: string  // 新增：用于辩论角色（support/challenge/arbitrator）
  content?: string  // 新增：辩论内容
}

// ── 全局应用状态 ──
export interface AppState {
  taskId: string | null
  baseUrl: string
  apiToken: string
  modelName: string

  ws: WebSocket | null
  wsConnected: boolean

  tenderFileName: string | null
  tenderFolderPath: string | null

  clauseList: ClauseItem[]

  bidFolders: Map<string, string>

  scoreMatrix: ScoreResult[]

  currentStep: AppStep

  chatMessages: ChatMessage[]
}
