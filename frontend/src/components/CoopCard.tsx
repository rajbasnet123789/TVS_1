import { useState, useRef } from 'react'
import { Box, Typography, Card, CardContent, Chip, IconButton } from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import VideocamIcon from '@mui/icons-material/Videocam'
import api from '../api/axios'
import type { Camera } from '../types'

export interface CoopData {
  id: string
  name: string
  sort_order: number
  created_at: string
  cameras: Camera[]
}

interface CoopCardProps {
  coop: CoopData
  canWrite: boolean
  onCameraClick: (camera: Camera) => void
  onEdit: (coop: CoopData) => void
  onDelete: (coop: CoopData) => void
  onRefresh?: (isSilent?: boolean) => void
}

export function CoopCard({ coop, canWrite, onCameraClick, onEdit, onDelete, onRefresh }: CoopCardProps) {
  const isUnassigned = coop.id === '00000000-0000-0000-0000-000000000000'
  const onlineCount = coop.cameras.filter((c) => c.status === 'online').length
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({})

  // Interactive perimeter placement state
  const containerRef = useRef<HTMLDivElement>(null)
  const [draggingCameraId, setDraggingCameraId] = useState<string | null>(null)
  const [tempPositions, setTempPositions] = useState<Record<string, { x: number; y: number }>>({})
  const [hasMoved, setHasMoved] = useState(false)

  // Snap position to the closest edge of [0, 100] x [0, 100] rectangle
  const snapToPerimeter = (x: number, y: number) => {
    const dLeft = x
    const dRight = 100 - x
    const dTop = y
    const dBottom = 100 - y
    const min = Math.min(dLeft, dRight, dTop, dBottom)
    if (min === dLeft) return { x: 0, y }
    if (min === dRight) return { x: 100, y }
    if (min === dTop) return { x, y: 0 }
    return { x, y: 100 }
  }

  // Get mount rotation so the camera lens points inward from the wall
  const getRotation = (x: number, y: number) => {
    if (x === 0) return 0     // Left wall -> points Right
    if (y === 0) return 90    // Top wall -> points Down
    if (x === 100) return 180 // Right wall -> points Left
    return 270                // Bottom wall -> points Up
  }

  // Create bracket styles to mount the camera base onto the wall
  const getMountBracketStyle = (x: number, y: number) => {
    const base = {
      position: 'absolute',
      backgroundColor: '#475569',
      zIndex: 1,
    }
    if (x === 0) {
      return {
        ...base,
        left: -6,
        top: '50%',
        transform: 'translateY(-50%)',
        width: 6,
        height: 6,
        borderRadius: '2px 0 0 2px',
      }
    }
    if (x === 100) {
      return {
        ...base,
        right: -6,
        top: '50%',
        transform: 'translateY(-50%)',
        width: 6,
        height: 6,
        borderRadius: '0 2px 2px 0',
      }
    }
    if (y === 0) {
      return {
        ...base,
        top: -6,
        left: '50%',
        transform: 'translateX(-50%)',
        width: 6,
        height: 6,
        borderRadius: '2px 2px 0 0',
      }
    }
    return {
      ...base,
      bottom: -6,
      left: '50%',
      transform: 'translateX(-50%)',
      width: 6,
      height: 6,
      borderRadius: '0 0 2px 2px',
    }
  }

  const handleMouseDown = (camId: string, currentX: number, currentY: number) => (e: React.MouseEvent) => {
    if (!canWrite) return
    e.preventDefault()
    setDraggingCameraId(camId)
    setHasMoved(false)
    setTempPositions(prev => ({
      ...prev,
      [camId]: { x: currentX, y: currentY }
    }))
  }

  const handleTouchStart = (camId: string, currentX: number, currentY: number) => (e: React.TouchEvent) => {
    if (!canWrite) return
    setDraggingCameraId(camId)
    setHasMoved(false)
    setTempPositions(prev => ({
      ...prev,
      [camId]: { x: currentX, y: currentY }
    }))
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!draggingCameraId || !containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    let x = ((e.clientX - rect.left) / rect.width) * 100
    let y = ((e.clientY - rect.top) / rect.height) * 100
    x = Math.max(0, Math.min(100, x))
    y = Math.max(0, Math.min(100, y))
    const snapped = snapToPerimeter(x, y)
    setHasMoved(true)
    setTempPositions(prev => ({
      ...prev,
      [draggingCameraId]: snapped
    }))
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!draggingCameraId || !containerRef.current || e.touches.length === 0) return
    const rect = containerRef.current.getBoundingClientRect()
    const touch = e.touches[0]
    let x = ((touch.clientX - rect.left) / rect.width) * 100
    let y = ((touch.clientY - rect.top) / rect.height) * 100
    x = Math.max(0, Math.min(100, x))
    y = Math.max(0, Math.min(100, y))
    const snapped = snapToPerimeter(x, y)
    setHasMoved(true)
    setTempPositions(prev => ({
      ...prev,
      [draggingCameraId]: snapped
    }))
  }

  const handleDragEnd = (cam: Camera) => async () => {
    if (!draggingCameraId) return
    const pos = tempPositions[draggingCameraId]
    setDraggingCameraId(null)

    if (!hasMoved) {
      // Short click/tap launches feed modal
      onCameraClick(cam)
      return
    }

    if (pos) {
      try {
        await api.put(`/cameras/${draggingCameraId}`, {
          pos_x: Math.round(pos.x),
          pos_y: Math.round(pos.y)
        })
        if (onRefresh) onRefresh(true)
      } catch (err) {
        console.error("Failed to update camera position", err)
      }
    }
  }

  return (
    <Card sx={{ border: '1px solid #e2e8f0', boxShadow: 'none', borderRadius: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ p: 2.5, flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0f172a', fontFamily: '"Outfit", sans-serif' }}>
              {isUnassigned ? '📦 Unassigned' : coop.name}
            </Typography>
            <Chip
              label={`${onlineCount}/${coop.cameras.length}`}
              size="small"
              sx={{
                fontWeight: 600,
                fontSize: '0.7rem',
                borderRadius: '6px',
                bgcolor: onlineCount > 0 ? '#e8f5e9' : '#fef2f2',
                color: onlineCount > 0 ? '#10b981' : '#ef4444',
              }}
            />
          </Box>
          {canWrite && !isUnassigned && (
            <Box sx={{ display: 'flex', gap: 0.5 }}>
              <IconButton size="small" onClick={() => onEdit(coop)} sx={{ color: '#5e5ce6' }}>
                <EditIcon fontSize="small" />
              </IconButton>
              <IconButton size="small" onClick={() => onDelete(coop)} sx={{ color: '#ef4444' }}>
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Box>
          )}
        </Box>

        {/* 1. Interactive Pen Layout Box (Except for Unassigned Card) */}
        {!isUnassigned && (
          <Box
            ref={containerRef}
            onMouseMove={handleMouseMove}
            onMouseUp={() => {
              if (draggingCameraId) {
                const cam = coop.cameras.find(c => c.id === draggingCameraId)
                if (cam) handleDragEnd(cam)()
              }
            }}
            onMouseLeave={() => {
              if (draggingCameraId) {
                const cam = coop.cameras.find(c => c.id === draggingCameraId)
                if (cam) handleDragEnd(cam)()
              }
            }}
            onTouchMove={handleTouchMove}
            onTouchEnd={() => {
              if (draggingCameraId) {
                const cam = coop.cameras.find(c => c.id === draggingCameraId)
                if (cam) handleDragEnd(cam)()
              }
            }}
            sx={{
              position: 'relative',
              width: '100%',
              height: 180,
              bgcolor: '#f8fafc',
              backgroundImage: 'radial-gradient(#cbd5e1 1.5px, transparent 1.5px)',
              backgroundSize: '16px 16px',
              border: '4px double #475569',
              borderRadius: 2.5,
              overflow: 'visible',
              mb: 2.5,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              userSelect: 'none',
              transition: 'border-color 0.2s ease',
              '&:hover': {
                borderColor: '#1e293b',
              }
            }}
          >
            <Typography
              variant="caption"
              sx={{
                color: '#94a3b8',
                fontWeight: 800,
                letterSpacing: '0.1em',
                fontFamily: '"Outfit", sans-serif',
                textTransform: 'uppercase',
                pointerEvents: 'none',
              }}
            >
              {coop.cameras.length === 0 ? 'No cameras mounted' : 'Pen Floor Layout'}
            </Typography>

            {coop.cameras.map((cam) => {
              const isDragging = draggingCameraId === cam.id
              const pos = isDragging && tempPositions[cam.id]
                ? tempPositions[cam.id]
                : { x: cam.pos_x, y: cam.pos_y }

              const x = pos.x
              const y = pos.y
              const rotation = getRotation(x, y)
              const bracketStyle = getMountBracketStyle(x, y)

              return (
                <Box
                  key={cam.id}
                  onMouseDown={handleMouseDown(cam.id, cam.pos_x, cam.pos_y)}
                  onTouchStart={handleTouchStart(cam.id, cam.pos_x, cam.pos_y)}
                  sx={{
                    position: 'absolute',
                    left: `${x}%`,
                    top: `${y}%`,
                    transform: 'translate(-50%, -50%)',
                    zIndex: isDragging ? 10 : 2,
                    cursor: canWrite ? (isDragging ? 'grabbing' : 'grab') : 'pointer',
                    transition: isDragging ? 'none' : 'left 0.15s ease-out, top 0.15s ease-out',
                    touchAction: 'none',
                  }}
                >
                  {/* Mount Bracket */}
                  <Box sx={bracketStyle} />

                  {/* Camera Icon Base */}
                  <Box
                    sx={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      bgcolor: cam.status === 'online' ? '#10b981' : '#ef4444',
                      border: '2px solid #ffffff',
                      boxShadow: isDragging ? '0 8px 16px rgba(0,0,0,0.25)' : '0 3px 8px rgba(0,0,0,0.15)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#ffffff',
                      transform: `rotate(${rotation}deg) scale(${isDragging ? 1.2 : 1})`,
                      transition: 'transform 0.15s ease-out, box-shadow 0.15s ease-out',
                      '&:hover': {
                        boxShadow: '0 5px 12px rgba(0,0,0,0.2)',
                        transform: `rotate(${rotation}deg) scale(1.1)`,
                      }
                    }}
                  >
                    <VideocamIcon sx={{ fontSize: '1rem' }} />
                  </Box>

                  {/* Drag Tooltip Camera Name */}
                  <Box
                    sx={{
                      position: 'absolute',
                      top: '100%',
                      left: '50%',
                      transform: 'translateX(-50%)',
                      bgcolor: 'rgba(15, 23, 42, 0.9)',
                      color: '#ffffff',
                      px: 1,
                      py: 0.25,
                      borderRadius: '4px',
                      whiteSpace: 'nowrap',
                      fontSize: '0.65rem',
                      fontWeight: 600,
                      pointerEvents: 'none',
                      opacity: isDragging ? 1 : 0,
                      transition: 'opacity 0.15s ease-in-out',
                      zIndex: 20,
                      mt: 0.75,
                    }}
                  >
                    {cam.name}
                  </Box>
                </Box>
              )
            })}
          </Box>
        )}

        {/* 2. Grid of Camera Previews */}
        {coop.cameras.length === 0 ? (
          <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 60 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
              No cameras assigned
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(auto-fill, minmax(110px, 1fr))', sm: 'repeat(auto-fill, minmax(130px, 1fr))' }, gap: 1.5, mt: 0.5 }}>
            {coop.cameras.map((cam) => (
              <Box
                key={cam.id}
                onClick={() => onCameraClick(cam)}
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 0.75,
                  p: 1.25,
                  borderRadius: 2,
                  border: '1px solid',
                  borderColor: cam.status === 'online' ? '#d1fae5' : '#fecaca',
                  bgcolor: cam.status === 'online' ? '#f0fdf4' : '#fef2f2',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  '&:hover': {
                    borderColor: '#5e5ce6',
                    bgcolor: '#f5f3ff',
                    transform: 'translateY(-1px)',
                    boxShadow: '0 2px 8px rgba(94, 92, 230, 0.12)',
                  },
                }}
              >
                <Box sx={{
                  width: '100%',
                  aspectRatio: '16/9',
                  borderRadius: 1,
                  bgcolor: cam.status === 'online' ? '#1e293b' : '#e2e8f0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                }}>
                  {failedImages[cam.id] ? (
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2">
                        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                        <circle cx="12" cy="13" r="4"/>
                      </svg>
                    </Box>
                  ) : (
                    <Box
                      component="img"
                      src={cam.snapshot_url || `/api/v1/nvr/snapshot/${cam.id}`}
                      alt={cam.name}
                      sx={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={() => {
                        setFailedImages((prev) => ({ ...prev, [cam.id]: true }))
                      }}
                    />
                  )}
                </Box>
                <Typography variant="caption" sx={{ fontWeight: 600, textAlign: 'center', color: '#1e293b', lineHeight: 1.2, fontSize: '0.725rem' }}>
                  {cam.name}
                </Typography>
              </Box>
            ))}
          </Box>
        )}
      </CardContent>
    </Card>
  )
}
