import { Dialog, DialogTitle, IconButton, Box } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { Go2rtcPlayer } from './Go2rtcPlayer'

interface CameraVideoModalProps {
  cameraId: string
  cameraName: string
  open: boolean
  onClose: () => void
}

export function CameraVideoModal({ cameraId, cameraName, open, onClose }: CameraVideoModalProps) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth PaperProps={{ sx: { borderRadius: 2, overflow: 'hidden' } }}>
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 1.5, px: 2, bgcolor: '#0f172a', color: '#fff' }}>
        {cameraName}
        <IconButton size="small" onClick={onClose} sx={{ color: '#94a3b8' }}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <Box sx={{ aspectRatio: '16/9', width: '100%', bgcolor: '#000' }}>
        <Go2rtcPlayer cameraId={cameraId} />
      </Box>
    </Dialog>
  )
}
