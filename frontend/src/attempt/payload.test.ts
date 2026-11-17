import { describe, expect, it } from 'vitest'
import {
  buildSubmitPayload,
  countAnswered,
  countFlagged,
  createDraft,
  detailQuestionIds,
  rebuildDraftFromEnvelope,
} from './payload'
import { makeDetail, makeEnvelope } from '../test/fixtures'

describe('T-03 提交 payload', () => {
  it('loaded IDs 按详情顺序，answers 只含已答并按题目顺序', () => {
    const payload = buildSubmitPayload(makeDetail(), { 13: 'C', 11: 'A' })
    expect(payload.loaded_question_ids).toEqual([11, 12, 13, 14])
    expect(payload.answers).toEqual([
      { question_id: 11, selected_option: 'A' },
      { question_id: 13, selected_option: 'C' },
    ])
  })

  it('空答案、大写过滤与无重复', () => {
    expect(buildSubmitPayload(makeDetail(), {}).answers).toEqual([])
    const lower = buildSubmitPayload(makeDetail(), {
      11: 'a' as never,
      12: 'B',
    })
    expect(lower.answers).toEqual([{ question_id: 12, selected_option: 'B' }])
    expect(detailQuestionIds(makeDetail())).toEqual([11, 12, 13, 14])
  })
})

describe('T-07 计数', () => {
  it('跨篇统计已答/标记', () => {
    const detail = makeDetail()
    expect(countAnswered(detail, { 11: 'A', 13: 'C' })).toBe(2)
    expect(countFlagged(detail, [12, 14])).toBe(2)
    expect(countFlagged(detail, [12, 99])).toBe(1)
  })
})

describe('N04 从信封重建草稿', () => {
  it('题目集合一致时重建并过滤非法答案', () => {
    const envelope = makeEnvelope()
    const draft = rebuildDraftFromEnvelope(envelope, makeDetail(), {
      now: '2026-11-15T00:00:00.000Z',
    })
    expect(draft).not.toBeNull()
    expect(draft?.answers).toEqual({ 11: 'A' })
    expect(draft?.flaggedQuestionIds).toEqual([])
    expect(draft?.currentPassageIndex).toBe(0)
    expect(draft?.loadedQuestionIds).toEqual([11, 12, 13, 14])
  })

  it('题目集合变化时拒绝重建（不无条件填入旧答案）', () => {
    const envelope = makeEnvelope({
      frozenPayload: {
        loaded_question_ids: [11, 12],
        answers: [{ question_id: 11, selected_option: 'A' }],
      },
    })
    expect(rebuildDraftFromEnvelope(envelope, makeDetail())).toBeNull()
  })
})

describe('草稿创建', () => {
  it('包含用户/试卷隔离与当前篇', () => {
    const draft = createDraft({
      userId: 7,
      detail: makeDetail(),
      paperLabel: 'label',
      answers: { 11: 'A' },
      flaggedQuestionIds: [12],
      currentPassageIndex: 1,
      now: '2026-11-14T00:00:00.000Z',
    })
    expect(draft.userId).toBe(7)
    expect(draft.examPaperId).toBe(1)
    expect(draft.createdAt).toBe('2026-11-14T00:00:00.000Z')
    expect(draft.answers).toEqual({ 11: 'A' })
    expect(draft.currentPassageIndex).toBe(1)
  })
})
