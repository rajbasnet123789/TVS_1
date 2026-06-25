import { useState, useEffect } from 'react'
import {
  Box, TextField, Button, Typography, Alert, Paper, InputAdornment, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material'
import { MailOutline, LockOutlined, Visibility, VisibilityOff } from '@mui/icons-material'
import { useAuth } from '../auth/AuthContext'
import type { AxiosError } from 'axios'
import api from '../api/axios'

interface ErrorResponse {
  detail?: string
}

export default function Login() {
  const { login, loginWithGoogle } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [videoError, setVideoError] = useState(false)
  const [logoError, setLogoError] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showForgotDialog, setShowForgotDialog] = useState(false)
  const [googleClientId, setGoogleClientId] = useState<string | null>(null)

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const { data } = await api.get('/auth/config')
        if (data.google_client_id) {
          setGoogleClientId(data.google_client_id)
        }
      } catch (err) {
        console.error('Failed to fetch auth config:', err)
      }
    }
    fetchConfig()
  }, [])

  useEffect(() => {
    if (!googleClientId) return

    let isMounted = true
    let script: HTMLScriptElement | null = null

    const handleGoogleLogin = async (response: any) => {
      if (!isMounted) return
      setLoading(true)
      setError('')
      try {
        await loginWithGoogle(response.credential)
      } catch (err: any) {
        if (!isMounted) return
        setError(err?.response?.data?.detail || 'Failed to authenticate with Google')
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    const initGoogle = () => {
      if ((window as any).google) {
        (window as any).google.accounts.id.initialize({
          client_id: googleClientId,
          callback: handleGoogleLogin,
        });
        (window as any).google.accounts.id.renderButton(
          document.getElementById('google-signin-btn'),
          { theme: 'outline', size: 'large', width: 380, shape: 'rectangular' }
        )
      }
    }

    if ((window as any).google) {
      initGoogle()
    } else {
      script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      script.onload = () => {
        if (isMounted) {
          initGoogle()
        }
      }
      document.body.appendChild(script)
    }

    return () => {
      isMounted = false
      if (script && document.body.contains(script)) {
        document.body.removeChild(script)
      }
    }
  }, [googleClientId, loginWithGoogle])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(email, password)
    } catch (err: unknown) {
      const axiosErr = err as AxiosError<ErrorResponse>
      if (axiosErr.response) {
        const status = axiosErr.response.status
        if (status === 429) {
          setError('Too many login attempts. Please wait a moment and try again.')
        } else if (status === 422) {
          setError('Please enter a valid email address and password.')
        } else if (status === 500) {
          setError('Server error. Please try again later.')
        } else {
          setError(axiosErr.response.data?.detail || 'Invalid email or password')
        }
      } else if (axiosErr.code === 'ERR_NETWORK') {
        setError('Cannot reach the server. Please check your connection.')
      } else {
        setError('Invalid email or password')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box sx={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden', bgcolor: '#f8f9fa' }}>
      
      {/* Left Side: Branding, Video of Hens & Staggered Telemetry Cards */}
      <Box
        sx={{
          flex: 1,
          display: { xs: 'none', md: 'flex' },
          flexDirection: 'column',
          position: 'relative',
          overflow: 'hidden',
          background: 'linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%)', // Elegant fallback gradient
        }}
      >
        {/* Video of Hens */}
        {!videoError && (
          <Box
            component="video"
            autoPlay
            muted
            loop
            playsInline
            src="/hens_optimized.mp4"
            onError={() => {
              console.error("Login hens video failed to load");
              setVideoError(true);
            }}
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              zIndex: 0,
            }}
          />
        )}

        {/* Soft overlay to ensure readability of overlaying UI */}
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            background: 'linear-gradient(135deg, rgba(248, 249, 250, 0.4) 0%, rgba(226, 232, 240, 0.6) 100%)',
            backdropFilter: 'blur(1px)',
            zIndex: 1,
          }}
        />

        {/* TVS Logo at Top Left */}
        <Box sx={{ position: 'absolute', top: 40, left: 48, zIndex: 2, display: 'flex', alignItems: 'center', gap: 1.5 }}>
          {!logoError ? (
            <Box
              component="img"
              src="/tvs_logo.png"
              alt="TVS Logo"
              onError={() => {
                console.error("Login TVS logo failed to load");
                setLogoError(true);
              }}
              sx={{
                height: 48,
                width: 'auto',
                objectFit: 'contain',
                borderRadius: 1,
              }}
            />
          ) : (
            <Box
              sx={{
                width: 32,
                height: 32,
                bgcolor: '#0f172a',
                borderRadius: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'white',
                fontWeight: 'bold',
                fontSize: 16,
              }}
            >
              T
            </Box>
          )}
          <Typography
            variant="h6"
            sx={{
              fontWeight: 800,
              fontFamily: '"Outfit", sans-serif',
              color: '#0f172a',
              letterSpacing: '0.08em',
              fontSize: '1.2rem',
            }}
          >
            COOP VISION
          </Typography>
        </Box>


      </Box>

      {/* Right Side: Elegant Minimalist Login Form */}
      <Box
        sx={{
          width: { xs: '100%', md: '540px' },
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          bgcolor: '#ffffff',
          px: { xs: 4, sm: 8, md: 10 },
          borderLeft: '1px solid',
          borderColor: '#e2e8f0',
        }}
      >
        <Box sx={{ width: '100%', maxWidth: '380px', mx: 'auto', py: 4 }}>
          
          {/* Logo & Brand */}
          <Box sx={{ mb: 4, display: 'flex', alignItems: 'center', gap: 1.5 }}>
            {!logoError ? (
              <Box
                component="img"
                src="/tvs_logo.png"
                alt="TVS Logo"
                onError={() => setLogoError(true)}
                sx={{
                  height: 44,
                  width: 'auto',
                  objectFit: 'contain',
                  borderRadius: 1,
                }}
              />
            ) : (
              <Box
                sx={{
                  width: 28,
                  height: 28,
                  bgcolor: '#0d3c3d',
                  borderRadius: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'white',
                  fontWeight: 'bold',
                  fontSize: 14,
                }}
              >
                T
              </Box>
            )}
            <Typography
              variant="subtitle1"
              sx={{
                fontWeight: 800,
                fontFamily: '"Outfit", sans-serif',
                color: '#0d3c3d',
                letterSpacing: '0.08em',
              }}
            >
              Coop Vision
            </Typography>
          </Box>

          {/* Welcome Text */}
          <Box sx={{ mb: 4 }}>
            <Typography
              variant="h4"
              sx={{
                fontWeight: 700,
                fontFamily: '"Outfit", sans-serif',
                color: '#1e293b',
                mb: 1,
                fontSize: '2rem',
                letterSpacing: '-0.02em'
              }}
            >
              Welcome Back!
            </Typography>
            <Typography variant="body2" sx={{ color: '#64748b', fontWeight: 500, lineHeight: 1.5 }}>
              Sign in to access your dashboard and continue optimizing your poultry management.
            </Typography>
          </Box>

          {/* Error Banner */}
          {error && (
            <Alert
              severity="error"
              sx={{
                mb: 3,
                borderRadius: 2,
                fontSize: '0.875rem',
              }}
            >
              {error}
            </Alert>
          )}

          {/* Form */}
          <Box component="form" onSubmit={handleSubmit} noValidate sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            {/* Email Field */}
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600, color: '#1e293b', mb: 0.75 }}>
                Email
              </Typography>
              <TextField
                fullWidth
                placeholder="Enter your email"
                type="email"
                variant="outlined"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                sx={{
                  '& .MuiOutlinedInput-root': {
                    borderRadius: 2.5,
                    bgcolor: '#ffffff',
                    height: 48,
                    '& fieldset': { borderColor: '#cbd5e1' },
                    '&:hover fieldset': { borderColor: '#94a3b8' },
                    '&.Mui-focused fieldset': { borderColor: '#0d3c3d' },
                  },
                  '& input:-webkit-autofill': {
                    WebkitBoxShadow: '0 0 0 100px #ffffff inset !important',
                    WebkitTextFillColor: '#1e293b !important',
                  }
                }}
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <MailOutline sx={{ color: '#0d3c3d', fontSize: 20, mr: 0.5 }} />
                      </InputAdornment>
                    ),
                    sx: {
                      fontSize: '0.95rem',
                      fontWeight: 400,
                    }
                  }
                }}
              />
            </Box>

            {/* Password Field */}
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600, color: '#1e293b', mb: 0.75 }}>
                Password
              </Typography>
              <TextField
                fullWidth
                placeholder="Enter your password"
                type={showPassword ? 'text' : 'password'}
                variant="outlined"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                sx={{
                  '& .MuiOutlinedInput-root': {
                    borderRadius: 2.5,
                    bgcolor: '#ffffff',
                    height: 48,
                    '& fieldset': { borderColor: '#cbd5e1' },
                    '&:hover fieldset': { borderColor: '#94a3b8' },
                    '&.Mui-focused fieldset': { borderColor: '#0d3c3d' },
                  },
                  '& input:-webkit-autofill': {
                    WebkitBoxShadow: '0 0 0 100px #ffffff inset !important',
                    WebkitTextFillColor: '#1e293b !important',
                  }
                }}
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <LockOutlined sx={{ color: '#0d3c3d', fontSize: 20, mr: 0.5 }} />
                      </InputAdornment>
                    ),
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton onClick={() => setShowPassword(!showPassword)} edge="end" size="small">
                          {showPassword ? <VisibilityOff sx={{ fontSize: 20, color: '#64748b' }} /> : <Visibility sx={{ fontSize: 20, color: '#64748b' }} />}
                        </IconButton>
                      </InputAdornment>
                    ),
                    sx: {
                      fontSize: '0.95rem',
                      fontWeight: 400,
                    }
                  }
                }}
              />
            </Box>

            {/* Forgot Password Link */}
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: -1 }}>
              <Typography
                variant="caption"
                onClick={() => setShowForgotDialog(true)}
                sx={{
                  fontWeight: 600,
                  color: '#0d3c3d',
                  cursor: 'pointer',
                  '&:hover': { textDecoration: 'underline' }
                }}
              >
                Forgot Password?
              </Typography>
            </Box>

            {/* Submit Button */}
            <Button
              fullWidth
              type="submit"
              variant="contained"
              disabled={loading}
              sx={{
                mt: 1.5,
                height: 48,
                bgcolor: '#0d3c3d',
                color: '#ffffff',
                textTransform: 'none',
                fontWeight: 700,
                fontSize: '0.95rem',
                borderRadius: 2.5,
                boxShadow: 'none',
                transition: 'all 0.2s ease',
                '&:hover': {
                  bgcolor: '#0a3031',
                },
                '&:active': {
                  transform: 'scale(0.99)'
                }
              }}
            >
              {loading ? 'Verifying Access...' : 'Sign In'}
            </Button>

            {/* Divider OR */}
            <Box sx={{ display: 'flex', alignItems: 'center', my: 1 }}>
              <Box sx={{ flex: 1, height: '1px', bgcolor: '#e2e8f0' }} />
              <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 600, px: 2 }}>
                OR
              </Typography>
              <Box sx={{ flex: 1, height: '1px', bgcolor: '#e2e8f0' }} />
            </Box>

            {/* Social Logins */}
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              {/* Google Button */}
              {googleClientId ? (
                <Box id="google-signin-btn" sx={{ width: '100%', display: 'flex', justifyContent: 'center' }} />
              ) : (
                <Button
                  disabled
                  fullWidth
                  variant="outlined"
                  sx={{
                    height: 48,
                    borderColor: '#cbd5e1',
                    color: '#1e293b',
                    textTransform: 'none',
                    fontWeight: 600,
                    fontSize: '0.9rem',
                    borderRadius: 2.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 1.5,
                    '&.Mui-disabled': {
                      color: '#94a3b8',
                      borderColor: '#e2e8f0',
                      bgcolor: '#f8fafc',
                    },
                    '&:hover': {
                      bgcolor: '#f8fafc',
                      borderColor: '#94a3b8',
                    }
                  }}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                  </svg>
                  Continue with Google
                </Button>
              )}

            </Box>
          </Box>
        </Box>
      </Box>

      {/* Forgot Password Dialog */}
      <Dialog 
        open={showForgotDialog} 
        onClose={() => setShowForgotDialog(false)} 
        PaperProps={{ sx: { borderRadius: 3, p: 1 } }}
      >
        <DialogTitle sx={{ fontWeight: 700, fontFamily: '"Outfit", sans-serif', color: '#1e293b' }}>
          Password Recovery
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ color: '#64748b', lineHeight: 1.6 }}>
            For security reasons, password resets in the Coop Vision system are managed by system administrators. 
            Please contact your farm manager or administrator to recover or reset your credentials.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button 
            onClick={() => setShowForgotDialog(false)} 
            variant="contained"
            sx={{ 
              bgcolor: '#0d3c3d', 
              color: 'white', 
              '&:hover': { bgcolor: '#0a3031' }, 
              textTransform: 'none', 
              px: 3, 
              borderRadius: 2 
            }}
          >
            Okay
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
