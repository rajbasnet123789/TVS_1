import { useState } from 'react'
import {
  Box, Typography, Card, CardContent, TextField, Button,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, IconButton, Select, MenuItem, FormControl, InputLabel,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import api from '../api/axios'
import { useAuth } from '../auth/AuthContext'

export default function Settings() {
  const { user, hasPermission } = useAuth()
  const [oldPw, setOldPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [pwMsg, setPwMsg] = useState('')

  const handleChangePassword = async () => {
    try {
      await api.post('/auth/change-password', { old_password: oldPw, new_password: newPw })
      setPwMsg('Password changed successfully')
      setOldPw('')
      setNewPw('')
    } catch {
      setPwMsg('Failed to change password')
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Settings</Typography>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Profile</Typography>
          <Typography variant="body2">Email: {user?.email}</Typography>
          <Typography variant="body2">Role: {user?.role?.name}</Typography>
          <Typography variant="body2">Name: {user?.full_name}</Typography>
        </CardContent>
      </Card>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Change Password</Typography>
          <TextField fullWidth label="Current Password" type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} margin="normal" size="small" />
          <TextField fullWidth label="New Password" type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} margin="normal" size="small" />
          <Button variant="contained" onClick={handleChangePassword} sx={{ mt: 1 }}>Update Password</Button>
          {pwMsg && <Typography variant="body2" color="success.main" sx={{ mt: 1 }}>{pwMsg}</Typography>}
        </CardContent>
      </Card>

      {hasPermission('users:read') && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>User Management (Admin)</Typography>
            <Typography variant="body2" color="text.secondary">Full user management coming in a future update.</Typography>
          </CardContent>
        </Card>
      )}
    </Box>
  )
}
