import { render, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MONITOR_POLL_INTERVAL_MS, useMonitorPolling } from './useMonitorPolling'

function Probe({ fetcher }: { fetcher: (signal: AbortSignal) => Promise<string> }) {
  const { data } = useMonitorPolling(fetcher)
  return <span>{data ?? 'loading'}</span>
}

describe('useMonitorPolling', () => {
  it('15 秒轮询、hidden 停止、visible 立即查询', async () => {
    const fetcher = vi.fn(async () => 'ok')
    const intervalSpy = vi.spyOn(window, 'setInterval')
    render(<Probe fetcher={fetcher} />)
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))

    const call = intervalSpy.mock.calls.find(
      (entry) => entry[1] === MONITOR_POLL_INTERVAL_MS,
    )
    expect(call).toBeDefined()
    const tick = call?.[0] as () => void

    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    tick()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(fetcher).toHaveBeenCalledTimes(1)

    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
    document.dispatchEvent(new Event('visibilitychange'))
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
    intervalSpy.mockRestore()
  })

  it('卸载时取消进行中的请求', async () => {
    let received: AbortSignal | null = null
    const fetcher = vi.fn(
      (signal: AbortSignal) =>
        new Promise<string>((resolve) => {
          received = signal
          setTimeout(() => resolve('done'), 10)
        }),
    )
    const view = render(<Probe fetcher={fetcher} />)
    await waitFor(() => expect(fetcher).toHaveBeenCalled())
    view.unmount()
    expect((received as AbortSignal | null)?.aborted).toBe(true)
  })
})
