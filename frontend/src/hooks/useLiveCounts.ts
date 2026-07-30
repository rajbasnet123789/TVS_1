import { useState, useEffect, useRef } from 'react'
import api from '../api/axios'

export interface LiveCount {
  camera_id: string
  camera_name: string
  count: number
}

export function useLiveCounts(pollInterval = 3000) {
  const [counts, setCounts] = useState<Map<string, number>>(new Map())
  const [loading, setLoading] = useState(true)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    let timer: ReturnType<typeof setTimeout>

    const fetchCounts = async () => {
      try {
        const { data } = await api.get<LiveCount[]>('/detection/live-counts')
        if (!mounted.current) return
        const map = new Map<string, number>()
        for (const item of data) {
          map.set(item.camera_id, item.count)
        }
        setCounts(map)
        setLoading(false)
      } catch {
        if (mounted.current) setLoading(false)
      }
      if (mounted.current) timer = setTimeout(fetchCounts, pollInterval)
    }

    fetchCounts()
    return () => {
      mounted.current = false
      clearTimeout(timer)
    }
  }, [pollInterval])

  return { counts, loading }
}
