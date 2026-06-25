import { useState, useEffect } from 'react'
import {
  Box, Typography, Card, CardContent, Grid, CircularProgress,
  Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Paper, Chip, Button,
} from '@mui/material'
import DownloadIcon from '@mui/icons-material/Download'
import api from '../api/axios'
import type { Camera } from '../types'
import { useAuth } from '../auth/AuthContext'

interface CamStats {
  id: string
  name: string
  total_detections: number
  unique_chickens: number
  peak_head_count: number
  avg_confidence: number
  detections_per_hour: number
}

export default function Reports() {
  const { currentFarm } = useAuth()
  const [cameras, setCameras] = useState<Camera[]>([])
  const [stats, setStats] = useState<CamStats[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchReports = async () => {
      setLoading(true)
      try {
        const camRes = await api.get('/cameras')
        const camerasData: Camera[] = camRes.data
        setCameras(camerasData)

        const results: CamStats[] = []
        for (const cam of camerasData) {
          try {
            const { data } = await api.get(`/cameras/${cam.id}/detection/summary`)
            results.push({
              id: cam.id,
              name: cam.name,
              total_detections: data.total_detections || 0,
              unique_chickens: data.unique_chickens || 0,
              peak_head_count: data.peak_head_count || 0,
              avg_confidence: data.avg_confidence || 0,
              detections_per_hour: data.detections_per_hour || 0,
            })
          } catch {
            results.push({ id: cam.id, name: cam.name, total_detections: 0, unique_chickens: 0, peak_head_count: 0, avg_confidence: 0, detections_per_hour: 0 })
          }
        }
        setStats(results)
      } catch { /* ignore */ }
      setLoading(false)
    }
    fetchReports()
  }, [currentFarm])

  const exportCSV = () => {
    const headers = ['Camera','Total Detections','Unique Chickens','Peak Headcount','Avg Confidence','Detections/hr']
    const rows = stats.map((s) => [s.name, s.total_detections, s.unique_chickens, s.peak_head_count, (s.avg_confidence * 100).toFixed(1) + '%', s.detections_per_hour.toFixed(1)])
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `detection-report-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>

  const totals = stats.reduce((acc, s) => ({
    detections: acc.detections + s.total_detections,
    unique: acc.unique + s.unique_chickens,
    peak: Math.max(acc.peak, s.peak_head_count),
  }), { detections: 0, unique: 0, peak: 0 })

  return (
    <Box>
      <Box sx={{ 
        mb: 3, 
        display: 'flex', 
        flexDirection: { xs: 'column', sm: 'row' }, 
        justifyContent: 'space-between', 
        alignItems: { xs: 'flex-start', sm: 'center' }, 
        gap: { xs: 2, sm: 0 } 
      }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Reports</Typography>
          <Typography variant="body2" color="text.secondary">
            Detection summary across {cameras.length} camera(s)
          </Typography>
        </Box>
        {stats.length > 0 && (
          <Button variant="outlined" startIcon={<DownloadIcon />} onClick={exportCSV} sx={{ width: { xs: '100%', sm: 'auto' } }}>
            Export CSV
          </Button>
        )}
      </Box>

      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#5e5ce6' }}>{totals.detections.toLocaleString()}</Typography>
              <Typography variant="body2" color="text.secondary">Total Detections</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#10b981' }}>{totals.unique}</Typography>
              <Typography variant="body2" color="text.secondary">Unique Chickens</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#f59e0b' }}>{totals.peak}</Typography>
              <Typography variant="body2" color="text.secondary">Peak Headcount</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {stats.length === 0 ? (
        <Paper sx={{ p: 6, textAlign: 'center', border: '1px solid #e2e8f0', boxShadow: 'none' }}>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>No Data</Typography>
          <Typography variant="body2" color="text.secondary">No cameras configured or detection data available.</Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper} sx={{ border: '1px solid #e2e8f0', boxShadow: 'none', overflowX: 'auto', width: '100%' }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Camera</TableCell>
                <TableCell align="right">Total Detections</TableCell>
                <TableCell align="right">Unique Chickens</TableCell>
                <TableCell align="right" sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Peak Headcount</TableCell>
                <TableCell align="right" sx={{ display: { xs: 'none', md: 'table-cell' } }}>Avg Confidence</TableCell>
                <TableCell align="right" sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Detections / hr</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {stats.map((s) => (
                <TableRow key={s.id} hover>
                  <TableCell sx={{ fontWeight: 600 }}>{s.name}</TableCell>
                  <TableCell align="right" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 600 }}>{s.total_detections.toLocaleString()}</TableCell>
                  <TableCell align="right" sx={{ fontFamily: '"JetBrains Mono", monospace' }}>{s.unique_chickens}</TableCell>
                  <TableCell align="right" sx={{ display: { xs: 'none', sm: 'table-cell' }, fontFamily: '"JetBrains Mono", monospace' }}>{s.peak_head_count}</TableCell>
                  <TableCell align="right" sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                    <Chip
                      label={(s.avg_confidence * 100).toFixed(0) + '%'}
                      size="small"
                      color={s.avg_confidence >= 0.8 ? 'success' : s.avg_confidence >= 0.5 ? 'warning' : 'error'}
                      sx={{ fontWeight: 600, fontSize: '0.75rem', borderRadius: '6px' }}
                    />
                  </TableCell>
                  <TableCell align="right" sx={{ display: { xs: 'none', sm: 'table-cell' }, fontFamily: '"JetBrains Mono", monospace' }}>{s.detections_per_hour.toFixed(1)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  )
}
