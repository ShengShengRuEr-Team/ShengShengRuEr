import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../../auth/AuthContext'
import type { AuthContextValue } from '../../auth/AuthContext'
import { ApiError } from '../../api/api-error'
import type { UserDto, UserPageDto } from '../../api/admin/types'
import UsersPage from './UsersPage'

vi.mock('../../api/admin/users', () => ({
  fetchUsers: vi.fn(),
  fetchUser: vi.fn(),
  createUser: vi.fn(),
  updateUserNickname: vi.fn(),
  changeUserStatus: vi.fn(),
  resetUserPassword: vi.fn(),
  fetchMe: vi.fn(),
  updateMyNickname: vi.fn(),
  changeMyPassword: vi.fn(),
}))

import {
  changeUserStatus,
  createUser,
  fetchUsers,
} from '../../api/admin/users'

const mockedFetch = vi.mocked(fetchUsers)
const mockedCreate = vi.mocked(createUser)
const mockedStatus = vi.mocked(changeUserStatus)

const USER: UserDto = {
  id: 2,
  username: 'student',
  nickname: '小明',
  role: 'student',
  status: 'active',
  created_at: '2026-11-01T10:00:00+08:00',
  updated_at: '2026-11-01T10:00:00+08:00',
}

const PAGE: UserPageDto = { items: [USER], total: 1, page: 1, page_size: 20 }

function authValue(permissions: string[], clearLocalSession = vi.fn()): AuthContextValue {
  return {
    status: 'authenticated',
    token: 'token',
    user: null,
    roles: ['admin'],
    permissions,
    isAdmin: true,
    login: vi.fn(),
    logout: vi.fn(),
    clearLocalSession,
    retry: vi.fn(),
    hasRole: () => true,
    hasPermission: (code: string) => permissions.includes(code),
  }
}

const ALL_PERMISSIONS = [
  'admin:user:read',
  'admin:user:create',
  'admin:user:update',
  'admin:user:status',
  'admin:user:resetPassword',
]

function renderPage(permissions = ALL_PERMISSIONS) {
  return render(
    <AuthContext.Provider value={authValue(permissions)}>
      <MemoryRouter initialEntries={['/admin/users']}>
        <UsersPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('用户管理页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedFetch.mockResolvedValue(PAGE)
  })

  it('渲染用户列表并显示角色/状态标签', async () => {
    renderPage()
    expect(await screen.findByText('student')).toBeInTheDocument()
    expect(screen.getByText('学生')).toBeInTheDocument()
    expect(screen.getByText('启用')).toBeInTheDocument()
  })

  it('无读权限时不发请求', () => {
    renderPage([])
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  it('加载失败显示错误与重试', async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError('加载用户失败', 500, 500))
    renderPage()
    expect(await screen.findByText('加载用户失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  })

  it('筛选写入 URL 并重新请求', async () => {
    renderPage()
    await screen.findByText('student')

    fireEvent.change(screen.getByPlaceholderText('用户名'), {
      target: { value: 'adm' },
    })

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenLastCalledWith(
        expect.objectContaining({ username: 'adm', page: 1 }),
      )
    })
  })

  it('无创建权限时不显示创建按钮', async () => {
    renderPage(['admin:user:read'])
    await screen.findByText('student')
    expect(screen.queryByRole('button', { name: /创建用户/ })).toBeNull()
  })

  it('创建用户：前端校验后提交', async () => {
    mockedCreate.mockResolvedValue({ ...USER, id: 9, username: 'newuser' })
    renderPage()
    await screen.findByText('student')

    fireEvent.click(screen.getByRole('button', { name: /创建用户/ }))

    const usernameInput = await screen.findByLabelText('用户名')
    fireEvent.change(usernameInput, { target: { value: 'ab' } })
    fireEvent.change(screen.getByLabelText('初始密码'), {
      target: { value: 'abcd123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^创\s*建$/ }))

    expect(await screen.findByText('用户名需为 3—50 位字母、数字或下划线')).toBeInTheDocument()
    expect(mockedCreate).not.toHaveBeenCalled()

    fireEvent.change(usernameInput, { target: { value: 'newuser' } })
    fireEvent.click(screen.getByRole('button', { name: /^创\s*建$/ }))

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalledWith(
        expect.objectContaining({ username: 'newuser', role: 'student' }),
      )
    })
  })

  it('启停同状态提示“状态未变化”且不当作错误', async () => {
    mockedStatus.mockResolvedValueOnce({
      id: USER.id,
      status: 'active',
      changed: false,
      revoked_session_count: 0,
    })
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})
    renderPage()
    await screen.findByText('student')

    fireEvent.click(screen.getByRole('button', { name: /启\s*停/ }))
    fireEvent.change(await screen.findByLabelText('操作理由'), {
      target: { value: '重复提交' },
    })
    fireEvent.click(screen.getByRole('button', { name: /提\s*交/ }))

    await waitFor(() => {
      expect(mockedStatus).toHaveBeenCalledWith(USER.id, {
        status: 'active',
        reason: '重复提交',
      })
    })
    expect(infoSpy).toHaveBeenCalledWith('状态未变化')
    infoSpy.mockRestore()
  })
})
