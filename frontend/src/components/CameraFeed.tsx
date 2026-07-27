import { useEffect, useRef, useState, useCallback } from 'react'
import {
  Box, Typography, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Button, FormControlLabel, Checkbox, IconButton, Grid
} from '@mui/material'
import SettingsIcon from '@mui/icons-material/Settings'
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord'
import api from '../api/axios'
import { useCameras } from '../hooks/useCameras'
import { useAuth } from '../auth/AuthContext'
import { useOnlineStatus } from '../hooks/useOnlineStatus'

function getAuthToken(): string | null {
  return localStorage.getItem('impersonation_token') || localStorage.getItem('access_token')
}

interface CameraFeedProps {
  id: string
  name: string
  status: string
  compact?: boolean
}

export function CameraFeed({ id, name, status, compact = false }: CameraFeedProps) {
  const { cameras, updateCamera, deleteCamera } = useCameras()
  const { hasPermission } = useAuth()
  const currentCamera = cameras.find(c => c.id === id)
  const canWrite = hasPermission('cameras:write')
  const isAppOnline = useOnlineStatus()

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<number>()
  const [streamStatus, setStreamStatus] = useState<'connecting' | 'live' | 'reconnecting' | 'error'>('connecting')
  const [detections, setDetections] = useState<any[]>([])
  const [showOverlay, setShowOverlay] = useState(true)
  const lastFrameTimeRef = useRef<number>(0)

  // Edit camera state
  const [editOpen, setEditOpen] = useState(false)
  const [form, setForm] = useState({
    name: '', rtspUrl: '', location: '', zone: '', fpsTarget: 5,
    username: '', password: '', enabled: true
  })
  const [points, setPoints] = useState<number[][]>([])
  const [editError, setEditError] = useState('')
  const [submitting, setSubmitting] = useState(false)

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
        name: form.name, rtsp_url: form.rtspUrl,
        location: form.location || null, zone: form.zone || null,
        fps_target: form.fpsTarget, username: form.username || null,
        password: form.password || null, enabled: form.enabled,
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
    if (!window.confirm(`Delete camera "${name}"?`)) return
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

  const svgRef = useRef<SVGSVGElement>(null)
  const dialogCanvasRef = useRef<HTMLCanvasElement>(null)
  const dialogWsRef = useRef<WebSocket | null>(null)
  const dialogImgRef = useRef<HTMLImageElement | null>(null)

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    setPoints(prev => [...prev, [parseFloat(x.toFixed(4)), parseFloat(y.toFixed(4))]])
  }

  const handleVertexClick = (idx: number, e: React.MouseEvent) => {
    e.stopPropagation()
    setPoints(prev => prev.filter((_, i) => i !== idx))
  }

  const drawFrameToCanvas = useCallback((canvas: HTMLCanvasElement, blob: Blob) => {
    if (!imgRef.current) {
      imgRef.current = new Image()
    }
    const img = imgRef.current
    const url = URL.createObjectURL(blob)
    img.onload = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      canvas.width = img.naturalWidth
      canvas.height = img.naturalHeight
      ctx.drawImage(img, 0, 0)
      URL.revokeObjectURL(url)
    }
    img.src = url
  }, [])

  const isOffline = status === 'offline' || status === 'error' || !isAppOnline

  // WebSocket connection for video stream
  useEffect(() => {
    if (isOffline || !isAppOnline) return

    let ws: WebSocket | null = null
    let reconnectAttempts = 0
    const maxReconnectDelay = 30000

    const connect = () => {
      const token = getAuthToken()
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${protocol}//${window.location.host}/cvws/${id}?token=${token}`

      ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        reconnectAttempts = 0
        setStreamStatus('live')
      }

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          const blob = new Blob([event.data], { type: 'image/jpeg' })
          const canvas = canvasRef.current
          if (canvas) {
            drawFrameToCanvas(canvas, blob)
          }
          lastFrameTimeRef.current = Date.now()
        } else {
          try {
            const msg = JSON.parse(event.data)
            if (msg.type === 'detections') {
              setDetections(msg.detections || [])
            }
          } catch { }
        }
      }

      ws.onclose = () => {
        setStreamStatus('reconnecting')
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), maxReconnectDelay)
        reconnectRef.current = window.setTimeout(() => {
          reconnectAttempts++
          connect()
        }, delay)
      }

      ws.onerror = () => {
        setStreamStatus('error')
      }
    }

    connect()

    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
      ws?.close()
      wsRef.current = null
    }
  }, [id, isAppOnline, drawFrameToCanvas])

  // Canvas overlay drawing
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !showOverlay) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    if (detections.length === 0) return

    const videoW = canvas.width || 640
    const videoH = canvas.height || 360

    // Draw detections on top of the frame
    detections.forEach((det: any) => {
      const { bbox, class_name, confidence, track_id } = det
      if (!bbox) return
      const x = bbox.x ?? 0, y = bbox.y ?? 0, w = bbox.w ?? 0, h = bbox.h ?? 0

      const color = '#00f3ff'
      ctx.strokeStyle = color
      ctx.lineWidth = 2

      const len = Math.min(12, w / 4, h / 4)
      ctx.beginPath(); ctx.moveTo(x, y + len); ctx.lineTo(x, y); ctx.lineTo(x + len, y); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(x + w - len, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + len); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(x, y + h - len); ctx.lineTo(x, y + h); ctx.lineTo(x + len, y + h); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(x + w - len, y + h); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w, y + h - len); ctx.stroke()

      const label = `#${track_id ?? '?'} ${class_name?.toUpperCase() ?? ''} ${((confidence ?? 0) * 100).toFixed(0)}%`
      ctx.font = '700 9px "JetBrains Mono", monospace'
      const tw = ctx.measureText(label).width
      ctx.fillStyle = 'rgba(5, 7, 12, 0.85)'
      ctx.fillRect(x, y - 15, tw + 6, 15)
      ctx.fillStyle = color
      ctx.fillText(label, x + 3, y - 4)
    })
  }, [detections, showOverlay])

  // Dialog preview WebSocket
  useEffect(() => {
    if (!editOpen || isOffline) return

    const canvas = dialogCanvasRef.current
    if (!canvas) return
    if (!dialogImgRef.current) dialogImgRef.current = new Image()

    const token = getAuthToken()
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/cvws/${id}?token=${token}`
    const ws = new WebSocket(wsUrl)
    dialogWsRef.current = ws

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const blob = new Blob([event.data], { type: 'image/jpeg' })
        const img = dialogImgRef.current!
        const url = URL.createObjectURL(blob)
        img.onload = () => {
          const ctx = canvas.getContext('2d')
          if (!ctx) return
          canvas.width = img.naturalWidth
          canvas.height = img.naturalHeight
          ctx.drawImage(img, 0, 0)
          URL.revokeObjectURL(url)
        }
        img.src = url
      }
    }

    return () => {
      ws.close()
      dialogWsRef.current = null
    }
  }, [editOpen, id, isOffline])

  const statusColor = status === 'online' ? '#10b981' : status === 'error' ? '#ef4444' : '#6b7280'

  return (
    <Box
      sx={{
        position: 'relative', bgcolor: '#020408', borderRadius: '12px', overflow: 'hidden',
        aspectRatio: '16/9', display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: `1px solid ${isOffline ? 'rgba(239, 68, 68, 0.2)' : 'rgba(255, 255, 255, 0.05)'}`,
        boxShadow: isOffline ? '0 4px 20px rgba(239, 68, 68, 0.05)' : 'none',
        '&:hover': { border: `1px solid ${status === 'online' ? 'rgba(94, 92, 230, 0.3)' : 'rgba(239, 68, 68, 0.3)'}` }
      }}
    >
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
          <canvas
            ref={canvasRef}
            style={{ width: '100%', height: '100%', objectFit: 'fill', display: 'block' }}
          />
        </Box>
      )}

      {/* Floating Header */}
      <Box sx={{ position: 'absolute', top: 12, left: 12, zIndex: 4, display: 'flex', alignItems: 'center', gap: 1, bgcolor: 'rgba(0, 0, 0, 0.6)', backdropFilter: 'blur(4px)', px: 1.25, py: 0.5, borderRadius: '6px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
        <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: statusColor, boxShadow: `0 0 8px ${statusColor}`, animation: status === 'online' ? 'pulse 1.5s infinite' : 'none', '@keyframes pulse': { '0%': { transform: 'scale(1)', opacity: 1 }, '50%': { transform: 'scale(1.3)', opacity: 0.4 }, '100%': { transform: 'scale(1)', opacity: 1 } } }} />
        <Typography variant="caption" sx={{ color: 'white', fontFamily: '"JetBrains Mono", monospace', fontSize: '10px', fontWeight: 700 }}>
          {streamStatus === 'live' ? 'LIVE' : streamStatus === 'connecting' ? 'CONNECTING...' : streamStatus === 'reconnecting' ? 'RECONNECTING...' : 'ERROR'}
        </Typography>
      </Box>

      {/* Camera Name */}
      <Typography variant="caption" sx={{ position: 'absolute', bottom: 12, left: 12, color: 'white', bgcolor: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', px: 1.5, py: 0.5, borderRadius: '6px', fontFamily: '"Outfit", sans-serif', fontWeight: 600, border: '1px solid rgba(255,255,255,0.08)', zIndex: 4 }}>
        {name}
      </Typography>

      {/* BBOX toggle */}
      {status === 'online' && !isOffline && (
        <Box onClick={(e) => { e.stopPropagation(); setShowOverlay(!showOverlay) }} sx={{ position: 'absolute', bottom: 12, right: 12, zIndex: 10, bgcolor: showOverlay ? 'rgba(0, 243, 255, 0.15)' : 'rgba(255,255,255,0.08)', backdropFilter: 'blur(4px)', border: `1px solid ${showOverlay ? 'rgba(0, 243, 255, 0.3)' : 'rgba(255,255,255,0.1)'}`, px: 0.75, py: 0.25, borderRadius: '4px', cursor: 'pointer', fontFamily: '"JetBrains Mono", monospace', fontSize: '9px', fontWeight: 700, color: showOverlay ? '#00f3ff' : 'text.secondary', transition: 'all 0.15s ease' }}>
          {showOverlay ? 'BBOX ON' : 'BBOX OFF'}
        </Box>
      )}

      {/* Settings */}
      {canWrite && (
        <IconButton onClick={(e) => { e.stopPropagation(); handleOpenEdit() }} sx={{ position: 'absolute', top: 12, right: 12, zIndex: 10, bgcolor: 'rgba(0, 0, 0, 0.6)', backdropFilter: 'blur(4px)', color: 'white', border: '1px solid rgba(255, 255, 255, 0.08)', p: 0.75, borderRadius: '6px', '&:hover': { bgcolor: 'rgba(94, 92, 230, 0.2)', borderColor: 'rgba(94, 92, 230, 0.4)', color: '#00f3ff' } }} size="small">
          <SettingsIcon sx={{ fontSize: '16px' }} />
        </IconButton>
      )}

      {/* Edit Camera Dialog */}
      <Dialog open={editOpen} onClose={() => setEditOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontWeight: 700, fontFamily: '"Outfit", sans-serif' }}>Edit Camera & ROI</DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={3}>
            <Grid item xs={12} md={5}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <TextField fullWidth label="Camera ID" value={id} size="small" InputProps={{ readOnly: true }} disabled />
                <TextField fullWidth label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} size="small" required />
                <TextField fullWidth label="RTSP URL" value={form.rtspUrl} onChange={(e) => setForm({ ...form, rtspUrl: e.target.value })} size="small" required />
                <TextField fullWidth label="Location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} size="small" />
                <TextField fullWidth label="Zone" value={form.zone} onChange={(e) => setForm({ ...form, zone: e.target.value })} size="small" />
                <TextField fullWidth label="FPS Target" type="number" value={form.fpsTarget} onChange={(e) => setForm({ ...form, fpsTarget: parseInt(e.target.value) || 5 })} size="small" />
                <TextField fullWidth label="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} size="small" />
                <TextField fullWidth label="Password" type="password" value={form.password} placeholder="Leave blank to keep current" onChange={(e) => setForm({ ...form, password: e.target.value })} size="small" />
                <FormControlLabel control={<Checkbox checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />} label="Enabled" />
                {editError && <Typography variant="body2" color="error">{editError}</Typography>}
                {hasPermission('cameras:delete') && (
                  <Button variant="outlined" color="error" size="small" onClick={handleDeleteCamera} disabled={submitting} sx={{ mt: 2, alignSelf: 'flex-start' }}>Delete Camera</Button>
                )}
              </Box>
            </Grid>
            <Grid item xs={12} md={7}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>ROI Polygon ({points.length} points)</Typography>
              <Box sx={{ position: 'relative', width: '100%', aspectRatio: '16/9', bgcolor: '#020408', borderRadius: '8px', overflow: 'hidden', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
                <canvas ref={dialogCanvasRef} style={{ width: '100%', height: '100%', objectFit: 'fill' }} />
                <svg ref={svgRef} viewBox="0 0 1000 1000" preserveAspectRatio="none" onClick={handleSvgClick} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', cursor: 'crosshair', zIndex: 10 }}>
                  {points.length > 0 && <polygon points={points.map(([x, y]) => `${x * 1000},${y * 1000}`).join(' ')} fill="rgba(16, 185, 129, 0.2)" stroke="#10b981" strokeWidth="4" />}
                  {points.map(([x, y], idx) => (
                    <circle key={idx} cx={x * 1000} cy={y * 1000} r="12" fill="#ffffff" stroke="#10b981" strokeWidth="3" style={{ cursor: 'pointer' }} onClick={(e) => handleVertexClick(idx, e)} />
                  ))}
                </svg>
              </Box>
              <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
                <Button size="small" variant="outlined" onClick={() => setPoints(prev => prev.slice(0, -1))} disabled={points.length === 0}>Undo</Button>
                <Button size="small" variant="outlined" color="warning" onClick={() => setPoints([])} disabled={points.length === 0}>Clear</Button>
                <Button size="small" variant="outlined" onClick={() => setPoints(currentCamera?.roi || [])}>Reset</Button>
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                Click to place vertices. 3+ points for a valid polygon.
              </Typography>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditOpen(false)} disabled={submitting}>Cancel</Button>
          <Button variant="contained" onClick={handleSaveEdit} disabled={submitting}>{submitting ? 'Saving...' : 'Save'}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
