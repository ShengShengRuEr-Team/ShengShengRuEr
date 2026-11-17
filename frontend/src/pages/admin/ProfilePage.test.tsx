import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../../auth/AuthContext'
import type { AuthContextValue } from '../../auth/AuthContext'
import { ApiError } from '../../api/api-error'
import type { UserDto } from '../../api/admin/types'
import ProfilePage from './ProfilePage'

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
  changeMyPassword,
  fetchMe,
  updateMyNickname,
} from '../../api/admin/users'

const mockedMe = vi.mocked(fetchMe)
const mockedNickname = vi.mocked(updateMyNickname)
const mockedPassword = vi.mocked(changeMyPassword)

const ME: UserDto = {
  id: 1,
  username: 'admin',
  nickname: '管理员',
  role: 'admin',
  status: 'active',
  created_at: '2026-11-01T10:00:00+08:00',
  updated_at: '2026-11-01T10:00:00+08:00',
}

function authValue(clearLocalSession: () => void): AuthContextValue {
  const permissions = [
    'admin:self:read',
    'admin:self:update',
    'admin:self:password',
  ]
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

function renderPage(clearLocalSession = vi.fn()) {
  render(
    <AuthContext.Provider value={authValue(clearLocalSession)}>
      <MemoryRouter initialEntries={['/admin/profile']}>
        <Routes>
          <Route path="/admin/profile" element={<ProfilePage />} />
          <Route path="/login" element={<div>登录页</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  )
  return clearLocalSession
}

describe('个人中心页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedMe.mockResolvedValue(ME)
  })

  it('展示本人信息', async () => {
    renderPage()
    expect(await screen.findByText('用户名：admin')).toBeInTheDocument()
    expect(screen.getByText('角色：管理员')).toBeInTheDocument()
  })

  it('修改昵称调用接口', async () => {
    mockedNickname.mockResolvedValue({ ...ME, nickname: '新昵称' })
    renderPage()
    await screen.findByText('用户名：admin')

    fireEvent.change(screen.getByLabelText('昵称'), {
      target: { value: '新昵称' },
    })
    fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => {
      expect(mockedNickname).toHaveBeenCalledWith('新昵称')
    })
  })

  it('改密成功清本地认证并跳登录，不重发请求', async () => {
    mockedPassword.mockResolvedValue({ changed: true, reauth_required: true })
    const clearLocalSession = renderPage()
    await screen.findByText('用户名：admin')

    fireEvent.change(screen.getByLabelText('旧密码'), {
      target: { value: 'admin123' },
    })
    fireEvent.change(screen.getByLabelText('新密码'), {
      target: { value: 'abcd123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: /修改密码/ }))

    await waitFor(() => {
      expect(mockedPassword).toHaveBeenCalledWith({
        old_password: 'admin123',
        new_password: 'abcd123456',
      })
    })
    expect(clearLocalSession).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('登录页')).toBeInTheDocument()
    expect(mockedPassword).toHaveBeenCalledTimes(1)
  })

  it('旧密码错误 400 显示后端文案且停留在本页', async () => {
    mockedPassword.mockRejectedValueOnce(new ApiError('旧密码不正确', 400, 400))
    const clearLocalSession = renderPage()
    await screen.findByText('用户名：admin')

    fireEvent.change(screen.getByLabelText('旧密码'), {
      target: { value: 'wrong' },
    })
    fireEvent.change(screen.getByLabelText('新密码'), {
      target: { value: 'abcd123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: /修改密码/ }))

    expect(await screen.findByText('旧密码不正确')).toBeInTheDocument()
    expect(clearLocalSession).not.toHaveBeenCalled()
  })
})
