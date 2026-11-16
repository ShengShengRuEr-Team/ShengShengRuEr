import { describe, expect, it } from 'vitest'
import {
  draftMatchesQuestionSet,
  isUuidV4,
  parseDraft,
  parseEnvelope,
  parseSubmitted,
} from './codec'
import { makeDraft, makeEnvelope, makeSubmittedCache } from '../test/fixtures'

describe('T-01/T-02 草稿 codec 与校验', () => {
  it('解析合法草稿', () => {
    const result = parseDraft(JSON.stringify(makeDraft()), 7, 1)
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.value.answers).toEqual({ 11: 'A', 13: 'C' })
      expect(result.value.flaggedQuestionIds).toEqual([12])
      expect(result.value.currentPassageIndex).toBe(1)
    }
  })

  it('坏 JSON → bad-json', () => {
    expect(parseDraft('{', 7, 1)).toEqual({ ok: false, reason: 'bad-json' })
  })

  it('用户/试卷不匹配 → invalid-payload', () => {
    expect(parseDraft(JSON.stringify(makeDraft()), 8, 1)).toEqual({
      ok: false,
      reason: 'invalid-payload',
    })
    expect(parseDraft(JSON.stringify(makeDraft()), 7, 2)).toEqual({
      ok: false,
      reason: 'invalid-payload',
    })
  })

  it('非法字母/未知题目/非法标记 → invalid-payload', () => {
    const badLetter = makeDraft({ answers: { 11: 'E' as never } })
    expect(parseDraft(JSON.stringify(badLetter), 7, 1).ok).toBe(false)
    const unknownQuestion = makeDraft({ answers: { 99: 'A' } })
    expect(parseDraft(JSON.stringify(unknownQuestion), 7, 1).ok).toBe(false)
    const badFlag = makeDraft({ flaggedQuestionIds: [99] })
    expect(parseDraft(JSON.stringify(badFlag), 7, 1).ok).toBe(false)
  })

  it('未知版本与旧 submission 数据分开识别', () => {
    const unknown = { ...makeDraft(), schemaVersion: 9 }
    expect(parseDraft(JSON.stringify(unknown), 7, 1)).toEqual({
      ok: false,
      reason: 'unknown-version',
    })
    const legacy = { ...makeDraft(), submission: { key: 'x' } }
    expect(parseDraft(JSON.stringify(legacy), 7, 1)).toEqual({
      ok: false,
      reason: 'legacy-v1',
    })
  })

  it('题目集合一致性', () => {
    const draft = makeDraft()
    expect(draftMatchesQuestionSet(draft, [11, 12, 13, 14])).toBe(true)
    expect(draftMatchesQuestionSet(draft, [11, 12, 13])).toBe(false)
    expect(draftMatchesQuestionSet(draft, [11, 12, 13, 15])).toBe(false)
  })
})

describe('T-04 UUIDv4', () => {
  it('crypto.randomUUID 满足版本/变体', () => {
    const value = crypto.randomUUID()
    expect(isUuidV4(value)).toBe(true)
    expect(value[14]).toBe('4')
    expect('89ab').toContain(value[19])
  })

  it('拒绝非 v4/非法值', () => {
    expect(isUuidV4('0f5c2a1e-9d4b-1f6a-9c77-2b1e8a3d5c40')).toBe(false)
    expect(isUuidV4('not-a-uuid')).toBe(false)
    expect(isUuidV4(undefined)).toBe(false)
  })
})

describe('T-09 信封 codec（损坏保护）', () => {
  it('解析合法信封并保留冻结 payload', () => {
    const result = parseEnvelope(JSON.stringify(makeEnvelope()), 7, 1)
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.value.key).toBe(makeEnvelope().key)
      expect(result.value.frozenPayload.answers).toEqual([
        { question_id: 11, selected_option: 'A' },
      ])
    }
  })

  it('缺 key / 非 UUIDv4 / 缺 state → 对应失败原因', () => {
    const missingKey = { ...makeEnvelope() } as Record<string, unknown>
    delete missingKey.key
    expect(parseEnvelope(JSON.stringify(missingKey), 7, 1)).toEqual({
      ok: false,
      reason: 'missing-key',
    })
    const badKey = { ...makeEnvelope(), key: 'x' }
    expect(parseEnvelope(JSON.stringify(badKey), 7, 1)).toEqual({
      ok: false,
      reason: 'missing-key',
    })
    const badState = { ...makeEnvelope(), state: 'done' }
    expect(parseEnvelope(JSON.stringify(badState), 7, 1).ok).toBe(false)
  })

  it('重复题目 ID / 答案不在 loaded / 非法字母 → invalid-payload', () => {
    const dupLoaded = makeEnvelope({
      frozenPayload: {
        loaded_question_ids: [11, 11],
        answers: [],
      },
    })
    expect(parseEnvelope(JSON.stringify(dupLoaded), 7, 1).ok).toBe(false)
    const foreignAnswer = makeEnvelope({
      frozenPayload: {
        loaded_question_ids: [11],
        answers: [{ question_id: 12, selected_option: 'A' }],
      },
    })
    expect(parseEnvelope(JSON.stringify(foreignAnswer), 7, 1).ok).toBe(false)
    const badLetter = makeEnvelope({
      frozenPayload: {
        loaded_question_ids: [11],
        answers: [{ question_id: 11, selected_option: 'Z' as never }],
      },
    })
    expect(parseEnvelope(JSON.stringify(badLetter), 7, 1).ok).toBe(false)
  })

  it('旧数据/未知版本/坏 JSON 不构造合法信封', () => {
    expect(parseEnvelope('{broken', 7, 1)).toEqual({
      ok: false,
      reason: 'bad-json',
    })
    const legacy = { ...makeEnvelope(), schemaVersion: 0, submission: {} }
    expect(parseEnvelope(JSON.stringify(legacy), 7, 1)).toEqual({
      ok: false,
      reason: 'legacy-v1',
    })
    const unknown = { ...makeEnvelope(), schemaVersion: 3 }
    expect(parseEnvelope(JSON.stringify(unknown), 7, 1)).toEqual({
      ok: false,
      reason: 'unknown-version',
    })
  })
})

describe('T-14 提交标记 codec', () => {
  it('submittedAt 可空且 source/summary 校验', () => {
    const nullTime = makeSubmittedCache({ submittedAt: null })
    const result = parseSubmitted(JSON.stringify(nullTime), 7, 1)
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.value.submittedAt).toBeNull()
      expect(result.value.source).toBe('api1')
    }
  })

  it('未知版本/非法 source/坏 summary 均拒绝', () => {
    const unknown = { ...makeSubmittedCache(), schemaVersion: 3 }
    expect(parseSubmitted(JSON.stringify(unknown), 7, 1).ok).toBe(false)
    const badSource = { ...makeSubmittedCache(), source: 'other' }
    expect(parseSubmitted(JSON.stringify(badSource), 7, 1).ok).toBe(false)
    const badSummary = {
      ...makeSubmittedCache(),
      summary: { attemptCode: 1 },
    }
    expect(parseSubmitted(JSON.stringify(badSummary), 7, 1).ok).toBe(false)
  })
})
