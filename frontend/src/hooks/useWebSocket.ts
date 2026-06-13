import { useEffect, useRef, useCallback } from 'react'
import type { WebSocketMessage } from '../types'

type MessageHandler = (msg: WebSocketMessage) => void

export function useWebSocket(handlers?: Record<string, MessageHandler>) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number>()

  const connect = useCallback(() => {
    const token = localStorage.getItem('access_token')
    if (!token) return

    const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const wsUrl = API_BASE.replace(/^http/, 'ws')
    const ws = new WebSocket(`${wsUrl}/ws?token=${token}`)

    ws.onopen = () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = undefined
      }
    }

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data)
        if (handlers?.[msg.type]) {
          handlers[msg.type](msg)
        }
      } catch { /* ignore */ }
    }

    ws.onclose = () => {
      reconnectTimeoutRef.current = window.setTimeout(connect, 3000)
    }

    wsRef.current = ws
  }, [handlers])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { ws: wsRef.current }
}
