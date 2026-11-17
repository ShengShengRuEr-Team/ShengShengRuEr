import type {
  AttemptDraftV2,
  AttemptSubmitEnvelopeV1,
  AttemptSubmittedCacheV2,
} from '../attempt/types'
import type { AttemptSummary, PaperDetail } from '../api/adapters'

export function makeDetail(overrides: Partial<PaperDetail> = {}): PaperDetail {
  const options = (prefix: string) => [
    { label: 'A', text: `${prefix}-A` },
    { label: 'B', text: `${prefix}-B` },
    { label: 'C', text: `${prefix}-C` },
    { label: 'D', text: `${prefix}-D` },
  ]
  return {
    examPaperId: 1,
    code: 'TEST_PAPER',
    level: 'CET4',
    year: 2025,
    month: 6,
    paperSet: 1,
    contentScope: 'listening',
    audioUrl: '/api/v1/listening-papers/1/audio',
    durationMs: 5000,
    passages: [
      {
        passageId: 101,
        passageIndex: 1,
        passageType: '长对话',
        topic: '第一篇',
        questions: [
          {
            questionNo: 1,
            questionId: 11,
            questionText: 'Question one',
            options: options('Q1'),
          },
          {
            questionNo: 2,
            questionId: 12,
            questionText: 'Question two',
            options: options('Q2'),
          },
        ],
      },
      {
        passageId: 102,
        passageIndex: 2,
        passageType: '短文',
        topic: '第二篇',
        questions: [
          {
            questionNo: 3,
            questionId: 13,
            questionText: 'Question three',
            options: options('Q3'),
          },
          {
            questionNo: 4,
            questionId: 14,
            questionText: 'Question four',
            options: options('Q4'),
          },
        ],
      },
    ],
    ...overrides,
  }
}

export function makeDraft(overrides: Partial<AttemptDraftV2> = {}): AttemptDraftV2 {
  const now = '2026-11-14T00:00:00.000Z'
  return {
    schemaVersion: 2,
    userId: 7,
    examPaperId: 1,
    paperLabel: '2025 年 6 月 · 第 1 套',
    createdAt: now,
    updatedAt: now,
    loadedQuestionIds: [11, 12, 13, 14],
    answers: { 11: 'A', 13: 'C' },
    flaggedQuestionIds: [12],
    currentPassageIndex: 1,
    ...overrides,
  }
}

export function makeEnvelope(
  overrides: Partial<AttemptSubmitEnvelopeV1> = {},
): AttemptSubmitEnvelopeV1 {
  return {
    schemaVersion: 1,
    userId: 7,
    examPaperId: 1,
    state: 'pending',
    key: '0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40',
    frozenPayload: {
      loaded_question_ids: [11, 12, 13, 14],
      answers: [{ question_id: 11, selected_option: 'A' }],
    },
    requestedAt: '2026-11-14T00:00:00.000Z',
    ...overrides,
  }
}

export function makeSummary(
  overrides: Partial<AttemptSummary> = {},
): AttemptSummary {
  return {
    attemptCode: '0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40',
    examPaperId: 1,
    submittedAt: '2026-11-14T06:30:00.000Z',
    questionCount: 4,
    correctCount: 3,
    correctRate: 75,
    practiceScore: {
      available: true,
      value: 30,
      max: 40,
      label: '练习估分，非官方成绩',
      reason: null,
    },
    ...overrides,
  }
}

export function makeSubmittedCache(
  overrides: Partial<AttemptSubmittedCacheV2> = {},
): AttemptSubmittedCacheV2 {
  return {
    schemaVersion: 2,
    userId: 7,
    examPaperId: 1,
    submitted: true,
    submittedAt: '2026-11-14T06:30:00.000Z',
    source: 'api1',
    summary: makeSummary(),
    savedAt: '2026-11-14T06:31:00.000Z',
    ...overrides,
  }
}
