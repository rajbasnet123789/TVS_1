import { useEffect, useRef, useState } from 'react'
import {
  Box, Typography, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Button, FormControlLabel, Checkbox, IconButton, Grid
} from '@mui/material'
import SettingsIcon from '@mui/icons-material/Settings'
import HistoryIcon from '@mui/icons-material/History'
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord'
import Hls from 'hls.js'
import api from '../api/axios'
import { useWebSocket } from '../hooks/useWebSocket'
import { useCameras } from '../hooks/useCameras'
import { useAuth } from '../auth/AuthContext'
import { useOnlineStatus } from '../hooks/useOnlineStatus'

function getAuthToken(): string | null {
  return localStorage.getItem('impersonation_token') || localStorage.getItem('access_token')
}

function hlsConfigWithAuth(overrides: Record<string, any> = {}): Record<string, any> {
  return {
    ...overrides,
    xhrSetup: (xhr: XMLHttpRequest, url: string) => {
      const token = getAuthToken()
      if (token) {
        xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      }
    },
  }
}

interface CameraFeedProps {
  id: string
  name: string
  hlsUrl: string | null
  rtspUrl: string
  status: string
  compact?: boolean
}

export function CameraFeed({ id, name, hlsUrl, status, compact = false }: CameraFeedProps) {
  const { cameras, updateCamera, deleteCamera } = useCameras()
  const { hasPermission } = useAuth()
  const currentCamera = cameras.find(c => c.id === id)
  const canWrite = hasPermission('cameras:write')
  const isAppOnline = useOnlineStatus()

  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const hlsRef = useRef<Hls | null>(null)
  const timeoutRef = useRef<number>()
  const [detections, setDetections] = useState<any[]>([])
  const [showOverlay, setShowOverlay] = useState(true)

  // Edit camera state
  const [editOpen, setEditOpen] = useState(false)
  const [form, setForm] = useState({
    name: '',
    rtspUrl: '',
    location: '',
    zone: '',
    fpsTarget: 5,
    username: '',
    password: '',
    enabled: true
  })
  const [points, setPoints] = useState<number[][]>([])
  const [editError, setEditError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Playback state
  const [playbackMode, setPlaybackMode] = useState(false)
  const [playbackHlsUrl, setPlaybackHlsUrl] = useState<string | null>(null)
  const [playbackSessionId, setPlaybackSessionId] = useState<string | null>(null)
  const [playbackDialogOpen, setPlaybackDialogOpen] = useState(false)
  const [playbackTime, setPlaybackTime] = useState(() => {
    const d = new Date()
    d.setHours(d.getHours() - 1)
    return d.toISOString().slice(0, 16)
  })
  const [playbackLoading, setPlaybackLoading] = useState(false)
  const [playbackError, setPlaybackError] = useState('')
  const playbackVideoRef = useRef<HTMLVideoElement>(null)
  const playbackHlsRef = useRef<Hls | null>(null)

  const handleOpenEdit = () => {
    if (currentCamera) {
      setForm({
        name: currentCamera.name,
        rtspUrl: currentCamera.rtsp_url,
        location: currentCamera.location || '',
        zone: currentCamera.zone || '',
        fpsTarget: currentCamera.fps_target,
        username: currentCamera.username || '',
        password: '',
        enabled: currentCamera.enabled
      })
      setPoints(currentCamera.roi || [])
      setEditError('')
      setEditOpen(true)
    }
  }

  const handleSaveEdit = async () => {
    if (submitting) return
    setEditError('')
    if (!form.name.trim() || !form.rtspUrl.trim()) {
      setEditError('Name and RTSP URL are required')
      return
    }
    setSubmitting(true)
    try {
      await updateCamera(id, {
        name: form.name,
        rtsp_url: form.rtspUrl,
        location: form.location || null,
        zone: form.zone || null,
        fps_target: form.fpsTarget,
        username: form.username || null,
        password: form.password || null,
        enabled: form.enabled,
        roi: points.length > 0 ? points : null
      })
      setEditOpen(false)
    } catch (e: any) {
      setEditError(e?.response?.data?.detail || 'Failed to update camera')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteCamera = async () => {
    if (submitting) return
    const ok = window.confirm(`Are you sure you want to delete camera "${name}"?`)
    if (!ok) return
    setSubmitting(true)
    try {
      await deleteCamera(id)
      setEditOpen(false)
    } catch (e: any) {
      setEditError(e?.response?.data?.detail || 'Failed to delete camera')
    } finally {
      setSubmitting(false)
    }
  }

  const startPlayback = async () => {
    setPlaybackLoading(true)
    setPlaybackError('')
    try {
      const { data } = await api.post(`/nvr/playback/start/${id}?at=${encodeURIComponent(playbackTime)}`)
      setPlaybackHlsUrl(data.hls_url)
      setPlaybackSessionId(data.session_id)
      setPlaybackDialogOpen(false)
      setPlaybackMode(true)
    } catch (e: any) {
      setPlaybackError(e?.response?.data?.detail || 'Failed to start playback')
    } finally {
      setPlaybackLoading(false)
    }
  }

  const stopPlayback = async () => {
    if (playbackSessionId) {
      try {
        await api.post(`/nvr/playback/stop?session_id=${playbackSessionId}`)
      } catch { }
    }
    playbackHlsRef.current?.destroy()
    playbackHlsRef.current = null
    setPlaybackSessionId(null)
    setPlaybackHlsUrl(null)
    setPlaybackMode(false)
  }

  const svgRef = useRef<SVGSVGElement>(null)
  const dialogVideoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    if (!editOpen || !dialogVideoRef.current || !hlsUrl || status !== 'online' || !isAppOnline) return

    const video = dialogVideoRef.current
    const hlsBase = window.location.origin
    const fullUrl = hlsUrl.startsWith('http') ? hlsUrl : `${hlsBase}${hlsUrl}`
    let hls: Hls | null = null

    if (Hls.isSupported()) {
      hls = new Hls(hlsConfigWithAuth({
        maxBufferLength: 1.0,
        maxBufferSize: 4000000,
        lowLatencyMode: true,
      }))
      hls.loadSource(fullUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {})
      })
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = fullUrl
      video.play().catch(() => {})
    }

    return () => {
      hls?.destroy()
    }
  }, [editOpen, hlsUrl, status])

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    const newPoint = [parseFloat(x.toFixed(4)), parseFloat(y.toFixed(4))]
    setPoints(prev => [...prev, newPoint])
  }

  const handleVertexClick = (idx: number, e: React.MouseEvent) => {
    e.stopPropagation()
    setPoints(prev => prev.filter((_, i) => i !== idx))
  }

  useWebSocket({
    detection: (msg: any) => {
      if (msg.camera_id === id) {
        setDetections(msg.detections || [])
        if (timeoutRef.current) window.clearTimeout(timeoutRef.current)
        timeoutRef.current = window.setTimeout(() => {
          setDetections([])
        }, 1500)
      }
    }
  })

  useEffect(() => {
    return () => {
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current)
    }
  }, [])

  useEffect(() => {
    if (!videoRef.current || !hlsUrl || status !== 'online' || !isAppOnline) return

    const video = videoRef.current
    const hlsBase = window.location.origin
    const fullUrl = hlsUrl.startsWith('http') ? hlsUrl : `${hlsBase}${hlsUrl}`

    const handleTimeUpdate = () => {
      if (hlsRef.current && !video.paused && hlsRef.current.liveSyncPosition) {
        const drift = hlsRef.current.liveSyncPosition - video.currentTime
        if (drift > 1.3) {
          video.currentTime = hlsRef.current.liveSyncPosition
        }
      }
    }

    if (Hls.isSupported()) {
      const hls = new Hls(hlsConfigWithAuth({
        maxBufferLength: 1.0,
        maxBufferSize: 4000000,
        liveSyncDuration: 0.4,
        liveMaxLatencyDuration: 1.2,
        liveSyncDurationCount: 1,
        liveMaxLatencyDurationCount: 2,
        backBufferLength: 0,
        lowLatencyMode: true,
        enableWorker: true,
      }))
      hls.loadSource(fullUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {})
        if (hls.liveSyncPosition) {
          video.currentTime = hls.liveSyncPosition
        }
      })
      hlsRef.current = hls
      video.addEventListener('timeupdate', handleTimeUpdate)
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = fullUrl
      video.play().catch(() => {})
    }

    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate)
      hlsRef.current?.destroy()
      hlsRef.current = null
    }
  }, [hlsUrl, status])

  useEffect(() => {
    if (!playbackMode || !playbackHlsUrl || !playbackVideoRef.current || !isAppOnline) return
    const video = playbackVideoRef.current
    const hlsBase = window.location.origin
    const fullUrl = playbackHlsUrl.startsWith('http') ? playbackHlsUrl : `${hlsBase}${playbackHlsUrl}`
    let hls: Hls | null = null

    if (Hls.isSupported()) {
      hls = new Hls(hlsConfigWithAuth({ maxBufferLength: 5, liveSyncDuration: 1, lowLatencyMode: false }))
      hls.loadSource(fullUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}))
      playbackHlsRef.current = hls
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = fullUrl
      video.play().catch(() => {})
    }

    return () => {
      hls?.destroy()
      playbackHlsRef.current = null
    }
  }, [playbackMode, playbackHlsUrl])

  const isOffline = status === 'offline' || status === 'error' || !isAppOnline

  // Canvas drawing loop
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    if (isOffline || status !== 'online' || !showOverlay) {
      return
    }

    canvas.width = canvas.clientWidth
    canvas.height = canvas.clientHeight

    // Draw ROI polygon if present
    if (currentCamera?.roi && currentCamera.roi.length >= 3) {
      ctx.beginPath()
      const startX = currentCamera.roi[0][0] * canvas.width
      const startY = currentCamera.roi[0][1] * canvas.height
      ctx.moveTo(startX, startY)
      for (let i = 1; i < currentCamera.roi.length; i++) {
        const px = currentCamera.roi[i][0] * canvas.width
        const py = currentCamera.roi[i][1] * canvas.height
        ctx.lineTo(px, py)
      }
      ctx.closePath()

      // Transparent fill
      ctx.fillStyle = 'rgba(16, 185, 129, 0.05)'
      ctx.fill()

      // Dotted border
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.6)'
      ctx.lineWidth = 1.5
      ctx.setLineDash([4, 4])
      ctx.stroke()
      ctx.setLineDash([]) // Reset
    }

    if (detections.length === 0) {
      return
    }

    const video = videoRef.current
    if (!video) return
    const videoW = video.videoWidth || 640
    const videoH = video.videoHeight || 360

    const scaleX = canvas.width / videoW
    const scaleY = canvas.height / videoH

    detections.forEach((det: any) => {
      const { bbox, class_name, confidence, track_id } = det
      const x = bbox.x * scaleX
      const y = bbox.y * scaleY
      const w = bbox.w * scaleX
      const h = bbox.h * scaleY

      const color = '#00f3ff'
      ctx.strokeStyle = color
      ctx.lineWidth = 2

      const len = Math.min(12, w / 4, h / 4)

      // Top-Left corner
      ctx.beginPath()
      ctx.moveTo(x, y + len)
      ctx.lineTo(x, y)
      ctx.lineTo(x + len, y)
      ctx.stroke()

      // Top-Right corner
      ctx.beginPath()
      ctx.moveTo(x + w - len, y)
      ctx.lineTo(x + w, y)
      ctx.lineTo(x + w, y + len)
      ctx.stroke()

      // Bottom-Left corner
      ctx.beginPath()
      ctx.moveTo(x, y + h - len)
      ctx.lineTo(x, y + h)
      ctx.lineTo(x + len, y + h)
      ctx.stroke()

      // Bottom-Right corner
      ctx.beginPath()
      ctx.moveTo(x + w - len, y + h)
      ctx.lineTo(x + w, y + h)
      ctx.lineTo(x + w, y + h - len)
      ctx.stroke()

      // Subtle filled background
      ctx.fillStyle = 'rgba(0, 243, 255, 0.04)'
      ctx.fillRect(x, y, w, h)

      // Tactical badge
      const label = `#${track_id ?? '?'} ${class_name.toUpperCase()} ${(confidence * 100).toFixed(0)}%`
      ctx.font = '700 9px "JetBrains Mono", monospace'
      const textWidth = ctx.measureText(label).width

      // Badge background
      ctx.fillStyle = 'rgba(5, 7, 12, 0.85)'
      ctx.fillRect(x, y - 15, textWidth + 6, 15)

      // Badge text
      ctx.fillStyle = color
      ctx.fillText(label, x + 3, y - 4)
    })
  }, [detections, isOffline, status, currentCamera, showOverlay])

  const statusColor = status === 'online' ? '#10b981' : status === 'error' ? '#ef4444' : '#6b7280'

  return (
    <Box
      sx={{
        position: 'relative',
        bgcolor: '#020408',
        borderRadius: '12px',
        overflow: 'hidden',
        aspectRatio: '16/9',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: `1px solid ${isOffline ? 'rgba(239, 68, 68, 0.2)' : 'rgba(255, 255, 255, 0.05)'}`,
        boxShadow: isOffline ? '0 4px 20px rgba(239, 68, 68, 0.05)' : 'none',
        '&:hover': {
          border: `1px solid ${status === 'online' ? 'rgba(94, 92, 230, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
        }
      }}
    >
      {/* High-tech Camera HUD corner bracket overlays */}
      <Box sx={{ position: 'absolute', top: 12, left: 12, width: 10, height: 10, borderTop: '2px solid rgba(255,255,255,0.25)', borderLeft: '2px solid rgba(255,255,255,0.25)' }} />
      <Box sx={{ position: 'absolute', top: 12, right: 12, width: 10, height: 10, borderTop: '2px solid rgba(255,255,255,0.25)', borderRight: '2px solid rgba(255,255,255,0.25)' }} />
      <Box sx={{ position: 'absolute', bottom: 12, left: 12, width: 10, height: 10, borderBottom: '2px solid rgba(255,255,255,0.25)', borderLeft: '2px solid rgba(255,255,255,0.25)' }} />
      <Box sx={{ position: 'absolute', bottom: 12, right: 12, width: 10, height: 10, borderBottom: '2px solid rgba(255,255,255,0.25)', borderRight: '2px solid rgba(255,255,255,0.25)' }} />

      {isOffline ? (
        <Box sx={{ textAlign: 'center', color: 'text.secondary', zIndex: 1 }}>
          <Typography variant="body2" sx={{ fontFamily: '"Outfit", sans-serif', fontWeight: 600, color: '#ef4444', letterSpacing: '0.05em' }}>
            {!isAppOnline ? 'APP OFFLINE' : 'CAMERA OFFLINE'}
          </Typography>
        </Box>
      ) : (
        <Box sx={{ position: 'relative', width: '100%', height: '100%' }}>
          {playbackMode ? (
            <video
              ref={playbackVideoRef}
              autoPlay
              muted
              playsInline
              style={{ width: '100%', height: '100%', objectFit: 'fill', filter: 'grayscale(0.3)' }}
            />
          ) : (
            <>
              <video
                ref={videoRef}
                autoPlay
                muted
                playsInline
                style={{ width: '100%', height: '100%', objectFit: 'fill' }}
              />
              <canvas
                ref={canvasRef}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                  zIndex: 3,
                }}
              />
            </>
          )}
        </Box>
      )}

      {/* Floating Header Info */}
      <Box 
        sx={{ 
          position: 'absolute', 
          top: 12, 
          left: 12, 
          zIndex: 4, 
          display: 'flex', 
          alignItems: 'center', 
          gap: 1,
          bgcolor: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(4px)',
          px: 1.25,
          py: 0.5,
          borderRadius: '6px',
          border: '1px solid rgba(255, 255, 255, 0.08)'
        }}
      >
        <Box 
          sx={{ 
            width: 6, 
            height: 6, 
            borderRadius: '50%', 
            bgcolor: statusColor,
            boxShadow: `0 0 8px ${statusColor}`,
            animation: status === 'online' ? 'pulse 1.5s infinite' : 'none',
            '@keyframes pulse': {
              '0%': { transform: 'scale(1)', opacity: 1 },
              '50%': { transform: 'scale(1.3)', opacity: 0.4 },
              '100%': { transform: 'scale(1)', opacity: 1 },
            }
          }}
        />
        <Typography 
          variant="caption" 
          sx={{ 
            color: 'white', 
            fontFamily: '"JetBrains Mono", monospace', 
            fontSize: '10px',
            fontWeight: 700
          }}
        >
          {playbackMode ? 'PLAYBACK' : status === 'online' ? 'LIVE' : 'LOSS'}
        </Typography>
      </Box>

      {/* Camera Name overlay at bottom left */}
      <Typography
        variant="caption"
        sx={{
          position: 'absolute',
          bottom: 12,
          left: 12,
          color: 'white',
          bgcolor: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(4px)',
          px: 1.5,
          py: 0.5,
          borderRadius: '6px',
          fontFamily: '"Outfit", sans-serif',
          fontWeight: 600,
          border: '1px solid rgba(255,255,255,0.08)',
          zIndex: 4,
        }}
      >
        {name}
      </Typography>

      {/* Detection overlay toggle */}
      {status === 'online' && !isOffline && (
        <Box
          onClick={(e) => { e.stopPropagation(); setShowOverlay(!showOverlay) }}
          sx={{
            position: 'absolute',
            bottom: 12,
            right: 12,
            zIndex: 10,
            bgcolor: showOverlay ? 'rgba(0, 243, 255, 0.15)' : 'rgba(255,255,255,0.08)',
            backdropFilter: 'blur(4px)',
            border: `1px solid ${showOverlay ? 'rgba(0, 243, 255, 0.3)' : 'rgba(255,255,255,0.1)'}`,
            px: 0.75,
            py: 0.25,
            borderRadius: '4px',
            cursor: 'pointer',
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: '9px',
            fontWeight: 700,
            color: showOverlay ? '#00f3ff' : 'text.secondary',
            transition: 'all 0.15s ease',
            '&:hover': { bgcolor: showOverlay ? 'rgba(0, 243, 255, 0.25)' : 'rgba(255,255,255,0.15)' },
          }}
        >
          {showOverlay ? 'BBOX ON' : 'BBOX OFF'}
        </Box>
      )}

      {/* Playback / Live Button */}
      {status === 'online' && !compact && (
        playbackMode ? (
          <Box
            onClick={(e) => { e.stopPropagation(); stopPlayback() }}
            sx={{
              position: 'absolute',
              top: 12,
              right: canWrite ? 48 : 12,
              zIndex: 10,
              display: 'flex', alignItems: 'center', gap: 0.5,
              bgcolor: 'rgba(239, 68, 68, 0.85)',
              backdropFilter: 'blur(4px)',
              color: 'white',
              border: '1px solid rgba(239, 68, 68, 0.5)',
              px: 1, py: 0.5,
              borderRadius: '6px',
              cursor: 'pointer',
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: '11px',
              fontWeight: 700,
              '&:hover': { bgcolor: 'rgba(239, 68, 68, 1)' },
            }}
          >
            <FiberManualRecordIcon sx={{ fontSize: 10 }} />
            LIVE
          </Box>
        ) : (
          <IconButton
            onClick={(e) => { e.stopPropagation(); setPlaybackDialogOpen(true) }}
            sx={{
              position: 'absolute',
              top: 12,
              right: canWrite ? 48 : 12,
              zIndex: 10,
              bgcolor: 'rgba(0, 0, 0, 0.6)',
              backdropFilter: 'blur(4px)',
              color: 'white',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              p: 0.75,
              borderRadius: '6px',
              '&:hover': {
                bgcolor: 'rgba(245, 158, 11, 0.2)',
                borderColor: 'rgba(245, 158, 11, 0.4)',
                color: '#f59e0b',
              }
            }}
            size="small"
          >
            <HistoryIcon sx={{ fontSize: '16px' }} />
          </IconButton>
        )
      )}

      {/* Settings / Edit Button */}
      {canWrite && (
        <IconButton
          onClick={(e) => { e.stopPropagation(); handleOpenEdit() }}
          sx={{
            position: 'absolute',
            top: 12,
            right: 12,
            zIndex: 10,
            bgcolor: 'rgba(0, 0, 0, 0.6)',
            backdropFilter: 'blur(4px)',
            color: 'white',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            p: 0.75,
            borderRadius: '6px',
            '&:hover': {
              bgcolor: 'rgba(94, 92, 230, 0.2)',
              borderColor: 'rgba(94, 92, 230, 0.4)',
              color: '#00f3ff',
            }
          }}
          size="small"
        >
          <SettingsIcon sx={{ fontSize: '16px' }} />
        </IconButton>
      )}

      {/* Playback Dialog */}
      <Dialog open={playbackDialogOpen} onClose={() => setPlaybackDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700, fontFamily: '"Outfit", sans-serif', display: 'flex', alignItems: 'center', gap: 1 }}>
          <HistoryIcon sx={{ color: '#f59e0b' }} />
          NVR Playback
        </DialogTitle>
        <DialogContent>
          <Typography variant="caption" sx={{ color: '#64748b', mb: 2, display: 'block' }}>
            Enter the date and time to start playback from. The NVR will stream recorded footage from that point.
          </Typography>
          <TextField
            fullWidth
            label="Playback Start Time"
            type="datetime-local"
            value={playbackTime}
            onChange={(e) => setPlaybackTime(e.target.value)}
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ mt: 1 }}
          />
          {playbackError && (
            <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
              {playbackError}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPlaybackDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={startPlayback} disabled={playbackLoading || !playbackTime}>
            {playbackLoading ? 'Connecting...' : 'Play'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Camera & ROI Dialog */}
      <Dialog open={editOpen} onClose={() => setEditOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontWeight: 700, fontFamily: '"Outfit", sans-serif' }}>
          Edit Camera & Region of Interest (ROI)
        </DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={3}>
            {/* Left Column: Form Fields */}
            <Grid item xs={12} md={5}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <TextField
                  fullWidth
                  label="Camera ID (Read-only)"
                  value={id}
                  size="small"
                  InputProps={{ readOnly: true }}
                  disabled
                />
                <TextField
                  fullWidth
                  label="Name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  size="small"
                  required
                />
                <TextField
                  fullWidth
                  label="RTSP URL"
                  value={form.rtspUrl}
                  onChange={(e) => setForm({ ...form, rtspUrl: e.target.value })}
                  size="small"
                  required
                />
                <TextField
                  fullWidth
                  label="Location"
                  value={form.location}
                  onChange={(e) => setForm({ ...form, location: e.target.value })}
                  size="small"
                />
                <TextField
                  fullWidth
                  label="Zone"
                  value={form.zone}
                  onChange={(e) => setForm({ ...form, zone: e.target.value })}
                  size="small"
                />
                <TextField
                  fullWidth
                  label="FPS Target"
                  type="number"
                  value={form.fpsTarget}
                  onChange={(e) => setForm({ ...form, fpsTarget: parseInt(e.target.value) || 5 })}
                  size="small"
                />
                <TextField
                  fullWidth
                  label="Username (optional)"
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  size="small"
                />
                <TextField
                  fullWidth
                  label="Password (optional)"
                  type="password"
                  value={form.password}
                  placeholder="Leave blank to keep current password"
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  size="small"
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={form.enabled}
                      onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                    />
                  }
                  label="Enabled"
                />
                {editError && (
                  <Typography variant="body2" color="error" sx={{ mt: 1 }}>
                    {editError}
                  </Typography>
                )}

                {hasPermission('cameras:delete') && (
                  <Button
                    variant="outlined"
                    color="error"
                    size="small"
                    onClick={handleDeleteCamera}
                    disabled={submitting}
                    sx={{ mt: 2, alignSelf: 'flex-start' }}
                  >
                    Delete Camera
                  </Button>
                )}
              </Box>
            </Grid>

            {/* Right Column: ROI Interactive Drawing */}
            <Grid item xs={12} md={7}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, fontFamily: '"Outfit", sans-serif' }}>
                ROI Polygon Coordinates ({points.length} points)
              </Typography>
              
              <Box
                sx={{
                  position: 'relative',
                  width: '100%',
                  aspectRatio: '16/9',
                  bgcolor: '#020408',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                }}
              >
                {status === 'online' && hlsUrl ? (
                  <video
                    ref={dialogVideoRef}
                    autoPlay
                    muted
                    playsInline
                    style={{ width: '100%', height: '100%', objectFit: 'fill' }}
                  />
                ) : (
                  <Box
                    sx={{
                      width: '100%',
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexDirection: 'column',
                      color: 'text.secondary',
                      p: 2,
                    }}
                  >
                    <Typography variant="body2" color="text.secondary" align="center">
                      Camera Offline
                    </Typography>
                    <Typography variant="caption" color="text.secondary" align="center">
                      (Drawing on normalized grid coordinate overlay)
                    </Typography>
                  </Box>
                )}

                {/* SVG Drawing Overlay */}
                <svg
                  ref={svgRef}
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                  onClick={handleSvgClick}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    cursor: 'crosshair',
                    zIndex: 10,
                  }}
                >
                  {points.length > 0 && (
                    <polygon
                      points={points.map(([x, y]) => `${x * 1000},${y * 1000}`).join(' ')}
                      fill="rgba(16, 185, 129, 0.2)"
                      stroke="#10b981"
                      strokeWidth="4"
                    />
                  )}
                  {points.map(([x, y], idx) => (
                    <circle
                      key={idx}
                      cx={x * 1000}
                      cy={y * 1000}
                      r="12"
                      fill="#ffffff"
                      stroke="#10b981"
                      strokeWidth="3"
                      style={{ cursor: 'pointer' }}
                      onClick={(e) => handleVertexClick(idx, e)}
                    />
                  ))}
                </svg>
              </Box>

              <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => setPoints(prev => prev.slice(0, -1))}
                  disabled={points.length === 0}
                >
                  Undo Point
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  color="warning"
                  onClick={() => setPoints([])}
                  disabled={points.length === 0}
                >
                  Clear ROI
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => setPoints(currentCamera?.roi || [])}
                >
                  Reset
                </Button>
              </Box>

              <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                💡 Click anywhere inside the video frame to place vertices.
                Connect points to define the Region of Interest. Detections will only be tracked inside this polygon.
                Click any white vertex dot to delete it.
              </Typography>
              {points.length > 0 && points.length < 3 && (
                <Typography variant="caption" color="warning.main" sx={{ mt: 0.5, display: 'block', fontWeight: 600 }}>
                  ⚠️ A valid polygon requires at least 3 points. Currently: {points.length}.
                </Typography>
              )}
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditOpen(false)} disabled={submitting}>Cancel</Button>
          <Button variant="contained" onClick={handleSaveEdit} disabled={submitting}>
            {submitting ? 'Saving...' : 'Save Changes'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
