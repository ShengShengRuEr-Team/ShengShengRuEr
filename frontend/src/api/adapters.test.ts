import { describe, expect, it } from 'vitest'
import { toAttemptStatusResult, toAttemptSubmitSuccess } from './adapters'
import type { AttemptStatusDto } from './types'

function statusDto(overrides: Partial<AttemptStatusDto> = {}): AttemptStatusDto {
  return {
    exam_paper_id: 1,
    submitted: true,
    attempt_count: 1,
    latest_attempt: {
      attempt_code: '0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40',
      exam_paper_id: 1,
      submitted_at: '2026-11-14T06:30:00Z',
      question_count: 4,
      correct_count: 3,
      correct_rate: 75,
      practice_score: {
        available: true,
        value: 30,
        max: 40,
        label: '练习估分，非官方成绩',
        reason: null,
      },
    },
    ...overrides,
  }
}

describe('T-10 API-3 分层解析', () => {
  it('true + 完整汇总 → submitted，字段 camelCase', () => {
    const result = toAttemptStatusResult(statusDto(), 1)
    expect(result.kind).toBe('submitted')
    if (result.kind === 'submitted') {
      expect(result.status.latestAttempt?.attemptCode).toBe(
        '0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40',
      )
      expect(result.status.latestAttempt?.practiceScore.value).toBe(30)
      expect(result.status.attemptCount).toBe(1)
    }
  })

  it('true + latest=null → submitted-summary-unavailable（确定已提交）', () => {
    const result = toAttemptStatusResult(
      statusDto({ latest_attempt: null }),
      1,
    )
    expect(result).toEqual({
      kind: 'submitted-summary-unavailable',
      examPaperId: 1,
      attemptCount: 1,
      submittedAt: null,
    })
  })

  it('true + 坏估分 → 汇总不可用，但保留真实提交时间', () => {
    const data = statusDto()
    // 非法 practice_score 结构
    data.latest_attempt = {
      ...data.latest_attempt!,
      practice_score: { available: 'yes' } as never,
    }
    const result = toAttemptStatusResult(data, 1)
    expect(result.kind).toBe('submitted-summary-unavailable')
    if (result.kind === 'submitted-summary-unavailable') {
      expect(result.submittedAt).toBe('2026-11-14T06:30:00Z')
    }
  })

  it('false + count=0 + latest=null → not-submitted', () => {
    const result = toAttemptStatusResult(
      statusDto({
        submitted: false,
        attempt_count: 0,
        latest_attempt: null,
      }),
      1,
    )
    expect(result.kind).toBe('not-submitted')
  })

  it('N02 矛盾响应 → status-conflict，不映射为可编辑', () => {
    const cases: Array<[Partial<AttemptStatusDto>, string]> = [
      [{ submitted: false, attempt_count: 0, latest_attempt: statusDto().latest_attempt }, 'false-with-latest'],
      [{ submitted: false, attempt_count: 2, latest_attempt: null }, 'false-with-count'],
      [{ submitted: true, attempt_count: 0, latest_attempt: null }, 'true-without-count'],
    ]
    for (const [overrides, reason] of cases) {
      const result = toAttemptStatusResult(statusDto(overrides), 1)
      expect(result.kind).toBe('status-conflict')
      if (result.kind === 'status-conflict') {
        expect(result.reason).toBe(reason)
      }
    }
  })

  it('嵌套试卷 ID 不一致 → paper-id-mismatch；缺失 → malformed', () => {
    const data = statusDto()
    data.latest_attempt = { ...data.latest_attempt!, exam_paper_id: 2 }
    const mismatch = toAttemptStatusResult(data, 1)
    expect(mismatch.kind).toBe('status-conflict')
    if (mismatch.kind === 'status-conflict') {
      expect(mismatch.reason).toBe('paper-id-mismatch')
    }

    const missing = statusDto()
    delete (missing.latest_attempt as unknown as Record<string, unknown>)
      .exam_paper_id
    expect(toAttemptStatusResult(missing, 1).kind).toBe(
      'status-unavailable',
    )
  })

  it('结构/类型非法 → status-unavailable/malformed', () => {
    const cases: unknown[] = [
      null,
      {},
      statusDto({ exam_paper_id: 2 }),
      { ...statusDto(), submitted: 'true' },
      { ...statusDto(), attempt_count: -1 },
      { ...statusDto(), latest_attempt: [] as never },
    ]
    for (const data of cases) {
      const result = toAttemptStatusResult(data, 1)
      expect(result.kind).toBe('status-unavailable')
      if (result.kind === 'status-unavailable') {
        expect(result.reason).toBe('malformed')
      }
    }
  })
})

describe('API-1 成功解析', () => {
  it('完整汇总 → submitted', () => {
    const data = statusDto().latest_attempt!
    const result = toAttemptSubmitSuccess(data, 1)
    expect(result.kind).toBe('submitted')
  })

  it('坏汇总或试卷 ID 不符 → submitted-without-summary（视为已提交）', () => {
    const data = { ...statusDto().latest_attempt!, correct_count: 'x' }
    expect(toAttemptSubmitSuccess(data, 1)).toEqual({
      kind: 'submitted-without-summary',
      examPaperId: 1,
    })
    expect(toAttemptSubmitSuccess(statusDto().latest_attempt, 2)).toEqual({
      kind: 'submitted-without-summary',
      examPaperId: 2,
    })
    expect(toAttemptSubmitSuccess(undefined, 1)).toEqual({
      kind: 'submitted-without-summary',
      examPaperId: 1,
    })
  })
})
