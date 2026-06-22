import { useState, useRef, useEffect } from 'react'
import {
  Box, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Card, CardContent, CardActions, Grid, LinearProgress,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import { useCameras } from '../hooks/useCameras'
import { CameraGrid } from '../components/CameraGrid'
import { useAuth } from '../auth/AuthContext'
import type { DiscoveredDevice } from '../types'

export default function LiveFeed() {
  const { cameras, addCamera, scanNetwork, getScanStatus, getScanResults } = useCameras()
  const { hasPermission } = useAuth()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', rtsp_url: '', location: '', zone: '', fps_target: 5, username: '', password: '' })
  const [addError, setAddError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [scanDialogOpen, setScanDialogOpen] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [scanProgress, setScanProgress] = useState<number | null>(null)
  const [scanError, setScanError] = useState('')
  const [discoveredDevices, setDiscoveredDevices] = useState<DiscoveredDevice[]>([])
  const scanPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    return () => {
      if (scanPollRef.current) {
        clearInterval(scanPollRef.current)
      }
    }
  }, [])

  const handleClose = () => {
    if (submitting) return
    setOpen(false)
    setAddError('')
  }

  const handleOpen = () => {
    setForm({ name: '', rtsp_url: '', location: '', zone: '', fps_target: 5, username: '', password: '' })
    setAddError('')
    setOpen(true)
  }

  const handleAdd = async () => {
    if (submitting) return
    setAddError('')
    if (!form.name.trim() || !form.rtsp_url.trim()) {
      setAddError('Name and RTSP URL are required')
      return
    }
    setSubmitting(true)
    try {
      await addCamera({
        name: form.name,
        rtsp_url: form.rtsp_url,
        location: form.location || undefined,
        zone: form.zone || undefined,
        fps_target: form.fps_target,
        username: form.username || undefined,
        password: form.password || undefined,
      })
      setOpen(false)
      setForm({ name: '', rtsp_url: '', location: '', zone: '', fps_target: 5, username: '', password: '' })
      setAddError('')
    } catch (e: any) {
      setAddError(e?.response?.data?.detail || 'Failed to add camera')
    } finally {
      setSubmitting(false)
    }
  }

  const isFirstCamera = cameras.length === 0

  return (
    <Box>
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Live Feed</Typography>
          <Typography variant="body2" color="text.secondary">
            {cameras.length > 0
              ? `Real-time video feeds from ${cameras.length} camera${cameras.length !== 1 ? 's' : ''}`
              : 'No cameras configured yet'}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1.5 }}>
          {hasPermission('cameras:scan') && (
            <Button variant="outlined" startIcon={<SearchIcon />} onClick={async () => {
              setScanDialogOpen(true)
              setScanning(true)
              setScanProgress(null)
              setScanError('')
              setDiscoveredDevices([])
              try {
                await scanNetwork()
                const poll = setInterval(async () => {
                  try {
                    const status = await getScanStatus()
                    if (!status.scanning) {
                      clearInterval(poll)
                      scanPollRef.current = null
                      setScanning(false)
                      setScanProgress(status.progress)
                      if (status.error) {
                        setScanError(status.error)
                      } else {
                        const devices = await getScanResults()
                        setDiscoveredDevices(devices)
                      }
                    } else {
                      setScanProgress(status.progress)
                    }
                  } catch { /* ignore */ }
                }, 1500)
                scanPollRef.current = poll
              } catch (e: any) {
                setScanning(false)
                setScanError(e?.response?.data?.detail || 'Failed to start scan')
              }
            }}>
              Discover Cameras
            </Button>
          )}
          <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpen}>
            {isFirstCamera ? 'Get Started' : 'Add Camera'}
          </Button>
        </Box>
      </Box>

      <CameraGrid compact={false} />

      {/* Scan Dialog */}
      <Dialog open={scanDialogOpen} onClose={() => { setScanDialogOpen(false); if (scanPollRef.current) clearInterval(scanPollRef.current) }} maxWidth="md" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SearchIcon /> Discover Cameras
          </Box>
        </DialogTitle>
        <DialogContent>
          {scanning && (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <LinearProgress sx={{ mb: 2 }} />
              <Typography variant="body2" color="text.secondary">
                Scanning network for ONVIF cameras...
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                Probing 239.255.255.250:3702 via WS-Discovery
              </Typography>
            </Box>
          )}
          {scanError && (
            <Typography color="error" sx={{ mt: 2 }}>{scanError}</Typography>
          )}
          {!scanning && !scanError && discoveredDevices.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="body1" color="text.secondary">
                No cameras found on the local network.
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Make sure cameras are ONVIF-compatible and on the same subnet.
              </Typography>
            </Box>
          )}
          {!scanning && discoveredDevices.length > 0 && (
            <Grid container spacing={2} sx={{ mt: 1 }}>
              {discoveredDevices.map((device, idx) => (
                <Grid item xs={12} sm={6} key={idx}>
                  <Card variant="outlined" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    <CardContent sx={{ flexGrow: 1 }}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>{device.name}</Typography>
                      <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', display: 'block', mb: 0.5, color: 'text.secondary' }}>
                        {device.ip}
                      </Typography>
                      <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', display: 'block', fontSize: '10px', color: 'text.secondary', wordBreak: 'break-all' }}>
                        {device.xaddrs}
                      </Typography>
                    </CardContent>
                    <CardActions sx={{ px: 2, pb: 2 }}>
                      <Button
                        size="small"
                        variant="contained"
                        fullWidth
                        onClick={() => {
                          setScanDialogOpen(false)
                          if (scanPollRef.current) clearInterval(scanPollRef.current)
                          const name = device.name || `Camera at ${device.ip}`
                          setForm({
                            name,
                            rtsp_url: `rtsp://${device.ip}:554/`,
                            location: '',
                            zone: '',
                            fps_target: 5,
                            username: '',
                            password: '',
                          })
                          setOpen(true)
                        }}
                      >
                        Add This Camera
                      </Button>
                    </CardActions>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setScanDialogOpen(false); if (scanPollRef.current) clearInterval(scanPollRef.current) }}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Add Camera Dialog */}
      <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
        <DialogTitle>Add Camera</DialogTitle>
        <DialogContent>
          <TextField fullWidth label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} margin="dense" size="small" required />
          <TextField fullWidth label="RTSP URL" value={form.rtsp_url} onChange={(e) => setForm({ ...form, rtsp_url: e.target.value })} margin="dense" size="small" placeholder="rtsp://192.168.1.100:554/stream1" required />
          <TextField fullWidth label="Location (e.g. Pen A)" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} margin="dense" size="small" />
          <TextField fullWidth label="Zone" value={form.zone} onChange={(e) => setForm({ ...form, zone: e.target.value })} margin="dense" size="small" />
          <TextField fullWidth label="FPS Target" type="number" value={form.fps_target} onChange={(e) => setForm({ ...form, fps_target: parseInt(e.target.value) || 5 })} margin="dense" size="small" />
          <TextField fullWidth label="Username (optional)" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} margin="dense" size="small" />
          <TextField fullWidth label="Password (optional)" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} margin="dense" size="small" />
          {addError && <Typography variant="body2" color="error" sx={{ mt: 1 }}>{addError}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose} disabled={submitting}>Cancel</Button>
          <Button variant="contained" onClick={handleAdd} disabled={submitting}>
            {submitting ? 'Adding...' : 'Add'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
