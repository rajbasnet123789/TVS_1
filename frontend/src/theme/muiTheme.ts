import { createTheme } from '@mui/material/styles'

export const muiTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#0f172a', // Slate 900
      light: '#1e293b',
      dark: '#020617',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#10b981', // Emerald Green
      light: '#34d399',
      dark: '#059669',
    },
    background: {
      default: '#f8fafc', // Slate 50
      paper: '#ffffff',
    },
    error: {
      main: '#ef4444',
    },
    warning: {
      main: '#f59e0b',
    },
    success: {
      main: '#10b981',
    },
    text: {
      primary: '#0f172a',
      secondary: '#475569',
    },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
    h1: { fontFamily: '"Outfit", sans-serif', fontWeight: 700 },
    h2: { fontFamily: '"Outfit", sans-serif', fontWeight: 700 },
    h3: { fontFamily: '"Outfit", sans-serif', fontWeight: 600 },
    h4: { fontFamily: '"Outfit", sans-serif', fontWeight: 600, letterSpacing: '-0.02em' },
    h5: { fontFamily: '"Outfit", sans-serif', fontWeight: 600, letterSpacing: '-0.01em' },
    h6: { fontFamily: '"Outfit", sans-serif', fontWeight: 500 },
    subtitle1: { fontFamily: '"Inter", sans-serif', fontWeight: 500 },
    body1: { fontFamily: '"Inter", sans-serif' },
    body2: { fontFamily: '"Inter", sans-serif' },
    button: { fontFamily: '"Outfit", sans-serif', fontWeight: 600, textTransform: 'none', letterSpacing: '0.02em' },
  },
  shape: { borderRadius: 12 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: '#f8fafc',
          color: '#0f172a',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          backgroundColor: '#ffffff',
          border: '1px solid rgba(0, 0, 0, 0.05)',
          boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.02), 0 1px 2px -1px rgba(0, 0, 0, 0.02)',
          transition: 'all 0.2s ease-in-out',
          '&:hover': {
            borderColor: 'rgba(16, 185, 129, 0.2)',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05)',
          },
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: '#f8fafc',
          borderRight: '1px solid rgba(0, 0, 0, 0.05)',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          padding: '8px 16px',
        },
        contained: {
          boxShadow: 'none',
          '&:hover': {
            boxShadow: 'none',
          },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottom: '1px solid rgba(0, 0, 0, 0.05)',
        },
        head: {
          fontFamily: '"Outfit", sans-serif',
          fontWeight: 600,
          backgroundColor: '#f1f5f9',
        },
      },
    },
  },
})
