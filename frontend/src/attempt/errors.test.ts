import { describe, expect, it } from 'vitest'
import { ATTEMPT_MESSAGES, classifySubmitError } from './errors'

describe('T-05 API-1 错误白名单', () => {
  it('401/403', () => {
    expect(classifySubmitError(401, '未登录').action).toBe('unauthorized')
    const forbidden = classifySubmitError(403, '无权限')
    expect(forbidden.action).toBe('restore-answer')
    expect(forbidden.rebuildDraftFirst).toBe(true)
    expect(forbidden.clearEnvelope).toBe(true)
  })

  it('404 E03/E14 保留答案：先重建再清信封', () => {
    const plan = classifySubmitError(404, ATTEMPT_MESSAGES.notAccessible)
    expect(plan.action).toBe('restore-answer')
    expect(plan.clearDraft).toBe(false)
    expect(plan.clearEnvelope).toBe(true)
    expect(plan.rebuildDraftFirst).toBe(true)
  })

  it('E04 清答案/标记/信封', () => {
    const plan = classifySubmitError(400, ATTEMPT_MESSAGES.contentUpdated)
    expect(plan.action).toBe('reload-clear')
    expect(plan.clearDraft).toBe(true)
    expect(plan.clearEnvelope).toBe(true)
  })

  it('E05/E07/422 保留答案', () => {
    for (const [status, msg] of [
      [400, ATTEMPT_MESSAGES.invalidIdempotencyKey],
      [400, `${ATTEMPT_MESSAGES.invalidContentPrefix}题目与本卷当前版本不一致`],
      [422, '请求参数校验失败'],
    ] as const) {
      const plan = classifySubmitError(status, msg)
      expect(plan.action).toBe('restore-answer')
      expect(plan.rebuildDraftFirst).toBe(true)
      expect(plan.clearDraft).toBe(false)
    }
  })

  it('E08 转终态，E09 查询状态', () => {
    expect(
      classifySubmitError(400, ATTEMPT_MESSAGES.alreadySubmitted).action,
    ).toBe('terminal-e08')
    expect(
      classifySubmitError(400, ATTEMPT_MESSAGES.idempotencyConflict).action,
    ).toBe('check-status')
  })

  it('500 与未知 400/4xx 一律保留信封，不放开编辑、不自动新键', () => {
    for (const [status, msg] of [
      [500, '服务器内部错误'],
      [400, '未知文案'],
      [418, 'teapot'],
    ] as const) {
      const plan = classifySubmitError(status, msg)
      expect(plan.action).toBe('unknown-retry')
      expect(plan.clearEnvelope).toBe(false)
      expect(plan.clearDraft).toBe(false)
      expect(plan.message).toContain('结果未确认')
      expect(plan.message).not.toContain('提交失败，请重新作答')
    }
  })

  it('E07 只按固定前缀识别，不靠 includes 猜测', () => {
    expect(
      classifySubmitError(400, `前缀不对${ATTEMPT_MESSAGES.invalidContentPrefix}`)
        .action,
    ).toBe('unknown-retry')
  })
})
