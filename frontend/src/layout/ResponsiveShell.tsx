import { useState } from 'react'
import { Box, Toolbar, Typography, CircularProgress } from '@mui/material'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { ProtectedRoute } from '../auth/ProtectedRoute'
import { useAuth } from '../auth/AuthContext'
import Login from '../auth/Login'
import ImpersonationBanner from '../components/ImpersonationBanner'
import CoopMap from '../pages/CoopMap'
import Dashboard from '../pages/Dashboard'
import LiveFeed from '../pages/LiveFeed'

import Settings from '../pages/Settings'
import Analytics from '../pages/Analytics'
import Alerts from '../pages/Alerts'
import Reports from '../pages/Reports'
import ProfitLoss from '../pages/ProfitLoss'
import AdminFarms from '../pages/admin/Farms'
import MediaGallery from '../pages/MediaGallery'

import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { PWAPrompt } from '../components/PWAPrompt'

const DRAWER_WIDTH = 240

function AuthLoading() {
  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', bgcolor: '#f8fafc', gap: 3 }}>
      <Box component="img" src="/tvs_logo.png" alt="Coop Vision" sx={{ height: 64, width: 'auto', opacity: 0.85, objectFit: 'contain' }} />
      <Typography variant="h5" sx={{ fontWeight: 700, color: '#0f172a', fontFamily: '"Outfit", sans-serif', letterSpacing: '-0.02em' }}>
        Coop Vision
      </Typography>
      <CircularProgress size={20} sx={{ color: '#94a3b8' }} />
    </Box>
  )
}

function OfflineBanner() {
  return (
    <Box
      sx={{
        bgcolor: '#ef4444',
        color: 'white',
        px: 2,
        py: 1,
        textAlign: 'center',
        fontWeight: 600,
        fontFamily: '"Outfit", sans-serif',
        fontSize: '13px',
        letterSpacing: '0.01em',
        boxShadow: '0 2px 4px rgba(239, 68, 68, 0.15)',
        zIndex: 1100,
      }}
    >
      You are currently offline. Live camera feeds and dashboard updates are paused.
    </Box>
  )
}

export function ResponsiveShell() {
  const { user, loading } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const isOnline = useOnlineStatus()

  if (loading) return <AuthLoading />
  if (!user) {
    return (
      <>
        <Login />
        <PWAPrompt />
      </>
    )
  }

  return (
    <Box sx={{ display: 'flex', bgcolor: '#f8fafc', minHeight: '100vh' }}>
      <Header onMenuClick={() => setMobileOpen(true)} />
      <Sidebar open={mobileOpen} onClose={() => setMobileOpen(false)} />

      <Box component="main" sx={{ flexGrow: 1, ml: { md: `${DRAWER_WIDTH}px` }, width: { md: `calc(100% - ${DRAWER_WIDTH}px)` }, display: 'flex', flexDirection: 'column' }}>
        {!isOnline && <OfflineBanner />}
        <ImpersonationBanner />
        <Box sx={{ p: { xs: 2, md: 4 } }}>
        <Toolbar sx={{ display: { xs: 'block', md: 'none' } }} />
        <Routes>
          <Route path="/" element={<ProtectedRoute permission="dashboard:read"><Dashboard /></ProtectedRoute>} />
          <Route path="/coop-map" element={<ProtectedRoute permission="dashboard:read"><CoopMap /></ProtectedRoute>} />
          <Route path="/live" element={<ProtectedRoute permission="live:read"><LiveFeed /></ProtectedRoute>} />
          <Route path="/analytics" element={<ProtectedRoute permission="analytics:read"><Analytics /></ProtectedRoute>} />
          <Route path="/alerts" element={<ProtectedRoute permission="dashboard:read"><Alerts /></ProtectedRoute>} />
          <Route path="/reports" element={<ProtectedRoute permission="dashboard:read"><Reports /></ProtectedRoute>} />
          <Route path="/profit-loss" element={<ProtectedRoute permission="dashboard:read"><ProfitLoss /></ProtectedRoute>} />
          <Route path="/admin/farms" element={<ProtectedRoute permission="system:audit"><AdminFarms /></ProtectedRoute>} />
          <Route path="/media" element={<ProtectedRoute permission="cameras:read"><MediaGallery /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute permission="settings:read"><Settings /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Box>
      </Box>
      <PWAPrompt />
    </Box>
  )
}
