import { useState, useRef, useEffect } from 'react'
import {
  Box, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Card, CardContent, CardActions, Grid, LinearProgress, Checkbox, FormControlLabel, Alert,
  Chip, Divider, ToggleButtonGroup, ToggleButton, Tooltip, Stack,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import DvrIcon from '@mui/icons-material/Dvr'
import VideocamIcon from '@mui/icons-material/Videocam'
import RouterIcon from '@mui/icons-material/Router'
import { useCameras } from '../hooks/useCameras'
import { CameraGrid } from '../components/CameraGrid'
import { useAuth } from '../auth/AuthContext'
import api from '../api/axios'
import { AddDeviceModal } from '../components/AddDeviceModal'
import type { DiscoveredDevice } from '../types'

interface NvrChannel {
  channel: number
  name: string
  online: boolean
  rtsp_url: string
}

// XMEye types
interface XMEyeDevice {
  ip: string
  tcp_port: number
  http_port: number
  device_name: string
  device_type: string
  serial_no: string
  mac: string
  channel_count: number
  software_version: string
  build_date: string
}

interface XMEyeChannel {
  channel: number
  name: string
  rtsp_url_main: string
  rtsp_url_sub: string
  rtsp_url_main_b: string
  rtsp_url_sub_b: string
}

type XMEyeStep = 'scan' | 'credentials' | 'channels'

export default function LiveFeed() {
  const { cameras, addCamera, refetchCameras, scanNetwork, getScanStatus, getScanResults } = useCameras()
  const { hasPermission, farms } = useAuth()
  const [open, setOpen] = useState(false)
  const [addDeviceModalOpen, setAddDeviceModalOpen] = useState(false)
  const [form, setForm] = useState({ name: '', rtsp_url: '', location: '', zone: '', fps_target: 5, username: '', password: '' })
  const [addError, setAddError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // ONVIF scan state
  const [scanDialogOpen, setScanDialogOpen] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [scanProgress, setScanProgress] = useState<number | null>(null)
  const [scanError, setScanError] = useState('')
  const [discoveredDevices, setDiscoveredDevices] = useState<DiscoveredDevice[]>([])
  const scanPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Dahua NVR state
  const [nvrDialogOpen, setNvrDialogOpen] = useState(false)
  const [nvrLoading, setNvrLoading] = useState(false)
  const [nvrError, setNvrError] = useState('')
  const [nvrChannels, setNvrChannels] = useState<NvrChannel[]>([])
  const [nvrSelected, setNvrSelected] = useState<Set<number>>(new Set())
  const [nvrRegistering, setNvrRegistering] = useState(false)
  const [nvrResult, setNvrResult] = useState('')

  // ── XMEye state ──────────────────────────────────────────────────────────
  const [xmeyeOpen, setXmeyeOpen] = useState(false)
  const [xmeyeStep, setXmeyeStep] = useState<XMEyeStep>('scan')
  const [xmeyeScanning, setXmeyeScanning] = useState(false)
  const [xmeyeScanError, setXmeyeScanError] = useState('')
  const [xmeyeDevices, setXmeyeDevices] = useState<XMEyeDevice[]>([])
  const [xmeyeSelectedDevice, setXmeyeSelectedDevice] = useState<XMEyeDevice | null>(null)
  const [xmeyeUsername, setXmeyeUsername] = useState('admin')
  const [xmeyePassword, setXmeyePassword] = useState('')
  const [xmeyeRtspPort, setXmeyeRtspPort] = useState('554')
  const [xmeyeConnecting, setXmeyeConnecting] = useState(false)
  const [xmeyeConnectError, setXmeyeConnectError] = useState('')
  const [xmeyeChannels, setXmeyeChannels] = useState<XMEyeChannel[]>([])
  const [xmeyeSelected, setXmeyeSelected] = useState<Set<number>>(new Set())
  const [xmeyeRtspFormat, setXmeyeRtspFormat] = useState<'A' | 'B'>('A')
  const [xmeyeSubstream, setXmeyeSubstream] = useState(false)
  const [xmeyeAdding, setXmeyeAdding] = useState(false)
  const [xmeyeAddError, setXmeyeAddError] = useState('')
  const [xmeyeAddResult, setXmeyeAddResult] = useState('')

  useEffect(() => {
    return () => { if (scanPollRef.current) clearInterval(scanPollRef.current) }
  }, [])

  const handleClose = () => { if (!submitting) { setOpen(false); setAddError('') } }
  const handleOpen = () => {
    setForm({ name: '', rtsp_url: '', location: '', zone: '', fps_target: 5, username: '', password: '' })
    setAddError('')
    setOpen(true)
  }

  const handleAdd = async () => {
    if (submitting) return
    setAddError('')
    if (!form.name.trim() || !form.rtsp_url.trim()) { setAddError('Name and RTSP URL are required'); return }
    setSubmitting(true)
    try {
      await addCamera({
        name: form.name, rtsp_url: form.rtsp_url,
        location: form.location || undefined, zone: form.zone || undefined,
        fps_target: form.fps_target, username: form.username || undefined, password: form.password || undefined,
      })
      setOpen(false)
      setForm({ name: '', rtsp_url: '', location: '', zone: '', fps_target: 5, username: '', password: '' })
    } catch (e: any) { setAddError(e?.response?.data?.detail || 'Failed to add camera') }
    finally { setSubmitting(false) }
  }

  const handleNvrRegister = async () => {
    if (nvrRegistering || !farms.length) return
    setNvrRegistering(true)
    setNvrResult('')
    try {
      const selected = nvrChannels.filter(c => nvrSelected.has(c.channel))
      const resp = await api.post('/nvr/register', { cameras: selected, farm_id: farms[0].id })
      setNvrResult(`Registered ${resp.data.count} camera(s)`)
      setTimeout(() => setNvrDialogOpen(false), 1500)
    } catch (e: any) {
      setNvrError(e?.response?.data?.detail || 'Failed to register cameras')
    } finally { setNvrRegistering(false) }
  }

  // ── XMEye handlers ───────────────────────────────────────────────────────
  const openXmeyeDialog = () => {
    setXmeyeOpen(true)
    setXmeyeStep('scan')
    setXmeyeDevices([])
    setXmeyeScanError('')
    setXmeyeSelectedDevice(null)
    setXmeyeChannels([])
    setXmeyeSelected(new Set())
    setXmeyeAddResult('')
    setXmeyeAddError('')
    startXmeyeScan()
  }

  const startXmeyeScan = async () => {
    setXmeyeScanning(true)
    setXmeyeScanError('')
    setXmeyeDevices([])
    try {
      const { data } = await api.post('/xmeye/scan')
      setXmeyeDevices(data.devices || [])
      if ((data.devices || []).length === 0) {
        setXmeyeScanError('No XMEye devices found on your local network.')
      }
    } catch (e: any) {
      setXmeyeScanError(e?.response?.data?.detail || 'Scan failed — check network access')
    } finally {
      setXmeyeScanning(false)
    }
  }

  const handleXmeyeSelectDevice = (device: XMEyeDevice) => {
    setXmeyeSelectedDevice(device)
    setXmeyeUsername('admin')
    setXmeyePassword('')
    setXmeyeConnectError('')
    setXmeyeStep('credentials')
  }

  const handleXmeyeConnect = async () => {
    if (!xmeyeSelectedDevice) return
    setXmeyeConnecting(true)
    setXmeyeConnectError('')
    try {
      const { data } = await api.post('/xmeye/connect', {
        ip: xmeyeSelectedDevice.ip,
        port: xmeyeSelectedDevice.tcp_port,
        rtsp_port: parseInt(xmeyeRtspPort) || 554,
        username: xmeyeUsername,
        password: xmeyePassword,
        channel_count: xmeyeSelectedDevice.channel_count,
      })
      if (!data.success) {
        setXmeyeConnectError(data.error || 'Login failed — check username and password')
        return
      }
      setXmeyeChannels(data.channels || [])
      setXmeyeSelected(new Set((data.channels || []).map((c: XMEyeChannel) => c.channel)))
      setXmeyeStep('channels')
    } catch (e: any) {
      setXmeyeConnectError(e?.response?.data?.detail || 'Connection failed')
    } finally {
      setXmeyeConnecting(false)
    }
  }

  const handleXmeyeAdd = async () => {
    if (!xmeyeSelectedDevice || xmeyeSelected.size === 0) return
    setXmeyeAdding(true)
    setXmeyeAddError('')
    try {
      const { data } = await api.post('/xmeye/add', {
        ip: xmeyeSelectedDevice.ip,
        username: xmeyeUsername,
        password: xmeyePassword,
        rtsp_port: parseInt(xmeyeRtspPort) || 554,
        channels: Array.from(xmeyeSelected).sort(),
        rtsp_format: xmeyeRtspFormat,
        use_substream: xmeyeSubstream,
      })
      const count = Array.isArray(data) ? data.length : 0
      setXmeyeAddResult(`Added ${count} camera(s) successfully! cv-engine will pick them up within 10 seconds.`)
      refetchCameras()
      setTimeout(() => setXmeyeOpen(false), 2500)
    } catch (e: any) {
      setXmeyeAddError(e?.response?.data?.detail || 'Failed to add cameras')
    } finally {
      setXmeyeAdding(false)
    }
  }

  const isFirstCamera = cameras.length === 0

  return (
    <Box>
      <Box sx={{ mb: 4, display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, justifyContent: 'space-between', alignItems: { xs: 'flex-start', sm: 'center' }, gap: { xs: 2, sm: 0 } }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Live Feed</Typography>
          <Typography variant="body2" color="text.secondary">
            {cameras.length > 0 ? `Real-time video feeds from ${cameras.length} camera${cameras.length !== 1 ? 's' : ''}` : 'No cameras configured yet'}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1.5, width: { xs: '100%', sm: 'auto' }, justifyContent: { xs: 'flex-start', sm: 'flex-end' }, flexWrap: 'wrap' }}>
          {hasPermission('cameras:scan') && (
            <Tooltip title="Discover XMEye / Xiongmai NVRs and IP cameras on your local network">
              <Button variant="outlined" color="warning" startIcon={<RouterIcon />} onClick={openXmeyeDialog}>
                Scan XMEye / DVRIP
              </Button>
            </Tooltip>
          )}
          {hasPermission('cameras:scan') && (
            <Button variant="outlined" color="primary" startIcon={<DvrIcon />} onClick={() => setAddDeviceModalOpen(true)}>
              NVR Auto Discover / Add Device
            </Button>
          )}
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
                      if (status.error) setScanError(status.error)
                      else { const devices = await getScanResults(); setDiscoveredDevices(devices) }
                    } else { setScanProgress(status.progress) }
                  } catch { /* ignore */ }
                }, 1500)
                scanPollRef.current = poll
              } catch (e: any) { setScanning(false); setScanError(e?.response?.data?.detail || 'Failed to start scan') }
            }}>Discover ONVIF</Button>
          )}
          <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpen}>
            {isFirstCamera ? 'Get Started' : 'Add Camera'}
          </Button>
        </Box>
      </Box>

      <CameraGrid compact={false} />

      <AddDeviceModal open={addDeviceModalOpen} onClose={() => setAddDeviceModalOpen(false)} onSuccess={refetchCameras} />

      {/* ── XMEye / DVRIP Dialog ─────────────────────────────────────────── */}
      <Dialog open={xmeyeOpen} onClose={() => setXmeyeOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <RouterIcon color="warning" />
            <Typography variant="h6" sx={{ fontWeight: 700 }}>XMEye / DVRIP Camera Discovery</Typography>
            <Box sx={{ ml: 'auto' }}>
              {xmeyeStep === 'scan' && <Chip label="Step 1 — Scan" size="small" color="warning" />}
              {xmeyeStep === 'credentials' && <Chip label="Step 2 — Login" size="small" color="primary" />}
              {xmeyeStep === 'channels' && <Chip label="Step 3 — Pick Channels" size="small" color="success" />}
            </Box>
          </Box>
        </DialogTitle>
        <DialogContent>
          {/* Step 1: Scan */}
          {xmeyeStep === 'scan' && (
            <Box>
              {xmeyeScanning && (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <LinearProgress color="warning" sx={{ mb: 2 }} />
                  <Typography variant="body2" color="text.secondary">Broadcasting UDP discovery on port 34568…</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                    All XMEye / Xiongmai devices on your LAN will respond within ~5 seconds
                  </Typography>
                </Box>
              )}
              {xmeyeScanError && !xmeyeScanning && <Alert severity="warning" sx={{ mb: 2 }}>{xmeyeScanError}</Alert>}
              {!xmeyeScanning && xmeyeDevices.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 700 }}>
                    Found {xmeyeDevices.length} device(s) — click one to connect
                  </Typography>
                  <Grid container spacing={2}>
                    {xmeyeDevices.map((dev) => (
                      <Grid item xs={12} sm={6} key={dev.ip}>
                        <Card
                          variant="outlined"
                          sx={{
                            cursor: 'pointer', border: '2px solid', borderColor: 'divider',
                            transition: 'border-color 0.15s', '&:hover': { borderColor: 'warning.main' },
                          }}
                          onClick={() => handleXmeyeSelectDevice(dev)}
                        >
                          <CardContent>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                              <VideocamIcon color="warning" />
                              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{dev.device_name || `XMEye @ ${dev.ip}`}</Typography>
                              <Chip label={dev.device_type || 'Device'} size="small" sx={{ ml: 'auto' }} />
                            </Box>
                            <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', display: 'block', color: 'text.secondary' }}>
                              IP: {dev.ip} &nbsp;|&nbsp; Channels: {dev.channel_count}
                            </Typography>
                            {dev.serial_no && <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>S/N: {dev.serial_no}</Typography>}
                            {dev.software_version && <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>FW: {dev.software_version}</Typography>}
                          </CardContent>
                        </Card>
                      </Grid>
                    ))}
                  </Grid>
                </Box>
              )}
            </Box>
          )}

          {/* Step 2: Credentials */}
          {xmeyeStep === 'credentials' && xmeyeSelectedDevice && (
            <Box>
              <Alert severity="info" sx={{ mb: 2 }}>
                Connecting to <strong>{xmeyeSelectedDevice.device_name || xmeyeSelectedDevice.ip}</strong>
                &nbsp;({xmeyeSelectedDevice.ip}) via DVRIP on port {xmeyeSelectedDevice.tcp_port}
              </Alert>
              <Stack spacing={2}>
                <TextField fullWidth label="Username" value={xmeyeUsername} onChange={(e) => setXmeyeUsername(e.target.value)} helperText="Default is 'admin'" />
                <TextField fullWidth label="Password" type="password" value={xmeyePassword} onChange={(e) => setXmeyePassword(e.target.value)} helperText="Leave blank if no password is set" />
                <TextField fullWidth label="RTSP Port" value={xmeyeRtspPort} onChange={(e) => setXmeyeRtspPort(e.target.value)} helperText="Usually 554. Change if NVR uses non-standard RTSP port." />
                {xmeyeConnectError && <Alert severity="error">{xmeyeConnectError}</Alert>}
              </Stack>
            </Box>
          )}

          {/* Step 3: Channel Picker */}
          {xmeyeStep === 'channels' && (
            <Box>
              {xmeyeAddResult && <Alert severity="success" sx={{ mb: 2 }}>{xmeyeAddResult}</Alert>}
              {xmeyeAddError && <Alert severity="error" sx={{ mb: 2 }}>{xmeyeAddError}</Alert>}
              {!xmeyeAddResult && (
                <>
                  <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      {xmeyeChannels.length} channel(s) available — select which to add
                    </Typography>
                    <Button size="small" onClick={() => {
                      const all = xmeyeChannels.every(c => xmeyeSelected.has(c.channel))
                      setXmeyeSelected(all ? new Set() : new Set(xmeyeChannels.map(c => c.channel)))
                    }}>
                      {xmeyeChannels.every(c => xmeyeSelected.has(c.channel)) ? 'Deselect All' : 'Select All'}
                    </Button>
                  </Box>
                  <Grid container spacing={2} sx={{ mb: 3 }}>
                    {xmeyeChannels.map((ch) => (
                      <Grid item xs={12} sm={6} key={ch.channel}>
                        <Card variant="outlined" sx={{
                          border: xmeyeSelected.has(ch.channel) ? '2px solid' : '1px solid',
                          borderColor: xmeyeSelected.has(ch.channel) ? 'success.main' : 'divider',
                        }}>
                          <CardContent sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, py: '12px !important' }}>
                            <Checkbox checked={xmeyeSelected.has(ch.channel)} onChange={() => setXmeyeSelected(prev => {
                              const next = new Set(prev)
                              if (next.has(ch.channel)) next.delete(ch.channel); else next.add(ch.channel)
                              return next
                            })} sx={{ mt: -0.5 }} />
                            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{ch.name}</Typography>
                              <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', color: 'text.secondary', fontSize: '10px', display: 'block', wordBreak: 'break-all' }}>
                                {xmeyeSubstream
                                  ? (xmeyeRtspFormat === 'A' ? ch.rtsp_url_sub : ch.rtsp_url_sub_b)
                                  : (xmeyeRtspFormat === 'A' ? ch.rtsp_url_main : ch.rtsp_url_main_b)}
                              </Typography>
                            </Box>
                          </CardContent>
                        </Card>
                      </Grid>
                    ))}
                  </Grid>
                  <Divider sx={{ mb: 2 }} />
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5, fontWeight: 600 }}>Stream Options</Typography>
                  <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                    <Box>
                      <Typography variant="caption" color="text.secondary">RTSP URL Format</Typography>
                      <ToggleButtonGroup size="small" exclusive value={xmeyeRtspFormat}
                        onChange={(_, v) => { if (v) setXmeyeRtspFormat(v) }} sx={{ display: 'flex', mt: 0.5 }}>
                        <ToggleButton value="A">Format A (Legacy)</ToggleButton>
                        <ToggleButton value="B">Format B (ch01/0)</ToggleButton>
                      </ToggleButtonGroup>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                        Try Format A first. Use B if streams fail to open.
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">Stream Quality</Typography>
                      <ToggleButtonGroup size="small" exclusive value={xmeyeSubstream ? 'sub' : 'main'}
                        onChange={(_, v) => { if (v) setXmeyeSubstream(v === 'sub') }} sx={{ display: 'flex', mt: 0.5 }}>
                        <ToggleButton value="main">Main (HD)</ToggleButton>
                        <ToggleButton value="sub">Sub (SD)</ToggleButton>
                      </ToggleButtonGroup>
                    </Box>
                  </Box>
                </>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          {xmeyeStep === 'credentials' && <Button onClick={() => setXmeyeStep('scan')}>← Back</Button>}
          {xmeyeStep === 'channels' && !xmeyeAddResult && <Button onClick={() => setXmeyeStep('credentials')}>← Back</Button>}
          <Button onClick={() => setXmeyeOpen(false)}>{xmeyeAddResult ? 'Done' : 'Cancel'}</Button>
          {xmeyeStep === 'scan' && !xmeyeScanning && (
            <Button variant="outlined" color="warning" onClick={startXmeyeScan}>Rescan</Button>
          )}
          {xmeyeStep === 'credentials' && (
            <Button variant="contained" onClick={handleXmeyeConnect} disabled={xmeyeConnecting || !xmeyeUsername}>
              {xmeyeConnecting ? 'Connecting…' : 'Connect & List Channels →'}
            </Button>
          )}
          {xmeyeStep === 'channels' && !xmeyeAddResult && (
            <Button variant="contained" color="success" onClick={handleXmeyeAdd} disabled={xmeyeAdding || xmeyeSelected.size === 0}>
              {xmeyeAdding ? 'Adding…' : `Add ${xmeyeSelected.size} Camera(s)`}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Dahua NVR Discover Dialog */}
      <Dialog open={nvrDialogOpen} onClose={() => setNvrDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle><Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><DvrIcon /> NVR Camera Discovery</Box></DialogTitle>
        <DialogContent>
          {nvrLoading && (<Box sx={{ textAlign: 'center', py: 4 }}><LinearProgress sx={{ mb: 2 }} /><Typography variant="body2" color="text.secondary">Connecting to NVR...</Typography></Box>)}
          {nvrError && <Alert severity="error" sx={{ mt: 2 }}>{nvrError}</Alert>}
          {nvrResult && <Alert severity="success" sx={{ mt: 2 }}>{nvrResult}</Alert>}
          {!nvrLoading && !nvrError && nvrChannels.length === 0 && !nvrResult && (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography color="text.secondary">No channels found.</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>Check NVR_HOST, NVR_USERNAME, NVR_PASSWORD in .env</Typography>
            </Box>
          )}
          {!nvrLoading && nvrChannels.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{nvrChannels.length} channel(s)</Typography>
                <Button size="small" onClick={() => {
                  const all = nvrChannels.every(c => nvrSelected.has(c.channel))
                  if (all) setNvrSelected(new Set()); else setNvrSelected(new Set(nvrChannels.map(c => c.channel)))
                }}>{nvrChannels.every(c => nvrSelected.has(c.channel)) ? 'Deselect All' : 'Select All'}</Button>
              </Box>
              <Grid container spacing={2}>
                {nvrChannels.map((ch) => (
                  <Grid item xs={12} sm={6} key={ch.channel}>
                    <Card variant="outlined" sx={{ opacity: ch.online ? 1 : 0.5 }}>
                      <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, py: '12px !important' }}>
                        <FormControlLabel control={<Checkbox checked={nvrSelected.has(ch.channel)} onChange={() => {
                          setNvrSelected(prev => { const next = new Set(prev); if (next.has(ch.channel)) next.delete(ch.channel); else next.add(ch.channel); return next })
                        }} />} label="" sx={{ m: 0 }} />
                        <Box sx={{ flexGrow: 1 }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{ch.name}</Typography>
                          <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', color: 'text.secondary' }}>
                            Channel {ch.channel} {ch.online ? '● Online' : '○ Offline'}
                          </Typography>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNvrDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleNvrRegister} disabled={nvrRegistering || nvrSelected.size === 0 || nvrLoading}>
            {nvrRegistering ? 'Registering...' : `Register ${nvrSelected.size} Camera(s)`}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ONVIF Scan Dialog */}
      <Dialog open={scanDialogOpen} onClose={() => { setScanDialogOpen(false); if (scanPollRef.current) clearInterval(scanPollRef.current) }} maxWidth="md" fullWidth>
        <DialogTitle><Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><SearchIcon /> Discover Cameras (ONVIF)</Box></DialogTitle>
        <DialogContent>
          {scanning && (<Box sx={{ textAlign: 'center', py: 4 }}><LinearProgress sx={{ mb: 2 }} /><Typography variant="body2" color="text.secondary">Scanning for ONVIF cameras...</Typography><Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>Probing 239.255.255.250:3702 via WS-Discovery</Typography></Box>)}
          {scanError && <Typography color="error" sx={{ mt: 2 }}>{scanError}</Typography>}
          {!scanning && !scanError && discoveredDevices.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography color="text.secondary">No ONVIF cameras found.</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Make sure cameras are on the same subnet.</Typography>
            </Box>
          )}
          {!scanning && discoveredDevices.length > 0 && (
            <Grid container spacing={2} sx={{ mt: 1 }}>
              {discoveredDevices.map((device, idx) => (
                <Grid item xs={12} sm={6} key={idx}>
                  <Card variant="outlined" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    <CardContent sx={{ flexGrow: 1 }}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>{device.name}</Typography>
                      <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', display: 'block', mb: 0.5, color: 'text.secondary' }}>{device.ip}</Typography>
                      <Typography variant="caption" sx={{ fontFamily: '"JetBrains Mono", monospace', display: 'block', fontSize: '10px', color: 'text.secondary', wordBreak: 'break-all' }}>{device.xaddrs}</Typography>
                    </CardContent>
                    <CardActions sx={{ px: 2, pb: 2 }}>
                      <Button size="small" variant="contained" fullWidth onClick={() => {
                        setScanDialogOpen(false)
                        if (scanPollRef.current) clearInterval(scanPollRef.current)
                        setForm({ name: device.name || `Camera at ${device.ip}`, rtsp_url: `rtsp://${device.ip}:554/`, location: '', zone: '', fps_target: 5, username: '', password: '' })
                        setOpen(true)
                      }}>Add This Camera</Button>
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
          <Button variant="contained" onClick={handleAdd} disabled={submitting}>{submitting ? 'Adding...' : 'Add'}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
