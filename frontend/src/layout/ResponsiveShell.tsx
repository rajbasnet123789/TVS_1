import { useState } from 'react'
import { Box, Toolbar } from '@mui/material'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { ProtectedRoute } from '../auth/ProtectedRoute'
import { useAuth } from '../auth/AuthContext'
import Login from '../auth/Login'
import Dashboard from '../pages/Dashboard'
import LiveFeed from '../pages/LiveFeed'
import Cameras from '../pages/Cameras'
import Chickens from '../pages/Chickens'
import Settings from '../pages/Settings'
import Analytics from '../pages/Analytics'
import Alerts from '../pages/Alerts'
import Reports from '../pages/Reports'

const DRAWER_WIDTH = 240

export function ResponsiveShell() {
  const { user, loading } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)

  if (loading) return null
  if (!user) return <Login />

  return (
    <Box sx={{ display: 'flex', bgcolor: '#f8fafc', minHeight: '100vh' }}>
      <Header onMenuClick={() => setMobileOpen(true)} />
      <Sidebar open={mobileOpen} onClose={() => setMobileOpen(false)} />

      <Box component="main" sx={{ flexGrow: 1, p: { xs: 2, md: 4 }, ml: { md: `${DRAWER_WIDTH}px` }, width: { md: `calc(100% - ${DRAWER_WIDTH}px)` } }}>
        <Toolbar sx={{ display: { xs: 'block', md: 'none' } }} />
        <Routes>
          <Route path="/" element={<ProtectedRoute permission="dashboard:read"><Dashboard /></ProtectedRoute>} />
          <Route path="/live" element={<ProtectedRoute permission="live:read"><LiveFeed /></ProtectedRoute>} />
          <Route path="/cameras" element={<ProtectedRoute permission="cameras:read"><Cameras /></ProtectedRoute>} />
          <Route path="/chickens" element={<ProtectedRoute permission="chickens:read"><Chickens /></ProtectedRoute>} />
          <Route path="/analytics" element={<ProtectedRoute permission="analytics:read"><Analytics /></ProtectedRoute>} />
          <Route path="/alerts" element={<ProtectedRoute permission="dashboard:read"><Alerts /></ProtectedRoute>} />
          <Route path="/reports" element={<ProtectedRoute permission="dashboard:read"><Reports /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute permission="settings:read"><Settings /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Box>
    </Box>
  )
}
