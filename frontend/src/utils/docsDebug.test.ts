import { describe, expect, it } from 'vitest'
import {
  isAllowedDebugRequest,
  normalizeDebugPath,
  templateMatches,
} from './docsDebug'

const ENTRIES = [
  { method: 'GET', path_template: '/api/v1/admin/users', permission: 'admin:user:read' },
  {
    method: 'GET',
    path_template: '/api/v1/admin/users/{user_id}',
    permission: 'admin:user:read',
  },
]

describe('templateMatches', () => {
  it('精确匹配与单段参数匹配', () => {
    expect(templateMatches('/api/v1/admin/users', '/api/v1/admin/users')).toBe(true)
    expect(templateMatches('/api/v1/admin/users/{user_id}', '/api/v1/admin/users/12')).toBe(
      true,
    )
    expect(templateMatches('/api/v1/admin/users/{user_id}', '/api/v1/admin/users/12/x')).toBe(
      false,
    )
    expect(templateMatches('/api/v1/admin/users', '/api/v1/admin/users/12')).toBe(false)
  })
})

describe('normalizeDebugPath', () => {
  it('拒绝歧义与编码绕过', () => {
    expect(normalizeDebugPath('/api/v1/admin/users')).toBe('/api/v1/admin/users')
    expect(normalizeDebugPath('/api/v1/admin/users/')).toBeNull()
    expect(normalizeDebugPath('/api/v1//admin/users')).toBeNull()
    expect(normalizeDebugPath('/api/v1/admin/users%2F1')).toBeNull()
    expect(normalizeDebugPath('/api/v1/admin/users%252F1')).toBeNull()
    expect(normalizeDebugPath('/api/v1/admin\\users')).toBeNull()
    expect(normalizeDebugPath('relative')).toBeNull()
  })
})

describe('isAllowedDebugRequest', () => {
  const origin = 'http://127.0.0.1:8000'

  it('只放行白名单内同源 GET', () => {
    expect(
      isAllowedDebugRequest(ENTRIES, 'GET', `${origin}/api/v1/admin/users/7`, origin),
    ).toBe(true)
    expect(
      isAllowedDebugRequest(ENTRIES, 'POST', `${origin}/api/v1/admin/users`, origin),
    ).toBe(false)
    expect(
      isAllowedDebugRequest(
        ENTRIES,
        'GET',
        `${origin}/api/v1/admin/exports/users`,
        origin,
      ),
    ).toBe(false)
    expect(
      isAllowedDebugRequest(ENTRIES, 'GET', 'http://evil.example/api/v1/admin/users', origin),
    ).toBe(false)
    expect(
      isAllowedDebugRequest(ENTRIES, 'GET', `${origin}/api/v1/admin/users/`, origin),
    ).toBe(false)
  })
})
