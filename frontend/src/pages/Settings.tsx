import { useState, useEffect, useCallback } from 'react'
import {
  Box, Typography, Card, CardContent, TextField, Button,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Dialog, DialogTitle, DialogContent, DialogActions,
  FormControl, InputLabel, Select, MenuItem, Chip, Alert
} from '@mui/material'
import api from '../api/axios'
import { useAuth } from '../auth/AuthContext'
import type { User, TokenResponse } from '../types'

interface DeletionRequestItem {
  id: string
  user_id: string | null
  email: string
  full_name: string | null
  reason: string | null
  status: string
  requested_at: string
  processed_at: string | null
  processed_by: string | null
}

export default function Settings() {
  const { user, hasPermission, currentFarm, startImpersonating, farms, logout } = useAuth()
  const [oldPw, setOldPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [pwMsg, setPwMsg] = useState('')
  const [pwError, setPwError] = useState(false)

  const [users, setUsers] = useState<User[]>([])
  const [usersLoading, setUsersLoading] = useState(false)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newName, setNewName] = useState('')
  const [newRole, setNewRole] = useState('viewer')
  const [addMsg, setAddMsg] = useState('')

  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editRole, setEditRole] = useState('')
  const [editFarmId, setEditFarmId] = useState('')
  const [editIsActive, setEditIsActive] = useState(true)

  const [delDialogOpen, setDelDialogOpen] = useState(false)
  const [delReason, setDelReason] = useState('')
  const [delSubmitting, setDelSubmitting] = useState(false)
  const [delSubmitted, setDelSubmitted] = useState(false)
  const [delError, setDelError] = useState('')

  const [deletionRequests, setDeletionRequests] = useState<DeletionRequestItem[]>([])
  const [deletionRequestsLoading, setDeletionRequestsLoading] = useState(false)
  const [delReqMsg, setDelReqMsg] = useState('')

  const fetchUsers = useCallback(async () => {
    setUsersLoading(true)
    try {
      const { data } = await api.get('/auth/users')
      setUsers(data)
    } catch {
      /* ignore */
    } finally {
      setUsersLoading(false)
    }
  }, [])

  useEffect(() => {
    if (hasPermission('users:read')) fetchUsers()
  }, [fetchUsers, hasPermission])

  const handleChangePassword = async () => {
    try {
      await api.post('/auth/change-password', { old_password: oldPw, new_password: newPw })
      setPwMsg('Password changed successfully')
      setPwError(false)
      setOldPw('')
      setNewPw('')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      let msg = 'Failed to change password'
      if (Array.isArray(detail)) {
        msg = detail.map((err: any) => err.msg.replace('Value error, ', '')).join(', ')
      } else if (typeof detail === 'string') {
        msg = detail
      }
      setPwMsg(msg)
      setPwError(true)
    }
  }

  const handleAddUser = async () => {
    if (newRole !== 'super_admin' && !currentFarm) {
      setAddMsg('Please select a specific farm before creating a farm-scoped user (viewer, operator, or admin).')
      return
    }
    try {
      const payload: Record<string, unknown> = {
        email: newEmail,
        password: newPassword,
        full_name: newName,
        role_name: newRole,
      }
      if (newRole !== 'super_admin' && currentFarm) {
        payload.farm_id = currentFarm.id
      }
      await api.post('/auth/register', payload)
      setAddDialogOpen(false)
      setAddMsg('')
      setNewEmail(''); setNewPassword(''); setNewName(''); setNewRole('viewer')
      fetchUsers()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      let msg = 'Failed to create user'
      if (Array.isArray(detail)) {
        msg = detail.map((err: any) => err.msg.replace('Value error, ', '')).join(', ')
      } else if (typeof detail === 'string') {
        msg = detail
      }
      setAddMsg(msg)
    }
  }

  const handleAddUserClose = () => {
    setAddDialogOpen(false)
    setAddMsg('')
    setNewEmail('')
    setNewPassword('')
    setNewName('')
    setNewRole('viewer')
  }

  const handleDeleteUser = async (userId: string) => {
    const ok = window.confirm("Are you sure you want to delete this user? This action cannot be undone.");
    if (!ok) return;
    try {
      await api.delete(`/auth/users/${userId}`)
      fetchUsers()
    } catch {
      /* ignore */
    }
  }

  const openEditDialog = (u: User) => {
    setEditingUser(u)
    setEditRole(u.role?.name || 'viewer')
    setEditFarmId(u.farm_id || '')
    setEditIsActive(u.is_active)
    setEditDialogOpen(true)
  }

  const handleEditUser = async () => {
    if (!editingUser) return
    try {
      const payload: Record<string, unknown> = {}
      if (editRole !== editingUser.role?.name) payload.role_name = editRole
      if (editFarmId !== (editingUser.farm_id || '')) payload.farm_id = editFarmId || null
      if (editIsActive !== editingUser.is_active) payload.is_active = editIsActive
      if (Object.keys(payload).length === 0) {
        setEditDialogOpen(false)
        return
      }
      await api.put(`/auth/users/${editingUser.id}`, payload)
      setEditDialogOpen(false)
      setEditingUser(null)
      fetchUsers()
    } catch {
      /* ignore */
    }
  }

  const handleEditUserClose = () => {
    setEditDialogOpen(false)
    setEditingUser(null)
  }

  const fetchDeletionRequests = useCallback(async () => {
    setDeletionRequestsLoading(true)
    try {
      const { data } = await api.get<DeletionRequestItem[]>('/auth/deletion-requests')
      setDeletionRequests(data)
    } catch {
      /* ignore */
    } finally {
      setDeletionRequestsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (hasPermission('users:write')) fetchDeletionRequests()
  }, [fetchDeletionRequests, hasPermission])

  const handleRequestDeletion = async () => {
    setDelSubmitting(true)
    setDelError('')
    try {
      await api.post('/auth/deletion-request', { reason: delReason || null })
      setDelSubmitted(true)
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      setDelError(typeof detail === 'string' ? detail : 'Failed to submit deletion request')
    } finally {
      setDelSubmitting(false)
    }
  }

  const handleDeletionDialogClose = () => {
    setDelDialogOpen(false)
    setDelReason('')
    setDelSubmitted(false)
    setDelError('')
  }

  const handleApproveRequest = async (id: string) => {
    const ok = window.confirm('Approve this deletion request? This will permanently delete the user account and profile.')
    if (!ok) return
    try {
      await api.post(`/auth/deletion-requests/${id}/approve`)
      setDelReqMsg(`Deletion request for ${deletionRequests.find(r => r.id === id)?.email || 'user'} approved.`)
      fetchDeletionRequests()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      setDelReqMsg(typeof detail === 'string' ? detail : 'Failed to approve deletion request')
    }
  }

  const handleRejectRequest = async (id: string) => {
    const ok = window.confirm('Reject this deletion request? The user account will be reactivated.')
    if (!ok) return
    try {
      await api.post(`/auth/deletion-requests/${id}/reject`)
      setDelReqMsg(`Deletion request for ${deletionRequests.find(r => r.id === id)?.email || 'user'} rejected.`)
      fetchDeletionRequests()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      setDelReqMsg(typeof detail === 'string' ? detail : 'Failed to reject deletion request')
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Settings</Typography>

      {hasPermission('users:impersonate') && (
        <Card sx={{ mb: 3, bgcolor: '#fef3c7' }}>
          <CardContent>
            <Typography variant="body2" sx={{ color: '#92400e' }}>
              You are a super admin. Click <strong>View as</strong> next to a user to see the app from their perspective.
            </Typography>
          </CardContent>
        </Card>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Profile</Typography>
          <Typography variant="body2">Email: {user?.email}</Typography>
          <Typography variant="body2">Role: {user?.role?.name}</Typography>
          <Typography variant="body2">Name: {user?.full_name}</Typography>
          <Typography variant="body2">Farm: {currentFarm?.name || 'All (Super Admin)'}</Typography>
        </CardContent>
      </Card>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Change Password</Typography>
          <TextField fullWidth label="Current Password" type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} margin="normal" size="small" sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }} />
          <TextField fullWidth label="New Password" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} margin="normal" size="small" helperText="At least 6 characters" sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }} />
          <Button variant="contained" onClick={handleChangePassword} sx={{ mt: 1, textTransform: 'none', fontWeight: 700, borderRadius: '8px', bgcolor: '#0f172a', '&:hover': { bgcolor: '#1e293b' } }}>Update Password</Button>
          {pwMsg && <Typography variant="body2" color={pwError ? "error.main" : "success.main"} sx={{ mt: 1 }}>{pwMsg}</Typography>}
        </CardContent>
      </Card>

      {user?.role?.name !== 'super_admin' && (
        <Card sx={{ mb: 3, border: '1px solid #fee2e2' }}>
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ color: '#b91c1c' }}>Delete Account &amp; Data</Typography>
            <Typography variant="body2" sx={{ color: '#64748b', mb: 1.5, lineHeight: 1.6 }}>
              Request deletion of your account and profile data. Your account will be deactivated immediately and an administrator
              will permanently delete your account and associated personal data. Farm data (cameras, recordings, analytics) is
              owned by the farm and remains unless the farm itself is removed.
            </Typography>
            <Button
              variant="outlined"
              color="error"
              onClick={() => setDelDialogOpen(true)}
              sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '8px' }}
            >
              Request Account Deletion
            </Button>
          </CardContent>
        </Card>
      )}

      {hasPermission('users:read') && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>User Management</Typography>
            {hasPermission('users:write') && (
              <Button variant="contained" size="small" onClick={() => setAddDialogOpen(true)} sx={{ mb: 2 }}>
                Add User
              </Button>
            )}
            {usersLoading ? (
              <Typography variant="body2" color="text.secondary">Loading...</Typography>
            ) : users.length === 0 ? (
              <Typography variant="body2" color="text.secondary">No users found.</Typography>
            ) : (
              <>
                {/* Mobile View: Stacked Cards */}
                <Box sx={{ display: { xs: 'flex', sm: 'none' }, flexDirection: 'column', gap: 2 }}>
                  {users.map((u) => (
                    <Box key={u.id} sx={{ p: 2, border: '1px solid #e2e8f0', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 700, wordBreak: 'break-all', fontFamily: '"Outfit", sans-serif' }}>
                            {u.email}
                          </Typography>
                          {u.full_name && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                              👤 {u.full_name}
                            </Typography>
                          )}
                        </Box>
                        <Chip label={u.role?.name} size="small" color="primary" variant="outlined" sx={{ fontWeight: 600, textTransform: 'capitalize', borderRadius: '6px' }} />
                      </Box>
                      
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="caption" color="text.secondary">
                          Farm: {u.farm_id ? (farms.find(f => f.id === u.farm_id)?.name || 'Farm User') : 'All (Super Admin)'}
                        </Typography>
                        <Typography variant="caption" sx={{ color: u.is_active ? 'success.main' : 'text.secondary', fontWeight: 600 }}>
                          {u.is_active ? '● Active' : '○ Inactive'}
                        </Typography>
                      </Box>

                      {(hasPermission('users:write') || hasPermission('users:impersonate')) && (
                        <Box sx={{ display: 'flex', gap: 1, mt: 0.5, flexWrap: 'wrap' }}>
                          {hasPermission('users:impersonate') && (
                            <Button
                              size="small"
                              variant="outlined"
                              disabled={!u.is_active}
                              onClick={async () => {
                                try {
                                  const { data } = await api.post<TokenResponse & { impersonating: { id: string; email: string; full_name: string | null; role: string; permissions: string[] } }>(`/auth/impersonate/${u.id}`)
                                  startImpersonating(data.access_token, data.impersonating)
                                  window.location.href = '/'
                                } catch {
                                  /* ignore */
                                }
                              }}
                              sx={{ flexGrow: 1, textTransform: 'none', borderRadius: '6px', fontSize: '0.75rem' }}
                            >
                              View as
                            </Button>
                          )}
                          {hasPermission('users:write') && (
                            <Button
                              size="small"
                              variant="outlined"
                              disabled={u.id === user?.id}
                              onClick={() => openEditDialog(u)}
                              sx={{ flexGrow: 1, textTransform: 'none', borderRadius: '6px', fontSize: '0.75rem' }}
                            >
                              Edit
                            </Button>
                          )}
                          {hasPermission('users:write') && u.role?.name !== 'super_admin' && (
                            <Button
                              size="small"
                              variant="outlined"
                              color="error"
                              disabled={u.id === user?.id}
                              onClick={() => handleDeleteUser(u.id)}
                              sx={{ flexGrow: 1, textTransform: 'none', borderRadius: '6px', fontSize: '0.75rem' }}
                            >
                              Delete
                            </Button>
                          )}
                        </Box>
                      )}
                    </Box>
                  ))}
                </Box>

                {/* Desktop View: Table */}
                <TableContainer sx={{ display: { xs: 'none', sm: 'block' }, border: '1px solid #e2e8f0', boxShadow: 'none', borderRadius: '8px' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Email</TableCell>
                        <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Name</TableCell>
                        <TableCell>Role</TableCell>
                        <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>Farm</TableCell>
                        <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Active</TableCell>
                        {(hasPermission('users:write') || hasPermission('users:impersonate')) && <TableCell>Actions</TableCell>}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {users.map((u) => (
                        <TableRow key={u.id}>
                          <TableCell>{u.email}</TableCell>
                          <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>{u.full_name || '—'}</TableCell>
                          <TableCell>{u.role?.name}</TableCell>
                          <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>{u.farm_id ? (farms.find(f => f.id === u.farm_id)?.name || u.farm_id.slice(0, 8) + '...') : '—'}</TableCell>
                          <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>{u.is_active ? 'Yes' : 'No'}</TableCell>
                          {(hasPermission('users:write') || hasPermission('users:impersonate')) && (
                            <TableCell>
                              <Box sx={{ display: 'flex', gap: 0.5 }}>
                              {hasPermission('users:impersonate') && (
                                <Button
                                  size="small"
                                  variant="outlined"
                                  disabled={!u.is_active}
                                  onClick={async () => {
                                    try {
                                      const { data } = await api.post<TokenResponse & { impersonating: { id: string; email: string; full_name: string | null; role: string; permissions: string[] } }>(`/auth/impersonate/${u.id}`)
                                      startImpersonating(data.access_token, data.impersonating)
                                      window.location.href = '/'
                                    } catch {
                                      /* ignore */
                                    }
                                  }}
                                >
                                  View as
                                </Button>
                              )}
                              {hasPermission('users:write') && (
                                <Button
                                  size="small"
                                  disabled={u.id === user?.id}
                                  onClick={() => openEditDialog(u)}
                                >
                                  Edit
                                </Button>
                              )}
                              {hasPermission('users:write') && u.role?.name !== 'super_admin' && (
                                <Button
                                  size="small"
                                  color="error"
                                  disabled={u.id === user?.id}
                                  onClick={() => handleDeleteUser(u.id)}
                                >
                                  Delete
                                </Button>
                              )}
                              </Box>
                            </TableCell>
                          )}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {hasPermission('users:write') && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>Deletion Requests</Typography>
            <Typography variant="body2" sx={{ color: '#64748b', mb: 2 }}>
              Users have requested permanent deletion of their accounts. Approving deletes the account; rejecting reactivates it.
            </Typography>
            {delReqMsg && (
              <Alert severity="info" sx={{ mb: 2, borderRadius: '8px' }} onClose={() => setDelReqMsg('')}>
                {delReqMsg}
              </Alert>
            )}
            {deletionRequestsLoading ? (
              <Typography variant="body2" color="text.secondary">Loading...</Typography>
            ) : deletionRequests.length === 0 ? (
              <Typography variant="body2" color="text.secondary">No deletion requests.</Typography>
            ) : (
              <TableContainer sx={{ border: '1px solid #e2e8f0', boxShadow: 'none', borderRadius: '8px' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Email</TableCell>
                      <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>Name</TableCell>
                      <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>Requested</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {deletionRequests.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell>{r.email}</TableCell>
                        <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>{r.full_name || '—'}</TableCell>
                        <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>{new Date(r.requested_at).toLocaleDateString()}</TableCell>
                        <TableCell>
                          <Chip
                            label={r.status}
                            size="small"
                            color={r.status === 'pending' ? 'warning' : r.status === 'completed' ? 'success' : 'default'}
                            variant="outlined"
                            sx={{ fontWeight: 600, textTransform: 'capitalize', borderRadius: '6px' }}
                          />
                        </TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', gap: 0.5 }}>
                            <Button size="small" color="error" disabled={r.status !== 'pending'} onClick={() => handleApproveRequest(r.id)}>
                              Approve
                            </Button>
                            <Button size="small" disabled={r.status !== 'pending'} onClick={() => handleRejectRequest(r.id)}>
                              Reject
                            </Button>
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
            {deletionRequests.some(r => r.reason) && (
              <Box sx={{ mt: 2 }}>
                {deletionRequests.filter(r => r.reason).map(r => (
                  <Typography key={r.id} variant="caption" sx={{ display: 'block', color: '#64748b', mb: 0.5 }}>
                    <strong>{r.email}:</strong> {r.reason}
                  </Typography>
                ))}
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      <Dialog open={addDialogOpen} onClose={handleAddUserClose} maxWidth="xs" fullWidth sx={{ '& .MuiDialog-paper': { borderRadius: '12px', p: 1 } }}>
        <DialogTitle sx={{ fontWeight: 800, fontFamily: '"Outfit", sans-serif', pb: 1 }}>Add User</DialogTitle>
        <DialogContent>
          <TextField fullWidth label="Email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} margin="dense" size="small" sx={{ mb: 1.5, '& .MuiOutlinedInput-root': { borderRadius: '8px' } }} />
          <TextField fullWidth label="Password" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} margin="dense" size="small" helperText="At least 6 characters" sx={{ mb: 1.5, '& .MuiOutlinedInput-root': { borderRadius: '8px' } }} />
          <TextField fullWidth label="Full Name" value={newName} onChange={(e) => setNewName(e.target.value)} margin="dense" size="small" sx={{ mb: 1.5, '& .MuiOutlinedInput-root': { borderRadius: '8px' } }} />
          <FormControl fullWidth margin="dense" size="small" sx={{ mb: 1.5 }}>
            <InputLabel id="add-user-role-label">Role</InputLabel>
            <Select
              labelId="add-user-role-label"
              id="add-user-role-select"
              value={newRole}
              label="Role"
              onChange={(e) => setNewRole(e.target.value)}
              sx={{ borderRadius: '8px' }}
            >
              <MenuItem value="viewer">Viewer</MenuItem>
              <MenuItem value="operator">Operator</MenuItem>
              <MenuItem value="admin">Admin</MenuItem>
            </Select>
          </FormControl>
          <TextField fullWidth label="Farm ID" value={currentFarm?.id || ''} margin="dense" size="small" disabled helperText="Auto-set to current farm" sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }} />
          {addMsg && <Typography variant="body2" color="error.main" sx={{ mt: 1.5 }}>{addMsg}</Typography>}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleAddUserClose} sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '6px', color: '#64748b' }}>Cancel</Button>
          <Button variant="contained" onClick={handleAddUser} sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '8px', px: 3, bgcolor: '#0f172a', '&:hover': { bgcolor: '#1e293b' } }}>Create</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={editDialogOpen} onClose={handleEditUserClose} maxWidth="xs" fullWidth sx={{ '& .MuiDialog-paper': { borderRadius: '12px', p: 1 } }}>
        <DialogTitle sx={{ fontWeight: 800, fontFamily: '"Outfit", sans-serif', pb: 1 }}>
          Edit User — {editingUser?.email}
        </DialogTitle>
        <DialogContent>
          <FormControl fullWidth margin="dense" size="small" sx={{ mb: 1.5 }}>
            <InputLabel id="edit-user-role-label">Role</InputLabel>
            <Select
              labelId="edit-user-role-label"
              value={editRole}
              label="Role"
              onChange={(e) => setEditRole(e.target.value)}
              sx={{ borderRadius: '8px' }}
            >
              <MenuItem value="viewer">Viewer</MenuItem>
              <MenuItem value="operator">Operator</MenuItem>
              <MenuItem value="admin">Admin</MenuItem>
              {user?.role?.name === 'super_admin' && <MenuItem value="super_admin">Super Admin</MenuItem>}
            </Select>
          </FormControl>
          <FormControl fullWidth margin="dense" size="small" sx={{ mb: 1.5 }}>
            <InputLabel id="edit-user-farm-label">Farm</InputLabel>
            <Select
              labelId="edit-user-farm-label"
              value={editFarmId}
              label="Farm"
              onChange={(e) => setEditFarmId(e.target.value)}
              sx={{ borderRadius: '8px' }}
            >
              <MenuItem value="">None (Super Admin)</MenuItem>
              {farms.map((f) => (
                <MenuItem key={f.id} value={f.id}>{f.name}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl fullWidth margin="dense" size="small" sx={{ mb: 1.5 }}>
            <InputLabel id="edit-user-active-label">Active</InputLabel>
            <Select
              labelId="edit-user-active-label"
              value={editIsActive ? 'active' : 'inactive'}
              label="Active"
              onChange={(e) => setEditIsActive(e.target.value === 'active')}
              sx={{ borderRadius: '8px' }}
            >
              <MenuItem value="active">Active</MenuItem>
              <MenuItem value="inactive">Inactive</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleEditUserClose} sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '6px', color: '#64748b' }}>Cancel</Button>
          <Button variant="contained" onClick={handleEditUser} sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '8px', px: 3, bgcolor: '#0f172a', '&:hover': { bgcolor: '#1e293b' } }}>Save</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={delDialogOpen} onClose={delSubmitted ? undefined : handleDeletionDialogClose} maxWidth="xs" fullWidth sx={{ '& .MuiDialog-paper': { borderRadius: '12px', p: 1 } }}>
        {delSubmitted ? (
          <>
            <DialogTitle sx={{ fontWeight: 800, fontFamily: '"Outfit", sans-serif', pb: 1, color: '#b91c1c' }}>
              Request Submitted
            </DialogTitle>
            <DialogContent>
              <Alert severity="success" sx={{ mb: 2, borderRadius: '8px' }}>
                Your account deletion request has been submitted. Your account is now deactivated and you will be signed out.
              </Alert>
              <Typography variant="body2" sx={{ color: '#64748b', lineHeight: 1.6 }}>
                An administrator will review your request and permanently delete your account and associated personal data. Farm
                data (cameras, recordings, analytics) is owned by the farm and is not deleted unless the farm itself is removed.
              </Typography>
            </DialogContent>
            <DialogActions sx={{ px: 3, pb: 2 }}>
              <Button
                variant="contained"
                color="error"
                onClick={() => logout()}
                sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '8px', px: 3 }}
              >
                Sign Out
              </Button>
            </DialogActions>
          </>
        ) : (
          <>
            <DialogTitle sx={{ fontWeight: 800, fontFamily: '"Outfit", sans-serif', pb: 1, color: '#b91c1c' }}>
              Request Account Deletion
            </DialogTitle>
            <DialogContent>
              <Typography variant="body2" sx={{ color: '#475569', lineHeight: 1.6, mb: 2 }}>
                This will deactivate your account immediately and submit a request for an administrator to permanently delete
                your account and profile data. This action cannot be undone.
              </Typography>
              {delError && (
                <Alert severity="error" sx={{ mb: 2, borderRadius: '8px' }} onClose={() => setDelError('')}>
                  {delError}
                </Alert>
              )}
              <TextField
                fullWidth
                label="Reason (optional)"
                value={delReason}
                onChange={(e) => setDelReason(e.target.value)}
                multiline
                minRows={3}
                margin="dense"
                size="small"
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: '8px' } }}
              />
            </DialogContent>
            <DialogActions sx={{ px: 3, pb: 2 }}>
              <Button onClick={handleDeletionDialogClose} sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '6px', color: '#64748b' }}>Cancel</Button>
              <Button
                variant="contained"
                color="error"
                disabled={delSubmitting}
                onClick={handleRequestDeletion}
                sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '8px', px: 3 }}
              >
                {delSubmitting ? 'Submitting...' : 'Request Deletion'}
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Box>
  )
}
