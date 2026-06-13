import { useEffect, useRef, useState } from 'react'
import { Box, Typography } from '@mui/material'
import Hls from 'hls.js'
import { useWebSocket } from '../hooks/useWebSocket'

interface CameraFeedProps {
  id: string
  name: string
  hlsUrl: string | null
  rtspUrl: string
  status: string
  compact?: boolean
}

export function CameraFeed({ id, name, hlsUrl, status, compact }: CameraFeedProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const hlsRef = useRef<Hls | null>(null)
  const timeoutRef = useRef<number>()
  const [detections, setDetections] = useState<any[]>([])
  const [showOverlay, setShowOverlay] = useState(true)

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
    if (!videoRef.current || !hlsUrl || status !== 'online') return

    const video = videoRef.current
    const hlsBase = import.meta.env.VITE_MEDIAMTX_HLS_BASE || 'http://localhost:8888'
    const fullUrl = hlsUrl.startsWith('http') ? hlsUrl : `${hlsBase}${hlsUrl}`

    if (Hls.isSupported()) {
      const hls = new Hls({
        maxBufferLength: 2,
        maxBufferSize: 20000000,
        liveSyncDuration: 2,
        liveMaxLatencyDuration: 4,
        backBufferLength: 0,
        lowLatencyMode: true,
        enableWorker: true,
      })
      hls.loadSource(fullUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}))
      hlsRef.current = hls
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = fullUrl
      video.play().catch(() => {})
    }

    return () => {
      hlsRef.current?.destroy()
      hlsRef.current = null
    }
  }, [hlsUrl, status])

  const isOffline = status === 'offline' || status === 'error'

  // Canvas drawing loop
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    if (isOffline || status !== 'online' || detections.length === 0 || !showOverlay) {
      return
    }

    canvas.width = canvas.clientWidth
    canvas.height = canvas.clientHeight

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
  }, [detections, isOffline, status])

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
            CAMERA OFFLINE
          </Typography>
        </Box>
      ) : (
        <Box sx={{ position: 'relative', width: '100%', height: '100%' }}>
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
          {status === 'online' ? 'LIVE' : 'LOSS'}
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
    </Box>
  )
}
