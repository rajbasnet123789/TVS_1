import { useState, useEffect } from 'react'
import { subscribe } from './sharedSocket'

export interface LiveCount {
  camera_id: string
  camera_name: string
  count: number
}

let globalCounts = new Map<string, number>()
let lastSeen = new Map<string, number>()
let globalLoading = true
let pruneTimer: ReturnType<typeof setInterval> | null = null
let consumerCount = 0

const listeners = new Set<() => void>()

const STALE_MS = 30000

function updateGlobalState(newCounts: Map<string, number>, newLoading: boolean) {
  globalCounts = newCounts
  globalLoading = newLoading
  listeners.forEach((listener) => listener())
}

function applyCountsMessage(msg: any) {
  const entries = Array.isArray(msg?.counts) ? msg.counts : []
  if (entries.length === 0) return
  const now = Date.now()
  const next = new Map(globalCounts)
  for (const item of entries) {
    if (item?.camera_id) {
      next.set(item.camera_id, Number(item.count) || 0)
      lastSeen.set(item.camera_id, now)
    }
  }
  updateGlobalState(next, false)
}

// Safety net: if the WebSocket goes silent for a camera (or disconnects), decay
// its count to zero instead of freezing a stale number on the UI.
function pruneStale() {
  const now = Date.now()
  let changed = false
  const next = new Map(globalCounts)
  for (const [camId, last] of lastSeen) {
    if (now - last > STALE_MS && next.has(camId)) {
      next.delete(camId)
      lastSeen.delete(camId)
      changed = true
    }
  }
  if (changed) updateGlobalState(next, false)
}

function startPruning(interval: number) {
  if (pruneTimer) return
  pruneTimer = setInterval(pruneStale, Math.max(interval, 1000))
}

function stopPruning() {
  if (pruneTimer) {
    clearInterval(pruneTimer)
    pruneTimer = null
  }
}

export function useLiveCounts(interval = 3000) {
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

    const unsubscribe = subscribe((msg) => {
      if (msg?.type === 'counts') {
        applyCountsMessage(msg)
      }
    })
    startPruning(interval)

    return () => {
      listeners.delete(handleChange)
      consumerCount--
      unsubscribe()
      if (consumerCount <= 0) {
        consumerCount = 0
        stopPruning()
      }
    }
  }, [interval])

  return { counts: state.counts, loading: state.loading }
}
