import { useState, useEffect } from 'react'
import api from '../api/axios'
import { subscribe } from './sharedSocket'

export interface LiveCount {
  camera_id: string
  camera_name: string
  count: number
}

let globalCounts = new Map<string, number>()
let globalLoading = true
let pollTimer: ReturnType<typeof setInterval> | null = null
let consumerCount = 0

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

    const unsubscribe = subscribe((msg) => {
      if (msg?.type === 'counts') {
        applyCountsMessage(msg)
      }
    })
    startPolling(pollInterval)

    return () => {
      listeners.delete(handleChange)
      consumerCount--
      unsubscribe()
      if (consumerCount <= 0) {
        consumerCount = 0
        stopPolling()
      }
    }
  }, [pollInterval])

  return { counts: state.counts, loading: state.loading }
}
