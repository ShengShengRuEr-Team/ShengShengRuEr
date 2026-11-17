import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../../auth/AuthContext'
import type { AuthContextValue } from '../../auth/AuthContext'
import { ApiError } from '../../api/api-error'
import type { LoginLogPageDto } from '../../api/admin/types'
import LoginLogsPage from './LoginLogsPage'

vi.mock('../../api/admin/logs', () => ({
  fetchLoginLogs: vi.fn(),
  fetchOperationLogs: vi.fn(),
  fetchLoginLog: vi.fn(),
  fetchOperationLog: vi.fn(),
}))

vi.mock('../../api/admin/exports', () => ({
  downloadCsv: vi.fn(),
  saveBlob: vi.fn(),
  parseFilename: vi.fn(),
  EXPORT_URLS: {},
}))

import { fetchLoginLogs } from '../../api/admin/logs'
import { downloadCsv, saveBlob } from '../../api/admin/exports'

const mockedFetch = vi.mocked(fetchLoginLogs)
const mockedDownload = vi.mocked(downloadCsv)
const mockedSave = vi.mocked(saveBlob)

const PAGE: LoginLogPageDto = {
  items: [
    {
      event_id: '11111111-1111-1111-1111-111111111111',
      request_id: '22222222-2222-2222-2222-222222222222',
      occurred_at: '2026-11-17T12:00:00+08:00',
      event_type: 'LOGIN_SUCCEEDED',
      username_attempted: 'admin',
      actor_user_id: 1,
      actor_name: 'admin',
      role_snapshot: 'admin',
      result: 'SUCCESS',
      reason_code: null,
      ip: '203.0.113.7',
      user_agent_summary: 'pytest',
      duration_ms: 10,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
}

function authValue(): AuthContextValue {
  const permissions = ['admin:log:read', 'admin:export:loginLogs']
  return {
    status: 'authenticated',
    token: 'token',
    user: null,
    roles: ['admin'],
    permissions,
    isAdmin: true,
    login: vi.fn(),
    logout: vi.fn(),
    retry: vi.fn(),
    hasRole: () => true,
    hasPermission: (code: string) => permissions.includes(code),
  }
}

function renderPage() {
  return render(
    <AuthContext.Provider value={authValue()}>
      <MemoryRouter>
        <LoginLogsPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('登录日志页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('加载列表并按标签展示', async () => {
    mockedFetch.mockResolvedValueOnce(PAGE)
    renderPage()

    expect(await screen.findByText('登录成功')).toBeInTheDocument()
    expect(screen.getAllByText('admin').length).toBeGreaterThan(0)
    expect(mockedFetch).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 20 }),
    )
  })

  it('加载失败显示错误与重试，不显示表格数据', async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError('加载失败', 500, 500))
    renderPage()

    expect(await screen.findByText('加载失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  })

  it('导出按钮调用下载并保存文件', async () => {
    mockedFetch.mockResolvedValue(PAGE)
    mockedDownload.mockResolvedValueOnce({
      blob: new Blob(['csv']),
      filename: 'admin-login-logs.csv',
    })
    renderPage()

    await screen.findByText('登录成功')
    fireEvent.click(screen.getByRole('button', { name: /导出 CSV/ }))

    await waitFor(() => {
      expect(mockedDownload).toHaveBeenCalledWith(
        'loginLogs',
        expect.objectContaining({ username: undefined }),
      )
    })
    expect(mockedSave).toHaveBeenCalledTimes(1)
  })

  it('导出失败不保存文件', async () => {
    mockedFetch.mockResolvedValue(PAGE)
    mockedDownload.mockRejectedValueOnce(new ApiError('导出行数超限', 400, 400))
    renderPage()

    await screen.findByText('登录成功')
    fireEvent.click(screen.getByRole('button', { name: /导出 CSV/ }))

    await waitFor(() => {
      expect(mockedDownload).toHaveBeenCalledTimes(1)
    })
    expect(mockedSave).not.toHaveBeenCalled()
  })
})
