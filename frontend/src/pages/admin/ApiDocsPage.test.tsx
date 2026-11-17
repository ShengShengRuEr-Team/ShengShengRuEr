import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../../auth/AuthContext'
import type { AuthContextValue } from '../../auth/AuthContext'
import { ApiError } from '../../api/api-error'
import { ACCESS_TOKEN_KEY } from '../../auth/storage'
import ApiDocsPage from './ApiDocsPage'

const { initMock } = vi.hoisted(() => ({
  initMock: vi.fn((_config: Record<string, unknown>) => ({})),
}))

vi.mock('swagger-ui-dist/swagger-ui-es-bundle.js', () => ({
  default: Object.assign(initMock, {
    presets: { apis: [] },
    plugins: {},
  }),
}))
vi.mock('swagger-ui-dist/swagger-ui.css', () => ({}))

vi.mock('../../api/admin/docs', () => ({
  fetchOpenapiSchema: vi.fn(),
}))

import { fetchOpenapiSchema } from '../../api/admin/docs'

const mockedFetch = vi.mocked(fetchOpenapiSchema)

const SCHEMA = {
  openapi: '3.1.0',
  info: { title: 'test', version: '1' },
  paths: { '/api/v1/admin/users': {} },
  'x-admin-debug-allowlist': [
    { method: 'GET', path_template: '/api/v1/admin/users', permission: 'admin:user:read' },
  ],
}

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
    hasPermission: (code) => permissions.includes(code),
  }
}

function renderPage(permissions = ['admin:docs:read']) {
  return render(
    <AuthContext.Provider value={authValue(permissions)}>
      <MemoryRouter>
        <ApiDocsPage />
      </MemoryRouter>
    </AuthContext.Provider>,
  )
}

describe('接口文档页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    mockedFetch.mockResolvedValue(SCHEMA)
  })

  it('加载受保护 schema 并初始化本地 Swagger UI', async () => {
    renderPage()

    await waitFor(() => expect(initMock).toHaveBeenCalledTimes(1))
    const config = initMock.mock.calls[0][0] as Record<string, unknown>
    // 用 spec 对象挂载，不给 Swagger 公开 URL。
    expect(config.spec).toBe(SCHEMA)
    expect(config.url).toBeUndefined()
    expect(config.persistAuthorization).toBe(false)
    expect(config.validatorUrl).toBeNull()
    expect(config.supportedSubmitMethods).toEqual([])
    expect(screen.queryByRole('switch', { name: '启用调试' })).toBeNull()
  })

  it('有 docs:debug 时可启用调试并只允许 GET', async () => {
    renderPage(['admin:docs:read', 'admin:docs:debug'])
    await waitFor(() => expect(initMock).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('switch', { name: '启用调试' }))
    await waitFor(() => expect(initMock).toHaveBeenCalledTimes(2))

    const config = initMock.mock.calls[1][0] as Record<string, unknown>
    expect(config.supportedSubmitMethods).toEqual(['get'])

    const interceptor = config.requestInterceptor as (
      request: Record<string, unknown>,
    ) => Record<string, unknown>
    window.localStorage.setItem(ACCESS_TOKEN_KEY, 'token-1')

    expect(() => interceptor({ method: 'POST', url: '/api/v1/admin/users' })).toThrow(
      '该请求不在调试白名单内',
    )
    const request = interceptor({
      method: 'GET',
      url: '/api/v1/admin/users',
      headers: {},
    })
    expect(request.headers).toMatchObject({
      Authorization: 'Bearer token-1',
      'X-Admin-Docs-Debug': '1',
    })
  })

  it('未启用调试时拦截器拒绝任何请求', async () => {
    renderPage(['admin:docs:read', 'admin:docs:debug'])
    await waitFor(() => expect(initMock).toHaveBeenCalledTimes(1))
    const config = initMock.mock.calls[0][0] as Record<string, unknown>
    const interceptor = config.requestInterceptor as (
      request: Record<string, unknown>,
    ) => unknown
    expect(() => interceptor({ method: 'GET', url: '/api/v1/admin/users' })).toThrow(
      '调试未启用',
    )
  })

  it('schema 加载失败显示错误与重试，不回退公开入口', async () => {
    mockedFetch.mockRejectedValueOnce(new ApiError('加载接口文档失败', 500, 500))
    renderPage()

    expect(await screen.findByText('加载接口文档失败')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
    expect(initMock).not.toHaveBeenCalled()
  })
})
