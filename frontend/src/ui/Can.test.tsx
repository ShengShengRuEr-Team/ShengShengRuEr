import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../auth/AuthContext'
import type { AuthContextValue } from '../auth/AuthContext'
import Can from './Can'
import RequirePermission from '../router/RequirePermission'

function authValue(permissions: string[]): AuthContextValue {
  return {
    status: 'authenticated',
    token: 'token',
    user: null,
    roles: ['admin'],
    permissions,
    isAdmin: true,
    login: vi.fn(),
    logout: vi.fn(),
    clearLocalSession: vi.fn(),
    retry: vi.fn(),
    hasRole: () => true,
    hasPermission: (code: string) => permissions.includes(code),
  }
}

function withAuth(permissions: string[], children: React.ReactNode) {
  return (
    <AuthContext.Provider value={authValue(permissions)}>
      {children}
    </AuthContext.Provider>
  )
}

describe('Can', () => {
  it('有权限渲染 children，无权限不渲染', () => {
    const { rerender } = render(
      withAuth(['admin:log:read'], <Can code="admin:log:read">导出</Can>),
    )
    expect(screen.getByText('导出')).toBeInTheDocument()

    rerender(withAuth([], <Can code="admin:log:read">导出</Can>))
    expect(screen.queryByText('导出')).toBeNull()
  })
})

describe('RequirePermission', () => {
  it('无权限跳 403 页', () => {
    render(
      withAuth(
        [],
        <MemoryRouter initialEntries={['/logs']}>
          <Routes>
            <Route
              path="/logs"
              element={
                <RequirePermission code="admin:log:read">
                  <div>日志页</div>
                </RequirePermission>
              }
            />
            <Route path="/403" element={<div>无权限页</div>} />
          </Routes>
        </MemoryRouter>,
      ),
    )
    expect(screen.getByText('无权限页')).toBeInTheDocument()
  })
})
