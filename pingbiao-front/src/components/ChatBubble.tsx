import type { ChatMessage } from '../types'
import type { ThemeConfig } from '../theme'

interface Props {
  message: ChatMessage
  theme?: ThemeConfig
}

export default function ChatBubble({ message, theme }: Props) {
  const { identity, content, extra } = message
  const isUser = identity.id === 'user'

  // Resolve colors: use theme overrides if available, otherwise fall back to identity defaults
  const chatOverride = theme?.chatIdentities?.[identity.id as keyof ThemeConfig['chatIdentities']]
  const bubbleColor = chatOverride?.bubbleColor ?? identity.bubbleColor
  const textColor = chatOverride?.textColor ?? identity.textColor

  return (
    <div className={`flex gap-3 mb-4 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className="w-9 h-9 flex items-center justify-center text-lg shrink-0"
        style={{
          backgroundColor: bubbleColor,
          borderRadius: theme?.borderRadius.lg ?? '9999px',
        }}
      >
        {identity.avatar}
      </div>

      {/* Bubble */}
      <div className={`max-w-[75%] ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        <span
          className="text-xs mb-1 px-1"
          style={{ color: theme?.colors.textMuted ?? '#9ca3af' }}
        >
          {identity.name}
        </span>
        <div
          className="px-4 py-2.5 text-sm leading-relaxed"
          style={{
            backgroundColor: bubbleColor,
            color: textColor,
            borderRadius: theme?.borderRadius.lg ?? '12px',
            boxShadow: theme?.shadow.sm ?? '0 1px 2px rgba(0,0,0,0.05)',
            border: `1px solid ${theme?.colors.cardBorder ?? '#f3f4f6'}`,
          }}
        >
          {/* Plain text content */}
          <div className="whitespace-pre-wrap">{content}</div>

          {/* Special cards */}
          {extra?.type === 'clause_table' && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr style={{ borderBottom: `1px solid ${textColor}30` }}>
                    <th className="text-left py-1.5 pr-3 font-medium">序号</th>
                    <th className="text-left py-1.5 pr-3 font-medium">条款描述</th>
                    <th className="text-left py-1.5 font-medium">评分标准</th>
                  </tr>
                </thead>
                <tbody>
                  {(extra.data as any[]).slice(0, 5).map((item: any, i: number) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${textColor}15` }}>
                      <td className="py-1.5 pr-3">{i + 1}</td>
                      <td className="py-1.5 pr-3 max-w-[200px] truncate">{item.条款描述}</td>
                      <td className="py-1.5 max-w-[150px] truncate">{item.评分标准}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(extra.data as any[]).length > 5 && (
                <p className="text-xs mt-2 opacity-70">
                  … 共 {(extra.data as any[]).length} 条，请在右侧面板查看完整列表
                </p>
              )}
            </div>
          )}

          {extra?.type === 'score_card' && extra.data && (
            <div className="mt-3 p-3 rounded-lg bg-white/50 text-xs space-y-2">
              <div className="flex items-center gap-2">
                <span className="font-medium">打分：</span>
                <span className="text-lg font-bold">{extra.data.打分}</span>
              </div>
              {extra.data.本地条款摘录 && (
                <div>
                  <span className="font-medium">摘录：</span>
                  <span className="opacity-80">{extra.data.本地条款摘录}</span>
                </div>
              )}
              {extra.data.思考过程 && (
                <details className="cursor-pointer">
                  <summary className="font-medium">思考过程</summary>
                  <p className="mt-1 opacity-80">{extra.data.思考过程}</p>
                </details>
              )}
            </div>
          )}

          {extra?.type === 'debate_card' && extra.data && (
            <div className="mt-3 p-3 rounded-lg bg-white/50 text-xs space-y-2">
              {extra.data.score !== undefined && (
                <div className="flex items-center gap-2">
                  <span className="font-medium">
                    {extra.data.role === 'support' ? '建议得分' : extra.data.role === 'challenge' ? '质疑后得分' : '最终得分'}：
                  </span>
                  <span className="text-lg font-bold">{extra.data.score}</span>
                </div>
              )}
              {extra.data.reason && (
                <div>
                  <span className="font-medium">理由：</span>
                  <span className="opacity-80">{extra.data.reason}</span>
                </div>
              )}
              {extra.data.challenge && (
                <div>
                  <span className="font-medium">质疑内容：</span>
                  <span className="opacity-80">{extra.data.challenge}</span>
                </div>
              )}
            </div>
          )}

          {extra?.type === 'progress' && (
            <div className="mt-2">
              <div className="w-full bg-white/30 rounded-full h-1.5">
                <div
                  className="h-1.5 rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.round((extra.data.current / extra.data.total) * 100)}%`,
                    backgroundColor: textColor,
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
