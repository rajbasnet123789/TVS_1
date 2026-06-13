import { Box, Typography } from '@mui/material'
import { CameraGrid } from '../components/CameraGrid'

export default function LiveFeed() {
  return (
    <Box>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Live Feed</Typography>
        <Typography variant="body2" color="text.secondary">Real-time video feeds from all active barn cameras</Typography>
      </Box>
      <CameraGrid compact={false} />
    </Box>
  )
}
