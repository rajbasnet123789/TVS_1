import { useState, useEffect } from 'react'
import { Box, Typography, Card, CardContent, CircularProgress, Grid, Chip, Alert } from '@mui/material'
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart,
} from 'recharts'
import PeopleIcon from '@mui/icons-material/People'
import RadarIcon from '@mui/icons-material/Radar'
import TimelineIcon from '@mui/icons-material/Timeline'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import api from '../api/axios'
import { StatCard } from '../components/StatCard'
import type { Camera } from '../types'
import { useAuth } from '../auth/AuthContext'

function useCombinedAnalytics() {
  const { currentFarm } = useAuth()
  const [cameras, setCameras] = useState<Camera[]>([])
  const [allHistory, setAllHistory] = useState<any>(null)
  const [allSummary, setAllSummary] = useState<any>(null)
  const [perCameraSummaries, setPerCameraSummaries] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [range, setRange] = useState<string>('-1h')

  const rangeToParams = (r: string) => {
    switch (r) {
      case '-15m': return { start: '-15m', end: 'now()', window: '1m' }
      case '-1h': return { start: '-1h', end: 'now()', window: '5m' }
      case '-6h': return { start: '-6h', end: 'now()', window: '15m' }
      case '-24h': return { start: '-24h', end: 'now()', window: '1h' }
      default: return { start: '-1h', end: 'now()', window: '5m' }
    }
  }

  const fetch = async (r: string) => {
    setLoading(true)
    setError(null)
    const params = rangeToParams(r)
    try {
      const camRes = await api.get('/cameras')
      const camerasData: Camera[] = camRes.data
      setCameras(camerasData)

      const [histRes] = await Promise.all([
        api.get('/detection/global/history', { params }),
      ])
      setAllHistory(histRes.data)

      let totalDetections = 0
      let totalUnique = 0
      let totalPeak = 0
      let totalConf = 0
      let totalActive = 0
      let cameraCount = 0

      const summaries: Record<string, any> = {}
      await Promise.all(
        camerasData.map(async (c) => {
          try {
            const sRes = await api.get(`/cameras/${c.id}/detection/summary`, {
              params: { start: params.start, end: params.end },
            })
            const s = sRes.data
            summaries[c.id] = s
            totalDetections += s.total_detections || 0
            totalUnique += s.unique_chickens || 0
            totalPeak = Math.max(totalPeak, s.peak_head_count || 0)
            totalConf += s.avg_confidence || 0
            totalActive += s.active_minutes || 0
            cameraCount++
          } catch { /* ignore */ }
        })
      )

      setPerCameraSummaries(summaries)
      setAllSummary({
        total_detections: totalDetections,
        unique_chickens: totalUnique,
        peak_head_count: totalPeak,
        avg_confidence: cameraCount > 0 ? +(totalConf / cameraCount).toFixed(3) : 0,
        active_minutes: totalActive,
        detections_per_hour: totalActive > 0 ? +(totalDetections / (totalActive / 60)).toFixed(1) : 0,
      })
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load analytics')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetch(range) }, [range, currentFarm])

  return { cameras, allHistory, allSummary, perCameraSummaries, loading, error, range, setRange, refresh: () => fetch(range) }
}

const RANGE_CHIPS = [
  { label: '15 min', value: '-15m' },
  { label: '1 hour', value: '-1h' },
  { label: '6 hours', value: '-6h' },
  { label: '24 hours', value: '-24h' },
]

function formatTime(time: string) {
  const d = new Date(time)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function CustomTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    return (
      <Box sx={{ bgcolor: 'background.paper', p: 1.5, borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)', boxShadow: 3 }}>
        <Typography variant="caption" sx={{ color: 'text.secondary', fontFamily: '"JetBrains Mono", monospace' }}>
          {formatTime(label)}
        </Typography>
        {payload.map((entry: any, i: number) => (
          <Typography key={i} variant="body2" sx={{ color: entry.color, fontWeight: 600 }}>
            {entry.name}: {entry.value}
          </Typography>
        ))}
      </Box>
    )
  }
  return null
}

export default function Analytics() {
  const { cameras, allHistory, allSummary, perCameraSummaries, loading, error, range, setRange, refresh } = useCombinedAnalytics()

  if (loading && !allHistory) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  }

  const detectionData = allHistory?.detection_series?.map((p: any) => ({
    time: p.time,
    Detections: p.value,
  })) || []

  const headcountData = allHistory?.headcount_series?.map((p: any) => ({
    time: p.time,
    'Head Count': p.value,
  })) || []

  return (
    <Box>
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Detection Analytics</Typography>
          <Typography variant="body2" color="text.secondary">
            Time-series analysis across {cameras.length} camera{cameras.length > 1 ? 's' : ''}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {RANGE_CHIPS.map((chip) => (
            <Chip
              key={chip.value}
              label={chip.label}
              onClick={() => setRange(chip.value)}
              variant={range === chip.value ? 'filled' : 'outlined'}
              color={range === chip.value ? 'primary' : 'default'}
              sx={{
                fontWeight: 600,
                fontFamily: '"Outfit", sans-serif',
                ...(range === chip.value ? {} : { borderColor: 'rgba(255,255,255,0.1)' }),
              }}
            />
          ))}
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => {}}>
          {error}
        </Alert>
      )}

      {allSummary && (
        <Grid container spacing={3} sx={{ mb: 4 }}>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Total Detections" value={allSummary.total_detections?.toLocaleString() || 0} icon={<RadarIcon />} color="#00f3ff" subtitle={allSummary.detections_per_hour > 0 ? `${allSummary.detections_per_hour}/hr` : undefined} />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Unique Chickens" value={allSummary.unique_chickens || 0} icon={<PeopleIcon />} color="#10b981" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Peak Head Count" value={allSummary.peak_head_count || 0} icon={<TimelineIcon />} color="#5e5ce6" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Avg Confidence" value={`${((allSummary.avg_confidence || 0) * 100).toFixed(1)}%`} icon={<CheckCircleIcon />} color="#f59e0b" />
          </Grid>
        </Grid>
      )}

      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} lg={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Detection Rate</Typography>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={detectionData}>
                  <defs>
                    <linearGradient id="detectionGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#00f3ff" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#00f3ff" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" tickFormatter={formatTime} stroke="rgba(255,255,255,0.3)" fontSize={11} fontFamily='"JetBrains Mono", monospace' />
                  <YAxis stroke="rgba(255,255,255,0.3)" fontSize={11} fontFamily='"JetBrains Mono", monospace' />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="Detections" stroke="#00f3ff" fill="url(#detectionGradient)" strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} lg={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Head Count</Typography>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={headcountData}>
                  <defs>
                    <linearGradient id="hcGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" tickFormatter={formatTime} stroke="rgba(255,255,255,0.3)" fontSize={11} fontFamily='"JetBrains Mono", monospace' />
                  <YAxis stroke="rgba(255,255,255,0.3)" fontSize={11} fontFamily='"JetBrains Mono", monospace' />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="Head Count" stroke="#10b981" fill="url(#hcGradient)" strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {cameras.map((camera) => {
          const s = perCameraSummaries[camera.id]
          if (!s) return null
          return (
            <Grid item xs={12} sm={6} md={4} key={camera.id}>
              <Card sx={{ opacity: camera.status === 'online' ? 1 : 0.5 }}>
                <CardContent>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5 }}>{camera.name}</Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="caption" color="text.secondary">Detections</Typography>
                      <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 600 }}>{s.total_detections?.toLocaleString() || 0}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="caption" color="text.secondary">Unique</Typography>
                      <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 600 }}>{s.unique_chickens || 0}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="caption" color="text.secondary">Peak Head Ct</Typography>
                      <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 600 }}>{s.peak_head_count || 0}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="caption" color="text.secondary">Confidence</Typography>
                      <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 600 }}>{((s.avg_confidence || 0) * 100).toFixed(1)}%</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="caption" color="text.secondary">Rate</Typography>
                      <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 600 }}>{s.detections_per_hour || 0}/hr</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          )
        })}
      </Grid>
    </Box>
  )
}
