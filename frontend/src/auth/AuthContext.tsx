import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import api from '../api/axios'
import type { Farm, User, TokenResponse } from '../types'

interface ImpersonationInfo {
  id: string
  email: string
  full_name: string | null
  role: string
  permissions: string[]
}

interface AuthState {
  user: User | null
  farms: Farm[]
  currentFarm: Farm | null
  loading: boolean
  impersonating: ImpersonationInfo | null
  login: (email: string, password: string) => Promise<void>
  loginWithGoogle: (credential: string) => Promise<void>
  logout: () => Promise<void>
  setCurrentFarm: (farm: Farm | null) => void
  hasPermission: (perm: string) => boolean
  startImpersonating: (token: string, info: ImpersonationInfo) => void
  stopImpersonating: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [farms, setFarms] = useState<Farm[]>([])
  const [currentFarm, setCurrentFarm] = useState<Farm | null>(null)
  const [loading, setLoading] = useState(true)
  const [impersonating, setImpersonating] = useState<ImpersonationInfo | null>(() => {
    const saved = localStorage.getItem('impersonation_info')
    if (!saved) return null
    try {
      return JSON.parse(saved)
    } catch (err) {
      console.error('Failed to parse impersonation_info:', err)
      return null
    }
  })

  const fetchUser = useCallback(async () => {
    try {
      const { data } = await api.get('/auth/me')
      setUser(data)
      const farmRes = await api.get('/farms')
      const farmList: Farm[] = farmRes.data
      setFarms(farmList)
      const saved = localStorage.getItem('selected_farm_id')
      if (saved && farmList.find((f) => f.id === saved)) {
        setCurrentFarm(farmList.find((f) => f.id === saved) || farmList[0] || null)
      } else {
        if (data.role.name === 'super_admin') {
          setCurrentFarm(null)
        } else {
          setCurrentFarm(farmList[0] || null)
        }
      }
    } catch {
      setUser(null)
      setFarms([])
      setCurrentFarm(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchUser() }, [fetchUser])

  const login = async (email: string, password: string) => {
    const { data } = await api.post<TokenResponse>('/auth/login', { email, password })
    await fetchUser()
  }

  const loginWithGoogle = async (credential: string) => {
    await api.post<TokenResponse>('/auth/google', { credential })
    await fetchUser()
  }

  const logout = async () => {
    try {
      await api.post('/auth/logout')
    } catch {
    }
    setUser(null)
    setFarms([])
    setCurrentFarm(null)
    localStorage.removeItem('selected_farm_id')
  }

  const handleSetCurrentFarm = (farm: Farm | null) => {
    setCurrentFarm(farm)
    if (farm) {
      localStorage.setItem('selected_farm_id', farm.id)
    } else {
      localStorage.removeItem('selected_farm_id')
    }
  }

  const startImpersonating = (token: string, info: ImpersonationInfo) => {
    localStorage.setItem('impersonation_token', token)
    localStorage.setItem('impersonation_info', JSON.stringify(info))
    setImpersonating(info)
  }

  const stopImpersonating = () => {
    localStorage.removeItem('impersonation_token')
    localStorage.removeItem('impersonation_info')
    setImpersonating(null)
    window.location.href = '/'
  }

  const hasPermission = (perm: string) => {
    if (impersonating) {
      return impersonating.permissions.includes(perm)
    }
    return user?.role?.permissions?.includes(perm) ?? false
  }

  return (
    <AuthContext.Provider value={{ user, farms, currentFarm, loading, impersonating, login, loginWithGoogle, logout, setCurrentFarm: handleSetCurrentFarm, hasPermission, startImpersonating, stopImpersonating }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
