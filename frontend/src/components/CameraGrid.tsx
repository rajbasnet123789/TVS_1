import { useState } from 'react'
import { Link } from 'react-router-dom'
import Grid from '@mui/material/Grid'
import { Box, Typography, CircularProgress } from '@mui/material'
import { useCameras } from '../hooks/useCameras'
import { CameraFeed } from './CameraFeed'
import { CameraVideoModal } from './CameraVideoModal'

interface CameraGridProps {
  compact?: boolean
  onDelete?: (cam: { id: string; name: string }) => void
}

export function CameraGrid({ compact = true, onDelete }: CameraGridProps) {
  const { cameras, loading } = useCameras()
  const [modalCam, setModalCam] = useState<{ id: string; name: string } | null>(null)

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
    <>
      <Grid container spacing={2}>
        {displayCameras.map((cam) => (
          <Grid item xs={12} sm={6} md={6} lg={compact ? false : 4} key={cam.id}>
            <CameraFeed
              id={cam.id}
              name={cam.name}
              status={cam.status}
              compact={compact}
              onClick={() => setModalCam({ id: cam.id, name: cam.name })}
              onDelete={onDelete ? () => onDelete(cam) : undefined}
            />
          </Grid>
        ))}
      </Grid>
      {modalCam && (
        <CameraVideoModal
          cameraId={modalCam.id}
          cameraName={modalCam.name}
          open
          onClose={() => setModalCam(null)}
        />
      )}
    </>
  )
}
