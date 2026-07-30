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

const listeners = new Set<() => void>()

function updateGlobalState(newCounts: Map<string, number>, newLoading: boolean) {
  globalCounts = newCounts
  globalLoading = newLoading
  listeners.forEach((listener) => listener())
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
    startPolling(pollInterval)

    return () => {
      listeners.delete(handleChange)
      consumerCount--
      if (consumerCount === 0) stopPolling()
    }
  }, [pollInterval])

  return { counts: state.counts, loading: state.loading }
}
