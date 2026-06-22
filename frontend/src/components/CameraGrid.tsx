import { Link } from 'react-router-dom'
import Grid from '@mui/material/Grid'
import { Box, Typography, CircularProgress } from '@mui/material'
import { useCameras } from '../hooks/useCameras'
import { CameraFeed } from './CameraFeed'

export function CameraGrid({ compact = true }: { compact?: boolean }) {
  const { cameras, loading } = useCameras()

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>

  if (cameras.length === 0) {
    return (
      <Typography variant="body1" color="text.secondary" align="center" sx={{ py: 8 }}>
        No cameras configured. <Link to="/live" style={{ color: '#10b981', fontWeight: 600, textDecoration: 'none' }}>Go to Live Feed</Link> to add one.
      </Typography>
    )
  }

  const displayCameras = compact ? cameras.slice(0, 4) : cameras

  return (
    <Grid container spacing={2}>
      {displayCameras.map((cam) => (
        <Grid item xs={12} sm={6} md={6} lg={compact ? false : 4} key={cam.id}>
          <CameraFeed
            id={cam.id}
            name={cam.name}
            hlsUrl={cam.hls_url}
            rtspUrl={cam.rtsp_url}
            status={cam.status}
            compact={compact}
          />
        </Grid>
      ))}
    </Grid>
  )
}
