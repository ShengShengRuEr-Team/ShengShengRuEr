import { describe, expect, it } from 'vitest'
import {
  ADMIN_PERMISSIONS,
  EVENT_TYPE_LABELS,
  LOGIN_FAILURE_LABELS,
  LOG_RESULT_LABELS,
  PERM_LOG_READ,
  ROLE_LABELS,
} from './adminConstants'
import { labelOf } from '../utils/adminLabels'

describe('生成的管理端常量', () => {
  it('权限码固定 21 个且包含日志读取码', () => {
    expect(ADMIN_PERMISSIONS).toHaveLength(21)
    expect(ADMIN_PERMISSIONS).toContain(PERM_LOG_READ)
    expect(PERM_LOG_READ).toBe('admin:log:read')
  })

  it('标签与后端枚举一致', () => {
    expect(EVENT_TYPE_LABELS.LOGIN_SUCCEEDED).toBe('登录成功')
    expect(LOG_RESULT_LABELS.SUCCESS).toBe('成功')
    expect(LOGIN_FAILURE_LABELS.BAD_PASSWORD).toBe('密码错误')
    expect(ROLE_LABELS.admin).toBe('管理员')
  })

  it('未知值保留原值并显示未知（原值）', () => {
    expect(labelOf(EVENT_TYPE_LABELS, 'NEW_EVENT')).toBe('未知（NEW_EVENT）')
    expect(labelOf(EVENT_TYPE_LABELS, null)).toBe('')
  })
})
