import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

const api = axios.create({
  baseURL: `${API_BASE}/v1`,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 15000,
})

api.interceptors.request.use((config) => {
  const farmId = localStorage.getItem('selected_farm_id')
  if (farmId) {
    config.headers['X-Farm-ID'] = farmId
  }
  const impToken = localStorage.getItem('impersonation_token')
  if (impToken) {
    config.headers.Authorization = `Bearer ${impToken}`
  }
  return config
})

let refreshPromise: Promise<boolean> | null = null

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const isAuthRoute = original.url?.includes('/auth/login') || original.url?.includes('/auth/refresh')
    if (error.response?.status === 401 && !original._retry && !isAuthRoute) {
      original._retry = true
      try {
        if (!refreshPromise) {
          refreshPromise = (async () => {
            localStorage.removeItem('impersonation_token')
            localStorage.removeItem('impersonation_info')
            try {
              const { data } = await axios.post(`${API_BASE}/v1/auth/refresh`, {}, { withCredentials: true })
              if (data.impersonation_token) {
                localStorage.setItem('impersonation_token', data.impersonation_token)
              }
              return true
            } catch {
              return false
            }
          })()
        }
        const ok = await refreshPromise
        if (ok) {
          const tokenToUse = localStorage.getItem('impersonation_token')
          if (tokenToUse) {
            original.headers.Authorization = `Bearer ${tokenToUse}`
          }
          return api(original)
        }
      } finally {
        refreshPromise = null
      }
    }
    return Promise.reject(error)
  }
)

export default api
