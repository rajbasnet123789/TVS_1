import { useState, useEffect } from 'react'
import {
  Box, Typography, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Chip, Card, CardContent, Grid, CircularProgress,
} from '@mui/material'
import api from '../api/axios'

export default function Alerts() {
  const [cameras, setCameras] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/cameras').then(({ data }) => {
      setCameras(data)
    }).catch(() => setError('Failed to load cameras')).finally(() => setLoading(false))
  }, [])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  if (error) return <Typography color="error" align="center" sx={{ mt: 8 }}>{error}</Typography>

  const totalCameras = cameras.length
  const onlineCameras = cameras.filter((c: any) => c.status === 'online').length
  const offlineCameras = cameras.filter((c: any) => c.status === 'offline').length
  const errorCameras = cameras.filter((c: any) => c.status === 'error').length
  const alerts = cameras.filter((c: any) => c.status !== 'online')

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Alerts</Typography>
        <Typography variant="body2" color="text.secondary">
          {alerts.length > 0 ? `${alerts.length} active alert(s)` : 'All systems operational'}
        </Typography>
      </Box>

      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ border: '1px solid #e2e8f0', boxShadow: 'none' }}>
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#10b981' }}>{onlineCameras}</Typography>
              <Typography variant="body2" color="text.secondary">Cameras Online</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ border: '1px solid #e2e8f0', boxShadow: 'none' }}>
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#ef4444' }}>{offlineCameras}</Typography>
              <Typography variant="body2" color="text.secondary">Offline</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ border: '1px solid #e2e8f0', boxShadow: 'none' }}>
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#f59e0b' }}>{errorCameras}</Typography>
              <Typography variant="body2" color="text.secondary">Errors</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ border: '1px solid #e2e8f0', boxShadow: 'none' }}>
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#5e5ce6' }}>{totalCameras}</Typography>
              <Typography variant="body2" color="text.secondary">Total Cameras</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {alerts.length === 0 ? (
        <Paper sx={{ p: 6, textAlign: 'center', border: '1px solid #e2e8f0', boxShadow: 'none' }}>
          <Box sx={{ width: 48, height: 48, borderRadius: '50%', bgcolor: '#e8f5e9', display: 'flex', alignItems: 'center', justifyContent: 'center', mx: 'auto', mb: 2 }}>
            <Box sx={{ width: 20, height: 20, borderRadius: '50%', bgcolor: '#10b981' }} />
          </Box>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>All Clear</Typography>
          <Typography variant="body2" color="text.secondary">No active alerts at this time.</Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper} sx={{ border: '1px solid #e2e8f0', boxShadow: 'none' }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Camera</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Severity</TableCell>
                <TableCell>Message</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {alerts.map((cam: any) => (
                <TableRow key={cam.id} hover>
                  <TableCell sx={{ fontWeight: 600 }}>{cam.name || cam.id}</TableCell>
                  <TableCell>
                    <Chip
                      label={cam.status}
                      size="small"
                      color={cam.status === 'offline' ? 'error' : 'warning'}
                      sx={{ fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', borderRadius: '6px' }}
                    />
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={cam.status === 'error' ? 'High' : 'Medium'}
                      size="small"
                      color={cam.status === 'error' ? 'error' : 'warning'}
                      variant="outlined"
                      sx={{ fontWeight: 600, fontSize: '0.75rem', borderRadius: '6px' }}
                    />
                  </TableCell>
                  <TableCell sx={{ color: '#64748b' }}>
                    {cam.status === 'offline' ? 'Camera is not responding' : 'Camera encountered an error'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  )
}
