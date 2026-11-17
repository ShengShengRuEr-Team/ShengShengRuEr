import type { OptionLetter } from '../api/adapters'
import { isOptionLetter } from '../api/adapters'
import type {
  AttemptDraftIndexEntryV2,
  AttemptDraftIndexV2,
  AttemptDraftV2,
  AttemptSubmitEnvelopeV1,
  AttemptSubmittedCacheV2,
  EnvelopeFailureReason,
  FrozenSubmitPayload,
} from './types'

export type ParseFailure = { ok: false; reason: EnvelopeFailureReason }
export type ParseResult<T> = { ok: true; value: T } | ParseFailure

const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

export function isUuidV4(value: unknown): value is string {
  return typeof value === 'string' && UUID_V4.test(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isInt(value: unknown, min = 0): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= min
}

function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value))
}

function parseJson(raw: string): ParseResult<Record<string, unknown>> {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ok: false, reason: 'bad-json' }
  }
  if (!isRecord(parsed)) {
    return { ok: false, reason: 'invalid-payload' }
  }
  return { ok: true, value: parsed }
}

function isLegacyRecord(record: Record<string, unknown>): boolean {
  return 'submission' in record || record.schemaVersion === 0
}

function uniqueIntArray(value: unknown): value is number[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((item) => isInt(item)) &&
    new Set(value).size === value.length
  )
}

/** 可编辑草稿：schema/用户/试卷/ID 集合/字母/标记/当前篇。 */
export function parseDraft(
  raw: string,
  userId: number,
  examPaperId: number,
): ParseResult<AttemptDraftV2> {
  const json = parseJson(raw)
  if (!json.ok) {
    return json
  }
  const record = json.value
  if (isLegacyRecord(record)) {
    return { ok: false, reason: 'legacy-v1' }
  }
  if (record.schemaVersion !== 2) {
    return { ok: false, reason: 'unknown-version' }
  }
  if (record.userId !== userId || record.examPaperId !== examPaperId) {
    return { ok: false, reason: 'invalid-payload' }
  }
  if (
    typeof record.paperLabel !== 'string' ||
    !isIsoDate(record.createdAt) ||
    !isIsoDate(record.updatedAt) ||
    !uniqueIntArray(record.loadedQuestionIds) ||
    !isInt(record.currentPassageIndex)
  ) {
    return { ok: false, reason: 'invalid-payload' }
  }
  const loaded = new Set(record.loadedQuestionIds)
  if (!isRecord(record.answers)) {
    return { ok: false, reason: 'invalid-payload' }
  }
  const answers: Record<string, OptionLetter> = {}
  for (const [key, value] of Object.entries(record.answers)) {
    const questionId = Number(key)
    if (
      !/^\d+$/.test(key) ||
      !loaded.has(questionId) ||
      !isOptionLetter(value)
    ) {
      return { ok: false, reason: 'invalid-payload' }
    }
    answers[key] = value
  }
  if (!Array.isArray(record.flaggedQuestionIds)) {
    return { ok: false, reason: 'invalid-payload' }
  }
  const flagged: number[] = []
  for (const item of record.flaggedQuestionIds) {
    if (!isInt(item) || !loaded.has(item)) {
      return { ok: false, reason: 'invalid-payload' }
    }
    if (!flagged.includes(item)) {
      flagged.push(item)
    }
  }
  return {
    ok: true,
    value: {
      schemaVersion: 2,
      userId,
      examPaperId,
      paperLabel: record.paperLabel,
      createdAt: record.createdAt,
      updatedAt: record.updatedAt,
      loadedQuestionIds: [...record.loadedQuestionIds],
      answers,
      flaggedQuestionIds: flagged,
      currentPassageIndex: record.currentPassageIndex,
    },
  }
}

/** 草稿题目集合是否与当前详情一致；不一致时普通草稿 stale，不恢复答案。 */
export function draftMatchesQuestionSet(
  draft: AttemptDraftV2,
  questionIds: number[],
): boolean {
  if (draft.loadedQuestionIds.length !== questionIds.length) {
    return false
  }
  const current = new Set(questionIds)
  return draft.loadedQuestionIds.every((id) => current.has(id))
}

export function parseFrozenPayload(value: unknown): FrozenSubmitPayload | null {
  if (!isRecord(value)) {
    return null
  }
  if (!uniqueIntArray(value.loaded_question_ids)) {
    return null
  }
  const loaded = new Set(value.loaded_question_ids)
  if (!Array.isArray(value.answers)) {
    return null
  }
  const seen = new Set<number>()
  const answers: FrozenSubmitPayload['answers'] = []
  for (const item of value.answers) {
    if (
      !isRecord(item) ||
      !isInt(item.question_id) ||
      !loaded.has(item.question_id) ||
      !isOptionLetter(item.selected_option) ||
      seen.has(item.question_id)
    ) {
      return null
    }
    seen.add(item.question_id)
    answers.push({
      question_id: item.question_id,
      selected_option: item.selected_option,
    })
  }
  return {
    loaded_question_ids: [...value.loaded_question_ids],
    answers,
  }
}

