import { useRef, useCallback, useEffect } from 'react'
import type { WsMessage } from '../types'

interface UseWebSocketOptions {
  onMessage: (msg: WsMessage) => void
  onConnected?: () => void
  onDisconnected?: () => void
}

export function useWebSocket({ onMessage, onConnected, onDisconnected }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const taskIdRef = useRef<string | null>(null)
  const closedByUserRef = useRef(false)
  const serverRejectedRef = useRef(false)

  const clearHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current)
      heartbeatRef.current = null
    }
  }, [])

  const startHeartbeat = useCallback((ws: WebSocket) => {
    clearHeartbeat()
    heartbeatRef.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'ping' }))
      }
    }, 30000)
  }, [clearHeartbeat])

  const connect = useCallback((taskId: string) => {
    // Close existing connection
    if (wsRef.current) {
      closedByUserRef.current = true
      wsRef.current.close()
    }

    taskIdRef.current = taskId
    closedByUserRef.current = false
    serverRejectedRef.current = false

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/api/ws/${taskId}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({ action: 'ping' }))
      startHeartbeat(ws)
      onConnected?.()
    }

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data)
        if (msg.type === 'pong') return
        // Server rejected this connection — stop reconnecting
        if (msg.type === 'error') {
          serverRejectedRef.current = true
        }
        onMessage(msg)
      } catch {
        console.warn('WS 消息解析失败:', event.data)
      }
    }

    ws.onclose = () => {
      clearHeartbeat()
      wsRef.current = null
      onDisconnected?.()
      // Do NOT reconnect if server rejected or user closed
    }

    ws.onerror = () => {
      // onclose will fire after onerror
    }

    return ws
  }, [onMessage, onConnected, onDisconnected, startHeartbeat, clearHeartbeat])

  const disconnect = useCallback(() => {
    closedByUserRef.current = true
    clearHeartbeat()
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    taskIdRef.current = null
  }, [clearHeartbeat])

  // Wait for a specific WS message type (used by serial scoring scheduler)
  const waitForMessage = useCallback((targetType: string, timeoutMs = 300000): Promise<WsMessage> => {
    return new Promise((resolve, reject) => {
      const ws = wsRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        reject(new Error('WebSocket 未连接'))
        return
      }

      const timer = setTimeout(() => {
        ws.removeEventListener('message', handler)
        reject(new Error(`等待 ${targetType} 超时`))
      }, timeoutMs)

      function handler(event: MessageEvent) {
        try {
          const msg: WsMessage = JSON.parse(event.data)
          if (msg.type === targetType) {
            clearTimeout(timer)
            ws!.removeEventListener('message', handler)
            resolve(msg)
          }
        } catch { /* ignore parse errors */ }
      }

      ws.addEventListener('message', handler)
    })
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      closedByUserRef.current = true
      clearHeartbeat()
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [clearHeartbeat])

  return { connect, disconnect, waitForMessage, wsRef }
}
