import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../types'
import type { ThemeConfig } from '../theme'
import ChatBubble from './ChatBubble'

interface Props {
  messages: ChatMessage[]
  theme?: ThemeConfig
}

export default function ChatPanel({ messages, theme }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-1">
      {messages.length === 0 ? (
        <div className="flex items-center justify-center h-full text-sm" style={{ color: theme?.colors.textMuted ?? '#9ca3af' }}>
          <div className="text-center">
            <svg
              className="w-16 h-16 mx-auto mb-3 opacity-30"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <p>配置模型后开始评标流程</p>
          </div>
        </div>
      ) : (
        <>
          {messages.map(msg => (
            <ChatBubble key={msg.id} message={msg} theme={theme} />
          ))}
          <div ref={bottomRef} />
        </>
      )}
    </div>
  )
}
