import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MonitorPage from './MonitorPage'
import MonitorCachePage from './MonitorCachePage'

vi.mock('../../api/admin/monitoring', () => ({
  fetchDatabase: vi.fn(),
  fetchServer: vi.fn(),
  fetchTransport: vi.fn(),
  fetchOauth: vi.fn(),
  fetchCache: vi.fn(),
  fetchCacheEntries: vi.fn(),
  clearCache: vi.fn(),
}))

import {
  clearCache,
  fetchCache,
  fetchCacheEntries,
  fetchDatabase,
  fetchOauth,
} from '../../api/admin/monitoring'

const metric = (status: string, value: string | number | boolean | null = 1) => ({
  value,
  unit: 'count',
  source: 'test',
  scope: 'instance',
  status,
  reason: status === 'ok' ? null : 'r',
  severity: 'normal',
  observed_at: '2026-11-17T10:00:00+08:00',
  last_success_at: null,
})

describe('监控页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchDatabase).mockResolvedValue({
      instance_id: 'i-1',
      booted_at: '2026-11-17T09:00:00+08:00',
      server_time: '2026-11-17T10:00:00+08:00',
      sampling: 'interval_15s',
      metrics: {
        'database.connection_available': metric('ok', true),
        'database.pool_size': metric('not_applicable', null),
        'database.database_size_bytes': metric('stale', null),
        'database.active_connections': metric('unknown', null),
        'database.total_connections': metric('not_configured', null),
      },
    })
    vi.mocked(fetchOauth).mockResolvedValue({
      status: 'not_configured',
      enabled: false,
      reason: 'oauth_server_not_deployed',
      login_mode: 'jwt_bearer',
    })
  })

  it('状态用文字呈现且覆盖 unknown/stale/not_configured/not_applicable', async () => {
    render(
      <MemoryRouter>
        <MonitorPage kind="database" />
      </MemoryRouter>,
    )
    expect(await screen.findByText('database.connection_available')).toBeInTheDocument()
    expect(await screen.findByText('数据过期')).toBeInTheDocument()
    expect(screen.getByText('未知')).toBeInTheDocument()
    expect(screen.getByText('未启用/未配置')).toBeInTheDocument()
    expect(screen.getByText('不适用')).toBeInTheDocument()
  })

  it('OAuth 页说明未启用与 JWT 现状', async () => {
    render(
      <MemoryRouter>
        <MonitorPage kind="oauth" />
      </MemoryRouter>,
    )
    expect(await screen.findByText(/未部署 OAuth Server/)).toBeInTheDocument()
    expect(screen.getByText('jwt_bearer')).toBeInTheDocument()
  })

  it('缓存页清理需理由并提交实例与域', async () => {
    vi.mocked(fetchCache).mockResolvedValue({
      domain: 'admin_dashboard_summary',
      instance_id: 'i-1',
      enabled: true,
      entries: 0,
      ttl_seconds: 15,
      hits: 1,
      misses: 2,
      redis: { status: 'not_configured' },
    })
    vi.mocked(fetchCacheEntries).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    })
    vi.mocked(clearCache).mockResolvedValue({ deleted_count: 0 })

    render(
      <MemoryRouter>
        <MonitorCachePage />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: '清理缓存' }))
    fireEvent.change(await screen.findByLabelText('清理理由'), {
      target: { value: '维护' },
    })
    fireEvent.click(screen.getByRole('button', { name: /确认清理/ }))

    await waitFor(() => {
      expect(clearCache).toHaveBeenCalledWith({
        domain: 'admin_dashboard_summary',
        expected_instance_id: 'i-1',
        reason: '维护',
      })
    })
  })
})
