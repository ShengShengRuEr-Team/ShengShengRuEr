import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/api-error'

export const MONITOR_POLL_INTERVAL_MS = 15_000

export function useMonitorPolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  interval = MONITOR_POLL_INTERVAL_MS,
) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const sequence = useRef(0)
  const inFlight = useRef(false)
  const controller = useRef<AbortController | null>(null)

  const load = useCallback(
    async (silent = false) => {
      if (inFlight.current) {
        return
      }
      inFlight.current = true
      if (!silent) {
        setLoading(true)
      }
      const id = ++sequence.current
      controller.current?.abort()
      const next = new AbortController()
      controller.current = next
      try {
        const payload = await fetcher(next.signal)
        if (id === sequence.current) {
          setData(payload)
          setError(null)
        }
      } catch (cause) {
        if (id === sequence.current && !next.signal.aborted) {
          setError(cause instanceof ApiError ? cause.message : '加载监控数据失败')
        }
      } finally {
        if (id === sequence.current) {
          inFlight.current = false
          setLoading(false)
        }
      }
    },
    [fetcher],
  )

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => {
      if (!document.hidden) {
        void load(true)
      }
    }, interval)
    const onVisible = () => {
      if (!document.hidden) {
        void load(true)
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      controller.current?.abort()
    }
  }, [load, interval])

  return { data, error, loading, reload: () => void load() }
}
