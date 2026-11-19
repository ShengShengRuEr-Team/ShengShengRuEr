import type { OptionLetter, PaperDetail, PaperPassage, PaperQuestion } from '../api/adapters'
import { isOptionLetter } from '../api/adapters'
import type {
  AttemptDraftV2,
  AttemptSubmitEnvelopeV1,
  FrozenSubmitPayload,
} from './types'

/** 详情顺序的题目 ID：跨篇、按接口返回顺序，不硬编码题数。 */
export function detailQuestionIds(detail: PaperDetail): number[] {
  return detail.passages.flatMap((passage) =>
    passage.questions.map((question) => question.questionId),
  )
}

export function detailQuestions(
  detail: PaperDetail,
): Array<{ passage: PaperPassage; question: PaperQuestion; passageIndex: number }> {
  return detail.passages.flatMap((passage, passageIndex) =>
    passage.questions.map((question) => ({ passage, question, passageIndex })),
  )
}

export function questionById(
  detail: PaperDetail,
  questionId: number,
): { passage: PaperPassage; question: PaperQuestion; passageIndex: number } | null {
  return (
    detailQuestions(detail).find((item) => item.question.questionId === questionId) ??
    null
  )
}

/**
 * 提交 payload（FR-18）：loaded IDs 为详情全部题目顺序；answers 只含已答、
 * 按题目顺序、大写 A–D、无重复；不存在的 ID 直接丢弃。
 */
export function buildSubmitPayload(
  detail: PaperDetail,
  answers: Record<string, OptionLetter>,
): FrozenSubmitPayload {
  const loadedQuestionIds: number[] = []
  const payloadAnswers: FrozenSubmitPayload['answers'] = []
  for (const passage of detail.passages) {
    for (const question of passage.questions) {
      const questionId = question.questionId
      if (loadedQuestionIds.includes(questionId)) {
        continue
      }
      loadedQuestionIds.push(questionId)
      const selected = answers[String(questionId)]
      if (isOptionLetter(selected)) {
        payloadAnswers.push({
          question_id: questionId,
          selected_option: selected,
        })
      }
    }
  }
  return {
    loaded_question_ids: loadedQuestionIds,
    answers: payloadAnswers,
  }
}

export function countAnswered(
  detail: PaperDetail,
  answers: Record<string, OptionLetter>,
): number {
  let count = 0
  for (const { question } of detailQuestions(detail)) {
    if (isOptionLetter(answers[String(question.questionId)])) {
      count += 1
    }
  }
  return count
}

export function countFlagged(
  detail: PaperDetail,
  flaggedQuestionIds: number[],
): number {
  const ids = new Set(detailQuestionIds(detail))
  return flaggedQuestionIds.filter((id) => ids.has(id)).length
}

export function createDraft(params: {
  userId: number
  detail: PaperDetail
  paperLabel: string
  answers: Record<string, OptionLetter>
  flaggedQuestionIds: number[]
  currentPassageIndex: number
  now?: string
  createdAt?: string
}): AttemptDraftV2 {
  const now = params.now ?? new Date().toISOString()
  return {
    schemaVersion: 2,
    userId: params.userId,
    examPaperId: params.detail.examPaperId,
    paperLabel: params.paperLabel,
    createdAt: params.createdAt ?? now,
    updatedAt: now,
    loadedQuestionIds: detailQuestionIds(params.detail),
    answers: params.answers,
    flaggedQuestionIds: params.flaggedQuestionIds,
    currentPassageIndex: params.currentPassageIndex,
  }
}

/**
 * N04：保留答案类明确失败时，先从信封 frozenPayload 重建普通草稿。
 * 仅当题目集合与当前详情完全一致才重建；非法参数（ID 不在集合、字母非
 * A–D、重复项）过滤；缺失标记/当前篇用默认值。
 */
export function rebuildDraftFromEnvelope(
  envelope: AttemptSubmitEnvelopeV1,
  detail: PaperDetail,
  options: { now?: string; createdAt?: string } = {},
): AttemptDraftV2 | null {
  const currentIds = detailQuestionIds(detail)
  const currentSet = new Set(currentIds)
  const loaded = envelope.frozenPayload.loaded_question_ids
  if (loaded.length !== currentIds.length) {
    return null
  }
  if (!loaded.every((id) => currentSet.has(id))) {
    return null
  }
  const allowed = currentSet
  const answers: Record<string, OptionLetter> = {}
  for (const answer of envelope.frozenPayload.answers) {
    if (
      allowed.has(answer.question_id) &&
      isOptionLetter(answer.selected_option)
    ) {
      answers[String(answer.question_id)] = answer.selected_option
    }
  }
  const now = options.now ?? new Date().toISOString()
  return {
    schemaVersion: 2,
    userId: envelope.userId,
    examPaperId: envelope.examPaperId,
    paperLabel: '',
    createdAt: options.createdAt ?? envelope.requestedAt,
    updatedAt: now,
    loadedQuestionIds: currentIds,
    answers,
    flaggedQuestionIds: [],
    currentPassageIndex: 0,
  }
}
