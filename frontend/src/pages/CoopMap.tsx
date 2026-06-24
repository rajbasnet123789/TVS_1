import { useState, useEffect, useCallback } from 'react'
import {
  Box, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, CircularProgress, Alert, Grid,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import { CoopCard, type CoopData } from '../components/CoopCard'
import { CameraFeed } from '../components/CameraFeed'
import api from '../api/axios'
import { useAuth } from '../auth/AuthContext'
import type { Camera } from '../types'

export default function CoopMap() {
  const { hasPermission } = useAuth()
  const canWrite = hasPermission('cameras:write')
  const [coops, setCoops] = useState<CoopData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Live feed modal
  const [feedCamera, setFeedCamera] = useState<Camera | null>(null)

  // Create/edit coop dialog
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingCoop, setEditingCoop] = useState<CoopData | null>(null)
  const [coopName, setCoopName] = useState('')
  const [saving, setSaving] = useState(false)

  // Assign camera dialog
  const [assignOpen, setAssignOpen] = useState(false)
  const [assignCameraId, setAssignCameraId] = useState('')
  const [assignCoopId, setAssignCoopId] = useState('')

  const loadCoops = useCallback(async (isSilent = false) => {
    if (!isSilent) {
      setLoading(true)
    }
    setError('')
    try {
      const { data } = await api.get('/coops')
      setCoops(data)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load coops')
    } finally {
      if (!isSilent) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => { loadCoops() }, [loadCoops])

  const handleOpenCreate = () => {
    setEditingCoop(null)
    setCoopName('')
    setDialogOpen(true)
  }

  const handleOpenEdit = (coop: CoopData) => {
    setEditingCoop(coop)
    setCoopName(coop.name)
    setDialogOpen(true)
  }

  const handleSaveCoop = async () => {
    if (!coopName.trim()) return
    setSaving(true)
    try {
      if (editingCoop) {
        await api.put(`/coops/${editingCoop.id}`, { name: coopName.trim() })
      } else {
        await api.post('/coops', { name: coopName.trim() })
      }
      setDialogOpen(false)
      await loadCoops()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to save coop')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteCoop = async (coop: CoopData) => {
    if (!confirm(`Delete "${coop.name}"? Cameras will be unassigned.`)) return
    try {
      await api.delete(`/coops/${coop.id}`)
      await loadCoops()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to delete coop')
    }
  }

  const handleCameraClick = (camera: Camera) => {
    setFeedCamera(camera)
  }

  const handleAssignOpen = () => {
    setAssignCameraId('')
    setAssignCoopId(coops[0]?.id || '')
    setAssignOpen(true)
  }

  const handleAssign = async () => {
    if (!assignCameraId || !assignCoopId) return
    try {
      await api.put(`/cameras/${assignCameraId}/assign-coop`, { coop_id: assignCoopId })
      setAssignOpen(false)
      await loadCoops()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to assign camera')
    }
  }

  if (loading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Coop Map</Typography>
          <Typography variant="body2" color="text.secondary">
            {coops.reduce((sum, c) => sum + c.cameras.length, 0)} cameras across {coops.length} coops
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1.5 }}>
          {canWrite && (
            <>
              <Button variant="outlined" startIcon={<AddIcon />} onClick={handleAssignOpen}>
                Assign Cameras
              </Button>
              <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenCreate}>
                Add Coop
              </Button>
            </>
          )}
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {coops.length === 0 && !error ? (
        <Box sx={{ textAlign: 'center', py: 8 }}>
          <Typography variant="h6" color="text.secondary" sx={{ mb: 1 }}>No coops yet</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Create your first coop to organize cameras by pen or house.
          </Typography>
          {canWrite && (
            <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenCreate}>
              Create Coop
            </Button>
          )}
        </Box>
      ) : (
        <Grid container spacing={3}>
          {coops.map((coop) => (
            <Grid item xs={12} sm={6} lg={4} key={coop.id}>
              <CoopCard
                coop={coop}
                canWrite={canWrite}
                onCameraClick={handleCameraClick}
                onEdit={handleOpenEdit}
                onDelete={handleDeleteCoop}
                onRefresh={loadCoops}
              />
            </Grid>
          ))}
        </Grid>
      )}

      {/* Live Feed Modal — only ONE stream at a time */}
      <Dialog
        open={!!feedCamera}
        onClose={() => setFeedCamera(null)}
        maxWidth="lg"
        fullWidth
        PaperProps={{ sx: { borderRadius: 3 } }}
      >
        {feedCamera && (
          <>
            <DialogTitle sx={{ fontWeight: 700, pb: 1 }}>
              {feedCamera.name}
            </DialogTitle>
            <DialogContent sx={{ p: 2 }}>
              <CameraFeed
                id={feedCamera.id}
                name={feedCamera.name}
                hlsUrl={feedCamera.hls_url}
                rtspUrl={feedCamera.rtsp_url}
                status={feedCamera.status}
              />
            </DialogContent>
            <DialogActions sx={{ px: 3, pb: 2 }}>
              <Button onClick={() => setFeedCamera(null)} variant="outlined">Close</Button>
            </DialogActions>
          </>
        )}
      </Dialog>

      {/* Create/Edit Coop Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>
          {editingCoop ? 'Rename Coop' : 'Create Coop'}
        </DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="Coop Name"
            value={coopName}
            onChange={(e) => setCoopName(e.target.value)}
            margin="dense"
            autoFocus
            placeholder="e.g. Pen A, House 3"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleSaveCoop} disabled={saving || !coopName.trim()}>
            {saving ? 'Saving...' : editingCoop ? 'Rename' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Assign Camera Dialog */}
      <Dialog open={assignOpen} onClose={() => setAssignOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Assign Camera to Coop</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField
              fullWidth
              label="Camera ID"
              value={assignCameraId}
              onChange={(e) => setAssignCameraId(e.target.value)}
              size="small"
              placeholder="Paste camera ID"
            />
            <TextField
              fullWidth
              select
              label="Target Coop"
              value={assignCoopId}
              onChange={(e) => setAssignCoopId(e.target.value)}
              size="small"
              SelectProps={{ native: true }}
            >
              {coops.filter(c => c.id !== '00000000-0000-0000-0000-000000000000').map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </TextField>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAssignOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleAssign} disabled={!assignCameraId || !assignCoopId}>
            Assign
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
