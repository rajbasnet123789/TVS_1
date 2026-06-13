import { useState, useEffect, useCallback } from 'react'
import api from '../api/axios'
import type { Camera, DetectionStats, ONVIFDevice } from '../types'

export function useCameras() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [loading, setLoading] = useState(true)

  const fetchCameras = useCallback(async () => {
    try {
      const { data } = await api.get('/cameras')
      setCameras(data)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchCameras() }, [fetchCameras])

  const addCamera = async (cameraData: Partial<Camera>) => {
    const { data } = await api.post('/cameras', cameraData)
    setCameras((prev) => [data, ...prev])
    return data
  }

  const updateCamera = async (id: string, cameraData: Partial<Camera>) => {
    const { data } = await api.put(`/cameras/${id}`, cameraData)
    setCameras((prev) => prev.map((c) => (c.id === id ? data : c)))
    return data
  }

  const deleteCamera = async (id: string) => {
    await api.delete(`/cameras/${id}`)
    setCameras((prev) => prev.filter((c) => c.id !== id))
  }

  const startScan = async (params?: { subnet?: string; ip?: string; username?: string; password?: string }) => {
    await api.post('/cameras/scan', params ?? {})
  }

  const getScanResults = async (): Promise<ONVIFDevice[]> => {
    const { data } = await api.get('/cameras/scan/results')
    return data
  }

  const startDetection = async (cameraId: string) => {
    const { data } = await api.post(`/cameras/${cameraId}/detection/start`)
    return data
  }

  const stopDetection = async (cameraId: string) => {
    const { data } = await api.post(`/cameras/${cameraId}/detection/stop`)
    return data
  }

  const getDetectionStatus = async (cameraId: string): Promise<{ camera_id: string; detection_enabled: boolean }> => {
    const { data } = await api.get(`/cameras/${cameraId}/detection/status`)
    return data
  }

  const getDetectionStats = async (cameraId: string): Promise<DetectionStats> => {
    const { data } = await api.get(`/cameras/${cameraId}/detection/stats`)
    return data
  }

  return { cameras, loading, addCamera, updateCamera, deleteCamera, startScan, getScanResults, startDetection, stopDetection, getDetectionStatus, getDetectionStats, refresh: fetchCameras }
}
