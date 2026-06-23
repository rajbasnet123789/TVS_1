import { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Box, Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText,
  Toolbar, Typography, Card, Select, MenuItem, FormControl
} from '@mui/material'
import api from '../api/axios'
import HomeOutlinedIcon from '@mui/icons-material/HomeOutlined'
import MapOutlinedIcon from '@mui/icons-material/MapOutlined'
import VideocamOutlinedIcon from '@mui/icons-material/VideocamOutlined'
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined'
import ThermostatOutlinedIcon from '@mui/icons-material/ThermostatOutlined'
import NotificationsNoneOutlinedIcon from '@mui/icons-material/NotificationsNoneOutlined'
import BarChartOutlinedIcon from '@mui/icons-material/BarChartOutlined'
import BusinessIcon from '@mui/icons-material/Business'
import CurrencyExchangeIcon from '@mui/icons-material/CurrencyExchange'
import PhotoLibraryOutlinedIcon from '@mui/icons-material/PhotoLibraryOutlined'
import LogoutIcon from '@mui/icons-material/Logout'
import ShieldOutlinedIcon from '@mui/icons-material/ShieldOutlined'
import { useAuth } from '../auth/AuthContext'
 
const DRAWER_WIDTH = 240
 
// Chicken icon SVG outline
export const ChickenIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <path d="M12 4C11.5 2.5 9.5 2.5 9 4" />
    <path d="M9 4C7.5 4.5 6 6 6 8C6 9 6.5 9.5 7 10" />
    <path d="M5 8.5L3 9.5L5 10.5" />
    <path d="M7 10C5 12 4 14.5 4 17C4 19.5 6 21.5 8.5 21.5C13 21.5 19 19.5 19 14C19 10 17 6.5 14 5C13.5 5.5 13 6 12 6C11 6 10 5.5 9.5 5" />
    <circle cx="7.5" cy="7.5" r="1" fill="currentColor" />
    <path d="M9 13C10.5 12 12.5 12 13.5 13.5C14.5 15 13.5 17 11 17C9.5 17 8.5 16 8.5 15" />
    <path d="M10 21.5V23.5" />
    <path d="M14 21.5V23.5" />
  </svg>
)
 
const navItems = [
  { label: 'Overview', path: '/', icon: <HomeOutlinedIcon />, permission: 'dashboard:read' },
  { label: 'Coop Map', path: '/coop-map', icon: <MapOutlinedIcon />, permission: 'dashboard:read' },
  { label: 'Live Feed', path: '/live', icon: <VideocamOutlinedIcon />, permission: 'live:read' },
  { label: 'Environment', path: '/analytics', icon: <ThermostatOutlinedIcon />, permission: 'analytics:read' },
  { label: 'Media Gallery', path: '/media', icon: <PhotoLibraryOutlinedIcon />, permission: 'cameras:read' },
  { label: 'Alerts', path: '/alerts', icon: <NotificationsNoneOutlinedIcon />, permission: 'dashboard:read' },
  { label: 'Reports', path: '/reports', icon: <BarChartOutlinedIcon />, permission: 'dashboard:read' },
  { label: 'P&L Projection', path: '/profit-loss', icon: <CurrencyExchangeIcon />, permission: 'dashboard:read' },
  { label: 'Farms', path: '/admin/farms', icon: <BusinessIcon />, permission: 'system:audit' },
  { label: 'Settings', path: '/settings', icon: <SettingsOutlinedIcon />, permission: 'settings:read' },
]


