import { useState, useEffect, useCallback } from 'react'
import {
  Box, Typography, Card, CardContent, TextField, Button,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Dialog, DialogTitle, DialogContent, DialogActions,
  Chip,
} from '@mui/material'
import api from '../../api/axios'
import type { Farm } from '../../types'

export default function AdminFarms() {
  const [farms, setFarms] = useState<Farm[]>([])
  const [loading, setLoading] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editFarm, setEditFarm] = useState<Farm | null>(null)
  const [newName, setNewName] = useState('')
  const [newLocation, setNewLocation] = useState('')
  const [newSlug, setNewSlug] = useState('')
  const [addMsg, setAddMsg] = useState('')
  const [editMsg, setEditMsg] = useState('')
  const [fetchError, setFetchError] = useState('')
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteFarm, setDeleteFarm] = useState<Farm | null>(null)
  const [deleteMsg, setDeleteMsg] = useState('')

  const fetchFarms = useCallback(async () => {
    setLoading(true)
    setFetchError('')
    try {
      const { data } = await api.get('/farms')
      setFarms(data)
    } catch (e: any) {
      console.error('Failed to fetch farms:', e)
      setFetchError(e?.response?.data?.detail || 'Failed to load farms')
    }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchFarms() }, [fetchFarms])

  const handleAdd = async () => {
    try {
      await api.post('/farms', { name: newName, location: newLocation || undefined, slug: newSlug || undefined })
      setAddOpen(false)
      setAddMsg('')
      setNewName(''); setNewLocation(''); setNewSlug('')
      fetchFarms()
    } catch (e: any) {
      setAddMsg(e?.response?.data?.detail || 'Failed to create farm')
    }
  }

  const handleEdit = async () => {
    if (!editFarm) return
    try {
      await api.put(`/farms/${editFarm.id}`, { name: newName, location: newLocation || undefined })
      setEditOpen(false)
      setEditFarm(null)
      setEditMsg('')
      fetchFarms()
    } catch (e: any) {
      setEditMsg(e?.response?.data?.detail || 'Failed to update farm')
    }
  }

  const openEdit = (farm: Farm) => {
    setEditFarm(farm)
    setNewName(farm.name)
    setNewLocation(farm.location || '')
    setEditMsg('')
    setEditOpen(true)
  }

  const handleDelete = async () => {
    if (!deleteFarm) return
    try {
      await api.delete(`/farms/${deleteFarm.id}`)
      setDeleteOpen(false)
      setDeleteFarm(null)
      setDeleteMsg('')
      fetchFarms()
    } catch (e: any) {
      setDeleteMsg(e?.response?.data?.detail || 'Failed to delete farm')
    }
  }

  const openDelete = (farm: Farm) => {
    setDeleteFarm(farm)
    setDeleteMsg('')
    setDeleteOpen(true)
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Farm Management</Typography>
      <Button variant="contained" size="small" onClick={() => { setAddOpen(true); setNewName(''); setNewLocation(''); setNewSlug('') }} sx={{ mb: 2 }}>
        Create Farm
      </Button>
      {fetchError && <Typography color="error.main" sx={{ mb: 2 }}>{fetchError}</Typography>}
      {loading ? (
        <Typography variant="body2" color="text.secondary">Loading...</Typography>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Location</TableCell>
                <TableCell>Slug</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {farms.map((farm) => (
                <TableRow key={farm.id}>
                  <TableCell>{farm.name}</TableCell>
                  <TableCell>{farm.location || '—'}</TableCell>
                  <TableCell>{farm.slug}</TableCell>
                  <TableCell>
                    <Chip size="small" label={farm.is_active ? 'Active' : 'Inactive'} color={farm.is_active ? 'success' : 'default'} />
                  </TableCell>
                  <TableCell>{new Date(farm.created_at).toLocaleDateString()}</TableCell>
                  <TableCell>
                    <Button size="small" onClick={() => openEdit(farm)} sx={{ mr: 1 }}>Edit</Button>
                    <Button size="small" color="error" onClick={() => openDelete(farm)}>Delete</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Create Farm</DialogTitle>
        <DialogContent>
          <TextField fullWidth label="Name" value={newName} onChange={(e) => setNewName(e.target.value)} margin="dense" size="small" />
          <TextField fullWidth label="Location" value={newLocation} onChange={(e) => setNewLocation(e.target.value)} margin="dense" size="small" />
          <TextField fullWidth label="Slug" value={newSlug} onChange={(e) => setNewSlug(e.target.value)} margin="dense" size="small" helperText="URL-friendly identifier (auto-generated if empty)" />
          {addMsg && <Typography variant="body2" color="error.main" sx={{ mt: 1 }}>{addMsg}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleAdd}>Create</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={editOpen} onClose={() => setEditOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Edit Farm</DialogTitle>
        <DialogContent>
          <TextField fullWidth label="Name" value={newName} onChange={(e) => setNewName(e.target.value)} margin="dense" size="small" />
          <TextField fullWidth label="Location" value={newLocation} onChange={(e) => setNewLocation(e.target.value)} margin="dense" size="small" />
          {editMsg && <Typography variant="body2" color="error.main" sx={{ mt: 1 }}>{editMsg}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleEdit}>Save</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Delete Farm</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Are you sure you want to delete the farm <strong>{deleteFarm?.name}</strong>? This action cannot be undone and will delete all associated resources.
          </Typography>
          {deleteMsg && <Typography variant="body2" color="error.main" sx={{ mt: 1 }}>{deleteMsg}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDelete}>Delete</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
