import { request } from '../client'

const BASE = '/api/v1/admin/monitor'

export interface MetricDto {
  value: number | string | boolean | null
  unit: string
  source: string
  scope: string
  status: string
  reason: string | null
  severity: string
  observed_at: string | null
  last_success_at: string | null
}

export interface MetricSnapshot {
  instance_id: string
  booted_at: string
  server_time: string
  sampling: string
  metrics: Record<string, MetricDto>
  module3?: {
    status: string
    reason: string | null
    worker_liveness: string
    tasks: number | null
    workers: number | null
  }
}

export interface CacheOverview {
  domain: string
  instance_id: string
  enabled: boolean
  entries: number
  ttl_seconds: number
  hits: number
  misses: number
  redis: { status: string; reason?: string }
}

export function fetchDatabase(signal?: AbortSignal): Promise<MetricSnapshot> {
  return request<MetricSnapshot>({ method: 'GET', url: `${BASE}/database`, signal })
}

export function fetchServer(signal?: AbortSignal): Promise<MetricSnapshot> {
  return request<MetricSnapshot>({ method: 'GET', url: `${BASE}/server`, signal })
}

export function fetchCache(signal?: AbortSignal): Promise<CacheOverview> {
  return request<CacheOverview>({ method: 'GET', url: `${BASE}/cache`, signal })
}

export function fetchCacheEntries(signal?: AbortSignal): Promise<{
  items: Array<Record<string, unknown>>
  total: number
  page: number
  page_size: number
}> {
  return request({ method: 'GET', url: `${BASE}/cache/entries`, signal })
}

export function clearCache(payload: {
  domain: string
  expected_instance_id: string
  reason: string
}): Promise<{ deleted_count: number }> {
  return request({ method: 'POST', url: `${BASE}/cache/clear`, data: payload })
}

export function fetchTransport(signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request({ method: 'GET', url: `${BASE}/transport`, signal })
}

export function fetchOauth(signal?: AbortSignal): Promise<Record<string, unknown>> {
  return request({ method: 'GET', url: `${BASE}/oauth`, signal })
}
