import { CssBaseline, ThemeProvider } from '@mui/material'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ResponsiveShell } from './layout/ResponsiveShell'
import { muiTheme } from './theme/muiTheme'

export default function App() {
  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline />
      <BrowserRouter>
        <AuthProvider>
          <ResponsiveShell />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  )
}