/** 提交信封：结构、用户/试卷、UUIDv4、payload、requestedAt。 */
export function parseEnvelope(
  raw: string,
  userId: number,
  examPaperId: number,
): ParseResult<AttemptSubmitEnvelopeV1> {
  const json = parseJson(raw)
  if (!json.ok) {
    return json
  }
  const record = json.value
  if (isLegacyRecord(record)) {
    return { ok: false, reason: 'legacy-v1' }
  }
  if (!('key' in record)) {
    return { ok: false, reason: 'missing-key' }
  }
  if (record.schemaVersion !== 1) {
    return { ok: false, reason: 'unknown-version' }
  }
  if (record.userId !== userId || record.examPaperId !== examPaperId) {
    return { ok: false, reason: 'invalid-payload' }
  }
  if (!isUuidV4(record.key)) {
    return { ok: false, reason: 'missing-key' }
  }
  if (record.state !== 'pending' && record.state !== 'unknown') {
    return { ok: false, reason: 'invalid-payload' }
  }
  const frozenPayload = parseFrozenPayload(record.frozenPayload)
  if (frozenPayload === null || !isIsoDate(record.requestedAt)) {
    return { ok: false, reason: 'invalid-payload' }
  }
  return {
    ok: true,
    value: {
      schemaVersion: 1,
      userId,
      examPaperId,
      state: record.state,
      key: record.key,
      frozenPayload,
      requestedAt: record.requestedAt,
    },
  }
}

function parseSummaryRecord(value: unknown): boolean {
  if (!isRecord(value)) {
    return false
  }
  return (
    typeof value.attemptCode === 'string' &&
    typeof value.examPaperId === 'number' &&
    typeof value.submittedAt === 'string' &&
    typeof value.questionCount === 'number' &&
    typeof value.correctCount === 'number' &&
    typeof value.correctRate === 'number' &&
    isRecord(value.practiceScore) &&
    typeof value.practiceScore.available === 'boolean'
  )
}

/** 提交标记：submitted=true、submittedAt 可空、source、summary 可空、savedAt。 */
export function parseSubmitted(
  raw: string,
  userId: number,
  examPaperId: number,
): ParseResult<AttemptSubmittedCacheV2> {
  const json = parseJson(raw)
  if (!json.ok) {
    return json
  }
  const record = json.value
  if (record.schemaVersion !== 2) {
    return { ok: false, reason: 'unknown-version' }
  }
  if (record.userId !== userId || record.examPaperId !== examPaperId) {
    return { ok: false, reason: 'invalid-payload' }
  }
  if (
    record.submitted !== true ||
    (record.submittedAt !== null && !isIsoDate(record.submittedAt)) ||
    !isIsoDate(record.savedAt) ||
    (record.source !== 'api1' && record.source !== 'api3' && record.source !== 'e08') ||
    (record.summary !== null && !parseSummaryRecord(record.summary))
  ) {
    return { ok: false, reason: 'invalid-payload' }
  }
  return {
    ok: true,
    value: {
      schemaVersion: 2,
      userId,
      examPaperId,
      submitted: true,
      submittedAt: record.submittedAt,
      source: record.source,
      summary: record.summary as AttemptSubmittedCacheV2['summary'],
      savedAt: record.savedAt,
    },
  }
}

function parseIndexEntry(value: unknown): AttemptDraftIndexEntryV2 | null {
  if (!isRecord(value)) {
    return null
  }
  if (
    !isInt(value.examPaperId, 1) ||
    typeof value.paperLabel !== 'string' ||
    !isIsoDate(value.updatedAt) ||
    !isInt(value.answeredCount) ||
    !isInt(value.totalCount) ||
    typeof value.hasPending !== 'boolean'
  ) {
    return null
  }
  return {
    examPaperId: value.examPaperId,
    paperLabel: value.paperLabel,
    updatedAt: value.updatedAt,
    answeredCount: value.answeredCount,
    totalCount: value.totalCount,
    hasPending: value.hasPending,
  }
}

/** 索引：逐条校验，坏条目忽略；整体结构非法视为无索引。 */
export function parseIndex(raw: string): AttemptDraftIndexV2 {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { entries: [] }
  }
  if (!isRecord(parsed) || !Array.isArray(parsed.entries)) {
    return { entries: [] }
  }
  const entries: AttemptDraftIndexEntryV2[] = []
  for (const item of parsed.entries) {
    const entry = parseIndexEntry(item)
    if (entry !== null) {
      entries.push(entry)
    }
  }
  return { entries }
}
