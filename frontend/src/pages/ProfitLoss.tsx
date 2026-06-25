import { useState } from 'react'
import {
  Box, Typography, Card, CardContent, Grid, TextField, Button,
  ToggleButton, ToggleButtonGroup, CircularProgress, Chip, Alert,
  Slider,
} from '@mui/material'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import CurrencyExchangeIcon from '@mui/icons-material/CurrencyExchange'
import api from '../api/axios'
import type { ProfitLossResult } from '../types'

export default function ProfitLoss() {
  const [purchasePricePerChick, setPurchasePricePerChick] = useState(30)
  const [numChickens, setNumChickens] = useState(100)
  const [pricePerChicken, setPricePerChicken] = useState(120)
  const [durationDays, setDurationDays] = useState(30)
  const [feedCost, setFeedCost] = useState(0.15)
  const [numLabourers, setNumLabourers] = useState(2)
  const [labourRatePerDay, setLabourRatePerDay] = useState(300)
  const [otherCosts, setOtherCosts] = useState(50)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ProfitLossResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const calculate = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const { data } = await api.post('/analytics/profit-loss', {
        purchase_price_per_chick: purchasePricePerChick,
        num_chickens: numChickens,
        price_per_chicken: pricePerChicken,
        duration_days: durationDays,
        feed_cost_per_chicken_per_day: feedCost,
        num_labourers: numLabourers,
        labour_rate_per_day: labourRatePerDay,
        other_costs: otherCosts,
      })
      setResult(data)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Calculation failed')
    } finally {
      setLoading(false)
    }
  }

  const handleDuration = (_: any, val: number | null) => {
    if (val !== null) setDurationDays(val)
  }

  const formatCurrency = (n: number) =>
    '₹' + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  return (
    <Box>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: 800, mb: 0.5 }}>Profit & Loss Projection</Typography>
        <Typography variant="body2" color="text.secondary">
          Estimate profitability based on flock size, selling price, and costs
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Input Card */}
        <Grid item xs={12} md={5}>
          <Card>
            <CardContent sx={{ p: 3 }}>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>Flock Parameters</Typography>

              <TextField
                fullWidth
                label="Number of Chickens"
                type="number"
                value={numChickens}
                onChange={(e) => setNumChickens(Math.max(1, parseInt(e.target.value) || 0))}
                sx={{ mb: 2.5 }}
                slotProps={{ input: { sx: { fontWeight: 600, fontFamily: '"JetBrains Mono", monospace' } } }}
              />

              <TextField
                fullWidth
                label="Purchase Price per Chick (₹)"
                type="number"
                value={purchasePricePerChick}
                onChange={(e) => setPurchasePricePerChick(Math.max(0, parseFloat(e.target.value) || 0))}
                sx={{ mb: 2.5 }}
                slotProps={{
                  input: {
                    startAdornment: <Typography sx={{ mr: 0.5, color: 'text.secondary', fontSize: 18, fontWeight: 700 }}>₹</Typography>,
                    sx: { fontWeight: 600, fontFamily: '"JetBrains Mono", monospace' },
                  },
                }}
              />

              <TextField
                fullWidth
                label="Selling Price per Chicken (₹)"
                type="number"
                value={pricePerChicken}
                onChange={(e) => setPricePerChicken(Math.max(0.01, parseFloat(e.target.value) || 0))}
                sx={{ mb: 2.5 }}
                slotProps={{
                  input: {
                    startAdornment: <Typography sx={{ mr: 0.5, color: 'text.secondary', fontSize: 18, fontWeight: 700 }}>₹</Typography>,
                    sx: { fontWeight: 600, fontFamily: '"JetBrains Mono", monospace' },
                  },
                }}
              />

              <Box sx={{ mb: 2.5 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 1, color: 'text.secondary' }}>
                  Projection Duration
                </Typography>
                <ToggleButtonGroup value={durationDays} exclusive onChange={handleDuration} fullWidth>
                  <ToggleButton value={30} sx={{ fontWeight: 700, textTransform: 'none' }}>
                    30 Days
                  </ToggleButton>
                  <ToggleButton value={45} sx={{ fontWeight: 700, textTransform: 'none' }}>
                    45 Days
                  </ToggleButton>
                </ToggleButtonGroup>
              </Box>

              <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5, color: 'text.secondary' }}>
                Daily Feed Cost per Chicken: ₹{feedCost.toFixed(2)}
              </Typography>
              <Slider
                value={feedCost}
                onChange={(_, v) => setFeedCost(v as number)}
                min={0.02}
                max={0.50}
                step={0.01}
                sx={{ mb: 2.5 }}
              />

              <Grid container spacing={2} sx={{ mb: 2.5 }}>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="No. of Labourers"
                    type="number"
                    value={numLabourers}
                    onChange={(e) => setNumLabourers(Math.max(0, parseInt(e.target.value) || 0))}
                    slotProps={{ input: { sx: { fontWeight: 600, fontFamily: '"JetBrains Mono", monospace' } } }}
                  />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Daily Rate / Labourer (₹)"
                    type="number"
                    value={labourRatePerDay}
                    onChange={(e) => setLabourRatePerDay(Math.max(0, parseFloat(e.target.value) || 0))}
                    slotProps={{
                      input: {
                        startAdornment: <Typography sx={{ mr: 0.5, color: 'text.secondary', fontSize: 18, fontWeight: 700 }}>₹</Typography>,
                        sx: { fontWeight: 600, fontFamily: '"JetBrains Mono", monospace' },
                      },
                    }}
                  />
                </Grid>
              </Grid>

              <TextField
                fullWidth
                label="Monthly Other Costs (₹)"
                type="number"
                value={otherCosts}
                onChange={(e) => setOtherCosts(Math.max(0, parseFloat(e.target.value) || 0))}
                sx={{ mb: 3 }}
                slotProps={{
                  input: {
                    startAdornment: <Typography sx={{ mr: 0.5, color: 'text.secondary', fontSize: 18, fontWeight: 700 }}>₹</Typography>,
                    sx: { fontWeight: 600, fontFamily: '"JetBrains Mono", monospace' },
                  },
                }}
              />

              <Button
                variant="contained"
                fullWidth
                size="large"
                onClick={calculate}
                disabled={loading}
                sx={{
                  py: 1.5,
                  fontWeight: 700,
                  fontSize: '1rem',
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #10b981, #059669)',
                  '&:hover': { background: 'linear-gradient(135deg, #059669, #047857)' },
                }}
              >
                {loading ? <CircularProgress size={22} sx={{ color: '#fff' }} /> : 'Calculate Projection'}
              </Button>
            </CardContent>
          </Card>
        </Grid>

        {/* Results Card */}
        <Grid item xs={12} md={7}>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
          )}

          {!result && !error && (
            <Card sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CardContent sx={{ textAlign: 'center', py: 8 }}>
                <CurrencyExchangeIcon sx={{ fontSize: 64, color: '#cbd5e1', mb: 2 }} />
                <Typography variant="h6" sx={{ fontWeight: 700, color: '#94a3b8' }}>Enter parameters & calculate</Typography>
                <Typography variant="body2" color="text.secondary">Projected profit/loss will appear here</Typography>
              </CardContent>
            </Card>
          )}

          {result && (
            <Box>
              {/* Key metrics */}
              <Grid container spacing={2} sx={{ mb: 2 }}>
                <Grid item xs={6} sm={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center', py: 2 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Projected</Typography>
                      <Typography variant="h5" sx={{ fontWeight: 800, fontFamily: '"JetBrains Mono", monospace' }}>{result.projected_headcount}</Typography>
                      <Typography variant="caption" color="text.secondary">of {result.input_chickens} chickens</Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center', py: 2 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Revenue</Typography>
                      <Typography variant="h5" sx={{ fontWeight: 800, color: '#10b981', fontFamily: '"JetBrains Mono", monospace' }}>{formatCurrency(result.revenue)}</Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center', py: 2 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Costs</Typography>
                      <Typography variant="h5" sx={{ fontWeight: 800, color: '#ef4444', fontFamily: '"JetBrains Mono", monospace' }}>{formatCurrency(result.costs.total_costs)}</Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Card>
                    <CardContent sx={{ textAlign: 'center', py: 2 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Net {result.is_profitable ? 'Profit' : 'Loss'}</Typography>
                      <Typography variant="h5" sx={{ fontWeight: 800, color: result.is_profitable ? '#10b981' : '#ef4444', fontFamily: '"JetBrains Mono", monospace' }}>
                        {formatCurrency(result.net_profit)}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>

              {/* Cost Breakdown */}
              <Card sx={{ mb: 2 }}>
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>Cost Breakdown</Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" color="text.secondary">Chick Purchase Cost</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: '"JetBrains Mono", monospace' }}>{formatCurrency(result.costs.chick_purchase_cost)}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" color="text.secondary">Feed Cost ({result.duration_days} days)</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: '"JetBrains Mono", monospace' }}>{formatCurrency(result.costs.feed_cost)}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" color="text.secondary">Labour Cost ({result.duration_days} days)</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: '"JetBrains Mono", monospace' }}>{formatCurrency(result.costs.labour_cost)}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" color="text.secondary">Other Costs</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: '"JetBrains Mono", monospace' }}>{formatCurrency(result.costs.other_costs)}</Typography>
                    </Box>
                    <Box sx={{ borderTop: '1px solid #e2e8f0', pt: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body1" sx={{ fontWeight: 700 }}>Total Costs</Typography>
                      <Typography variant="body1" sx={{ fontWeight: 800, fontFamily: '"JetBrains Mono", monospace', color: '#ef4444' }}>{formatCurrency(result.costs.total_costs)}</Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>

              {/* Profit Margins + Context */}
              <Card>
                <CardContent sx={{ p: 3 }}>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <Box sx={{ textAlign: 'center', py: 1 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, mb: 0.5 }}>
                          {result.is_profitable
                            ? <TrendingUpIcon sx={{ color: '#10b981', fontSize: 28 }} />
                            : <TrendingDownIcon sx={{ color: '#ef4444', fontSize: 28 }} />
                          }
                          <Typography variant="h3" sx={{ fontWeight: 800, color: result.is_profitable ? '#10b981' : '#ef4444', fontFamily: '"JetBrains Mono", monospace' }}>
                            {result.profit_margin_percent}%
                          </Typography>
                        </Box>
                        <Typography variant="body2" color="text.secondary">Profit Margin</Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Typography variant="caption" color="text.secondary">Mortality Rate (est.)</Typography>
                          <Chip label={(result.estimated_mortality_rate * 100).toFixed(1) + '%'} size="small" sx={{ fontWeight: 600, fontSize: '0.7rem', borderRadius: '6px' }} />
                        </Box>
                        {result.avg_health_score !== null && (
                          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Typography variant="caption" color="text.secondary">Avg Health Score</Typography>
                            <Chip
                              label={result.avg_health_score.toFixed(1)}
                              size="small"
                              color={result.avg_health_score >= 0.7 ? 'success' : result.avg_health_score >= 0.4 ? 'warning' : 'error'}
                              sx={{ fontWeight: 600, fontSize: '0.7rem', borderRadius: '6px' }}
                            />
                          </Box>
                        )}
                        {result.current_headcount !== null && (
                          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Typography variant="caption" color="text.secondary">Current Headcount</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: '"JetBrains Mono", monospace' }}>{result.current_headcount}</Typography>
                          </Box>
                        )}
                        <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Typography variant="caption" color="text.secondary">Duration</Typography>
                          <Typography variant="body2" sx={{ fontWeight: 700 }}>{result.duration_days} days</Typography>
                        </Box>
                      </Box>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Box>
          )}
        </Grid>
      </Grid>
    </Box>
  )
}
