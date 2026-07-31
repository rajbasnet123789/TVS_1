import { useState, useEffect, useCallback } from 'react'
import {
  Box, Typography, Grid, Card, CardMedia, CardContent, CircularProgress,
  Alert, Dialog, IconButton, Chip, Tooltip
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import DownloadIcon from '@mui/icons-material/Download'
import BrokenImageIcon from '@mui/icons-material/BrokenImage'
import api from '../api/axios'
import { useAuth } from '../auth/AuthContext'
import { buildMortalityMedia } from '../demo/mortality'

interface MediaItem {
  key: string
  url: string
  mortality?: boolean
}

export default function MediaGallery() {
  const { currentFarm } = useAuth()
  const [items, setItems] = useState<MediaItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<MediaItem | null>(null)

  const fetchMedia = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.get('/media/list', {
        params: { prefix: 'snapshots' },
      })
      const apiItems: MediaItem[] = (data.objects || []).map((o: any) => ({
        key: o.key,
        url: o.url,
      }))
      const demoItems: MediaItem[] = buildMortalityMedia().map((m) => ({
        key: m.key,
        url: m.url,
        mortality: true,
      }))
      const sorted = [...apiItems, ...demoItems].sort((a, b) =>
        b.key.localeCompare(a.key)
      )
      setItems(sorted)
    } catch (e: any) {
      if (e?.response?.status !== 404) {
        setError(e?.response?.data?.detail || 'Failed to load media')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchMedia() }, [fetchMedia, currentFarm])

  const cameraName = (key: string) => {
    const parts = key.split('/')
    return parts.length >= 2 ? parts[1] : key
  }

  return (
    <Box>
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Media Gallery</Typography>
          <Typography variant="body2" color="text.secondary">
            {items.length} snapshot{items.length !== 1 ? 's' : ''} — bird detections and mortality events
          </Typography>
        </Box>
        {!loading && (
          <Chip
            label="Refresh"
            onClick={fetchMedia}
            variant="outlined"
            sx={{ fontWeight: 600, cursor: 'pointer' }}
          />
        )}
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
      ) : items.length === 0 ? (
        <Box sx={{ textAlign: 'center', mt: 8, color: 'text.secondary' }}>
          <BrokenImageIcon sx={{ fontSize: 64, mb: 2, opacity: 0.3 }} />
          <Typography>No snapshots yet. Bird detections will appear here.</Typography>
        </Box>
      ) : (
        <Grid container spacing={2}>
          {items.map((item) => (
            <Grid item xs={6} sm={4} md={3} lg={2} key={item.key}>
              <Card
                sx={{
                  cursor: 'pointer',
                  transition: 'transform 0.15s, box-shadow 0.15s',
                  '&:hover': { transform: 'scale(1.03)', boxShadow: 4 },
                  position: 'relative',
                  border: item.mortality ? '1px solid #fecaca' : 'none',
                }}
                onClick={() => setSelected(item)}
              >
                {item.mortality && (
                  <Chip
                    label="DEAD CHICKEN DETECTED"
                    size="small"
                    color="error"
                    sx={{
                      position: 'absolute',
                      top: 8,
                      left: 8,
                      zIndex: 2,
                      fontWeight: 700,
                      fontSize: '0.6rem',
                      borderRadius: '4px',
                    }}
                  />
                )}
                <CardMedia
                  component="img"
                  height={140}
                  image={item.url}
                  alt={item.key}
                  sx={{ objectFit: 'cover', bgcolor: '#f1f5f9' }}
                />
                <CardContent sx={{ p: 1, '&:last-child': { pb: 1 } }}>
                  <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {cameraName(item.key)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      <Dialog open={!!selected} onClose={() => setSelected(null)} maxWidth="lg" fullWidth>
        {selected && (
          <Box sx={{ position: 'relative', bgcolor: '#000' }}>
            <IconButton
              onClick={() => setSelected(null)}
              sx={{ position: 'absolute', top: 8, right: 8, color: '#fff', bgcolor: 'rgba(0,0,0,0.5)', '&:hover': { bgcolor: 'rgba(0,0,0,0.7)' } }}
            >
              <CloseIcon />
            </IconButton>
            <Tooltip title="Download">
              <IconButton
                component="a"
                href={selected.url}
                download
                sx={{ position: 'absolute', top: 8, right: 56, color: '#fff', bgcolor: 'rgba(0,0,0,0.5)', '&:hover': { bgcolor: 'rgba(0,0,0,0.7)' } }}
              >
                <DownloadIcon />
              </IconButton>
            </Tooltip>
            <Box
              component="img"
              src={selected.url}
              alt={selected.key}
              sx={{ width: '100%', maxHeight: '90vh', objectFit: 'contain', display: 'block' }}
            />
            <Typography variant="caption" sx={{ position: 'absolute', bottom: 8, left: 8, color: '#fff', bgcolor: 'rgba(0,0,0,0.6)', px: 1, py: 0.5, borderRadius: 1 }}>
              {selected.key}
            </Typography>
            {selected.mortality && (
              <Chip
                label="DEAD CHICKEN DETECTED"
                size="small"
                color="error"
                sx={{ position: 'absolute', bottom: 8, right: 8, fontWeight: 700, fontSize: '0.65rem', borderRadius: '4px' }}
              />
            )}
          </Box>
        )}
      </Dialog>
    </Box>
  )
}
