import { useState, useEffect } from 'react'
import api from '../api/axios'
import type { Camera, DiscoveredDevice, ScanStatus } from '../types'
import { useAuth } from '../auth/AuthContext'

// Global shared state for cameras to avoid out-of-sync states between components
let globalCameras: Camera[] = []
let globalLoading = true
let activeFetchPromise: Promise<void> | null = null
let currentFetchId = 0

const listeners = new Set<() => void>()

function updateGlobalState(newCameras: Camera[], newLoading: boolean) {
  globalCameras = newCameras
  globalLoading = newLoading
  listeners.forEach((listener) => listener())
}

async function fetchCamerasGlobal(fetchId: number) {
  if (activeFetchPromise && fetchId === currentFetchId) {
    return activeFetchPromise
  }
  activeFetchPromise = (async () => {
    try {
      const { data } = await api.get('/cameras')
      if (fetchId === currentFetchId) {
        updateGlobalState(data, false)
      }
    } catch {
      if (fetchId === currentFetchId) {
        updateGlobalState(globalCameras, false)
      }
    } finally {
      if (fetchId === currentFetchId) {
        activeFetchPromise = null
      }
    }
  })()
  return activeFetchPromise
}

export function useCameras() {
  const { currentFarm } = useAuth()
  const [state, setState] = useState({
    cameras: globalCameras,
    loading: globalLoading,
  })

  useEffect(() => {
    const handleChange = () => {
      setState({
        cameras: globalCameras,
        loading: globalLoading,
      })
    }
    listeners.add(handleChange)
    
    // Clear in-flight promise and reset state when currentFarm changes
    currentFetchId += 1
    activeFetchPromise = null
    updateGlobalState([], true)
    fetchCamerasGlobal(currentFetchId)

    return () => {
      listeners.delete(handleChange)
    }
  }, [currentFarm])

  const addCamera = async (cameraData: Partial<Camera>) => {
    const { data } = await api.post('/cameras', cameraData)
    const newCameras = [data, ...globalCameras]
    updateGlobalState(newCameras, globalLoading)
    return data
  }

  const updateCamera = async (id: string, cameraData: Partial<Camera>) => {
    const { data } = await api.put(`/cameras/${id}`, cameraData)
    const newCameras = globalCameras.map((c) => (c.id === id ? data : c))
    updateGlobalState(newCameras, globalLoading)
    return data
  }

  const deleteCamera = async (id: string) => {
    await api.delete(`/cameras/${id}`)
    const newCameras = globalCameras.filter((c) => c.id !== id)
    updateGlobalState(newCameras, globalLoading)
  }

  const scanNetwork = async () => {
    const { data } = await api.post('/cameras/scan')
    return data
  }

  const getScanStatus = async (): Promise<ScanStatus> => {
    const { data } = await api.get('/cameras/scan/status')
    return data
  }

  const getScanResults = async (): Promise<DiscoveredDevice[]> => {
    const { data } = await api.get('/cameras/scan/results')
    return data
  }

  return {
    cameras: state.cameras,
    loading: state.loading,
    addCamera,
    updateCamera,
    deleteCamera,
    scanNetwork,
    getScanStatus,
    getScanResults
  }
}
