import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import type { ReactNode } from 'react'

export function ProtectedRoute({ children, permission }: { children: ReactNode; permission?: string }) {
  const { user, loading, hasPermission } = useAuth()

  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  if (permission && !hasPermission(permission)) return <Navigate to="/" replace />

  return <>{children}</>
}
