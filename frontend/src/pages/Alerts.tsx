import { useState, useEffect, useCallback } from 'react'
import {
  Box, Typography, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Chip, Card, CardContent, Grid, CircularProgress,
  Tabs, Tab, Button, IconButton, Divider, TextField, Slider, Avatar, Tooltip, Alert
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import FaceIcon from '@mui/icons-material/Face'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ShieldOutlinedIcon from '@mui/icons-material/ShieldOutlined'
import CheckIcon from '@mui/icons-material/Check'
import RefreshIcon from '@mui/icons-material/Refresh'
import { useCameras } from '../hooks/useCameras'
import { useAuth } from '../auth/AuthContext'
import api from '../api/axios'

interface AlertItem {
  id: string
  camera_id: string | null
  chicken_id: string | null
  track_id: string | null
  type: string
  severity: number
  message: string
  created_at: string
  acknowledged_at: string | null
}

interface Person {
  name: string
  num_images: number
  created_at: number
  last_seen: number
  match_count: number
}

export default function Alerts() {
  const { cameras, loading: camerasLoading } = useCameras()
  const { hasPermission, currentFarm } = useAuth()
  const [tabValue, setTabValue] = useState(0)

  // Alerts states
  const [alertList, setAlertList] = useState<AlertItem[]>([])
  const [alertsLoading, setAlertsLoading] = useState(true)
  const [alertsError, setAlertsError] = useState<string | null>(null)

  // Intruder Gallery states
  const [persons, setPersons] = useState<Person[]>([])
  const [threshold, setThreshold] = useState<number>(0.3)
  const [galleryLoading, setGalleryLoading] = useState(false)
  const [enrollName, setEnrollName] = useState('')
  const [enrollFile, setEnrollFile] = useState<File | null>(null)
  const [galleryError, setGalleryError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const fetchAlerts = useCallback(async () => {
    setAlertsLoading(true)
    setAlertsError(null)
    try {
      const { data } = await api.get('/alerts')
      setAlertList(data || [])
    } catch (e: any) {
      setAlertsError(e?.response?.data?.detail || 'Failed to fetch alerts')
    } finally {
      setAlertsLoading(false)
    }
  }, [])

  const fetchGallery = useCallback(async () => {
    setGalleryLoading(true)
    setGalleryError(null)
    try {
      const [galleryRes, configRes] = await Promise.all([
        api.get('/intruders/gallery'),
        api.get('/intruders/config')
      ])
      setPersons(galleryRes.data || [])
      setThreshold(configRes.data?.threshold ?? 0.3)
    } catch (e: any) {
      setGalleryError(e?.response?.data?.detail || 'Failed to fetch face gallery')
    } finally {
      setGalleryLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAlerts()
    if (tabValue === 1) {
      fetchGallery()
    }
  }, [fetchAlerts, fetchGallery, tabValue, currentFarm])

  const handleAcknowledge = async (alertId: string) => {
    try {
      await api.put(`/alerts/${alertId}/acknowledge`, {})
      setAlertList(prev =>
        prev.map(a => a.id === alertId ? { ...a, acknowledged_at: new Date().toISOString() } : a)
      )
      setSuccessMsg('Alert successfully acknowledged')
    } catch (e: any) {
      setAlertsError(e?.response?.data?.detail || 'Failed to acknowledge alert')
    }
  }

  const handleEnroll = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!enrollName.trim() || !enrollFile) {
      setGalleryError('Please provide both a name and an image file')
      return
    }

    setGalleryLoading(true)
    setGalleryError(null)
    setSuccessMsg(null)

    const formData = new FormData()
    formData.append('name', enrollName.trim())
    formData.append('file', enrollFile)

    try {
      await api.post('/intruders/gallery/enroll', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setSuccessMsg(`Successfully enrolled ${enrollName}`)
      setEnrollName('')
      setEnrollFile(null)
      fetchGallery()
    } catch (e: any) {
      setGalleryError(e?.response?.data?.detail || 'Failed to enroll face')
    } finally {
      setGalleryLoading(false)
    }
  }

  const handleDeleteFace = async (name: string) => {
    if (!window.confirm(`Are you sure you want to remove ${name} from the gallery?`)) {
      return
    }

    setGalleryLoading(true)
    setGalleryError(null)
    setSuccessMsg(null)

    try {
      await api.delete(`/intruders/gallery/${name}`)
      setSuccessMsg(`Successfully removed ${name}`)
      setPersons(prev => prev.filter(p => p.name !== name))
    } catch (e: any) {
      setGalleryError(e?.response?.data?.detail || 'Failed to delete face')
    } finally {
      setGalleryLoading(false)
    }
  }

  const handleThresholdChangeCommitted = async (_event: any, newValue: number | number[]) => {
    const val = newValue as number
    setThreshold(val)
    if (!hasPermission('settings:write')) return

    try {
      await api.put('/intruders/config', { threshold: val })
      setSuccessMsg(`Similarity threshold updated to ${val}`)
    } catch (e: any) {
      setGalleryError(e?.response?.data?.detail || 'Failed to update threshold configuration')
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString()
  }

  const formatEpoch = (epochSecs: number) => {
    if (!epochSecs) return 'Never'
    return new Date(epochSecs * 1000).toLocaleString()
  }

  const totalCameras = cameras.length
  const onlineCameras = cameras.filter((c: any) => c.status === 'online').length
  const offlineCameras = cameras.filter((c: any) => c.status === 'offline').length
  const errorCameras = cameras.filter((c: any) => c.status === 'error').length

  return (
    <Box>
      <Box sx={{ 
        mb: 4, 
        display: 'flex', 
        flexDirection: { xs: 'column', sm: 'row' }, 
        justifyContent: 'space-between', 
        alignItems: { xs: 'flex-start', sm: 'center' }, 
        gap: { xs: 2, sm: 0 } 
      }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>System Alerts</Typography>
          <Typography variant="body2" color="text.secondary">
            Monitor real-time security events, health anomalies, and camera operations
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1.5, width: { xs: '100%', sm: 'auto' }, justifyContent: { xs: 'flex-start', sm: 'flex-end' } }}>
          {tabValue === 0 && (
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={fetchAlerts}
              size="small"
              sx={{ textTransform: 'none' }}
            >
              Refresh
            </Button>
          )}
        </Box>
      </Box>

      {/* Tabs */}
      <Tabs
        value={tabValue}
        onChange={(_e, val) => setTabValue(val)}
        sx={{
          mb: 4,
          borderBottom: '1px solid #e2e8f0',
          '& .MuiTab-root': { textTransform: 'none', fontWeight: 600 }
        }}
      >
        <Tab label="Active Alerts" />
        <Tab label="Face Gallery & Intruder Settings" />
      </Tabs>

      {successMsg && (
        <Alert severity="success" sx={{ mb: 3 }} onClose={() => setSuccessMsg(null)}>
          {successMsg}
        </Alert>
      )}

      {tabValue === 0 && (
        <>
          {/* Summary Cards */}
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

          {alertsError && (
            <Alert severity="error" sx={{ mb: 3 }} onClose={() => setAlertsError(null)}>
              {alertsError}
            </Alert>
          )}

          {/* Alerts Table */}
          {alertsLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
          ) : alertList.length === 0 ? (
            <Paper sx={{ p: 6, textAlign: 'center', border: '1px solid #e2e8f0', boxShadow: 'none' }}>
              <Box sx={{ width: 48, height: 48, borderRadius: '50%', bgcolor: '#e8f5e9', display: 'flex', alignItems: 'center', justifyContent: 'center', mx: 'auto', mb: 2 }}>
                <Box sx={{ width: 20, height: 20, borderRadius: '50%', bgcolor: '#10b981' }} />
              </Box>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>All Clear</Typography>
              <Typography variant="body2" color="text.secondary">No active alerts at this time.</Typography>
            </Paper>
          ) : (
            <TableContainer component={Paper} sx={{ border: '1px solid #e2e8f0', boxShadow: 'none', overflowX: 'auto', width: '100%' }}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Time</TableCell>
                    <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Camera ID</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>Severity</TableCell>
                    <TableCell>Message</TableCell>
                    <TableCell align="right">Action</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {alertList.map((alert) => {
                    const isIntruder = alert.type === 'intruder';
                    return (
                      <TableRow 
                        key={alert.id} 
                        hover
                        sx={isIntruder && !alert.acknowledged_at ? {
                          bgcolor: 'rgba(254, 226, 226, 0.35)',
                          borderLeft: '4px solid #ef4444'
                        } : {}}
                      >
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDate(alert.created_at)}</TableCell>
                        <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' }, fontWeight: 600 }}>{alert.camera_id || 'Global'}</TableCell>
                        <TableCell>
                           <Chip
                             label={alert.type.toUpperCase()}
                             size="small"
                             color={isIntruder ? 'error' : alert.type === 'health_critical' ? 'warning' : 'default'}
                             sx={{ fontWeight: 700, fontSize: '0.7rem', borderRadius: '4px' }}
                           />
                        </TableCell>
                        <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                          <Chip
                            label={alert.severity === 2 ? 'CRITICAL' : alert.severity === 1 ? 'HIGH' : 'MEDIUM'}
                            size="small"
                            variant="outlined"
                            color={alert.severity === 2 ? 'error' : alert.severity === 1 ? 'warning' : 'default'}
                            sx={{ fontWeight: 600, fontSize: '0.7rem', borderRadius: '4px' }}
                          />
                        </TableCell>
                        <TableCell sx={{ color: isIntruder ? '#b91c1c' : '#334155', fontWeight: isIntruder ? 700 : 400 }}>
                          {alert.message}
                        </TableCell>
                        <TableCell align="right">
                          {alert.acknowledged_at ? (
                            <Chip
                              label="Acknowledged"
                              size="small"
                              variant="outlined"
                              color="success"
                              sx={{ fontWeight: 600, fontSize: '0.75rem', borderRadius: '6px' }}
                            />
                          ) : hasPermission('cameras:write') ? (
                            <Button
                              variant="contained"
                              size="small"
                              startIcon={<CheckIcon />}
                              onClick={() => handleAcknowledge(alert.id)}
                              sx={{ 
                                bgcolor: isIntruder ? '#ef4444' : '#0f172a',
                                color: '#fff',
                                '&:hover': { bgcolor: isIntruder ? '#dc2626' : '#1e293b' },
                                textTransform: 'none',
                                fontWeight: 600,
                                borderRadius: '6px'
                              }}
                            >
                              Acknowledge
                            </Button>
                          ) : (
                            <Chip
                              label="Unacknowledged"
                              size="small"
                              color="warning"
                              variant="outlined"
                              sx={{ fontWeight: 600, fontSize: '0.75rem', borderRadius: '6px' }}
                            />
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}

      {tabValue === 1 && (
        <>
          {galleryError && (
            <Alert severity="error" sx={{ mb: 3 }} onClose={() => setGalleryError(null)}>
              {galleryError}
            </Alert>
          )}

          <Grid container spacing={4}>
            {/* Left Column: Config and Enroll */}
            <Grid item xs={12} md={4}>
              <Grid container spacing={4}>
                {/* Similarity Config */}
                <Grid item xs={12}>
                  <Paper sx={{ p: 3, borderRadius: 3, border: '1px solid #e2e8f0' }} elevation={0}>
                    <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
                      Matching Configuration
                    </Typography>
                    <Divider sx={{ mb: 3 }} />
                    
                    <Box sx={{ px: 1 }}>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        The similarity threshold controls how strictly the facial recognition engine verifies matches. 
                        A higher threshold requires more precise similarity (reduces false positives, may miss matches). 
                        The default target is <b>0.3</b>.
                      </Typography>

                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                          Match Threshold
                        </Typography>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#ef4444' }}>
                          {threshold.toFixed(2)}
                        </Typography>
                      </Box>

                      <Slider
                        value={threshold}
                        min={0.1}
                        max={0.9}
                        step={0.05}
                        onChange={(_e, val) => setThreshold(val as number)}
                        onChangeCommitted={handleThresholdChangeCommitted}
                        disabled={!hasPermission('settings:write')}
                        valueLabelDisplay="auto"
                        sx={{
                          color: '#ef4444',
                          '& .MuiSlider-thumb': {
                            '&:hover, &.Mui-focusVisible': {
                              boxShadow: '0px 0px 0px 8px rgba(239, 68, 68, 0.16)',
                            },
                          },
                        }}
                      />
                      {!hasPermission('settings:write') && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                          * Read-only. Requires Settings Write permissions to modify.
                        </Typography>
                      )}
                    </Box>
                  </Paper>
                </Grid>

                {/* Enroll New Face */}
                {hasPermission('cameras:write') && (
                  <Grid item xs={12}>
                    <Paper sx={{ p: 3, borderRadius: 3, border: '1px solid #e2e8f0' }} elevation={0}>
                      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
                        Enroll New Face
                      </Typography>
                      <Divider sx={{ mb: 3 }} />

                      <Box component="form" onSubmit={handleEnroll} sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
                        <TextField
                          label="Person's Full Name"
                          variant="outlined"
                          size="small"
                          value={enrollName}
                          onChange={(e) => setEnrollName(e.target.value)}
                          required
                          disabled={galleryLoading}
                          fullWidth
                        />

                        <Button
                          variant="outlined"
                          component="label"
                          startIcon={<CloudUploadIcon />}
                          disabled={galleryLoading}
                          color={enrollFile ? 'success' : 'primary'}
                          fullWidth
                          sx={{ textTransform: 'none', py: 1 }}
                        >
                          {enrollFile ? enrollFile.name : 'Upload Face Image'}
                          <input
                            type="file"
                            accept="image/*"
                            hidden
                            onChange={(e) => {
                              if (e.target.files && e.target.files.length > 0) {
                                setEnrollFile(e.target.files[0])
                              }
                            }}
                          />
                        </Button>

                        <Button
                          type="submit"
                          variant="contained"
                          disabled={galleryLoading || !enrollName.trim() || !enrollFile}
                          sx={{
                            bgcolor: '#0f172a',
                            color: '#fff',
                            '&:hover': { bgcolor: '#1e293b' },
                            py: 1,
                            textTransform: 'none',
                            fontWeight: 600
                          }}
                          fullWidth
                        >
                          {galleryLoading ? <CircularProgress size={24} color="inherit" /> : 'Register Face'}
                        </Button>
                      </Box>
                    </Paper>
                  </Grid>
                )}
              </Grid>
            </Grid>

            {/* Right Column: Known Faces List */}
            <Grid item xs={12} md={8}>
              <Paper sx={{ p: 3, borderRadius: 3, border: '1px solid #e2e8f0', minHeight: 480 }} elevation={0}>
                <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
                  Enrolled Face Database
                </Typography>
                <Divider sx={{ mb: 3 }} />

                {galleryLoading ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
                    <CircularProgress color="error" />
                  </Box>
                ) : persons.length === 0 ? (
                  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, color: 'text.secondary', gap: 2 }}>
                    <FaceIcon sx={{ fontSize: 64, opacity: 0.3 }} />
                    <Typography>No face profiles enrolled yet</Typography>
                    {hasPermission('cameras:write') && (
                      <Typography variant="body2">Use the form on the left to add your first profile</Typography>
                    )}
                  </Box>
                ) : (
                  <Grid container spacing={2.5}>
                    {persons.map((person) => (
                      <Grid item xs={12} sm={6} key={person.name}>
                        <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2, boxShadow: 'none', transition: 'transform 0.2s, box-shadow 0.2s', '&:hover': { transform: 'translateY(-2px)', boxShadow: '0 4px 12px rgba(0,0,0,0.05)' } }}>
                          <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, p: 2.5, '&:last-child': { pb: 2.5 } }}>
                            <Avatar sx={{ bgcolor: '#fee2e2', color: '#ef4444', width: 48, height: 48 }}>
                              <CheckCircleIcon sx={{ fontSize: 28 }} />
                            </Avatar>
                            
                            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                              <Typography variant="subtitle1" sx={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {person.name}
                              </Typography>
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                                Enrolled: {formatEpoch(person.created_at)}
                              </Typography>
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                Last Match: {formatEpoch(person.last_seen)}
                              </Typography>
                              <Typography variant="caption" sx={{ fontWeight: 600, color: '#10b981', display: 'block', mt: 0.5 }}>
                                Matches: {person.match_count} times
                              </Typography>
                            </Box>

                            {hasPermission('cameras:write') && (
                              <Tooltip title="Delete Face Profile">
                                <IconButton 
                                  onClick={() => handleDeleteFace(person.name)} 
                                  disabled={galleryLoading}
                                  color="error"
                                  size="small"
                                  sx={{ border: '1px solid #fee2e2', bgcolor: '#fff', '&:hover': { bgcolor: '#fef2f2' } }}
                                >
                                  <DeleteIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            )}
                          </CardContent>
                        </Card>
                      </Grid>
                    ))}
                  </Grid>
                )}
              </Paper>
            </Grid>
          </Grid>
        </>
      )}
    </Box>
  )
}
