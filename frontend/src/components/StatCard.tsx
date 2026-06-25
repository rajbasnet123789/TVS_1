import { Card, CardContent, Typography, Box } from '@mui/material'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

const getCardColors = (hex: string) => {
  const clean = hex.toLowerCase()
  if (clean === '#10b981') {
    return { bg: '#e8f5e9', iconColor: '#10b981', border: 'rgba(16, 185, 129, 0.2)' }
  }
  if (clean === '#5e5ce6' || clean === '#3b82f6' || clean === '#0ea5e9') {
    return { bg: '#e0f2fe', iconColor: '#0284c7', border: 'rgba(2, 132, 199, 0.2)' }
  }
  if (clean === '#f59e0b') {
    return { bg: '#edf7ed', iconColor: '#2e7d32', border: 'rgba(46, 125, 50, 0.2)' } // Green leaf theme from screenshot
  }
  if (clean === '#ef4444') {
    return { bg: '#ffebee', iconColor: '#d32f2f', border: 'rgba(211, 47, 47, 0.2)' }
  }
  if (clean === '#00f3ff') {
    return { bg: '#e0f7fa', iconColor: '#006064', border: 'rgba(0, 96, 100, 0.2)' }
  }
  return { bg: '#f1f5f9', iconColor: '#475569', border: 'rgba(71, 85, 105, 0.2)' }
}

export function StatCard({ title, value, icon, color, subtitle, onClick, to }: { title: string; value: number | string; icon: ReactNode; color: string; subtitle?: string; onClick?: () => void; to?: string }) {
  const { bg, iconColor, border } = getCardColors(color)
  const navigate = useNavigate()

  const handleClick = onClick || (to ? () => navigate(to) : undefined)

  return (
    <Card
      onClick={handleClick}
      sx={{
        cursor: handleClick ? 'pointer' : 'default',
        transition: 'all 0.2s ease-in-out',
        '&:hover': handleClick ? {
          transform: 'translateY(-2px)',
          borderColor: iconColor,
          boxShadow: '0 8px 32px 0 rgba(15, 23, 42, 0.08)',
          backgroundColor: 'rgba(255, 255, 255, 0.65)',
        } : undefined,
      }}
    >
      <CardContent 
        sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: { xs: 1.5, sm: 2, md: 1.5, lg: 2 }, 
          p: { xs: 2, sm: 2.25, md: 2, lg: 2.25 }, 
          '&:last-child': { pb: { xs: 2, sm: 2.25, md: 2, lg: 2.25 } } 
        }}
      >
        <Box 
          sx={{ 
            color: iconColor, 
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: { xs: 40, sm: 48, md: 40, lg: 48 },
            height: { xs: 40, sm: 48, md: 40, lg: 48 },
            borderRadius: '50%',
            backgroundColor: bg,
            border: `1px solid ${border}`,
            flexShrink: 0,
            '& svg': {
              fontSize: { xs: '1.2rem', sm: '1.4rem', md: '1.2rem', lg: '1.4rem' }
            }
          }}
        >
          {icon}
        </Box>
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography 
            variant="caption" 
            sx={{ 
              color: '#64748b', 
              fontWeight: 700, 
              letterSpacing: '0.08em', 
              textTransform: 'uppercase',
              fontSize: { xs: '0.625rem', sm: '0.675rem', md: '0.625rem', lg: '0.675rem' },
              display: 'block'
            }}
          >
            {title}
          </Typography>
          <Typography 
            variant="h4" 
            sx={{ 
              fontWeight: 800, 
              fontFamily: '"Outfit", sans-serif',
              mt: 0.1,
              color: '#0f172a',
              fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.3rem', lg: '1.5rem' },
              lineHeight: 1.2
            }}
          >
            {value}
          </Typography>
          {subtitle && (
            <Typography 
              variant="caption" 
              sx={{ 
                color: '#64748b', 
                fontSize: { xs: '0.675rem', sm: '0.725rem', md: '0.675rem', lg: '0.725rem' },
                fontWeight: 500,
                display: 'block',
                mt: 0.2,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}
            >
              {subtitle}
            </Typography>
          )}
        </Box>
      </CardContent>
    </Card>
  )
}
