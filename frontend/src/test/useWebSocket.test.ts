import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useWebSocket } from '../hooks/useWebSocket'

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    currentFarm: null
  })
}))

describe('useWebSocket', () => {
  let mockWs: any
  let wsInstances: any[]

  beforeEach(() => {
    wsInstances = []
    mockWs = {
      onopen: null,
      onclose: null,
      onmessage: null,
      close: vi.fn(),
    }
    globalThis.WebSocket = vi.fn().mockImplementation(() => {
      const ws = { ...mockWs }
      wsInstances.push(ws)
      setTimeout(() => { if (ws.onopen) ws.onopen() }, 0)
      return ws
    }) as any
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('connects and calls handlers on message', async () => {
    const handler = vi.fn()
    renderHook(() => useWebSocket({ detection: handler }))

    await act(() => vi.advanceTimersByTimeAsync(10))

    const ws = wsInstances[0]
    expect(ws).toBeDefined()

    act(() => { ws.onmessage({ data: JSON.stringify({ type: 'detection', camera_id: 'cam1' }) }) })
    expect(handler).toHaveBeenCalledWith({ type: 'detection', camera_id: 'cam1' })
  })

  it('reconnects with exponential backoff on close', async () => {
    renderHook(() => useWebSocket())

    await act(() => vi.advanceTimersByTimeAsync(10))

    const setTimeoutSpy = vi.spyOn(window, 'setTimeout')
    const ws = wsInstances[0]

    act(() => { ws.onclose() })

    expect(setTimeoutSpy).toHaveBeenCalled()
    const firstDelay = setTimeoutSpy.mock.calls[0][1]
    expect(firstDelay).toBeGreaterThanOrEqual(500)
    expect(firstDelay).toBeLessThanOrEqual(1500)
  })

  it('resets attempt counter on reconnect', async () => {
    renderHook(() => useWebSocket())

    await act(() => vi.advanceTimersByTimeAsync(10))

    const ws = wsInstances[0]

    act(() => { ws.onclose() })
    await act(() => vi.advanceTimersByTimeAsync(3000))

    expect(globalThis.WebSocket).toHaveBeenCalledTimes(2)

    const ws2 = wsInstances[1]
    act(() => { ws2.onopen?.() })
    act(() => { ws2.onclose() })
    await act(() => vi.advanceTimersByTimeAsync(3000))

    expect(globalThis.WebSocket).toHaveBeenCalledTimes(3)
  })
})
