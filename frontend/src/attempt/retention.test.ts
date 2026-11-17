import { describe, expect, it } from 'vitest'
import { canAutoRetry, KEY_RETENTION_POLICY, retentionNotice } from './retention'
import type { KeyRetentionPolicy } from './types'

const NOW = Date.parse('2026-11-14T00:00:00.000Z')
const DAY = 24 * 60 * 60 * 1000

function iso(daysAgo: number): string {
  return new Date(NOW - daysAgo * DAY).toISOString()
}

describe('T-11 保留期与自动重试', () => {
  it('流程 P-03 未确认：固定 unknown，禁止自动、手动需强警告', () => {
    expect(KEY_RETENTION_POLICY).toEqual({ kind: 'unknown' })
    const decision = canAutoRetry(iso(1), KEY_RETENTION_POLICY, NOW)
    expect(decision.autoRetry).toBe(false)
    expect(decision.manualRetry).toBe(true)
    expect(decision.warning).toBe('strong')
    expect(decision.reason).toBe('unknown-policy')
  })

  it('permanent：合法时间允许自动', () => {
    const policy: KeyRetentionPolicy = { kind: 'permanent' }
    expect(canAutoRetry(iso(100), policy, NOW).autoRetry).toBe(true)
  })

  it('days：年龄 < days-1 才允许自动（含边界）', () => {
    const policy: KeyRetentionPolicy = { kind: 'days', days: 7 }
    expect(canAutoRetry(iso(5), policy, NOW).autoRetry).toBe(true)
    // 6 天 = days-1，边界按「>=」关闭
    expect(canAutoRetry(iso(6), policy, NOW).autoRetry).toBe(false)
    expect(canAutoRetry(iso(6), policy, NOW).warning).toBe('strong')
    expect(canAutoRetry(iso(6), policy, NOW).reason).toBe('expired')
  })

  it('requestedAt 非法/未来时间：禁止自动，手动强警告', () => {
    const decision = canAutoRetry('not-a-time', KEY_RETENTION_POLICY, NOW)
    expect(decision.autoRetry).toBe(false)
    expect(decision.reason).toBe('invalid-time')
    const future = new Date(NOW + DAY).toISOString()
    expect(canAutoRetry(future, { kind: 'permanent' }, NOW).autoRetry).toBe(false)
  })

  it('提示文案不暴露内部策略常量', () => {
    const notice = retentionNotice(canAutoRetry(iso(1), KEY_RETENTION_POLICY, NOW))
    expect(notice).toContain('自动重试已关闭')
    expect(notice).not.toContain('KEY_RETENTION_POLICY')
    expect(notice).not.toContain('unknown')
  })
})
