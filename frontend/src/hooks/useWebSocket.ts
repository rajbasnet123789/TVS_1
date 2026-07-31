import { useEffect, useRef, useCallback } from 'react'
import type { WebSocketMessage } from '../types'
import { useAuth } from '../auth/AuthContext'
import { subscribe, setSocketFarmId, type MessageHandler } from './sharedSocket'

type MessageHandlers = Record<string, MessageHandler>

export function useWebSocket(handlers?: MessageHandlers) {
  const { currentFarm } = useAuth()
  const handlersRef = useRef<MessageHandlers | undefined>(handlers)

  useEffect(() => {
    handlersRef.current = handlers
  }, [handlers])

  const connect = useCallback(() => {
    return subscribe((msg: WebSocketMessage) => {
      const handler = handlersRef.current?.[msg.type]
      if (handler) {
        handler(msg)
      }
    })
  }, [])

  useEffect(() => {
    const farmId = currentFarm?.id || null
    setSocketFarmId(farmId)
    const unsubscribe = connect()
    return () => {
      unsubscribe()
    }
  }, [connect, currentFarm?.id])

  return {}
}