export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { hasPermission, logout, user, farms, currentFarm, setCurrentFarm } = useAuth()
  const [healthIndex, setHealthIndex] = useState(0)
  const [statusText, setStatusText] = useState('Loading...')
  const [dotColor, setDotColor] = useState('#94a3b8')

  // Poll cameras to compute health index
  useEffect(() => {
    const fetchHealth = () => {
      api.get('/cameras').catch(() => ({ data: [] })).then(async (camerasRes) => {
        const camerasList = camerasRes.data
        const onlineCount = camerasList.filter((c: any) => c.status === 'online').length
        const alerts = camerasList.filter((c: any) => c.status === 'offline').length
        const healthyPct = Math.min(100, Math.round(
          (onlineCount / Math.max(camerasList.length, 1)) * 40 +
          (1 - Math.min(alerts, 5) / 5) * 30 +
          30 // assume detection activity for sidebar simplicity
        ))
        setHealthIndex(healthyPct)
        if (healthyPct >= 80) { setStatusText('All systems normal'); setDotColor('#10b981') }
        else if (healthyPct >= 50) { setStatusText('Attention needed'); setDotColor('#f59e0b') }
        else { setStatusText('Critical'); setDotColor('#ef4444') }
      }).catch(() => {
        setHealthIndex(0)
        setStatusText('Offline')
        setDotColor('#94a3b8')
      })
    }
    fetchHealth()
    const interval = setInterval(fetchHealth, 10000)
    return () => clearInterval(interval)
  }, [])

  // Circular progress gauge variables
  const radius = 38
  const strokeWidth = 6
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (healthIndex / 100) * circumference

  const content = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', bgcolor: '#ffffff' }}>
      <Toolbar sx={{ px: 3, py: 2.5, display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Box component="img" src="/tvs_logo.png" alt="Coop Vision Logo" sx={{ height: 36, objectFit: 'contain' }} />
        <Typography 
          variant="caption" 
          sx={{ 
            fontFamily: '"Outfit", sans-serif', 
            fontWeight: 800, 
            letterSpacing: '0.08em',
            fontSize: '0.625rem',
            color: '#64748b',
            textTransform: 'uppercase',
            display: 'block',
            lineHeight: 1.2,
            borderLeft: '1px solid #cbd5e1',
            pl: 1.5
          }}
        >
          MONITORING<br />DECK
        </Typography>
      </Toolbar>

      {user?.role?.name === 'super_admin' && farms.length > 0 && (
        <Box sx={{ px: 2, pb: 1 }}>
          <FormControl size="small" fullWidth>
            <Select
              value={currentFarm ? currentFarm.id : 'all'}
              onChange={(e) => {
                if (e.target.value === 'all') {
                  setCurrentFarm(null)
                } else {
                  const farm = farms.find((f) => f.id === e.target.value) || null
                  setCurrentFarm(farm)
                }
              }}
              sx={{
                color: '#0f172a',
                fontSize: '0.8rem',
                fontFamily: '"Inter", sans-serif',
                fontWeight: 500,
                borderRadius: '8px',
                '& .MuiOutlinedInput-notchedOutline': { borderColor: '#e2e8f0' },
              }}
            >
              <MenuItem value="all" sx={{ fontSize: '0.8rem', fontWeight: 700 }}>
                🌐 All Farms
              </MenuItem>
              {farms.map((farm) => (
                <MenuItem key={farm.id} value={farm.id} sx={{ fontSize: '0.8rem' }}>
                  🏡 {farm.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      )}

      <List sx={{ px: 2, py: 1, flexGrow: 1 }}>
        {navItems
          .filter((item) => hasPermission(item.permission))
          .map((item) => {
            const isSelected = location.pathname === item.path
            return (
              <ListItem key={item.path} disablePadding sx={{ mb: 0.5 }}>
                <ListItemButton
                  selected={isSelected}
                  onClick={() => { navigate(item.path); onClose() }}
                  sx={{
                    borderRadius: '8px',
                    py: 1,
                    px: 1.5,
                    position: 'relative',
                    transition: 'all 0.15s ease-in-out',
                    backgroundColor: isSelected ? '#e8f5e9 !important' : 'transparent',
                    color: isSelected ? '#10b981' : '#475569',
                    '&:hover': {
                      backgroundColor: '#f8fafc',
                      color: '#0f172a',
                      '& .MuiListItemIcon-root': {
                        color: '#0f172a'
                      }
                    },
                    '& .MuiListItemIcon-root': {
                      color: isSelected ? '#10b981' : '#475569',
                      minWidth: 32,
                      '& svg': {
                        fontSize: '1.25rem'
                      }
                    }
                  }}
                >
                  <ListItemIcon>{item.icon}</ListItemIcon>
                  <ListItemText 
                    primary={item.label} 
                    primaryTypographyProps={{
                      fontFamily: '"Inter", sans-serif',
                      fontWeight: isSelected ? 600 : 500,
                      fontSize: '0.875rem'
                    }}
                  />
                </ListItemButton>
              </ListItem>
            )
          })}
      </List>

      {/* Bottom: COOP STATUS + Logout */}
      <Box sx={{ mt: 'auto', borderTop: '1px solid #f1f5f9' }}>
        <Box sx={{ p: 2.5, pb: 1 }}>
          <Card sx={{ bgcolor: '#ffffff', border: '1px solid #e2e8f0', p: 2, borderRadius: '12px', boxShadow: 'none', '&:hover': {} }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#475569', letterSpacing: '0.05em', display: 'block', mb: 1.5, fontSize: '0.7rem' }}>
              COOP STATUS
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <Box sx={{ position: 'relative', display: 'inline-flex' }}>
                <svg width="96" height="96" viewBox="0 0 96 96">
                  <circle cx="48" cy="48" r={radius} fill="transparent" stroke="#f1f5f9" strokeWidth={strokeWidth} />
                  <circle cx="48" cy="48" r={radius} fill="transparent" stroke={dotColor} strokeWidth={strokeWidth} strokeDasharray={circumference} strokeDashoffset={strokeDashoffset} strokeLinecap="round" transform="rotate(-90 48 48)" />
                </svg>
                <Box sx={{ position: 'absolute', top: 0, left: 0, bottom: 0, right: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                  <Typography variant="h6" sx={{ fontWeight: 800, fontSize: '1.35rem', color: '#0f172a', lineHeight: 1.1 }}>
                    {healthIndex}%
                  </Typography>
                  <Typography variant="caption" sx={{ fontSize: '0.55rem', fontWeight: 800, color: '#64748b', letterSpacing: '0.04em', mt: 0.15 }}>
                    HEALTH INDEX
                  </Typography>
                </Box>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mt: 1.5 }}>
                <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: dotColor, animation: 'pulse 2s infinite', '@keyframes pulse': { '0%': { transform: 'scale(1)', opacity: 1 }, '50%': { transform: 'scale(1.3)', opacity: 0.5 }, '100%': { transform: 'scale(1)', opacity: 1 } } }} />
                <Typography variant="caption" sx={{ color: '#475569', fontWeight: 600, fontSize: '0.75rem' }}>
                  {statusText}
                </Typography>
              </Box>
            </Box>
          </Card>
        </Box>
        <ListItem disablePadding sx={{ px: 2, pb: 2 }}>
          <ListItemButton
            onClick={() => { logout(); navigate('/') }}
            sx={{ borderRadius: '8px', py: 1, px: 1.5, color: '#ef4444', '&:hover': { backgroundColor: '#fef2f2' } }}
          >
            <ListItemIcon sx={{ color: '#ef4444', minWidth: 32 }}><LogoutIcon /></ListItemIcon>
            <ListItemText primary="Logout" primaryTypographyProps={{ fontFamily: '"Inter", sans-serif', fontWeight: 500, fontSize: '0.875rem' }} />
          </ListItemButton>
        </ListItem>
      </Box>
    </Box>
  )

  return (
    <>
      <Drawer
        variant="temporary"
        open={open}
        onClose={onClose}
        sx={{ display: { xs: 'block', md: 'none' }, '& .MuiDrawer-paper': { width: DRAWER_WIDTH, borderRight: '1px solid #e2e8f0', bgcolor: '#ffffff' } }}
      >
        {content}
      </Drawer>
      <Drawer
        variant="permanent"
        sx={{ display: { xs: 'none', md: 'block' }, '& .MuiDrawer-paper': { width: DRAWER_WIDTH, borderRight: '1px solid #e2e8f0', bgcolor: '#ffffff' } }}
        open
      >
        {content}
      </Drawer>
    </>
  )
}
