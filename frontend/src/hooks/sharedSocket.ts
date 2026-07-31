// Single shared WebSocket connection for the whole app.
//
// Both useWebSocket and useLiveCounts subscribe here so the browser only ever
// opens ONE /ws connection (previously each hook opened its own).
import type { WebSocketMessage } from '../types'

export type MessageHandler = (msg: WebSocketMessage) => void

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let attempt = 0
let consumerCount = 0
let currentFarmId: string | null = null

const listeners = new Set<MessageHandler>()

function buildWsUrl(): string {
  const API_BASE = import.meta.env.VITE_API_URL || '/api'
  let wsUrl: string
  if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
    wsUrl = `${API_BASE.replace(/^http/, 'ws')}/ws`
  } else {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    wsUrl = `${protocol}//${window.location.host}/ws`
  }
  const farmId = currentFarmId || localStorage.getItem('selected_farm_id')
  const impToken = localStorage.getItem('impersonation_token')
  const queryParams: string[] = []
  if (farmId) queryParams.push(`farm_id=${encodeURIComponent(farmId)}`)
  if (impToken) queryParams.push(`token=${encodeURIComponent(impToken)}`)
  if (queryParams.length > 0) {
    wsUrl += `?${queryParams.join('&')}`
  }
  return wsUrl
}

function connect() {
  if (ws && (ws.readyState === 0 || ws.readyState === 1)) {
    return
  }
  try {
    ws = new WebSocket(buildWsUrl())
  } catch {
    return
  }

  ws.onopen = () => {
    attempt = 0
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  ws.onmessage = (event) => {
    let msg: WebSocketMessage
    try {
      msg = JSON.parse(event.data)
    } catch {
      return
    }
    listeners.forEach((listener) => {
      try {
        listener(msg)
      } catch { /* ignore */ }
    })
  }

  ws.onclose = () => {
    const delay = Math.min(1000 * 2 ** attempt, 30000)
    const jitter = delay * (0.5 + Math.random() * 0.5)
    attempt += 1
    reconnectTimer = setTimeout(connect, jitter)
  }
}

function teardown() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
}

export function subscribe(handler: MessageHandler): () => void {
  listeners.add(handler)
  consumerCount += 1
  connect()
  return () => {
    listeners.delete(handler)
    consumerCount -= 1
    if (consumerCount <= 0) {
      consumerCount = 0
      teardown()
    }
  }
}

// Call when the active farm changes so the shared socket reconnects with the
// new ?farm_id= scope.
export function setSocketFarmId(farmId: string | null) {
  if (farmId === currentFarmId) return
  currentFarmId = farmId
  if (ws || reconnectTimer) {
    teardown()
    connect()
  }
}

