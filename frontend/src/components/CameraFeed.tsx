import { Box, Typography, CircularProgress } from '@mui/material'
import VideocamOutlinedIcon from '@mui/icons-material/VideocamOutlined'
import VideocamOffOutlinedIcon from '@mui/icons-material/VideocamOffOutlined'
import { useLiveCounts } from '../hooks/useLiveCounts'

interface CameraFeedProps {
  id: string
  name: string
  status: string
  compact?: boolean
  onClick?: () => void
}

export function CameraFeed({ id, name, status, compact, onClick }: CameraFeedProps) {
  const { counts, loading } = useLiveCounts(3000)
  const liveCount = counts.get(id) ?? 0
  const online = status === 'online'

  return (
    <Box
      onClick={onClick}
      sx={{
        bgcolor: online ? '#f0fdf4' : '#f8fafc',
        border: online ? '1.5px solid #10b981' : '1px solid #e2e8f0',
        borderRadius: '12px',
        p: compact ? 1.5 : 2,
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.2s ease-in-out',
        '&:hover': onClick ? {
          transform: 'translateY(-2px)',
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          borderColor: '#5e5ce6',
        } : {},
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography
          variant="caption"
          sx={{
            fontWeight: 700,
            color: '#334155',
            fontSize: compact ? '0.75rem' : '0.825rem',
            fontFamily: '"Outfit", sans-serif',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: compact ? '70%' : '80%',
          }}
        >
          {name}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Box sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: online ? '#10b981' : '#cbd5e1' }} />
          <Typography variant="caption" sx={{ color: online ? '#10b981' : '#94a3b8', fontSize: '0.6rem', fontWeight: 700 }}>
            {online ? 'LIVE' : 'OFFLINE'}
          </Typography>
        </Box>
      </Box>

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        {online ? (
          <VideocamOutlinedIcon sx={{ fontSize: compact ? '1.25rem' : '1.5rem', color: '#10b981' }} />
        ) : (
          <VideocamOffOutlinedIcon sx={{ fontSize: compact ? '1.25rem' : '1.5rem', color: '#94a3b8' }} />
        )}
        {loading ? (
          <CircularProgress size={16} sx={{ color: '#94a3b8' }} />
        ) : (
          <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.5 }}>
            <Typography
              variant={compact ? 'h6' : 'h5'}
              sx={{ fontWeight: 800, color: liveCount > 0 ? '#047857' : '#64748b', fontFamily: '"Outfit", sans-serif' }}
            >
              {liveCount}
            </Typography>
            <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 600 }}>
              chickens
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  )
}
