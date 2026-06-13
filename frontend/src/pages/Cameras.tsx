import { useState, useEffect, useCallback } from 'react'
import Grid from '@mui/material/Grid'
import {
  Box, Typography, Button, Card, CardContent, CardActions,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  IconButton, Chip,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import WifiFindIcon from '@mui/icons-material/WifiFind'
import { useCameras } from '../hooks/useCameras'
import { useAuth } from '../auth/AuthContext'
import { ONVIFScanModal } from '../components/ONVIFScanModal'
import type { DetectionStats, ONVIFDevice, ONVIFChannel } from '../types'

export default function Cameras() {
  const { cameras, loading, addCamera, updateCamera, deleteCamera, startScan, getScanResults, startDetection, stopDetection, getDetectionStats } = useCameras()
  const [detecting, setDetecting] = useState<Record<string, boolean>>({})
  const [stats, setStats] = useState<Record<string, DetectionStats>>({})

  const pollStats = useCallback(async () => {
    for (const cam of cameras) {
      if (detecting[cam.id]) {
        try {
          const s = await getDetectionStats(cam.id)
          setStats((prev) => ({ ...prev, [cam.id]: s }))
        } catch { /* ignore */ }
      }
    }
  }, [cameras, detecting, getDetectionStats])

  useEffect(() => {
    if (Object.values(detecting).some(Boolean)) {
      pollStats()
      const interval = setInterval(pollStats, 5000)
      return () => clearInterval(interval)
    }
  }, [detecting, pollStats])
  const { hasPermission } = useAuth()
  const [open, setOpen] = useState(false)
  const [scanOpen, setScanOpen] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', rtsp_url: '', location: '', zone: '', fps_target: 5, username: '', password: '' })

  const handleOpen = (cam?: (typeof cameras)[0]) => {
    if (cam) {
      setEditId(cam.id)
      setForm({ name: cam.name, rtsp_url: cam.rtsp_url, location: cam.location || '', zone: cam.zone || '', fps_target: cam.fps_target, username: '', password: '' })
    } else {
      setEditId(null)
      setForm({ name: '', rtsp_url: '', location: '', zone: '', fps_target: 5, username: '', password: '' })
    }
    setOpen(true)
  }

  const handleSave = async () => {
    if (editId) {
      await updateCamera(editId, form)
    } else {
      await addCamera(form)
    }
    setOpen(false)
  }

  const handleDelete = async (id: string) => {
    if (confirm('Delete this camera?')) {
      await deleteCamera(id)
    }
  }

  const handleAddFromScan = async (device: ONVIFDevice, channel?: ONVIFChannel) => {
    if (channel) {
      await addCamera({
        name: channel.name || `Camera ${device.ip} - Ch ${channel.channel}`,
        rtsp_url: channel.rtsp_url || `rtsp://${device.ip}:554/stream1`,
        location: '',
        zone: `Channel ${channel.channel}`,
        fps_target: 5,
      } as Parameters<typeof addCamera>[0])
    } else {
      for (const ch of device.channels) {
        if (ch.rtsp_url) {
          await addCamera({
            name: ch.name || `Camera ${device.ip} - Ch ${ch.channel}`,
            rtsp_url: ch.rtsp_url,
            location: '',
            zone: `Channel ${ch.channel}`,
            fps_target: 5,
          } as Parameters<typeof addCamera>[0])
        }
      }
    }
    setScanOpen(false)
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Cameras</Typography>
          <Typography variant="body2" color="text.secondary">Register and manage RTSP streams or discover local ONVIF nodes</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1.5 }}>
          {hasPermission('cameras:scan') && (
            <Button variant="outlined" startIcon={<WifiFindIcon />} onClick={async () => { setScanOpen(true); await startScan() }}>
              Scan Network
            </Button>
          )}
          {hasPermission('cameras:write') && (
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => handleOpen()}>
              Add Camera
            </Button>
          )}
        </Box>
      </Box>

      <Grid container spacing={3}>
        {cameras.map((cam) => (
          <Grid item xs={12} sm={6} md={4} key={cam.id}>
            <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                  <Typography variant="h6" sx={{ fontFamily: '"Outfit", sans-serif', fontWeight: 700 }}>
                    {cam.name}
                  </Typography>
                  <Chip
                    label={cam.status.toUpperCase()}
                    size="small"
                    color={cam.status === 'online' ? 'success' : cam.status === 'error' ? 'error' : 'default'}
                    sx={{
                      fontFamily: '"Outfit", sans-serif',
                      fontWeight: 700,
                      fontSize: '9px',
                      borderRadius: '6px',
                    }}
                  />
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  📍 {cam.location || 'No location set'}
                </Typography>
                <Box 
                  sx={{ 
                    bgcolor: 'rgba(0,0,0,0.2)', 
                    p: 1, 
                    borderRadius: '6px', 
                    border: '1px solid rgba(255,255,255,0.05)',
                    mb: 1.5,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}
                >
                  <Typography 
                    variant="caption" 
                    sx={{ 
                      fontFamily: '"JetBrains Mono", monospace', 
                      fontSize: '11px', 
                      color: 'text.secondary' 
                    }}
                  >
                    {cam.rtsp_url}
                  </Typography>
                </Box>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', fontFamily: '"JetBrains Mono", monospace' }}>
                  RESOLUTION: {cam.resolution_width}x{cam.resolution_height} | FPS: {cam.fps_target}
                </Typography>
                {detecting[cam.id] && stats[cam.id] && (
                  <Box sx={{ display: 'flex', gap: 2, mt: 1.5, p: 1, bgcolor: 'rgba(0,200,83,0.05)', borderRadius: '6px', border: '1px solid rgba(0,200,83,0.15)' }}>
                    <Box sx={{ textAlign: 'center' }}>
                      <Typography variant="h6" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 700, color: 'success.light', lineHeight: 1 }}>
                        {stats[cam.id].total_detections}
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '9px' }}>DETECTIONS</Typography>
                    </Box>
                    <Box sx={{ textAlign: 'center' }}>
                      <Typography variant="h6" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 700, color: 'info.light', lineHeight: 1 }}>
                        {stats[cam.id].unique_chickens}
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '9px' }}>CHICKENS</Typography>
                    </Box>
                    <Box sx={{ textAlign: 'center' }}>
                      <Typography variant="h6" sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 700, color: 'warning.light', lineHeight: 1 }}>
                        {stats[cam.id].detections_per_minute.toFixed(0)}
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '9px' }}>/MIN</Typography>
                    </Box>
                  </Box>
                )}
              </CardContent>
              <CardActions sx={{ borderTop: '1px solid rgba(255,255,255,0.03)', px: 2, py: 1, justifyContent: 'space-between', gap: 1 }}>
                <Box>
                  {hasPermission('cameras:write') && cam.status === 'online' && (
                    <Button
                      size="small"
                      variant={detecting[cam.id] ? 'contained' : 'outlined'}
                      color={detecting[cam.id] ? 'success' : 'inherit'}
                      sx={{ fontSize: '10px', fontFamily: '"JetBrains Mono", monospace' }}
                      onClick={async () => {
                        if (detecting[cam.id]) {
                          await stopDetection(cam.id)
                          setDetecting((p) => ({ ...p, [cam.id]: false }))
                          setStats((p) => { const s = { ...p }; delete s[cam.id]; return s })
                        } else {
                          await startDetection(cam.id)
                          setDetecting((p) => ({ ...p, [cam.id]: true }))
                          try {
                            const s = await getDetectionStats(cam.id)
                            setStats((prev) => ({ ...prev, [cam.id]: s }))
                          } catch { /* ignore */ }
                        }
                      }}
                    >
                      {detecting[cam.id] ? 'AI ON' : 'AI OFF'}
                    </Button>
                  )}
                </Box>
                <Box sx={{ display: 'flex', gap: 0.5 }}>
                  {hasPermission('cameras:write') && (
                    <IconButton size="small" sx={{ color: '#7d7aff' }} onClick={() => handleOpen(cam)}><EditIcon fontSize="small" /></IconButton>
                  )}
                  {hasPermission('cameras:delete') && (
                    <IconButton size="small" color="error" onClick={() => handleDelete(cam.id)}><DeleteIcon fontSize="small" /></IconButton>
                  )}
                </Box>
              </CardActions>
            </Card>
          </Grid>
        ))}
        {!loading && cameras.length === 0 && (
          <Grid item xs={12}>
            <Typography variant="body1" color="text.secondary" align="center" sx={{ py: 8 }}>
              No cameras yet. Add one manually or scan the network.
            </Typography>
          </Grid>
        )}
      </Grid>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editId ? 'Edit Camera' : 'Add Camera'}</DialogTitle>
        <DialogContent>
          <TextField fullWidth label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} margin="normal" required />
          <TextField fullWidth label="RTSP URL" value={form.rtsp_url} onChange={(e) => setForm({ ...form, rtsp_url: e.target.value })} margin="normal" required />
          <TextField fullWidth label="Location (e.g. Pen A)" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} margin="normal" />
          <TextField fullWidth label="Zone" value={form.zone} onChange={(e) => setForm({ ...form, zone: e.target.value })} margin="normal" />
          <TextField fullWidth label="FPS Target" type="number" value={form.fps_target} onChange={(e) => setForm({ ...form, fps_target: parseInt(e.target.value) || 5 })} margin="normal" />
          <TextField fullWidth label="Username (optional)" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} margin="normal" />
          <TextField fullWidth label="Password (optional)" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} margin="normal" />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleSave}>{editId ? 'Save' : 'Add'}</Button>
        </DialogActions>
      </Dialog>

      <ONVIFScanModal
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        onAddDevice={handleAddFromScan}
        getResults={getScanResults}
        startScan={startScan}
      />
    </Box>
  )
}
