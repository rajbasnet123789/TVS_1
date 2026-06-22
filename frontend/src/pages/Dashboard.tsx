import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import Grid from '@mui/material/Grid'
import {
  Card, CardContent, Typography, Box, CircularProgress, Button, IconButton,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  LinearProgress, Chip, Alert
} from '@mui/material'
import { ChickenIcon } from '../layout/Sidebar'
import VideocamOutlinedIcon from '@mui/icons-material/VideocamOutlined'
import FavoriteBorderIcon from '@mui/icons-material/FavoriteBorder'
import ShieldOutlinedIcon from '@mui/icons-material/ShieldOutlined'
import OpenInFullIcon from '@mui/icons-material/OpenInFull'
import VideocamOffOutlinedIcon from '@mui/icons-material/VideocamOffOutlined'
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import ThermostatIcon from '@mui/icons-material/Thermostat'
import CloudQueueIcon from '@mui/icons-material/CloudQueue'
import WaterDropOutlinedIcon from '@mui/icons-material/WaterDropOutlined'
import AirIcon from '@mui/icons-material/Air'
import HeartIcon from '@mui/icons-material/Favorite'
import DirectionsWalkIcon from '@mui/icons-material/DirectionsWalk'
import PersonOutlineIcon from '@mui/icons-material/PersonOutline'
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew'
import AddIcon from '@mui/icons-material/Add'
import MapOutlinedIcon from '@mui/icons-material/MapOutlined'
import VideocamIcon from '@mui/icons-material/Videocam'
import BusinessIcon from '@mui/icons-material/Business'

import api from '../api/axios'
import { StatCard } from '../components/StatCard'
import { CameraFeed } from '../components/CameraFeed'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuth } from '../auth/AuthContext'

interface LogEntry {
  time: string
  type: string
  title: string
  text: string
  iconType: 'health' | 'movement' | 'sensor' | 'camera' | 'system' | 'intruder'
  color: string
}

