import { useState } from 'react'
import { Box, Typography, Card, CardContent, Chip, IconButton } from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import VideocamIcon from '@mui/icons-material/Videocam'
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
}

export function CoopCard({ coop, canWrite, onCameraClick, onEdit, onDelete }: CoopCardProps) {
  const isUnassigned = coop.id === '00000000-0000-0000-0000-000000000000'
  const onlineCount = coop.cameras.filter((c) => c.status === 'online').length
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({})

  return (
    <Card sx={{ border: '1px solid #e2e8f0', boxShadow: 'none', borderRadius: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ p: 2.5, flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0f172a' }}>
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

        {coop.cameras.length === 0 ? (
          <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
              No cameras assigned
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 1.5, mt: 0.5 }}>
            {coop.cameras.map((cam) => (
              <Box
                key={cam.id}
                onClick={() => onCameraClick(cam)}
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 0.75,
                  p: 1.5,
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
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2">
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
                <Typography variant="caption" sx={{ fontWeight: 600, textAlign: 'center', color: '#1e293b', lineHeight: 1.2 }}>
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
