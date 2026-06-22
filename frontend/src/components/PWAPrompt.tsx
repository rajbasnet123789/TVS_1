import { Button, Snackbar, Alert, Box, IconButton } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import RefreshIcon from '@mui/icons-material/Refresh'
import { useRegisterSW } from 'virtual:pwa-register/react'

export function PWAPrompt() {
  const {
    offlineReady: [offlineReady, setOfflineReady],
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegistered(_r) {
    },
    onRegisterError(_error) {
    },
  })

  const close = () => {
    setOfflineReady(false)
    setNeedRefresh(false)
  }

  return (
    <>
      <Snackbar
        open={offlineReady}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        autoHideDuration={6000}
        onClose={close}
      >
        <Alert
          severity="success"
          onClose={close}
          sx={{
            bgcolor: '#0f172a',
            color: '#f8fafc',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            fontFamily: '"Outfit", sans-serif',
            fontWeight: 500,
            borderRadius: '12px',
            boxShadow: '0 4px 20px rgba(0, 0, 0, 0.3)',
            '& .MuiAlert-icon': {
              color: '#10b981'
            }
          }}
        >
          App is ready to work offline.
        </Alert>
      </Snackbar>

      <Snackbar
        open={needRefresh}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          severity="info"
          icon={<RefreshIcon sx={{ color: '#00f3ff' }} />}
          sx={{
            bgcolor: '#0f172a',
            color: '#f8fafc',
            border: '1px solid rgba(0, 243, 255, 0.3)',
            fontFamily: '"Outfit", sans-serif',
            fontWeight: 500,
            borderRadius: '12px',
            boxShadow: '0 4px 25px rgba(0, 243, 255, 0.1)',
            alignItems: 'center',
            '& .MuiAlert-icon': {
              alignSelf: 'center'
            }
          }}
          action={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Button
                color="info"
                size="small"
                variant="contained"
                onClick={() => updateServiceWorker(true)}
                sx={{
                  bgcolor: '#00f3ff',
                  color: '#020408',
                  fontWeight: 700,
                  fontFamily: '"Outfit", sans-serif',
                  '&:hover': {
                    bgcolor: '#00cce6',
                  }
                }}
              >
                Reload
              </Button>
              <IconButton size="small" color="inherit" onClick={close}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Box>
          }
        >
          A new version of this app is available.
        </Alert>
      </Snackbar>
    </>
  )
}
