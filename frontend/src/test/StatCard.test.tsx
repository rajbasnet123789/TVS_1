import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { StatCard } from '../components/StatCard'
import PeopleIcon from '@mui/icons-material/People'

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('StatCard', () => {
  it('renders title and value', () => {
    renderWithRouter(
      <StatCard title="Total Detections" value={42} icon={<PeopleIcon />} color="#00f3ff" />
    )
    expect(screen.getByText('Total Detections')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('renders subtitle when provided', () => {
    renderWithRouter(
      <StatCard title="Rate" value="10/hr" icon={<PeopleIcon />} color="#10b981" subtitle="Last 1 hour" />
    )
    expect(screen.getByText('Last 1 hour')).toBeInTheDocument()
  })

  it('renders with a string value', () => {
    renderWithRouter(
      <StatCard title="Confidence" value="95.2%" icon={<PeopleIcon />} color="#f59e0b" />
    )
    expect(screen.getByText('95.2%')).toBeInTheDocument()
  })
})
