import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ImpersonationBanner from '../components/ImpersonationBanner'

vi.mock('../auth/AuthContext', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '../auth/AuthContext'

describe('ImpersonationBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when not impersonating', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '1', email: 'admin@test.com' },
      impersonating: null,
      stopImpersonating: vi.fn(),
    } as any)

    const { container } = render(<ImpersonationBanner />)
    expect(container.innerHTML).toBe('')
  })

  it('renders yellow banner when impersonating', () => {
    const stopImpersonating = vi.fn()
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '1', email: 'admin@test.com' },
      impersonating: {
        id: '2',
        email: 'user@farm.com',
        full_name: 'John Doe',
        role: 'operator',
        permissions: ['dashboard:read'],
      },
      stopImpersonating,
    } as any)

    render(<ImpersonationBanner />)
    expect(screen.getByText('John Doe')).toBeInTheDocument()
    expect(screen.getByText(/operator/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Stop Impersonating'))
    expect(stopImpersonating).toHaveBeenCalled()
  })
})
