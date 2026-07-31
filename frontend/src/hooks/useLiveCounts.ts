import { useState, useEffect } from 'react'
import api from '../api/axios'

export interface LiveCount {
  camera_id: string
  camera_name: string
  count: number
}

let globalCounts = new Map<string, number>()
let globalLoading = true
let pollTimer: ReturnType<typeof setInterval> | null = null
let consumerCount = 0

let ws: WebSocket | null = null
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null
let wsAttempt = 0

const listeners = new Set<() => void>()

function updateGlobalState(newCounts: Map<string, number>, newLoading: boolean) {
  globalCounts = newCounts
  globalLoading = newLoading
  listeners.forEach((listener) => listener())
}

function applyCountsMessage(msg: any) {
  const entries = Array.isArray(msg?.counts) ? msg.counts : []
  if (entries.length === 0) return
  const next = new Map(globalCounts)
  for (const item of entries) {
    if (item?.camera_id) {
      next.set(item.camera_id, Number(item.count) || 0)
    }
  }
  updateGlobalState(next, false)
}

async function fetchLiveCounts() {
  try {
    const { data } = await api.get<LiveCount[]>('/detection/live-counts')
    const map = new Map<string, number>()
    for (const item of data) {
      map.set(item.camera_id, item.count)
    }
    updateGlobalState(map, false)
  } catch {
    updateGlobalState(globalCounts, false)
  }
}

function buildWsUrl() {
  const API_BASE = import.meta.env.VITE_API_URL || '/api'
  let wsUrl: string
  if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
    wsUrl = `${API_BASE.replace(/^http/, 'ws')}/ws`
  } else {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    wsUrl = `${protocol}//${window.location.host}/ws`
  }
  const farmId = localStorage.getItem('selected_farm_id')
  const impToken = localStorage.getItem('impersonation_token')
  const queryParams: string[] = []
  if (farmId) queryParams.push(`farm_id=${encodeURIComponent(farmId)}`)
  if (impToken) queryParams.push(`token=${encodeURIComponent(impToken)}`)
  if (queryParams.length > 0) {
    wsUrl += `?${queryParams.join('&')}`
  }
  return wsUrl
}

function connectWs() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return
  }
  try {
    ws = new WebSocket(buildWsUrl())
  } catch {
    return
  }

  ws.onopen = () => {
    wsAttempt = 0
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer)
      wsReconnectTimer = null
    }
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg?.type === 'counts') {
        applyCountsMessage(msg)
      }
    } catch {
      /* ignore */
    }
  }

  ws.onclose = () => {
    const delay = Math.min(1000 * 2 ** wsAttempt, 30000)
    const jitter = delay * (0.5 + Math.random() * 0.5)
    wsAttempt += 1
    wsReconnectTimer = setTimeout(connectWs, jitter)
  }
}

function startPolling(interval: number) {
  if (pollTimer) return
  fetchLiveCounts()
  pollTimer = setInterval(fetchLiveCounts, interval)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

export function useLiveCounts(pollInterval = 3000) {
  const [state, setState] = useState({
    counts: globalCounts,
    loading: globalLoading,
  })

  useEffect(() => {
    const handleChange = () => {
      setState({
        counts: globalCounts,
        loading: globalLoading,
      })
    }
    listeners.add(handleChange)
    consumerCount++
    connectWs()
    startPolling(pollInterval)

    return () => {
      listeners.delete(handleChange)
      consumerCount--
      if (consumerCount === 0) {
        stopPolling()
        if (wsReconnectTimer) {
          clearTimeout(wsReconnectTimer)
          wsReconnectTimer = null
        }
        if (ws) {
          ws.onclose = null
          ws.close()
          ws = null
        }
      }
    }
  }, [pollInterval])

  return { counts: state.counts, loading: state.loading }
}
