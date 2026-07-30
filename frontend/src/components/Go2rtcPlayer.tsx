import { useRef, useEffect } from 'react'
import { Box, CircularProgress, Typography } from '@mui/material'

interface Go2rtcPlayerProps {
  cameraId: string
  className?: string
}

export function Go2rtcPlayer({ cameraId, className }: Go2rtcPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<any>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const hlsUrl = `/go2rtc/api/hls/${cameraId}.m3u8`

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = hlsUrl
      video.play().catch(() => {})
    } else {
      import('hls.js').then(({ default: Hls }) => {
        if (Hls.isSupported()) {
          const hls = new Hls()
          hlsRef.current = hls
          hls.loadSource(hlsUrl)
          hls.attachMedia(video)
          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            video.play().catch(() => {})
          })
        }
      }).catch(() => {})
    }

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy()
        hlsRef.current = null
      }
      if (video) video.src = ''
    }
  }, [cameraId])

  return (
    <Box sx={{ position: 'relative', bgcolor: '#000', width: '100%', height: '100%' }} className={className}>
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
      />
    </Box>
  )
}
