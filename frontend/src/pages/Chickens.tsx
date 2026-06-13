import { useState, useEffect } from 'react'
import {
  Box, Typography, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Chip, TablePagination, Tabs, Tab,
  CircularProgress, Button, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, IconButton,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import api from '../api/axios'
import type { Chicken, DetectedChicken } from '../types'

function formatTime(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  return d.toLocaleDateString()
}

const emptyForm = { chicken_id: 1, name: '', breed: '', notes: '' }

export default function Chickens() {
  const [tab, setTab] = useState(0)
  const [chickens, setChickens] = useState<Chicken[]>([])
  const [detected, setDetected] = useState<DetectedChicken[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(10)

  const load = () => {
    setLoading(true)
    Promise.all([
      api.get('/chickens').catch(() => ({ data: [] })),
      api.get('/chickens/detected', { params: { start: '-1h', end: 'now()' } }).catch(() => ({ data: [] })),
    ]).then(([manualRes, detectedRes]) => {
      setChickens(manualRes.data)
      setDetected(detectedRes.data)
    }).finally(() => setLoading(false))
  }

  useEffect(load, [])

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState(emptyForm)

  const openCreate = (prefillTrackId?: number) => {
    setEditingId(null)
    setForm(prefillTrackId ? { ...emptyForm, chicken_id: prefillTrackId } : { ...emptyForm })
    setDialogOpen(true)
  }

  const openEdit = (chicken: Chicken) => {
    setEditingId(chicken.id)
    setForm({ chicken_id: chicken.chicken_id, name: chicken.name || '', breed: chicken.breed || '', notes: chicken.notes || '' })
    setDialogOpen(true)
  }

  const handleSave = async () => {
    if (editingId) {
      await api.put(`/chickens/${editingId}`, { name: form.name || null, breed: form.breed || null, notes: form.notes || null })
    } else {
      await api.post('/chickens', form)
    }
    setDialogOpen(false)
    load()
  }

  const handleDelete = async (id: string) => {
    if (confirm('Delete this chicken?')) {
      await api.delete(`/chickens/${id}`)
      load()
    }
  }

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>

  const manualCount = chickens.length
  const detectedCount = detected.length
  const merged = detected.map((d) => {
    const manual = chickens.find((c) => c.chicken_id === d.track_id)
    return { ...d, manual }
  })

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Chickens</Typography>
          <Typography variant="body2" color="text.secondary">
            {detectedCount} chickens detected &middot; {manualCount} manually registered
          </Typography>
        </Box>
        {tab === 1 && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => openCreate()}>
            Register Chicken
          </Button>
        )}
      </Box>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3, '& .MuiTab-root': { fontWeight: 600, fontFamily: '"Outfit", sans-serif' } }}>
        <Tab label={`Detected (${detectedCount})`} />
        <Tab label={`Registered (${manualCount})`} />
      </Tabs>

      {tab === 0 && (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Last Seen</TableCell>
                <TableCell>Detections</TableCell>
                <TableCell>Avg Confidence</TableCell>
                <TableCell>Camera</TableCell>
                <TableCell>Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {merged
                .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                .map((ch) => (
                  <TableRow key={ch.track_id} hover>
                    <TableCell sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 700, color: '#7d7aff', fontSize: '0.95rem' }}>
                      #{ch.track_id.toString().padStart(4, '0')}
                    </TableCell>
                    <TableCell sx={{ fontFamily: '"Outfit", sans-serif', fontWeight: 600 }}>
                      {ch.manual ? (ch.manual.name || `#${ch.track_id}`) : (
                        <Typography variant="body2" color="text.secondary" component="span" sx={{ fontStyle: 'italic' }}>
                          Auto-detected
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={ch.status}
                        size="small"
                        color={ch.status === 'active' ? 'success' : 'default'}
                        sx={{ fontFamily: '"Outfit", sans-serif', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', borderRadius: '6px' }}
                      />
                    </TableCell>
                    <TableCell sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.85rem' }}>
                      {formatTime(ch.last_seen)}
                    </TableCell>
                    <TableCell sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 600 }}>
                      {ch.detections.toLocaleString()}
                    </TableCell>
                    <TableCell sx={{ fontFamily: '"JetBrains Mono", monospace' }}>
                      {(ch.avg_confidence * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.85rem' }}>
                      {ch.cameras.join(', ')}
                    </TableCell>
                    <TableCell>
                      {!ch.manual && (
                        <Button size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} onClick={() => openCreate(ch.track_id)}>
                          Register
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              {merged.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} align="center">
                    <Typography variant="body2" color="text.secondary" sx={{ py: 4 }}>
                      No chickens detected yet. Start detection on a camera.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={merged.length}
            page={page}
            onPageChange={(_, p) => setPage(p)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value, 10)); setPage(0) }}
          />
        </TableContainer>
      )}

      {tab === 1 && (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Breed</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Notes</TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {chickens
                .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                .map((chicken) => (
                  <TableRow key={chicken.id} hover>
                    <TableCell sx={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 700, color: '#7d7aff', fontSize: '0.95rem' }}>
                      #{chicken.chicken_id.toString().padStart(4, '0')}
                    </TableCell>
                    <TableCell sx={{ fontFamily: '"Outfit", sans-serif', fontWeight: 600 }}>{chicken.name || '—'}</TableCell>
                    <TableCell>{chicken.breed || '—'}</TableCell>
                    <TableCell>
                      <Chip
                        label={chicken.status}
                        size="small"
                        color={chicken.status === 'active' ? 'success' : 'default'}
                        sx={{ fontFamily: '"Outfit", sans-serif', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', borderRadius: '6px' }}
                      />
                    </TableCell>
                    <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {chicken.notes || '—'}
                    </TableCell>
                    <TableCell sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.85rem' }}>
                      {new Date(chicken.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <IconButton size="small" onClick={() => openEdit(chicken)} sx={{ color: '#5e5ce6' }}>
                        <EditIcon fontSize="small" />
                      </IconButton>
                      <IconButton size="small" onClick={() => handleDelete(chicken.id)} sx={{ color: '#ef4444' }}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              {chickens.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} align="center">
                    <Typography variant="body2" color="text.secondary" sx={{ py: 4 }}>
                      No chickens registered yet. Switch to "Detected" tab to see auto-detected chickens.
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={chickens.length}
            page={page}
            onPageChange={(_, p) => setPage(p)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value, 10)); setPage(0) }}
          />
        </TableContainer>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>
          {editingId ? 'Edit Chicken' : form.notes !== '' && !editingId ? 'Register Detected Chicken' : 'Register Chicken'}
        </DialogTitle>
        <DialogContent>
          <TextField
            fullWidth label="Chicken ID" type="number"
            value={form.chicken_id}
            onChange={(e) => setForm({ ...form, chicken_id: parseInt(e.target.value, 10) || 1 })}
            margin="normal" required disabled={!!editingId}
          />
          <TextField
            fullWidth label="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            margin="normal"
          />
          <TextField
            fullWidth label="Breed"
            value={form.breed}
            onChange={(e) => setForm({ ...form, breed: e.target.value })}
            margin="normal"
          />
          <TextField
            fullWidth label="Notes" multiline rows={2}
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            margin="normal"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleSave}>
            {editingId ? 'Update' : 'Register'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
