import { Box, Typography, Button } from '@mui/material'
import { useAuth } from '../auth/AuthContext'

export default function ImpersonationBanner() {
  const { impersonating, stopImpersonating } = useAuth()

  if (!impersonating) return null

  return (
    <Box
      sx={{
        bgcolor: '#fef3c7',
        borderBottom: '1px solid #fde68a',
        px: 3,
        py: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 2,
        flexWrap: 'wrap',
      }}
    >
      <Typography variant="body2" sx={{ color: '#92400e', fontWeight: 500 }}>
        Viewing as <strong>{impersonating.full_name || impersonating.email}</strong> ({impersonating.role})
      </Typography>
      <Button
        size="small"
        variant="outlined"
        sx={{
          borderColor: '#d97706',
          color: '#92400e',
          '&:hover': { borderColor: '#92400e', bgcolor: '#fffbeb' },
          textTransform: 'none',
          fontWeight: 600,
        }}
        onClick={stopImpersonating}
      >
        Stop Impersonating
      </Button>
    </Box>
  )
}