import { useState, useEffect } from 'react'
import type { LLMConfig } from '../types'
import type { ThemeConfig } from '../theme'

interface Props {
  open: boolean
  config: LLMConfig
  onSave: (config: LLMConfig) => void
  onVerified: (taskId: string, config: LLMConfig) => void
  onClose: () => void
  theme?: ThemeConfig
}

export default function ConfigModal({ open, config, onSave, onVerified, onClose, theme }: Props) {
  const [draft, setDraft] = useState<LLMConfig>(config)
  const [showKey, setShowKey] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle')
  const [statusMsg, setStatusMsg] = useState('')

  useEffect(() => { setDraft(config) }, [config])
  useEffect(() => {
    if (open) { setStatus('idle'); setStatusMsg('') }
  }, [open])

  if (!open) return null

  const handleSave = async () => {
    if (!draft.apiToken.trim()) {
      setStatus('error'); setStatusMsg('请输入 API Key'); return
    }
    if (!draft.baseUrl.trim()) {
      setStatus('error'); setStatusMsg('请输入 API Base URL'); return
    }
    if (!draft.modelName.trim()) {
      setStatus('error'); setStatusMsg('请输入模型名称'); return
    }

    setVerifying(true)
    setStatus('idle')
    setStatusMsg('')

    try {
      const res = await fetch('/api/verify-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: draft.baseUrl.trim(),
          api_token: draft.apiToken.trim(),
          model_name: draft.modelName.trim(),
        }),
      })

      const data = await res.json()

      if (data.code === 1) {
        setStatus('success')
        setStatusMsg('大模型验证成功')
        onSave(draft)
        onVerified(data.taskId || data.task_id, draft)
        setTimeout(onClose, 800)
      } else {
        setStatus('error')
        setStatusMsg(data.message || '大模型连接失败，请检查配置')
      }
    } catch (err) {
      setStatus('error')
      setStatusMsg(err instanceof Error ? err.message : '网络请求失败')
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div
        className="relative w-full max-w-md mx-4 p-6"
        style={{
          backgroundColor: theme?.colors.cardBg ?? '#ffffff',
          borderRadius: theme?.borderRadius.xl ?? '12px',
          boxShadow: theme?.shadow.lg ?? '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          fontFamily: theme?.fontFamily,
        }}
      >
        <div className="flex items-center justify-between mb-5">
          <h2
            className="text-lg font-semibold"
            style={{ color: theme?.colors.textPrimary ?? '#111827' }}
          >
            模型配置
          </h2>
          <button
            type="button"
            onClick={onClose}
            style={{ color: theme?.colors.textMuted ?? '#9ca3af' }}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label
              className="block text-sm font-medium mb-1"
              style={{ color: theme?.colors.textSecondary ?? '#374151' }}
            >
              API Base URL
            </label>
            <input
              type="text"
              className="w-full px-3 py-2 text-sm focus:outline-none transition-colors"
              placeholder="https://api.deepseek.com/v1"
              value={draft.baseUrl}
              onChange={e => setDraft({ ...draft, baseUrl: e.target.value })}
              style={{
                border: `1px solid ${theme?.colors.inputBorder ?? '#d1d5db'}`,
                borderRadius: theme?.borderRadius.md ?? '6px',
                backgroundColor: theme?.colors.inputBg ?? '#ffffff',
                color: theme?.colors.textPrimary ?? '#111827',
              }}
              onFocus={e => { e.target.style.borderColor = theme?.colors.inputFocusBorder ?? '#3b82f6' }}
              onBlur={e => { e.target.style.borderColor = theme?.colors.inputBorder ?? '#d1d5db' }}
            />
          </div>
          <div>
            <label
              className="block text-sm font-medium mb-1"
              style={{ color: theme?.colors.textSecondary ?? '#374151' }}
            >
              API Key
            </label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                className="w-full px-3 py-2 pr-10 text-sm focus:outline-none transition-colors"
                placeholder="sk-..."
                value={draft.apiToken}
                onChange={e => setDraft({ ...draft, apiToken: e.target.value })}
                style={{
                  border: `1px solid ${theme?.colors.inputBorder ?? '#d1d5db'}`,
                  borderRadius: theme?.borderRadius.md ?? '6px',
                  backgroundColor: theme?.colors.inputBg ?? '#ffffff',
                  color: theme?.colors.textPrimary ?? '#111827',
                }}
                onFocus={e => { e.target.style.borderColor = theme?.colors.inputFocusBorder ?? '#3b82f6' }}
                onBlur={e => { e.target.style.borderColor = theme?.colors.inputBorder ?? '#d1d5db' }}
              />
              <button
                type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2"
                style={{ color: theme?.colors.textMuted ?? '#9ca3af' }}
                onClick={() => setShowKey(!showKey)}
              >
                {showKey ? (
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.98 8.223A10.477 10.477 0 001.934 12c1.292 4.338 5.31 7.5 10.066 7.5.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                )}
              </button>
            </div>
          </div>
          <div>
            <label
              className="block text-sm font-medium mb-1"
              style={{ color: theme?.colors.textSecondary ?? '#374151' }}
            >
              模型名称
            </label>
            <input
              type="text"
              className="w-full px-3 py-2 text-sm focus:outline-none transition-colors"
              placeholder="deepseek-chat"
              value={draft.modelName}
              onChange={e => setDraft({ ...draft, modelName: e.target.value })}
              style={{
                border: `1px solid ${theme?.colors.inputBorder ?? '#d1d5db'}`,
                borderRadius: theme?.borderRadius.md ?? '6px',
                backgroundColor: theme?.colors.inputBg ?? '#ffffff',
                color: theme?.colors.textPrimary ?? '#111827',
              }}
              onFocus={e => { e.target.style.borderColor = theme?.colors.inputFocusBorder ?? '#3b82f6' }}
              onBlur={e => { e.target.style.borderColor = theme?.colors.inputBorder ?? '#d1d5db' }}
            />
          </div>
        </div>

        {/* Status message */}
        {status !== 'idle' && (
          <div
            className="mt-4 px-3 py-2 text-sm"
            style={{
              borderRadius: theme?.borderRadius.md ?? '6px',
              backgroundColor: status === 'success' ? '#f0fdf4' : '#fef2f2',
              color: status === 'success' ? '#15803d' : '#b91c1c',
            }}
          >
            {status === 'success' ? '✅' : '❌'} {statusMsg}
          </div>
        )}

        <div className="flex justify-end gap-3 mt-6">
          <button
            type="button"
            className="px-4 py-2 text-sm transition-colors"
            style={{
              color: theme?.colors.textSecondary ?? '#374151',
              border: `1px solid ${theme?.colors.inputBorder ?? '#d1d5db'}`,
              borderRadius: theme?.borderRadius.md ?? '6px',
            }}
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className="px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            style={{
              backgroundColor: theme?.colors.buttonBg ?? '#2563eb',
              color: theme?.colors.buttonText ?? '#ffffff',
              borderRadius: theme?.borderRadius.md ?? '6px',
            }}
            onClick={handleSave}
            disabled={verifying}
          >
            {verifying && (
              <svg className="animate-spin h-4 w-4" style={{ color: theme?.colors.buttonText ?? '#ffffff' }} fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
            {verifying ? '验证中...' : '验证并保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
