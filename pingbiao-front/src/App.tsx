import { useState, useCallback, useRef } from 'react'
import { useLocalStorage } from './hooks/useLocalStorage'
import { useWebSocket } from './hooks/useWebSocket'
import { useTheme } from './hooks/useTheme'
import type {
  LLMConfig, AppStep, ClauseItem, ScoreResult,
  ChatMessage, WsMessage, CompletedPdf,
} from './types'
import { CHAT_IDENTITIES } from './types'
import ConfigModal from './components/ConfigModal'
import ChatPanel from './components/ChatPanel'
import Sidebar from './components/Sidebar'
import ErrorToast from './components/ErrorToast'
import ThemeSwitcher from './components/ThemeSwitcher'

const DEFAULT_CONFIG: LLMConfig = {
  baseUrl: '',
  apiToken: '',
  modelName: '',
}

function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function App() {
  // Theme
  const { theme, themeKey, setTheme } = useTheme()

  // Global state
  const [config, setConfig] = useLocalStorage<LLMConfig>('pingbiao_llm_config', DEFAULT_CONFIG)
  const [showConfig, setShowConfig] = useState(false)
  const [error, setError] = useState('')

  // App state
  const [taskId, setTaskId] = useState<string | null>(null)
  const [currentStep, setCurrentStep] = useState<AppStep>('INIT')
  const [wsConnected, setWsConnected] = useState(false)

  // Step 2: Tender file
  const [tenderFile, setTenderFile] = useState<File | null>(null)
  const [, setTenderFolderPath] = useState<string | null>(null)

  // Step 3: Clause list
  const [clauseList, setClauseList] = useState<ClauseItem[]>([])
  const clauseListRef = useRef<ClauseItem[]>([])

  // Step 4: Bid files
  const [bidFiles, setBidFiles] = useState<File[]>([])

  // Step 5: Score matrix
  const [scoreMatrix, setScoreMatrix] = useState<ScoreResult[]>([])
  const latestAnalysisResultRef = useRef<any>(null)

  // Chat messages
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])

  // Ref to hold latest triggerScoring (avoids declaration-order issue with useCallback)
  const triggerScoringRef = useRef<(pdfs: CompletedPdf[]) => void>(() => {})

  const isConfigured = !!config.apiToken && !!config.baseUrl && !!config.modelName

  // Add chat message helper
  const addChatMessage = useCallback((identity: any, content: string, extra?: any) => {
    const msg: ChatMessage = {
      id: generateId(),
      identity,
      content,
      timestamp: Date.now(),
      extra,
    }
    setChatMessages(prev => [...prev, msg])
  }, [])

  // WebSocket message handler
  const handleWsMessage = useCallback((msg: WsMessage) => {
    // Convert WS message to chat message
    let chatMsg: ChatMessage | null = null

    switch (msg.type) {
      case 'pdf_log':
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.file,
          content: msg.pdf_name ? `[${msg.pdf_name}] ${msg.message}` : msg.message || '',
        }
        break

      case 'ocr_done':
        if (currentStep === 'TENDER_UPLOADING') {
          setTenderFolderPath(msg.parent_dir || null)
        }
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.file,
          content: `✅「${msg.pdf_name}」解析完成`,
        }
        break

      case 'task_done':
        if (msg.result === 1) {
          setCurrentStep('CLAUSE_EXTRACTING')
          chatMsg = {
            id: generateId(),
            timestamp: Date.now(),
            identity: CHAT_IDENTITIES.file,
            content: '✅ 招标文件处理完毕，正在提取条款列表…',
          }
        } else {
          chatMsg = {
            id: generateId(),
            timestamp: Date.now(),
            identity: CHAT_IDENTITIES.file,
            content: '❌ 招标文件处理失败',
          }
        }
        break

      case 'clause_list_log':
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.clause,
          content: msg.message || '',
        }
        break

      case 'clause_list_result':
        setClauseList(msg.data || [])
        clauseListRef.current = msg.data || []
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.clause,
          content: msg.data && msg.data.length > 0
            ? `✅ 已提取 ${msg.data.length} 条评审条款，请在右侧面板查看和编辑`
            : '⚠️ 未能提取到评审条款，请检查招标文件内容',
          extra: msg.data && msg.data.length > 0
            ? { type: 'clause_table', data: msg.data }
            : undefined,
        }
        break

      case 'clause_list_done':
        setCurrentStep('CLAUSE_READY')
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.clause,
          content: '条款列表提取完成，请上传投标文件继续评审',
        }
        break

      case 'pdf_progress':
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.file,
          content: `正在处理第 ${msg.current}/${msg.total} 个投标文件：${msg.pdf_name}`,
          extra: {
            type: 'progress',
            data: { current: msg.current, total: msg.total, name: msg.pdf_name },
          },
        }
        break

      case 'all_pdfs_done':
        setCurrentStep('BIDS_DONE')
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.file,
          content: `✅ 全部 ${msg.total} 个投标文件处理完成（成功 ${msg.success} 个）`,
        }
        // Auto trigger Step 5 using completed_pdfs from the message
        if (msg.completed_pdfs && msg.completed_pdfs.length > 0) {
          const pdfs = msg.completed_pdfs
          setTimeout(() => {
            triggerScoringRef.current(pdfs)
          }, 500)
        }
        break

      case 'analysis_clause_log':
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.scorer,
          content: msg.message || '',
        }
        break

      case 'debate_support':
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.support,
          content: msg.content || msg.message || '',
          extra: msg.data ? { type: 'debate_card', data: { role: 'support', score: msg.data.score, reason: msg.data.reason } } : undefined,
        }
        break

      case 'debate_challenge':
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.challenge,
          content: msg.content || msg.message || '',
          extra: msg.data ? { type: 'debate_card', data: { role: 'challenge', score: msg.data.suggested_score, challenge: msg.data.challenge } } : undefined,
        }
        break

      case 'debate_arbitrator':
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.arbitrator,
          content: msg.content || msg.message || '',
          extra: msg.data ? { type: 'debate_card', data: { role: 'arbitrator', score: msg.data.score, reason: msg.data.reason } } : undefined,
        }
        break

      case 'analysis_clause_result':
        latestAnalysisResultRef.current = msg.data
        if (msg.data) {
          chatMsg = {
            id: generateId(),
            timestamp: Date.now(),
            identity: CHAT_IDENTITIES.scorer,
            content: `评审完成，得分：${msg.data.打分}`,
            extra: { type: 'score_card', data: msg.data },
          }
        } else {
          chatMsg = {
            id: generateId(),
            timestamp: Date.now(),
            identity: CHAT_IDENTITIES.scorer,
            content: '❌ 未能产出有效评审结果，已标记为「未评审」',
          }
        }
        break

      case 'error':
        chatMsg = {
          id: generateId(),
          timestamp: Date.now(),
          identity: CHAT_IDENTITIES.error,
          content: msg.message || '发生错误',
        }
        setError(msg.message || '发生错误')
        break
    }

    if (chatMsg) {
      setChatMessages(prev => [...prev, chatMsg!])
    }
  }, [currentStep])

  // WebSocket setup
  const { connect, disconnect: _disconnect, waitForMessage } = useWebSocket({
    onMessage: handleWsMessage,
    onConnected: () => {
      setWsConnected(true)
      addChatMessage(CHAT_IDENTITIES.system, '🟢 WebSocket 连接已建立')
    },
    onDisconnected: () => {
      setWsConnected(false)
    },
  })

  // Step 1: Model verified
  const handleModelVerified = useCallback((newTaskId: string, newConfig: LLMConfig) => {
    setTaskId(newTaskId)
    setConfig(newConfig)
    setCurrentStep('MODEL_VERIFIED')
    addChatMessage(CHAT_IDENTITIES.system, '🟢 大模型连接验证成功')
    // Connect WebSocket
    connect(newTaskId)
  }, [connect, setConfig, addChatMessage])

  // Step 2: Upload tender file
  const handleTenderUpload = useCallback(async () => {
    if (!tenderFile || !taskId) return

    setCurrentStep('TENDER_UPLOADING')
    addChatMessage(CHAT_IDENTITIES.user, `📎 已上传招标文件：${tenderFile.name}`)

    const formData = new FormData()
    formData.append('file', tenderFile)
    formData.append('task_id', taskId)
    formData.append('base_url', config.baseUrl)
    formData.append('api_token', config.apiToken)
    formData.append('model_name', config.modelName)

    try {
      const res = await fetch('/api/upload-pdf', {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      if (data.result !== 1) {
        setError(data.error || '招标文件上传失败')
        setCurrentStep('MODEL_VERIFIED')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '网络请求失败')
      setCurrentStep('MODEL_VERIFIED')
    }
  }, [tenderFile, taskId, config, addChatMessage])

  // Step 3: Backend auto-extracts clauses, frontend just waits for WebSocket message
  // No need to call /api/get-clause-list anymore

  // Step 4: Upload bid files
  const handleBidUpload = useCallback(async () => {
    if (bidFiles.length === 0 || !taskId) return

    setCurrentStep('BIDS_UPLOADING')
    addChatMessage(
      CHAT_IDENTITIES.user,
      `📎 已上传 ${bidFiles.length} 个投标文件：\n${bidFiles.map(f => `· ${f.name}`).join('\n')}`
    )

    const formData = new FormData()
    bidFiles.forEach(f => formData.append('files', f))
    formData.append('task_id', taskId)
    formData.append('base_url', config.baseUrl)
    formData.append('api_token', config.apiToken)
    formData.append('model_name', config.modelName)

    try {
      const res = await fetch('/api/upload-many-pdfs', {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      if (data.result !== 1) {
        setError(data.error || '投标文件上传失败')
        setCurrentStep('CLAUSE_READY')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '网络请求失败')
      setCurrentStep('CLAUSE_READY')
    }
  }, [bidFiles, taskId, config, addChatMessage])

  // Step 5: Serial scoring — receives completed_pdfs directly from all_pdfs_done
  const triggerScoring = useCallback(async (completedPdfs: CompletedPdf[]) => {
    const clauses = clauseListRef.current
    if (clauses.length === 0 || completedPdfs.length === 0 || !taskId) return

    setCurrentStep('SCORING')

    for (const pdf of completedPdfs) {
      for (let i = 0; i < clauses.length; i++) {
        const clause = clauses[i]

        try {
          const res = await fetch('/api/analysis-clause', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              folder_path: pdf.parent_dir,
              clause_describe: clause.条款描述,
              score_criteria: clause.评分标准,
              other_requirements: clause.其他要求 || '',
              task_id: taskId,
              base_url: config.baseUrl,
              api_token: config.apiToken,
              model_name: config.modelName,
            }),
          })

          const httpResult = await res.json()

          if (httpResult.result !== 1) {
            setScoreMatrix(prev => [...prev, { bidName: pdf.pdf_name, clauseIndex: i, data: null }])
            continue
          }

          // Wait for WS message
          await waitForMessage('analysis_clause_done')

          // Save result
          setScoreMatrix(prev => [
            ...prev,
            { bidName: pdf.pdf_name, clauseIndex: i, data: latestAnalysisResultRef.current },
          ])
        } catch (err) {
          console.error('Scoring error:', err)
          setScoreMatrix(prev => [...prev, { bidName: pdf.pdf_name, clauseIndex: i, data: null }])
        }
      }
    }

    setCurrentStep('COMPLETED')
    addChatMessage(CHAT_IDENTITIES.system, '🎉 全部评审完成！')
  }, [taskId, config, waitForMessage, addChatMessage])

  // Keep ref in sync with latest triggerScoring
  triggerScoringRef.current = triggerScoring

  return (
    <div className="h-screen flex flex-col" style={{ backgroundColor: theme.colors.bodyBg }}>
      {/* Top bar */}
      <div
        className="h-14 flex items-center justify-between px-6"
        style={{
          backgroundColor: theme.colors.headerBg,
          borderBottom: `1px solid ${theme.colors.headerBorder}`,
          fontFamily: theme.fontFamily,
        }}
      >
        <h1 className="text-lg font-bold" style={{ color: theme.colors.headerText }}>
          Pingbiao-Power 智能评标系统
        </h1>
        <div className="flex items-center">
          <ThemeSwitcher currentTheme={themeKey} onThemeChange={setTheme} />
          <button
            type="button"
            className="relative p-2 rounded-lg transition-colors"
            style={{ color: theme.colors.textSecondary }}
            onClick={() => setShowConfig(true)}
            title="模型配置"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {isConfigured && wsConnected && (
              <span
                className="absolute top-1 right-1 w-2 h-2 rounded-full"
                style={{ backgroundColor: '#10b981' }}
              />
            )}
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chat area */}
        <div className="flex-1 flex flex-col">
          <ChatPanel messages={chatMessages} theme={theme} />

          {/* Bottom upload controls */}
          <div
            className="p-4"
            style={{
              borderTop: `1px solid ${theme.colors.headerBorder}`,
              backgroundColor: theme.colors.cardBg,
            }}
          >
            {currentStep === 'MODEL_VERIFIED' && (
              <div className="flex gap-3">
                <input
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  id="tender-upload"
                  onChange={e => {
                    const file = e.target.files?.[0]
                    if (file) setTenderFile(file)
                  }}
                />
                <label
                  htmlFor="tender-upload"
                  className="flex-1 px-4 py-2 border-2 border-dashed rounded-lg text-center text-sm cursor-pointer transition-colors"
                  style={{
                    borderColor: tenderFile ? theme.colors.primary : theme.colors.inputBorder,
                    backgroundColor: tenderFile ? `${theme.colors.primary}10` : 'transparent',
                    color: theme.colors.textSecondary,
                    borderRadius: theme.borderRadius.md,
                  }}
                >
                  {tenderFile ? `✅ ${tenderFile.name}` : '📎 选择招标文件'}
                </label>
                <button
                  type="button"
                  className="px-6 py-2 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{
                    backgroundColor: tenderFile ? theme.colors.buttonBg : theme.colors.inputBorder,
                    color: theme.colors.buttonText,
                    borderRadius: theme.borderRadius.md,
                  }}
                  onClick={handleTenderUpload}
                  disabled={!tenderFile}
                >
                  上传招标文件
                </button>
              </div>
            )}

            {currentStep === 'CLAUSE_READY' && (
              <div className="flex gap-3">
                <input
                  type="file"
                  accept=".pdf"
                  multiple
                  className="hidden"
                  id="bid-upload"
                  onChange={e => {
                    const files = Array.from(e.target.files || [])
                    setBidFiles(files)
                  }}
                />
                <label
                  htmlFor="bid-upload"
                  className="flex-1 px-4 py-2 border-2 border-dashed text-center text-sm cursor-pointer transition-colors"
                  style={{
                    borderColor: bidFiles.length > 0 ? theme.colors.primary : theme.colors.inputBorder,
                    backgroundColor: bidFiles.length > 0 ? `${theme.colors.primary}10` : 'transparent',
                    color: theme.colors.textSecondary,
                    borderRadius: theme.borderRadius.md,
                  }}
                >
                  {bidFiles.length > 0 ? `✅ 已选择 ${bidFiles.length} 个文件` : '📎 选择投标文件（可多选）'}
                </label>
                <button
                  type="button"
                  className="px-6 py-2 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{
                    backgroundColor: bidFiles.length > 0 ? theme.colors.buttonBg : theme.colors.inputBorder,
                    color: theme.colors.buttonText,
                    borderRadius: theme.borderRadius.md,
                  }}
                  onClick={handleBidUpload}
                  disabled={bidFiles.length === 0}
                >
                  上传投标文件
                </button>
              </div>
            )}

            {['TENDER_UPLOADING', 'CLAUSE_EXTRACTING', 'BIDS_UPLOADING', 'SCORING'].includes(currentStep) && (
              <div className="text-center text-sm" style={{ color: theme.colors.textMuted }}>
                <svg
                  className="animate-spin h-5 w-5 inline-block mr-2"
                  style={{ color: theme.colors.primary }}
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                处理中，请稍候...
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <Sidebar
          clauseList={clauseList}
          bidFiles={bidFiles.map(f => f.name)}
          scoreMatrix={scoreMatrix}
          theme={theme}
        />
      </div>

      {/* Config modal */}
      <ConfigModal
        open={showConfig}
        config={config}
        onSave={setConfig}
        onVerified={handleModelVerified}
        onClose={() => setShowConfig(false)}
        theme={theme}
      />

      {/* Error toast */}
      {error && <ErrorToast message={error} onClose={() => setError('')} />}
    </div>
  )
}

export default App