export default function Dashboard() {
  const { user, farms, currentFarm, setCurrentFarm } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState({ chickens: 0, cameras: 0, onlineCameras: 0, healthyPct: 0, alerts: 0 })
  const [cameras, setCameras] = useState<any[]>([])
  const [detectedChickens, setDetectedChickens] = useState<any[]>([])
  const [coops, setCoops] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [clockTime, setClockTime] = useState('')
  const [activeIntruderAlert, setActiveIntruderAlert] = useState<any>(null)
  
  const [temp, setTemp] = useState<number | null>(null)
  const [ammonia, setAmmonia] = useState<number | null>(null)
  const [humidity, setHumidity] = useState<number | null>(null)
  const [windSpeed, setWindSpeed] = useState<number | null>(null)

  const [penAActive, setPenAActive] = useState(false)
  const [penBActive, setPenBActive] = useState(false)
  const penATimeout = useRef<number>()
  const penBTimeout = useRef<number>()

  // Calculate dynamic initials
  const initials = user?.full_name?.split(' ').map((n) => n[0]).join('').toUpperCase() || 'SA'

  // Live updated clock
  useEffect(() => {
    const updateClock = () => {
      const now = new Date()
      setClockTime(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }))
    }
    updateClock()
    const interval = setInterval(updateClock, 1000)
    return () => clearInterval(interval)
  }, [])

  // Fetch environment telemetry
  useEffect(() => {
    api.get('/environment').then(({ data }) => {
      if (data.status === 'available') {
        if (data.temperature != null) setTemp(data.temperature)
        if (data.ammonia != null) setAmmonia(data.ammonia)
        if (data.humidity != null) setHumidity(data.humidity)
        if (data.wind_speed != null) setWindSpeed(data.wind_speed)
      }
    }).catch(() => { })
  }, [])

  // Poll active stats and camera status
  useEffect(() => {
    const fetchStats = () => {
      Promise.all([
        api.get('/cameras').catch(() => ({ data: [] })),
        api.get('/chickens/detected', { params: { start: '-1h', end: 'now()' } }).catch(() => ({ data: [] })),
        api.get('/coops').catch(() => ({ data: [] })),
      ]).then(async ([camerasRes, detectedRes, coopsRes]) => {
        const camerasList = camerasRes.data
        const detected = detectedRes.data
        setCameras(camerasList)
        setCoops(coopsRes.data)
        setDetectedChickens(detected)

        const onlineCamerasList = camerasList.filter((c: any) => c.status === 'online')

        let totalDetections = 0
        let uniqueChickensCount = 0

        await Promise.all(
          onlineCamerasList.map(async (c: any) => {
            try {
              const { data } = await api.get(`/cameras/${c.id}/detection/stats`)
              totalDetections += data.total_detections || 0
              uniqueChickensCount += data.unique_chickens || 0
            } catch (err) { /* ignore */ }
          })
        )

        const alerts = camerasList.filter((c: any) => c.status === 'offline').length
        const healthyPct = Math.min(100, Math.round(
          (onlineCamerasList.length / Math.max(camerasList.length, 1)) * 60 +
          (uniqueChickensCount > 0 ? 40 : 0)
        ))

        setStats({
          chickens: detected.length > 0 ? detected.length : (uniqueChickensCount || 0),
          cameras: camerasList.length,
          onlineCameras: onlineCamerasList.length,
          healthyPct,
          alerts,
        })
      }).finally(() => setLoading(false))
    }

    fetchStats()
    const interval = setInterval(fetchStats, 5000)
    return () => {
      clearInterval(interval)
      if (penATimeout.current) window.clearTimeout(penATimeout.current)
      if (penBTimeout.current) window.clearTimeout(penBTimeout.current)
    }
  }, [currentFarm])

  // WebSocket alerts and telemetry listener
  useWebSocket({
    detection: (msg: any) => {
      const now = new Date()
      const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
      
      const camName = msg.camera_name || ''
      const isPenA = camName.toLowerCase().includes('pen a') || camName.toLowerCase().includes('main')
      
      // Update Pen Active State on Coop Map
      if (isPenA) {
        setPenAActive(true)
        if (penATimeout.current) window.clearTimeout(penATimeout.current)
        penATimeout.current = window.setTimeout(() => setPenAActive(false), 2500)
      } else {
        setPenBActive(true)
        if (penBTimeout.current) window.clearTimeout(penBTimeout.current)
        penBTimeout.current = window.setTimeout(() => setPenBActive(false), 2500)
      }

      if (msg.detections && msg.detections.length > 0) {
        const farmName = farms.find(f => f.id === msg.farm_id)?.name || ''
        const farmLabel = farmName ? `at ${farmName} ` : ''
        setLogs((prev) => {
          const logEntry: LogEntry = {
            time: timeStr,
            type: 'detection',
            title: 'Chickens detected',
            text: `Tracked ${msg.detections.length} chickens ${farmLabel}(${camName})`,
            iconType: 'sensor',
            color: '#10b981'
          }
          return [logEntry, ...prev.slice(0, 19)]
        })
      }
    },
    alert: (msg: any) => {
      const now = new Date()
      const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
      const farmName = farms.find(f => f.id === msg.farm_id)?.name || ''
      const farmLabel = farmName ? `[${farmName}] ` : ''
      
      const isIntruder = msg.alert_type === 'intruder'
      if (isIntruder) {
        setActiveIntruderAlert(msg)
      }

      setLogs((prev) => [
        {
          time: timeStr,
          type: isIntruder ? 'error' : 'warning',
          title: isIntruder ? 'CRITICAL INTRUDER' : 'Alert triggered',
          text: `${farmLabel}${msg.message || 'Anomaly detected'}`,
          iconType: isIntruder ? 'intruder' : 'movement',
          color: isIntruder ? '#ef4444' : '#f59e0b'
        },
        ...prev.slice(0, 19)
      ])
    },
    status: (msg: any) => {
      const now = new Date()
      const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
      const camName = msg.camera_name || 'Unknown camera'
      const farmName = farms.find(f => f.id === msg.farm_id)?.name || ''
      const farmLabel = farmName ? `at ${farmName} ` : ''
      const isOnline = msg.status === 'online'
      setLogs((prev) => [
        {
          time: timeStr,
          type: isOnline ? 'system' : 'camera',
          title: isOnline ? 'Camera reconnected' : 'Camera disconnected',
          text: `${camName} ${farmLabel}${isOnline ? 'came back online' : 'went offline'}`,
          iconType: isOnline ? 'system' : 'camera',
          color: isOnline ? '#10b981' : '#ef4444'
        },
        ...prev.slice(0, 19)
      ])
    }
  })

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>

  // Empty state: no cameras configured
  if (!loading && cameras.length === 0) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', textAlign: 'center', gap: 2.5 }}>
        <Box sx={{ width: 72, height: 72, borderRadius: '50%', bgcolor: '#e8f5e9', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <VideocamIcon sx={{ fontSize: 32, color: '#10b981' }} />
        </Box>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 800, color: '#0f172a', fontFamily: '"Outfit", sans-serif', mb: 0.5 }}>
            Welcome to Poultry Monitor
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748b', maxWidth: 440, mx: 'auto', lineHeight: 1.6 }}>
            This dashboard shows live camera feeds, detection analytics, and environmental data from your poultry coop. Get started by adding your first camera.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 1.5, mt: 1 }}>
          <Button variant="contained" size="large" startIcon={<AddIcon />} onClick={() => navigate('/live')}>
            Add Your First Camera
          </Button>
        </Box>
        <Box sx={{ display: 'flex', gap: 4, mt: 3, flexWrap: 'wrap', justifyContent: 'center' }}>
          {[
            { step: '1', title: 'Add a Camera', desc: 'Enter RTSP stream URL and credentials' },
            { step: '2', title: 'Connect Stream', desc: 'Frigate ingests RTSP and serves HLS to the dashboard' },
            { step: '3', title: 'View Live Detection', desc: 'AI identifies and tracks chickens automatically' },
          ].map((s) => (
            <Box key={s.step} sx={{ textAlign: 'center', maxWidth: 160 }}>
              <Box sx={{ width: 32, height: 32, borderRadius: '50%', bgcolor: '#0f172a', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', mx: 'auto', mb: 1, fontWeight: 800, fontSize: '0.85rem', fontFamily: '"Outfit", sans-serif' }}>
                {s.step}
              </Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#0f172a', fontFamily: '"Outfit", sans-serif', mb: 0.25 }}>
                {s.title}
              </Typography>
              <Typography variant="caption" sx={{ color: '#64748b' }}>
                {s.desc}
              </Typography>
            </Box>
          ))}
        </Box>
      </Box>
    )
  }

  // Timeline node icon rendering helper
  const getTimelineIcon = (iconType: string, color: string) => {
    const style = { fontSize: '0.9rem', color: '#ffffff' }
    const containerStyle = { 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      width: 24, 
      height: 24, 
      borderRadius: '50%', 
      bgcolor: color,
      flexShrink: 0
    }
    switch (iconType) {
      case 'health': return <Box sx={containerStyle}><HeartIcon sx={style} /></Box>
      case 'movement': return <Box sx={containerStyle}><DirectionsWalkIcon sx={style} /></Box>
      case 'sensor': return <Box sx={containerStyle}><PersonOutlineIcon sx={style} /></Box>
      case 'camera': return <Box sx={containerStyle}><VideocamOffOutlinedIcon sx={style} /></Box>
      case 'system': return <Box sx={containerStyle}><PowerSettingsNewIcon sx={style} /></Box>
      case 'intruder': return <Box sx={containerStyle}><ShieldOutlinedIcon sx={style} /></Box>
      default: return <Box sx={containerStyle}><PowerSettingsNewIcon sx={style} /></Box>
    }
  }

  const slots = cameras.map((c: any) => ({ id: c.id, name: c.name, location: c.location }))

  return (
    <Box sx={{ pb: 4 }}>
      {activeIntruderAlert && (
        <Alert 
          severity="error" 
          variant="filled"
          onClose={() => setActiveIntruderAlert(null)}
          sx={{ 
            mb: 3, 
            animation: 'pulse 1.5s infinite', 
            '@keyframes pulse': {
              '0%': { opacity: 1, transform: 'scale(1)' },
              '50%': { opacity: 0.85, transform: 'scale(1.005)' },
              '100%': { opacity: 1, transform: 'scale(1)' }
            },
            bgcolor: '#ef4444',
            color: '#fff',
            fontWeight: 800,
            fontSize: '1.05rem',
            border: '2px solid #b91c1c'
          }}
        >
          {activeIntruderAlert.message}
        </Alert>
      )}
      {/* 1. Inline Header Section */}
      <Box sx={{ 
        display: 'flex', 
        flexDirection: { xs: 'column', sm: 'row' }, 
        justifyContent: 'space-between', 
        alignItems: { xs: 'flex-start', sm: 'center' }, 
        gap: { xs: 2, sm: 0 },
        mb: 3.5 
      }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em', mb: 0.5, fontFamily: '"Outfit", sans-serif' }}>
            {currentFarm ? `${currentFarm.name} Overview` : 'Global Command'}
          </Typography>
          <Typography variant="body2" sx={{ color: '#64748b', fontWeight: 500 }}>
            {currentFarm ? 'Real-time status of your connected poultry coop' : 'Consolidated status and diagnostics across all poultry farms'}
          </Typography>
        </Box>
        <Box sx={{ 
          display: { xs: 'none', md: 'flex' }, 
          flexDirection: 'column', 
          alignItems: 'flex-end', 
          gap: 1 
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            {/* System Secure Indicator — derived from alert state */}
            {(() => {
              const alertLevel = stats.alerts === 0 ? 'secure' : stats.alerts === 1 ? 'attention' : 'critical'
              const colors = {
                secure: { bg: '#e8f5e9', border: '#10b981', dot: '#10b981', text: '#10b981', label: 'SYSTEM SECURE' },
                attention: { bg: '#fff7ed', border: '#f59e0b', dot: '#f59e0b', text: '#d97706', label: 'ATTENTION NEEDED' },
                critical: { bg: '#fef2f2', border: '#ef4444', dot: '#ef4444', text: '#dc2626', label: 'CRITICAL' },
              }
              const c = colors[alertLevel]
              return (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, bgcolor: c.bg, border: `1px solid ${c.border}`, px: 1.5, py: 0.5, borderRadius: '20px' }}>
                  <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: c.dot }} />
                  <Typography variant="caption" sx={{ fontFamily: '"Outfit", sans-serif', color: c.text, fontWeight: 700, fontSize: '0.675rem', letterSpacing: '0.02em' }}>
                    {c.label}
                  </Typography>
                </Box>
              )
            })()}

            {/* User Initials Avatar with arrow */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, cursor: 'pointer' }}>
              <Box 
                sx={{ 
                  width: 32, 
                  height: 32, 
                  bgcolor: '#0f172a',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                <Typography variant="caption" sx={{ color: '#ffffff', fontWeight: 700, fontSize: '0.85rem', fontFamily: '"Outfit", sans-serif' }}>
                  {initials}
                </Typography>
              </Box>
              <KeyboardArrowDownIcon sx={{ fontSize: '1rem', color: '#64748b' }} />
            </Box>
          </Box>
          <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 500, fontSize: '0.75rem', fontFamily: '"Inter", sans-serif' }}>
            Last updated: {clockTime}
          </Typography>
        </Box>
      </Box>

      {/* 2. Stat Cards Grid */}
      {currentFarm === null && user?.role?.name === 'super_admin' ? (
        <Grid container spacing={3} sx={{ mb: 4 }}>
          <Grid item xs={12} sm={6} md={6} lg={3}>
            <StatCard 
              title="Active Farms" 
              value={farms.length} 
              icon={<BusinessIcon />} 
              color="#10b981" 
              subtitle="Operational locations"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={6} lg={3}>
            <StatCard 
              title="Global Cameras" 
              value={`${stats.onlineCameras} / ${stats.cameras}`} 
              icon={<VideocamOutlinedIcon />} 
              color="#5e5ce6" 
              subtitle={stats.cameras - stats.onlineCameras > 0 ? `${stats.cameras - stats.onlineCameras} offline` : "All operational"}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={6} lg={3}>
            <StatCard 
              title="Total Chickens" 
              value={stats.chickens} 
              icon={<ChickenIcon />} 
              color="#f59e0b" 
              subtitle="Tracked globally"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={6} lg={3}>
            <StatCard 
              title="System Alerts" 
              value={stats.alerts} 
              icon={<ShieldOutlinedIcon />} 
              color="#ef4444" 
              subtitle={stats.alerts === 0 ? "All clear" : `${stats.alerts} offline devices`}
            />
          </Grid>
        </Grid>
      ) : (
        <Grid container spacing={3} sx={{ mb: 4 }}>
          <Grid item xs={12} sm={6} md={6} lg={3}>
            <StatCard 
              title="Active Chickens" 
              value={stats.chickens} 
              icon={<ChickenIcon />} 
              color="#10b981" 
              subtitle={stats.chickens > 0 ? "Tracking live" : "No chickens detected"}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={6} lg={3}>
            <StatCard 
              title="Cameras Online" 
              value={`${stats.onlineCameras} / ${stats.cameras}`} 
              icon={<VideocamOutlinedIcon />} 
              color="#5e5ce6" 
              subtitle={stats.cameras - stats.onlineCameras > 0 ? `${stats.cameras - stats.onlineCameras} offline` : "All operational"}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={6} lg={3}>
            <StatCard 
              title="Avg Health Index" 
              value={`${stats.healthyPct}%`} 
              icon={<FavoriteBorderIcon />} 
              color="#f59e0b" 
              subtitle={stats.healthyPct >= 80 ? 'Good condition' : stats.healthyPct >= 50 ? 'Fair condition' : 'At risk'}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={6} lg={3}>
            <StatCard 
              title="Active Alerts" 
              value={stats.alerts} 
              icon={<ShieldOutlinedIcon />} 
              color="#ef4444" 
              subtitle={stats.alerts === 0 ? "All clear" : `${stats.alerts} alerts pending`}
            />
          </Grid>
        </Grid>
      )}

      {/* 3. Middle Section: Map, Cameras, Timeline */}
      {currentFarm === null && user?.role?.name === 'super_admin' ? (
        <Grid container spacing={3} sx={{ mb: 4 }}>
          {/* A. Farms Overview Table */}
          <Grid item xs={12} lg={8}>
            <Card sx={{ height: '100%', border: '1px solid #e2e8f0', boxShadow: 'none', display: 'flex', flexDirection: 'column', p: 2.5 }}>
              <Box sx={{ mb: 2 }}>
                <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.7rem' }}>
                  SYSTEM REGISTRY
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#0f172a', fontSize: '1rem', mt: 0.1, fontFamily: '"Outfit", sans-serif' }}>
                  Farms Status & Performance
                </Typography>
              </Box>

              <TableContainer component={Paper} sx={{ border: '1px solid #e2e8f0', boxShadow: 'none', borderRadius: '8px', mt: 1, overflow: 'hidden' }}>
                <Table size="small">
                  <TableHead sx={{ bgcolor: '#f8fafc' }}>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 700, color: '#475569', py: 1.5 }}>Farm Name</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#475569', py: 1.5 }}>Location</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#475569', py: 1.5 }} align="center">Cameras</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#475569', py: 1.5 }} align="center">Active Chickens</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#475569', py: 1.5 }}>Health Status</TableCell>
                      <TableCell sx={{ fontWeight: 700, color: '#475569', py: 1.5 }} align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {farms.map((farm) => {
                      const farmCameras = cameras.filter((c: any) => c.farm_id === farm.id)
                      const totalCams = farmCameras.length
                      const onlineCams = farmCameras.filter((c: any) => c.status === 'online').length
                      
                      const farmCamIds = new Set(farmCameras.map((c: any) => c.id))
                      const farmChickens = detectedChickens.filter((ch: any) => 
                        ch.cameras && ch.cameras.some((camId: string) => farmCamIds.has(camId))
                      ).length

                      let healthStatus = 'Unconfigured'
                      let chipColor: 'default' | 'success' | 'warning' | 'error' = 'default'
                      if (totalCams > 0) {
                        const ratio = onlineCams / totalCams
                        if (ratio === 1.0) {
                          healthStatus = 'Optimal'
                          chipColor = 'success'
                        } else if (ratio > 0) {
                          healthStatus = 'Warning'
                          chipColor = 'warning'
                        } else {
                          healthStatus = 'Critical'
                          chipColor = 'error'
                        }
                      }

                      return (
                        <TableRow key={farm.id} sx={{ '&:last-child td': { border: 0 } }}>
                          <TableCell sx={{ fontWeight: 600, fontFamily: '"Outfit", sans-serif' }}>
                            🏡 {farm.name}
                          </TableCell>
                          <TableCell sx={{ color: 'text.secondary' }}>
                            {farm.location || '—'}
                          </TableCell>
                          <TableCell align="center" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 700 }}>
                            {onlineCams} / {totalCams}
                          </TableCell>
                          <TableCell align="center" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 700 }}>
                            {farmChickens}
                          </TableCell>
                          <TableCell>
                            <Chip label={healthStatus} size="small" color={chipColor} sx={{ fontWeight: 700, borderRadius: '6px', fontSize: '0.7rem' }} />
                          </TableCell>
                          <TableCell align="right">
                            <Button 
                              variant="outlined" 
                              size="small"
                              onClick={() => setCurrentFarm(farm)}
                              sx={{ 
                                textTransform: 'none', 
                                fontWeight: 700, 
                                borderRadius: '6px',
                                border: '1px solid #cbd5e1',
                                color: '#0f172a',
                                '&:hover': {
                                  borderColor: '#0f172a',
                                  bgcolor: 'rgba(15, 23, 42, 0.04)'
                                }
                              }}
                            >
                              Inspect
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </Card>
          </Grid>

          {/* B. Activity Timeline Card */}
          <Grid item xs={12} lg={4}>
            <Card sx={{ height: '100%', border: '1px solid #e2e8f0', boxShadow: 'none', display: 'flex', flexDirection: 'column', p: 2.5 }}>
              <Box sx={{ mb: 2.5 }}>
                <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.7rem' }}>
                  ACTIVITY TIMELINE
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#0f172a', fontSize: '1rem', mt: 0.1, fontFamily: '"Outfit", sans-serif' }}>
                  System logging events
                </Typography>
              </Box>

              <Box sx={{ position: 'relative', flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <Box sx={{ position: 'absolute', left: 20, top: 10, bottom: 10, width: '2px', bgcolor: '#f1f5f9', zIndex: 0 }} />

                {logs.length === 0 && (
                  <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 500, fontStyle: 'italic', textAlign: 'center', py: 4 }}>
                    Waiting for events…
                  </Typography>
                )}
                {logs.slice(0, 5).map((log, idx) => (
                  <Box key={idx} sx={{ display: 'flex', gap: 2.25, zIndex: 1, position: 'relative' }}>
                    <Box sx={{ flexShrink: 0, width: 40, display: 'flex', justifyContent: 'center' }}>
                      {getTimelineIcon(log.iconType, log.color)}
                    </Box>
                    <Box sx={{ minWidth: 0, mt: 0.25 }}>
                      <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', color: '#94a3b8', fontSize: '0.7rem', fontWeight: 700, display: 'block' }}>
                        {log.time}
                      </Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#0f172a', fontSize: '0.825rem', fontFamily: '"Outfit", sans-serif', mt: 0.1, lineHeight: 1.2 }}>
                        {log.title}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.75rem', fontWeight: 500, display: 'block', mt: 0.1 }}>
                        {log.text}
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </Box>

              <Box sx={{ pt: 2, borderTop: '1px solid #f1f5f9', mt: 'auto' }}>
                <Button 
                  variant="text" 
                  fullWidth 
                  endIcon={<ArrowForwardIcon sx={{ fontSize: '0.85rem' }} />} 
                  onClick={() => navigate('/analytics')}
                  sx={{ 
                    justifyContent: 'space-between', 
                    color: '#0f172a', 
                    fontFamily: '"Outfit", sans-serif', 
                    fontWeight: 700, 
                    fontSize: '0.8rem',
                    p: 0,
                    '&:hover': { bgcolor: 'transparent', color: '#10b981' }
                  }}
                >
                  View Full Timeline
                </Button>
              </Box>
            </Card>
          </Grid>

          {/* C. Global Video Wall */}
          {cameras.filter((c: any) => c.status === 'online').length > 0 && (
            <Grid item xs={12} sx={{ mt: 1 }}>
              <Card sx={{ border: '1px solid #e2e8f0', boxShadow: 'none', p: 2.5 }}>
                <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.7rem', display: 'block', mb: 2 }}>
                  GLOBAL VIDEO WALL
                </Typography>
                <Grid container spacing={2}>
                  {cameras.filter((c: any) => c.status === 'online').slice(0, 6).map((cam: any) => (
                    <Grid item xs={12} sm={6} md={4} key={cam.id}>
                      <Box sx={{ borderRadius: '12px', overflow: 'hidden', border: '1px solid #e2e8f0', aspectRatio: '16/9' }}>
                        <CameraFeed
                          id={cam.id}
                          name={`${cam.name} (${farms.find((f: any) => f.id === cam.farm_id)?.name || 'Unknown'})`}
                          hlsUrl={cam.hls_url}
                          rtspUrl={cam.rtsp_url}
                          status={cam.status}
                          compact
                        />
                      </Box>
                    </Grid>
                  ))}
                </Grid>
              </Card>
            </Grid>
          )}
        </Grid>
      ) : (
        <Grid container spacing={3} sx={{ mb: 4 }}>
          {/* A. Coop Map Card */}
          <Grid item xs={12} lg={5}>
            <Card sx={{ height: '100%', border: '1px solid #e2e8f0', boxShadow: 'none', display: 'flex', flexDirection: 'column', p: 2.5 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                <Box>
                  <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.7rem' }}>
                    COOP MAP
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700, color: '#0f172a', fontSize: '1rem', mt: 0.1, fontFamily: '"Outfit", sans-serif' }}>
                    Live overview of pen activity
                  </Typography>
                </Box>
                <IconButton size="small" sx={{ color: '#64748b' }} onClick={() => navigate('/coop-map')}>
                  <OpenInFullIcon sx={{ fontSize: '0.9rem' }} />
                </IconButton>
              </Box>

              {coops.length === 0 ? (
                <Box sx={{
                  flexGrow: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
                  justifyContent: 'center', borderRadius: '8px', border: '1px dashed #cbd5e1',
                  bgcolor: '#fafafa', mt: 1, minHeight: 280, gap: 1.5,
                }}>
                  <MapOutlinedIcon sx={{ fontSize: 40, color: '#cbd5e1' }} />
                  <Typography variant="subtitle2" sx={{ color: '#64748b', fontWeight: 700 }}>
                    No coop map configured yet
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#94a3b8', textAlign: 'center', maxWidth: 240 }}>
                    Create coops and assign cameras to see live pen activity at a glance.
                  </Typography>
                  <Button
                    variant="contained" size="small"
                    onClick={() => navigate('/coop-map')}
                    sx={{ mt: 0.5, textTransform: 'none', fontWeight: 700, borderRadius: '8px' }}
                  >
                    Add Map
                  </Button>
                </Box>
              ) : (
                <Box 
                  sx={{ 
                    flexGrow: 1,
                    position: 'relative', 
                    width: '100%', 
                    minHeight: 280, 
                    backgroundImage: 'radial-gradient(#cbd5e1 1.5px, transparent 1.5px)',
                    backgroundSize: '16px 16px',
                    bgcolor: '#f8fafc',
                    borderRadius: '8px',
                    border: '1px dashed #cbd5e1',
                    p: 2,
                    mt: 1,
                    overflow: 'hidden'
                  }}
                >
                  {/* Pen A Enclosure overlay */}
                  <Box
                    sx={{
                      position: 'absolute',
                      left: '12%',
                      top: '15%',
                      width: '34%',
                      height: '70%',
                      border: penAActive ? '2px dashed #10b981' : '2px dashed #cbd5e1',
                      borderRadius: '12px',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      bgcolor: penAActive ? 'rgba(232, 245, 233, 0.9)' : 'rgba(255, 255, 255, 0.85)',
                      backdropFilter: 'blur(2px)',
                      transition: 'all 0.3s ease',
                      boxShadow: penAActive ? '0 4px 15px rgba(16, 185, 129, 0.1)' : 'none'
                    }}
                  >
                    <Box 
                      sx={{ 
                        width: 8, 
                        height: 8, 
                        borderRadius: '50%', 
                        bgcolor: penAActive ? '#10b981' : '#94a3b8',
                        mb: 1,
                        boxShadow: penAActive ? '0 0 8px #10b981' : 'none'
                      }} 
                    />
                    <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#0f172a', fontSize: '0.8rem', letterSpacing: '0.05em' }}>
                      PEN A
                    </Typography>
                    <Typography variant="caption" sx={{ color: penAActive ? '#10b981' : '#64748b', fontWeight: 600, fontSize: '0.7rem' }}>
                      {penAActive ? 'Active' : 'No activity'}
                    </Typography>
                  </Box>

                  {/* Pen B Enclosure overlay */}
                  <Box
                    sx={{
                      position: 'absolute',
                      right: '12%',
                      top: '15%',
                      width: '34%',
                      height: '70%',
                      border: penBActive ? '2px dashed #10b981' : '2px dashed #cbd5e1',
                      borderRadius: '12px',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      bgcolor: penBActive ? 'rgba(232, 245, 233, 0.9)' : 'rgba(255, 255, 255, 0.85)',
                      backdropFilter: 'blur(2px)',
                      transition: 'all 0.3s ease',
                      boxShadow: penBActive ? '0 4px 15px rgba(16, 185, 129, 0.1)' : 'none'
                    }}
                  >
                    <Box 
                      sx={{ 
                        width: 8, 
                        height: 8, 
                        borderRadius: '50%', 
                        bgcolor: penBActive ? '#10b981' : '#94a3b8',
                        mb: 1,
                        boxShadow: penBActive ? '0 0 8px #10b981' : 'none'
                      }} 
                    />
                    <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#0f172a', fontSize: '0.8rem', letterSpacing: '0.05em' }}>
                      PEN B
                    </Typography>
                    <Typography variant="caption" sx={{ color: penBActive ? '#10b981' : '#64748b', fontWeight: 600, fontSize: '0.7rem' }}>
                      {penBActive ? 'Active' : 'No activity'}
                    </Typography>
                  </Box>
                </Box>
              )}
            </Card>
          </Grid>

          {/* B. Live Cameras Card */}
          <Grid item xs={12} md={6} lg={3.5}>
            <Card sx={{ height: '100%', border: '1px solid #e2e8f0', boxShadow: 'none', display: 'flex', flexDirection: 'column', p: 2.5 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                <Box>
                  <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.7rem' }}>
                    LIVE CAMERAS
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700, color: '#0f172a', fontSize: '1rem', mt: 0.1, fontFamily: '"Outfit", sans-serif' }}>
                    Feed viewport channels
                  </Typography>
                </Box>
                <Button 
                  variant="text" 
                  size="small" 
                  onClick={() => navigate('/live')}
                  sx={{ 
                    color: '#64748b', 
                    fontFamily: '"Outfit", sans-serif', 
                    fontWeight: 700, 
                    fontSize: '0.75rem',
                    p: 0,
                    minWidth: 0,
                    '&:hover': { backgroundColor: 'transparent', color: '#0f172a' }
                  }}
                >
                  View All
                </Button>
              </Box>

              {/* Cameras viewport list */}
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, flexGrow: 1, justifyContent: 'center' }}>
                {slots.map((slot) => {
                  const cam = cameras.find((c: any) => c.id === slot.id)
                  if (!cam) return null

                  return (
                    <Box key={cam.id} sx={{ position: 'relative', borderRadius: '12px', overflow: 'hidden' }}>
                      {cam.status === 'online' ? (
                        <Box sx={{ width: '100%', aspectRatio: '16/9' }}>
                          <CameraFeed
                            id={cam.id}
                            name={cam.name}
                            hlsUrl={cam.hls_url}
                            rtspUrl={cam.rtsp_url}
                            status={cam.status}
                            compact
                          />
                        </Box>
                      ) : (
                        <Box 
                          sx={{ 
                            bgcolor: '#f8fafc', 
                            borderRadius: '12px', 
                            p: 2, 
                            aspectRatio: '16/9',
                            position: 'relative', 
                            display: 'flex', 
                            flexDirection: 'column', 
                            justifyContent: 'center', 
                            alignItems: 'center',
                            border: '1px solid #e2e8f0'
                          }}
                        >
                          <Box sx={{ position: 'absolute', top: 10, left: 12 }}>
                            <Typography variant="caption" sx={{ fontWeight: 700, color: '#334155', fontSize: '0.75rem', fontFamily: '"Outfit", sans-serif' }}>
                              {cam.name}
                            </Typography>
                          </Box>
                          <Box sx={{ position: 'absolute', top: 10, right: 12 }}>
                            <Box sx={{ bgcolor: '#fee2e2', border: '1px solid #fecaca', px: 1, py: 0.1, borderRadius: '4px' }}>
                              <Typography variant="caption" sx={{ color: '#ef4444', fontWeight: 800, fontSize: '0.6rem' }}>
                                OFFLINE
                              </Typography>
                            </Box>
                          </Box>
                          <VideocamOffOutlinedIcon sx={{ fontSize: '1.75rem', color: '#94a3b8', mb: 0.5 }} />
                          <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 600, fontSize: '0.75rem', fontFamily: '"Inter", sans-serif' }}>
                            No Signal
                          </Typography>
                        </Box>
                      )}
                    </Box>
                  )
                })}
              </Box>
            </Card>
          </Grid>

          {/* C. Activity Timeline Card */}
          <Grid item xs={12} md={6} lg={3.5}>
            <Card sx={{ height: '100%', border: '1px solid #e2e8f0', boxShadow: 'none', display: 'flex', flexDirection: 'column', p: 2.5 }}>
              <Box sx={{ mb: 2.5 }}>
                <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.7rem' }}>
                  ACTIVITY TIMELINE
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#0f172a', fontSize: '1rem', mt: 0.1, fontFamily: '"Outfit", sans-serif' }}>
                  Coop logging events
                </Typography>
              </Box>

              {/* Vertical Timeline Box */}
              <Box sx={{ position: 'relative', flexGrow: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {/* Vertical connector line */}
                <Box 
                  sx={{ 
                    position: 'absolute', 
                    left: 20, 
                    top: 10, 
                    bottom: 10, 
                    width: '2px', 
                    bgcolor: '#f1f5f9',
                    zIndex: 0 
                  }} 
                />

                {logs.length === 0 && (
                  <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 500, fontStyle: 'italic', textAlign: 'center', py: 4 }}>
                    Waiting for events…
                  </Typography>
                )}
                {logs.slice(0, 5).map((log, idx) => (
                  <Box key={idx} sx={{ display: 'flex', gap: 2.25, zIndex: 1, position: 'relative' }}>
                    {/* Left Column Icon */}
                    <Box sx={{ flexShrink: 0, width: 40, display: 'flex', justifyContent: 'center' }}>
                      {getTimelineIcon(log.iconType, log.color)}
                    </Box>

                    {/* Right Column details */}
                    <Box sx={{ minWidth: 0, mt: 0.25 }}>
                      <Typography 
                        variant="caption" 
                        sx={{ 
                          fontFamily: '"JetBrains Mono", monospace', 
                          color: '#94a3b8', 
                          fontSize: '0.7rem', 
                          fontWeight: 700,
                          display: 'block' 
                        }}
                      >
                        {log.time}
                      </Typography>
                      <Typography 
                        variant="subtitle2" 
                        sx={{ 
                          fontWeight: 800, 
                          color: '#0f172a', 
                          fontSize: '0.825rem', 
                          fontFamily: '"Outfit", sans-serif',
                          mt: 0.1,
                          lineHeight: 1.2 
                        }}
                      >
                        {log.title}
                      </Typography>
                      <Typography 
                        variant="caption" 
                        sx={{ 
                          color: '#64748b', 
                          fontSize: '0.75rem', 
                          fontWeight: 500,
                          display: 'block', 
                          mt: 0.1 
                        }}
                      >
                        {log.text}
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </Box>

              {/* Footer View Full Timeline */}
              <Box sx={{ pt: 2, borderTop: '1px solid #f1f5f9', mt: 'auto' }}>
                <Button 
                  variant="text" 
                  fullWidth 
                  endIcon={<ArrowForwardIcon sx={{ fontSize: '0.85rem' }} />} 
                  onClick={() => navigate('/analytics')}
                  sx={{ 
                    justifyContent: 'space-between', 
                    color: '#0f172a', 
                    fontFamily: '"Outfit", sans-serif', 
                    fontWeight: 700, 
                    fontSize: '0.8rem',
                    p: 0,
                    '&:hover': { bgcolor: 'transparent', color: '#10b981' }
                  }}
                >
                  View Full Timeline
                </Button>
              </Box>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* 4. Environment Section (Bottom Row) */}
      {currentFarm === null && user?.role?.name === 'super_admin' ? (
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card sx={{ border: '1px solid #e2e8f0', boxShadow: 'none', display: 'flex', flexDirection: 'column', p: 3, textAlign: 'center', bgcolor: '#f8fafc', borderRadius: '12px' }}>
              <ThermostatIcon sx={{ fontSize: 40, color: '#94a3b8', mx: 'auto', mb: 1.5 }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#334155', fontFamily: '"Outfit", sans-serif', mb: 0.5 }}>
                Farm Telemetry Scope
              </Typography>
              <Typography variant="body2" sx={{ color: '#64748b', maxWidth: 520, mx: 'auto', lineHeight: 1.6 }}>
                Environmental IoT metrics (temperature, ammonia, humidity, wind speed) are captured locally per coop. Select a specific farm from the registry to view its telemetry.
              </Typography>
            </Card>
          </Grid>
        </Grid>
      ) : (
        <Grid container spacing={3}>
          {/* Environment Summary Grid & Banner */}
          <Grid item xs={12}>
            <Card sx={{ height: '100%', border: '1px solid #e2e8f0', boxShadow: 'none', display: 'flex', flexDirection: 'column', p: 0 }}>
              <Box sx={{ p: 2.5, pb: 1.5 }}>
                <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.08em', fontSize: '0.7rem' }}>
                  ENVIRONMENT SUMMARY
                </Typography>
              </Box>

              {/* Metrics detail row */}
              <Box sx={{ flexGrow: 1, px: 2.5, pb: 2 }}>
                {temp === null && humidity === null && ammonia === null && windSpeed === null ? (
                  <Box sx={{ textAlign: 'center', py: 4, color: '#94a3b8' }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      No IoT sensors connected
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#94a3b8', mt: 0.5 }}>
                      Connect an IoT gateway to receive environmental telemetry
                    </Typography>
                  </Box>
                ) : (
                <Grid container spacing={1} sx={{ textAlign: 'center', height: '100%', alignItems: 'center' }}>
                  {/* Temp */}
                  <Grid item xs={3}>
                    <Box sx={{ display: 'flex', justifyContent: 'center', mb: 1, color: '#475569' }}>
                      <ThermostatIcon />
                    </Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#0f172a', fontSize: '1rem', fontFamily: '"Outfit", sans-serif', lineHeight: 1.1 }}>
                      {temp != null ? `${temp}°C` : '—'}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.65rem', fontWeight: 600, display: 'block', mt: 0.25 }}>
                      Temperature
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#10b981', fontSize: '0.65rem', fontWeight: 700, display: 'block', mt: 0.1 }}>
                      Normal
                    </Typography>
                  </Grid>

                  {/* Ammonia */}
                  <Grid item xs={3}>
                    <Box sx={{ display: 'flex', justifyContent: 'center', mb: 1, color: '#475569' }}>
                      <CloudQueueIcon />
                    </Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#0f172a', fontSize: '1rem', fontFamily: '"Outfit", sans-serif', lineHeight: 1.1 }}>
                      {ammonia != null ? `${ammonia} ppm` : '—'}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.65rem', fontWeight: 600, display: 'block', mt: 0.25 }}>
                      Ammonia
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#10b981', fontSize: '0.65rem', fontWeight: 700, display: 'block', mt: 0.1 }}>
                      Normal
                    </Typography>
                  </Grid>

                  {/* Humidity */}
                  <Grid item xs={3}>
                    <Box sx={{ display: 'flex', justifyContent: 'center', mb: 1, color: '#475569' }}>
                      <WaterDropOutlinedIcon />
                    </Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#0f172a', fontSize: '1rem', fontFamily: '"Outfit", sans-serif', lineHeight: 1.1 }}>
                      {humidity != null ? `${humidity}%` : '—'}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.65rem', fontWeight: 600, display: 'block', mt: 0.25 }}>
                      Humidity
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#10b981', fontSize: '0.65rem', fontWeight: 700, display: 'block', mt: 0.1 }}>
                      Normal
                    </Typography>
                  </Grid>

                  {/* Wind Speed */}
                  <Grid item xs={3}>
                    <Box sx={{ display: 'flex', justifyContent: 'center', mb: 1, color: '#475569' }}>
                      <AirIcon />
                    </Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#0f172a', fontSize: '1rem', fontFamily: '"Outfit", sans-serif', lineHeight: 1.1 }}>
                      {windSpeed != null ? `${windSpeed} km/h` : '—'}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.65rem', fontWeight: 600, display: 'block', mt: 0.25 }}>
                      Wind Speed
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#10b981', fontSize: '0.65rem', fontWeight: 700, display: 'block', mt: 0.1 }}>
                      Normal
                    </Typography>
                  </Grid>
                </Grid>
                )}
              </Box>

              {/* Safety Banner Footer — derived from alert state */}
              {(() => {
                const alertLevel = stats.alerts === 0 ? 'secure' : stats.alerts === 1 ? 'attention' : 'critical'
                const banner = {
                  secure: { icon: '#10b981', text: '#10b981', bg: '#f0fdf4', msg: 'All systems are operating within normal parameters.' },
                  attention: { icon: '#d97706', text: '#92400e', bg: '#fffbeb', msg: '1 camera offline. Check connection or power supply.' },
                  critical: { icon: '#dc2626', text: '#991b1b', bg: '#fef2f2', msg: `${stats.alerts} cameras offline. Immediate attention required.` },
                }
                const b = banner[alertLevel]
                return (
                  <Box sx={{ bgcolor: b.bg, borderTop: '1px solid #e2e8f0', p: 2, display: 'flex', alignItems: 'center', gap: 1.25 }}>
                    <ShieldOutlinedIcon sx={{ color: b.icon, fontSize: '1.1rem' }} />
                    <Typography variant="caption" sx={{ color: b.text, fontWeight: 600, fontSize: '0.725rem', fontFamily: '"Inter", sans-serif' }}>
                      {b.msg}
                    </Typography>
                  </Box>
                )
              })()}
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  )
}
