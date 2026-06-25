import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ProtectedRoute } from '../auth/ProtectedRoute'

vi.mock('../auth/AuthContext', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '../auth/AuthContext'

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders children when user has permission', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '1' },
      loading: false,
      hasPermission: () => true,
    } as any)

    render(
      <MemoryRouter>
        <ProtectedRoute permission="dashboard:read">
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    )

    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })

  it('redirects to / when user lacks permission', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '1' },
      loading: false,
      hasPermission: () => false,
    } as any)

    render(
      <MemoryRouter>
        <ProtectedRoute permission="admin:access">
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    )

    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('redirects to /login when user is not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: false,
      hasPermission: () => false,
    } as any)

    render(
      <MemoryRouter>
        <ProtectedRoute permission="dashboard:read">
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    )

    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('renders nothing while loading', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: true,
      hasPermission: () => false,
    } as any)

    const { container } = render(
      <MemoryRouter>
        <ProtectedRoute permission="dashboard:read">
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>
    )

    expect(container.innerHTML).toBe('')
  })
})
