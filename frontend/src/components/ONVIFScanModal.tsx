import { useState, useEffect, useCallback } from 'react'
import {
  Box, Dialog, DialogTitle, DialogContent, DialogActions,
  Button, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Typography, CircularProgress, Chip,
  TextField, Accordion, AccordionSummary, AccordionDetails,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import type { ONVIFDevice, ONVIFChannel } from '../types'

interface ONVIFScanModalProps {
  open: boolean
  onClose: () => void
  onAddDevice: (device: ONVIFDevice, channel?: ONVIFChannel) => void
  getResults: () => Promise<ONVIFDevice[]>
  startScan: (params?: { subnet?: string; ip?: string; username?: string; password?: string }) => Promise<void>
}

export function ONVIFScanModal({ open, onClose, onAddDevice, getResults, startScan }: ONVIFScanModalProps) {
  const [results, setResults] = useState<ONVIFDevice[]>([])
  const [scanning, setScanning] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [targetIp, setTargetIp] = useState('')

  const doScan = useCallback(async () => {
    setScanning(true)
    setResults([])
    try {
      await startScan({
        username: username || undefined,
        password: password || undefined,
        ip: targetIp || undefined,
      })
    } catch { /* ignore */ }
  }, [username, password, targetIp, startScan])

  const poll = useCallback(async () => {
    const interval = setInterval(async () => {
      const devices = await getResults()
      setResults(devices)
      if (devices.length > 0) {
        clearInterval(interval)
        setScanning(false)
      }
    }, 2000)

    setTimeout(() => { clearInterval(interval); setScanning(false) }, 45000)
  }, [getResults])

  useEffect(() => {
    if (open) {
      doScan()
      poll()
    }
  }, [open, doScan, poll])

  const hasRtsp = (url: string | null): url is string => !!url && url.startsWith('rtsp://')

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Network Scan</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          <TextField
            size="small" label="Username (optional)"
            value={username} onChange={(e) => setUsername(e.target.value)}
            sx={{ minWidth: 160 }}
          />
          <TextField
            size="small" label="Password (optional)" type="password"
            value={password} onChange={(e) => setPassword(e.target.value)}
            sx={{ minWidth: 160 }}
          />
          <TextField
            size="small" label="Specific IP (optional)"
            value={targetIp} onChange={(e) => setTargetIp(e.target.value)}
            placeholder="e.g. 192.168.1.100"
            sx={{ minWidth: 200 }}
          />
        </Box>

        {scanning && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Scanning for ONVIF cameras...</Typography>
          </Box>
        )}

        {results.length > 0 ? (
          <TableContainer component={Paper}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Device</TableCell>
                  <TableCell>Channels</TableCell>
                  <TableCell>Brand</TableCell>
                  <TableCell>Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {results.map((dev) => (
                  <TableRow key={dev.ip}>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{dev.ip}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {dev.manufacturer} {dev.model}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {dev.channels.filter((ch) => hasRtsp(ch.rtsp_url)).length > 0 ? (
                        <Accordion sx={{ boxShadow: 'none', bgcolor: 'transparent' }} disableGutters>
                          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 32, p: 0 }}>
                            <Chip
                              label={`${dev.channels.length} channel(s)`}
                              size="small"
                              color="primary"
                              variant="outlined"
                            />
                          </AccordionSummary>
                          <AccordionDetails sx={{ p: 0, pt: 1 }}>
                            {dev.channels.map((ch) => (
                              <Box key={ch.channel} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                                <Chip label={`Ch ${ch.channel}`} size="small" />
                                {ch.name && <Typography variant="caption">{ch.name}</Typography>}
                                {hasRtsp(ch.rtsp_url) ? (
                                  <Typography variant="caption" sx={{ fontFamily: 'monospace', fontSize: 10, color: 'success.light', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {ch.rtsp_url}
                                  </Typography>
                                ) : (
                                  <Typography variant="caption" color="text.disabled">no RTSP</Typography>
                                )}
                                <Button size="small" variant="text" sx={{ fontSize: 10, minWidth: 40 }}
                                  onClick={() => onAddDevice(dev, ch)}>
                                  Add
                                </Button>
                              </Box>
                            ))}
                          </AccordionDetails>
                        </Accordion>
                      ) : (
                        <Typography variant="caption" color="text.disabled">No RTSP streams found</Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      {dev.brand ? (
                        <Chip label={dev.brand} size="small" variant="outlined" color="info" />
                      ) : (
                        <Typography variant="caption" color="text.disabled">—</Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Button size="small" variant="outlined"
                        disabled={!dev.channels.some((ch) => hasRtsp(ch.rtsp_url))}
                        onClick={() => onAddDevice(dev)}>
                        Add All
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : !scanning ? (
          <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 4 }}>
            No ONVIF devices found. Try entering a specific IP or NVR credentials above.
          </Typography>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}
