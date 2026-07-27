import { useState } from 'react'
import {
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, Select, MenuItem,
  Button, Box, Typography, FormControl, InputLabel, InputAdornment, IconButton,
  Card, CardContent, Checkbox, FormControlLabel, Grid, LinearProgress, Alert, Tabs, Tab
} from '@mui/material'
import Visibility from '@mui/icons-material/Visibility'
import VisibilityOff from '@mui/icons-material/VisibilityOff'
import DvrIcon from '@mui/icons-material/Dvr'
import SearchIcon from '@mui/icons-material/Search'
import RefreshIcon from '@mui/icons-material/Refresh'
import { useAuth } from '../auth/AuthContext'
import api from '../api/axios'

interface DiscoveredChannel {
  channel: number
  name: string
  online: boolean
  rtsp_url: string
}

interface AddDeviceModalProps {
  open: boolean
  onClose: () => void
  onSuccess?: () => void
}

export function AddDeviceModal({ open, onClose, onSuccess }: AddDeviceModalProps) {
  const { farms } = useAuth()
  const [tab, setTab] = useState<number>(0) // 0 = Manual Add, 1 = Auto Discover

  // Form State (matching user screenshot)
  const [deviceName, setDeviceName] = useState('192.168.31.169')
  const [selectedGroup, setSelectedGroup] = useState<string>(farms[0]?.id || 'default')
  const [loginType, setLoginType] = useState('IP Address')
  const [ip, setIp] = useState('192.168.31.169')
  const [port, setPort] = useState('34567')
  const [userName, setUserName] = useState('admin')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [protocol, setProtocol] = useState('General')

  // Connection & Discovery state
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [discoveredChannels, setDiscoveredChannels] = useState<DiscoveredChannel[]>([])
  const [selectedChannels, setSelectedChannels] = useState<Set<number>>(new Set())
  const [registering, setRegistering] = useState(false)
  const [successMsg, setSuccessMsg] = useState('')

  // Auto Discover State
  const [autoScanning, setAutoScanning] = useState(false)

  const handleRandomUser = () => {
    const randomUsers = ['admin', 'operator', 'supervisor', 'nvr_admin', 'viewer']
    const picked = randomUsers[Math.floor(Math.random() * randomUsers.length)]
    setUserName(picked)
  }

  const handleConnect = async () => {
    if (!ip.trim()) {
      setError('IP address or domain name is required')
      return
    }
    setLoading(true)
    setError('')
    setSuccessMsg('')
    setDiscoveredChannels([])
    setSelectedChannels(new Set())

    try {
      const resp = await api.post('/v1/nvr/connect', {
        device_name: deviceName || ip,
        group: selectedGroup,
        login_type: loginType,
        ip: ip.trim(),
        port: parseInt(port, 10) || 34567,
        username: userName,
        password: password,
        protocol: protocol,
      })
      const channels: DiscoveredChannel[] = resp.data.cameras || []
      setDiscoveredChannels(channels)
      setSelectedChannels(new Set(channels.map((c) => c.channel)))
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to connect to NVR / Camera device')
    } finally {
      setLoading(false)
    }
  }

  const handleAutoDiscover = async () => {
    setAutoScanning(true)
    setError('')
    setSuccessMsg('')
    try {
      const resp = await api.get('/v1/nvr/discover')
      const channels: DiscoveredChannel[] = resp.data.cameras || []
      setDiscoveredChannels(channels)
      setSelectedChannels(new Set(channels.map((c) => c.channel)))
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'No NVR / ONVIF devices discovered on local network.')
    } finally {
      setAutoScanning(false)
    }
  }

  const handleRegisterSelected = async () => {
    if (selectedChannels.size === 0 || registering) return
    setRegistering(true)
    setError('')
    try {
      const targetFarmId = selectedGroup !== 'default' && selectedGroup ? selectedGroup : farms[0]?.id
      if (!targetFarmId) {
        setError('Please select a valid Farm / Group.')
        setRegistering(false)
        return
      }

      const selectedList = discoveredChannels.filter((c) => selectedChannels.has(c.channel))
      const resp = await api.post('/v1/nvr/register', {
        cameras: selectedList,
        farm_id: targetFarmId,
        username: userName || undefined,
        password: password || undefined,
      })

      setSuccessMsg(`Successfully registered ${resp.data.count} camera stream(s)!`)
      setTimeout(() => {
        if (onSuccess) onSuccess()
        onClose()
      }, 1500)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to register cameras.')
    } finally {
      setRegistering(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3 } }}>
      {/* Header bar matching screenshot */}
      <Box sx={{ bgcolor: '#222222', color: '#ffffff', px: 3, py: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="h6" sx={{ fontWeight: 700, fontFamily: '"Outfit", sans-serif', fontSize: '1.1rem' }}>
          Edit / Add Device
        </Typography>
        <IconButton size="small" onClick={onClose} sx={{ color: '#aaaaaa', '&:hover': { color: '#ffffff' } }}>
          ✕
        </IconButton>
      </Box>

      <Tabs value={tab} onChange={(_, val) => setTab(val)} variant="fullWidth" sx={{ borderBottom: '1px solid rgba(0,0,0,0.08)' }}>
        <Tab icon={<DvrIcon fontSize="small" />} iconPosition="start" label="Manual Add Device" />
        <Tab icon={<SearchIcon fontSize="small" />} iconPosition="start" label="Auto Discover (Scan)" />
      </Tabs>

      <DialogContent sx={{ p: 3 }}>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {successMsg && <Alert severity="success" sx={{ mb: 2 }}>{successMsg}</Alert>}

        {/* TAB 0: MANUAL ADD DEVICE FORM (MATCHING USER SCREENSHOT) */}
        {tab === 0 && discoveredChannels.length === 0 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography sx={{ width: 120, fontWeight: 600, fontSize: '0.875rem', color: '#334155' }}>Device Name:</Typography>
              <TextField
                size="small"
                fullWidth
                value={deviceName}
                onChange={(e) => setDeviceName(e.target.value)}
                placeholder="e.g. 192.168.31.169"
              />
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography sx={{ width: 120, fontWeight: 600, fontSize: '0.875rem', color: '#334155' }}>Group:</Typography>
              <FormControl size="small" fullWidth>
                <Select value={selectedGroup} onChange={(e) => setSelectedGroup(e.target.value)}>
                  <MenuItem value="default">Default Group</MenuItem>
                  {farms.map((f) => (
                    <MenuItem key={f.id} value={f.id}>{f.name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography sx={{ width: 120, fontWeight: 600, fontSize: '0.875rem', color: '#334155' }}>Login Type:</Typography>
              <FormControl size="small" fullWidth>
                <Select value={loginType} onChange={(e) => setLoginType(e.target.value)}>
                  <MenuItem value="IP Address">IP Address</MenuItem>
                  <MenuItem value="Domain Name">Domain Name</MenuItem>
                  <MenuItem value="ONVIF">ONVIF</MenuItem>
                </Select>
              </FormControl>
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography sx={{ width: 120, fontWeight: 600, fontSize: '0.875rem', color: '#334155' }}>IP:</Typography>
              <TextField
                size="small"
                fullWidth
                value={ip}
                onChange={(e) => {
                  setIp(e.target.value)
                  if (!deviceName || deviceName === ip) setDeviceName(e.target.value)
                }}
                placeholder="192.168.31.169"
              />
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography sx={{ width: 120, fontWeight: 600, fontSize: '0.875rem', color: '#334155' }}>Port:</Typography>
              <TextField
                size="small"
                fullWidth
                value={port}
                onChange={(e) => setPort(e.target.value)}
                placeholder="34567"
              />
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography sx={{ width: 120, fontWeight: 600, fontSize: '0.875rem', color: '#334155' }}>UserName:</Typography>
              <TextField
                size="small"
                fullWidth
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                placeholder="admin"
              />
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography sx={{ width: 120, fontWeight: 600, fontSize: '0.875rem', color: '#334155' }}>Password:</Typography>
              <TextField
                size="small"
                fullWidth
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton size="small" onClick={() => setShowPassword(!showPassword)}>
                        {showPassword ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                      </IconButton>
                    </InputAdornment>
                  )
                }}
              />
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography sx={{ width: 120, fontWeight: 600, fontSize: '0.875rem', color: '#334155' }}>Protocol:</Typography>
              <FormControl size="small" fullWidth>
                <Select value={protocol} onChange={(e) => setProtocol(e.target.value)}>
                  <MenuItem value="General">General</MenuItem>
                  <MenuItem value="Dahua">Dahua</MenuItem>
                  <MenuItem value="Hikvision">Hikvision</MenuItem>
                  <MenuItem value="ONVIF">ONVIF</MenuItem>
                  <MenuItem value="Uniview">Uniview</MenuItem>
                </Select>
              </FormControl>
            </Box>
          </Box>
        )}

        {/* TAB 1: AUTO DISCOVER */}
        {tab === 1 && discoveredChannels.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            {autoScanning ? (
              <Box>
                <LinearProgress sx={{ mb: 2 }} />
                <Typography variant="body2" color="text.secondary">Scanning local network for ONVIF & NVR devices...</Typography>
              </Box>
            ) : (
              <Box>
                <SearchIcon sx={{ fontSize: 48, color: '#94a3b8', mb: 1 }} />
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Auto Discover NVR Devices</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                  Click below to automatically scan the local network for ONVIF cameras and NVR channels.
                </Typography>
                <Button variant="contained" startIcon={<RefreshIcon />} onClick={handleAutoDiscover}>
                  Start Network Scan
                </Button>
              </Box>
            )}
          </Box>
        )}

        {/* DISCOVERED CHANNELS LIST VIEW */}
        {discoveredChannels.length > 0 && (
          <Box>
            <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                {discoveredChannels.length} Channel(s) Discovered on {deviceName || ip}
              </Typography>
              <Button
                size="small"
                onClick={() => {
                  if (selectedChannels.size === discoveredChannels.length) setSelectedChannels(new Set())
                  else setSelectedChannels(new Set(discoveredChannels.map((c) => c.channel)))
                }}
              >
                {selectedChannels.size === discoveredChannels.length ? 'Deselect All' : 'Select All'}
              </Button>
            </Box>

            <Grid container spacing={1.5} sx={{ maxHeight: 320, overflowY: 'auto' }}>
              {discoveredChannels.map((ch) => (
                <Grid item xs={12} sm={6} key={ch.channel}>
                  <Card variant="outlined">
                    <CardContent sx={{ display: 'flex', alignItems: 'center', p: '10px !important' }}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={selectedChannels.has(ch.channel)}
                            onChange={() => {
                              setSelectedChannels((prev) => {
                                const next = new Set(prev)
                                if (next.has(ch.channel)) next.delete(ch.channel)
                                else next.add(ch.channel)
                                return next
                              })
                            }}
                          />
                        }
                        label=""
                        sx={{ m: 0 }}
                      />
                      <Box sx={{ overflow: 'hidden' }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: '0.825rem' }}>
                          {ch.name}
                        </Typography>
                        <Typography variant="caption" noWrap sx={{ fontFamily: '"JetBrains Mono", monospace', color: 'text.secondary', display: 'block' }}>
                          Ch {ch.channel} • {ch.online ? '● Online' : '○ Offline'}
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>

            <Button size="small" color="secondary" onClick={() => setDiscoveredChannels([])} sx={{ mt: 2 }}>
              ← Back to Device Settings
            </Button>
          </Box>
        )}
      </DialogContent>

      {/* Buttons matching screenshot: RandomUser, OK, Cancel */}
      <DialogActions sx={{ px: 3, pb: 2.5, justifyContent: 'space-between', bgcolor: '#f8fafc', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
        {tab === 0 && discoveredChannels.length === 0 ? (
          <>
            <Button variant="outlined" color="inherit" onClick={handleRandomUser} sx={{ borderColor: '#cbd5e1', textTransform: 'none' }}>
              RandomUser
            </Button>
            <Box sx={{ display: 'flex', gap: 1.5 }}>
              <Button variant="contained" color="primary" onClick={handleConnect} disabled={loading} sx={{ minWidth: 90 }}>
                {loading ? 'Connecting...' : 'OK'}
              </Button>
              <Button variant="outlined" color="inherit" onClick={onClose} sx={{ borderColor: '#cbd5e1' }}>
                Cancel
              </Button>
            </Box>
          </>
        ) : (
          <>
            <Box />
            <Box sx={{ display: 'flex', gap: 1.5 }}>
              {discoveredChannels.length > 0 && (
                <Button
                  variant="contained"
                  color="primary"
                  onClick={handleRegisterSelected}
                  disabled={registering || selectedChannels.size === 0}
                >
                  {registering ? 'Registering...' : `Register ${selectedChannels.size} Channel(s)`}
                </Button>
              )}
              <Button variant="outlined" color="inherit" onClick={onClose}>
                Cancel
              </Button>
            </Box>
          </>
        )}
      </DialogActions>
    </Dialog>
  )
}
