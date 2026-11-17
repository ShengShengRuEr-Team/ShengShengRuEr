import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from './AuthContext'
import { useAuth } from './useAuth'
import { ACCESS_TOKEN_KEY } from './storage'
import { ApiError } from '../api/api-error'
import { getInfo } from '../api/auth'

vi.mock('../api/auth', () => ({
  getInfo: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}))

const mockedGetInfo = vi.mocked(getInfo)

const PROFILE = {
  user: { user_id: 1, username: 'admin', nickname: '管理员' },
  roles: ['admin'],
  is_admin: true,
  permissions: ['admin:log:read'],
}

function Probe() {
  const { status, permissions, retry } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="permissions">{permissions.length}</span>
      <button onClick={() => void retry()}>重试</button>
    </div>
  )
}

function renderProvider() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
}

describe('AuthContext 恢复态', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.localStorage.setItem(ACCESS_TOKEN_KEY, 'token-1')
    vi.clearAllMocks()
  })

  it('getInfo 500 时保留 token、进入 recovery-error 且不授予权限', async () => {
    mockedGetInfo.mockRejectedValueOnce(new ApiError('服务器内部错误', 500, 500))

    renderProvider()

    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('recovery-error')
    })
    expect(screen.getByTestId('permissions')).toHaveTextContent('0')
    expect(window.localStorage.getItem(ACCESS_TOKEN_KEY)).toBe('token-1')
  })

  it('网络错误同样保留 token', async () => {
    mockedGetInfo.mockRejectedValueOnce(new ApiError('网络请求失败', -1, 0))

    renderProvider()

    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('recovery-error')
    })
    expect(window.localStorage.getItem(ACCESS_TOKEN_KEY)).toBe('token-1')
  })

  it('重试成功后恢复登录态并带权限', async () => {
    mockedGetInfo
      .mockRejectedValueOnce(new ApiError('服务器内部错误', 500, 500))
      .mockResolvedValueOnce(PROFILE)

    renderProvider()
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('recovery-error')
    })

    fireEvent.click(screen.getByRole('button', { name: '重试' }))

    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    })
    expect(screen.getByTestId('permissions')).toHaveTextContent('1')
  })

  it('只有 401 清 token 并回到 anonymous', async () => {
    mockedGetInfo.mockRejectedValueOnce(new ApiError('未登录', 401, 401))

    renderProvider()

    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    })
    expect(window.localStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull()
  })
})
