import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/api-error'
import type { DashboardDto } from '../../api/admin/types'
import HomePage from './HomePage'

vi.mock('../../api/admin/dashboard', () => ({
  fetchDashboard: vi.fn(),
}))

import { fetchDashboard } from '../../api/admin/dashboard'

const mockedFetch = vi.mocked(fetchDashboard)

const DATA: DashboardDto = {
  as_of: '2026-11-17T14:10:00+08:00',
  window_start: '2026-11-11T00:00:00+08:00',
  window_end: '2026-11-17T14:10:00+08:00',
  timezone: 'Asia/Shanghai',
  cache: {
    enabled: true,
    status: 'hit',
    ttl_seconds: 15,
    cached_at: '2026-11-17T14:09:58+08:00',
    expires_at: '2026-11-17T14:10:13+08:00',
    age_seconds: 2,
  },
  cards: {
    paper_count: 7,
    awaiting_visibility_count: 1,
    failed_check_count: 2,
    active_student_count: 3,
    disabled_student_count: 4,
    successful_attempts_7d: 5,
  },
}

function renderPage() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  )
}

describe('管理端首页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染汇总卡片、采集时间与缓存状态', async () => {
    mockedFetch.mockResolvedValueOnce(DATA)
    renderPage()

    expect(await screen.findByText('试卷总数')).toBeInTheDocument()
    expect(screen.getByText('检查通过待确认')).toBeInTheDocument()
    expect(screen.getByText('近 7 天成功提交')).toBeInTheDocument()
    expect(screen.getByText(/采集时间（as_of）：2026-11-17T14:10:00\+08:00/)).toBeInTheDocument()
    expect(screen.getByText('缓存命中')).toBeInTheDocument()
    expect(screen.getByText(/缓存 TTL：15 秒/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /题库管理/ })).toBeInTheDocument()
  })

  it('加载失败显示错误与重试，不显示 0 卡片', async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError('加载首页汇总失败', 500, 500))
    renderPage()

    expect(await screen.findByText('加载首页汇总失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
    expect(screen.queryByText('试卷总数')).toBeNull()
  })

  it('刷新失败保留旧数据并标记可能已过期', async () => {
    mockedFetch.mockResolvedValueOnce(DATA).mockRejectedValueOnce(
      new ApiError('服务器内部错误', 500, 500),
    )
    renderPage()
    await screen.findByText('试卷总数')

    fireEvent.click(screen.getByRole('button', { name: /刷\s*新/ }))

    await waitFor(() => {
      expect(
        screen.getByText(/数据可能已过期（as_of: 2026-11-17T14:10:00\+08:00）/),
      ).toBeInTheDocument()
    })
    // 旧卡片保留，不显示 0 或错误页。
    expect(screen.getByText('试卷总数')).toBeInTheDocument()
    expect(mockedFetch).toHaveBeenCalledTimes(2)
  })

  it('缓存未启用时显示 not_configured 对应文案', async () => {
    mockedFetch.mockResolvedValueOnce({
      ...DATA,
      cache: {
        enabled: false,
        status: 'not_configured',
        ttl_seconds: 15,
        cached_at: null,
        expires_at: null,
        age_seconds: null,
      },
    })
    renderPage()

    expect(await screen.findByText('缓存未启用')).toBeInTheDocument()
  })
})
