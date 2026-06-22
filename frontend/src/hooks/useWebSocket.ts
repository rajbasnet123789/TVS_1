import { useEffect, useRef, useCallback } from 'react'
import type { WebSocketMessage } from '../types'
import { useAuth } from '../auth/AuthContext'

type MessageHandler = (msg: WebSocketMessage) => void

export function useWebSocket(handlers?: Record<string, MessageHandler>) {
  const { currentFarm } = useAuth()
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number>()
  const attemptRef = useRef(0)
  const handlersRef = useRef(handlers)

  useEffect(() => {
    handlersRef.current = handlers
  }, [handlers])

  const connect = useCallback(() => {
    const API_BASE = import.meta.env.VITE_API_URL || '/api'
    let wsUrl: string
    if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
      wsUrl = `${API_BASE.replace(/^http/, 'ws')}/ws`
    } else {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      wsUrl = `${protocol}//${window.location.host}/ws`
    }
    const farmId = currentFarm?.id || localStorage.getItem('selected_farm_id')
    if (farmId) {
      wsUrl += `?farm_id=${encodeURIComponent(farmId)}`
    }
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      attemptRef.current = 0
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = undefined
      }
    }

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data)
        if (handlersRef.current?.[msg.type]) {
          handlersRef.current[msg.type](msg)
        }
      } catch { /* ignore */ }
    }

    ws.onclose = () => {
      const delay = Math.min(1000 * 2 ** attemptRef.current, 30000)
      const jitter = delay * (0.5 + Math.random() * 0.5)
      attemptRef.current += 1
      reconnectTimeoutRef.current = window.setTimeout(connect, jitter)
    }

    wsRef.current = ws
  }, [currentFarm?.id])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { ws: wsRef.current }
}
