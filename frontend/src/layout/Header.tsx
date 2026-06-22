import { AppBar, Toolbar, Typography, IconButton, Box, Avatar, Menu, MenuItem, Tooltip, Select, FormControl } from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import { useAuth } from '../auth/AuthContext'
import { useState } from 'react'

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { user, logout, farms, currentFarm, setCurrentFarm } = useAuth()
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  const initials = user?.full_name?.split(' ').map((n) => n[0]).join('').toUpperCase() || '?'

  return (
    <AppBar 
      position="fixed" 
      sx={{ 
        zIndex: (t) => t.zIndex.drawer + 1,
        backgroundColor: '#ffffff',
        color: '#0f172a',
        borderBottom: '1px solid rgba(0, 0, 0, 0.05)',
        boxShadow: 'none',
        display: { xs: 'block', md: 'none' }
      }}
    >
      <Toolbar sx={{ display: 'flex', justifyContent: 'space-between', px: { xs: 2, md: 3 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <IconButton color="default" edge="start" onClick={onMenuClick} sx={{ mr: 2, display: { md: 'none' } }}>
            <MenuIcon />
          </IconButton>
          <Box sx={{ display: { xs: 'none', sm: 'block' } }}>
            <Typography 
              variant="subtitle2" 
              sx={{ 
                fontFamily: '"Outfit", sans-serif', 
                fontWeight: 600, 
                letterSpacing: '0.1em',
                color: 'text.secondary',
                fontSize: '0.75rem',
                textTransform: 'uppercase'
              }}
            >
              System Command
            </Typography>
            <Typography 
              variant="h6" 
              sx={{ 
                fontFamily: '"Outfit", sans-serif', 
                fontWeight: 700, 
                fontSize: '1.05rem',
                lineHeight: 1.1,
                mt: 0.1
              }}
            >
              TVS Monitoring Deck
            </Typography>
          </Box>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2.5 }}>
          {user?.role?.name === 'super_admin' && farms.length > 0 && (
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <Select
                value={currentFarm ? currentFarm.id : 'all'}
                onChange={(e) => {
                  if (e.target.value === 'all') {
                    setCurrentFarm(null)
                  } else {
                    const farm = farms.find((f) => f.id === e.target.value) || null
                    setCurrentFarm(farm)
                  }
                }}
                sx={{
                  color: '#0f172a',
                  fontSize: '0.8rem',
                  fontFamily: '"Inter", sans-serif',
                  fontWeight: 500,
                  borderRadius: '8px',
                  '& .MuiOutlinedInput-notchedOutline': { borderColor: '#e2e8f0' },
                }}
              >
                <MenuItem value="all" sx={{ fontSize: '0.8rem', fontWeight: 700 }}>
                  🌐 All Farms
                </MenuItem>
                {farms.map((farm) => (
                  <MenuItem key={farm.id} value={farm.id} sx={{ fontSize: '0.8rem' }}>
                    🏡 {farm.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          {/* Status Indicator Tag */}
          <Box 
            sx={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 1,
              bgcolor: '#e8f5e9',
              border: '1px solid #10b981',
              px: 1.5,
              py: 0.5,
              borderRadius: '20px'
            }}
          >
            <Box 
              sx={{ 
                width: 6, 
                height: 6, 
                borderRadius: '50%', 
                bgcolor: '#10b981'
              }}
            />
            <Typography 
              variant="caption" 
              sx={{ 
                fontFamily: '"Outfit", sans-serif', 
                color: '#10b981', 
                fontWeight: 700,
                fontSize: '10px'
              }}
            >
              SYSTEM SECURE
            </Typography>
          </Box>

          <Tooltip title={user?.full_name || 'User'}>
            <IconButton onClick={(e) => setAnchorEl(e.currentTarget)} sx={{ p: 0.5 }}>
              <Avatar 
                sx={{ 
                  width: 32, 
                  height: 32, 
                  bgcolor: '#0f172a',
                  fontFamily: '"Outfit", sans-serif',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  color: '#ffffff'
                }}
              >
                {initials}
              </Avatar>
            </IconButton>
          </Tooltip>
          
          <Menu 
            anchorEl={anchorEl} 
            open={Boolean(anchorEl)} 
            onClose={() => setAnchorEl(null)}
            slotProps={{
              paper: {
                sx: {
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  mt: 1,
                  boxShadow: '0 4px 12px rgba(0,0,0,0.05)'
                }
              }
            }}
          >
            <MenuItem disabled>
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.primary' }}>
                  {user?.full_name}
                </Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontFamily: '"JetBrains Mono", monospace' }}>
                  {user?.email} ({user?.role?.name})
                </Typography>
              </Box>
            </MenuItem>
            <MenuItem 
              onClick={() => { setAnchorEl(null); logout() }}
              sx={{ 
                color: 'error.main',
                fontFamily: '"Outfit", sans-serif',
                fontWeight: 600,
                fontSize: '0.9rem'
              }}
            >
              Disconnect (Logout)
            </MenuItem>
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  )
}
