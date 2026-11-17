import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/api-error'
import type { JobOverviewDto, JobRunDto } from '../../api/admin/types'
import MonitorJobsPage, { POLL_INTERVAL_MS } from './MonitorJobsPage'

vi.mock('../../api/admin/jobs', () => ({
  JOB_ID: 'admin.retention_cleanup',
  fetchJobOverview: vi.fn(),
  fetchJobRuns: vi.fn(),
  setJobEnabled: vi.fn(),
  triggerJob: vi.fn(),
}))

import {
  fetchJobOverview,
  fetchJobRuns,
  setJobEnabled,
  triggerJob,
} from '../../api/admin/jobs'

const mockedOverview = vi.mocked(fetchJobOverview)
const mockedRuns = vi.mocked(fetchJobRuns)
const mockedSetEnabled = vi.mocked(setJobEnabled)
const mockedTrigger = vi.mocked(triggerJob)

const OVERVIEW: JobOverviewDto = {
  job: {
    job_id: 'admin.retention_cleanup',
    enabled: true,
    timezone: 'Asia/Shanghai',
    next_scheduled_at: '2026-11-18T03:10:00+08:00',
    last_scheduled_slot: '2026-11-17',
    last_run_id: null,
    active_run_id: null,
    missed_slots: 0,
    updated_at: '2026-11-17T10:00:00+08:00',
  },
  scheduler_health: 'ok',
  instances: [
    {
      instance_id: '11111111-1111-1111-1111-111111111111',
      booted_at: '2026-11-17T09:00:00+08:00',
      heartbeat_at: '2026-11-17T10:00:10+08:00',
      last_error_code: null,
      state: 'idle',
      version: 1,
    },
  ],
}

const RUN: JobRunDto = {
  id: '22222222-2222-2222-2222-222222222222',
  job_id: 'admin.retention_cleanup',
  trigger: 'scheduled',
  slot_key: '2026-11-17',
  actor_id: null,
  state: 'PARTIAL',
  queued_at: '2026-11-17T03:10:00+08:00',
  started_at: '2026-11-17T03:10:01+08:00',
  finished_at: '2026-11-17T03:10:30+08:00',
  heartbeat_at: '2026-11-17T03:10:30+08:00',
  attempt_count: 1,
  retry_at: null,
  retry_pending: false,
  counts: { admin_login_events: 3 },
  counts_complete: false,
  error_code: null,
  created_at: '2026-11-17T03:10:00+08:00',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <MonitorJobsPage />
    </MemoryRouter>,
  )
}

describe('任务监控页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedOverview.mockResolvedValue(OVERVIEW)
    mockedRuns.mockResolvedValue({
      items: [RUN],
      total: 1,
      page: 1,
      page_size: 20,
    })
  })

  it('展示任务配置、心跳与执行记录', async () => {
    renderPage()

    expect(await screen.findByText('admin.retention_cleanup')).toBeInTheDocument()
    expect(screen.getByText('正常')).toBeInTheDocument()
    expect(screen.getByText('Asia/Shanghai')).toBeInTheDocument()
    expect(screen.getByText('部分完成')).toBeInTheDocument()
    expect(screen.getByText('否（结果未确认）')).toBeInTheDocument()
  })

  it('立即执行需要理由并调用接口', async () => {
    mockedTrigger.mockResolvedValue({
      run_id: '33333333-3333-3333-3333-333333333333',
      state: 'QUEUED',
    })
    renderPage()
    await screen.findByText('admin.retention_cleanup')

    fireEvent.click(screen.getByRole('button', { name: /立即执行/ }))
    fireEvent.change(screen.getByLabelText('操作理由'), {
      target: { value: '手动补跑' },
    })
    fireEvent.click(screen.getByRole('button', { name: /排\s*队/ }))

    await waitFor(() => {
      expect(mockedTrigger).toHaveBeenCalledWith('手动补跑')
    })
  })

  it('暂停任务需要理由并调用接口', async () => {
    mockedSetEnabled.mockResolvedValue({
      job_id: 'admin.retention_cleanup',
      enabled: false,
      changed: true,
    })
    renderPage()
    await screen.findByText('admin.retention_cleanup')

    fireEvent.click(screen.getByRole('switch'))
    fireEvent.change(screen.getByLabelText('操作理由'), {
      target: { value: '维护窗口' },
    })
    fireEvent.click(screen.getByRole('button', { name: /确\s*认/ }))

    await waitFor(() => {
      expect(mockedSetEnabled).toHaveBeenCalledWith(false, '维护窗口')
    })
  })

  it('轮询间隔 15 秒且 hidden 时不刷新', async () => {
    const intervalSpy = vi.spyOn(window, 'setInterval')
    renderPage()
    await screen.findByText('admin.retention_cleanup')

    const intervalCall = intervalSpy.mock.calls.find(
      (call) => call[1] === POLL_INTERVAL_MS,
    )
    expect(intervalCall).toBeDefined()
    const tick = intervalCall?.[0] as () => void

    const overviewCalls = mockedOverview.mock.calls.length
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => true,
    })
    tick()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(mockedOverview.mock.calls.length).toBe(overviewCalls)

    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => false,
    })
    tick()
    await waitFor(() => {
      expect(mockedOverview.mock.calls.length).toBeGreaterThan(overviewCalls)
    })
    intervalSpy.mockRestore()
  })

  it('加载失败显示错误与重试', async () => {
    mockedOverview.mockRejectedValueOnce(new ApiError('加载任务配置失败', 500, 500))
    renderPage()

    expect(await screen.findByText('加载任务配置失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  })
})
