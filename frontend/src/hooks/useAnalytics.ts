import { useState, useCallback } from 'react'
import api from '../api/axios'
import type { DetectionHistory, DetectionSummary } from '../types'

export function useAnalytics() {
  const [history, setHistory] = useState<DetectionHistory | null>(null)
  const [summary, setSummary] = useState<DetectionSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchCameraHistory = useCallback(async (
    cameraId: string,
    start = '-1h',
    end = 'now()',
    window = '5m',
  ) => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.get(`/cameras/${cameraId}/detection/history`, {
        params: { start, end, window },
      })
      setHistory(data)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load history')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchCameraSummary = useCallback(async (
    cameraId: string,
    start = '-1h',
    end = 'now()',
  ) => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.get(`/cameras/${cameraId}/detection/summary`, {
        params: { start, end },
      })
      setSummary(data)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load summary')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchGlobalHistory = useCallback(async (
    start = '-1h',
    end = 'now()',
    window = '5m',
  ) => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.get('/detection/global/history', {
        params: { start, end, window },
      })
      setHistory(data)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load global history')
    } finally {
      setLoading(false)
    }
  }, [])

  return { history, summary, loading, error, fetchCameraHistory, fetchCameraSummary, fetchGlobalHistory }
}
