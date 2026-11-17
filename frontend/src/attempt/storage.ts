import type { OptionLetter } from '../api/adapters'
import {
  draftMatchesQuestionSet,
  parseDraft,
  parseEnvelope,
  parseIndex,
  parseSubmitted,
} from './codec'
import type {
  AttemptDraftIndexEntryV2,
  AttemptDraftIndexV2,
  AttemptDraftV2,
  AttemptSubmitEnvelopeV1,
  AttemptSubmittedCacheV2,
  EnvelopeFailureReason,
} from './types'

export const DRAFT_TTL_MS = 30 * 24 * 60 * 60 * 1000
export const SUBMITTED_TTL_MS = 30 * 24 * 60 * 60 * 1000
export const MAX_DRAFTS_PER_USER = 10

export function draftKey(userId: number, examPaperId: number): string {
  return `ssre.attemptDraft.v2.${userId}.${examPaperId}`
}

export function envelopeKey(userId: number, examPaperId: number): string {
  return `ssre.attemptEnvelope.v1.${userId}.${examPaperId}`
}

export function indexKey(userId: number): string {
  return `ssre.attemptDraftIndex.v2.${userId}`
}

export function submittedKey(userId: number, examPaperId: number): string {
  return `ssre.attemptSubmitted.v2.${userId}.${examPaperId}`
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem' | 'key' | 'length'>

function getStorage(): StorageLike | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

function safeGet(storage: StorageLike, key: string): string | null {
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(storage: StorageLike, key: string, value: string): boolean {
  try {
    storage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

function safeRemove(storage: StorageLike, key: string): void {
  try {
    storage.removeItem(key)
  } catch {
    // 存储异常不阻断页面；下次进入按数据自然收敛。
  }
}

function isExpired(updatedAt: string, ttlMs: number, now: number): boolean {
  const updated = Date.parse(updatedAt)
  if (Number.isNaN(updated)) {
    return true
  }
  return now - updated >= ttlMs
}

export type DraftReadResult =
  | { kind: 'valid'; draft: AttemptDraftV2 }
  | { kind: 'empty' }
  | { kind: 'invalid'; reason: EnvelopeFailureReason }
  | { kind: 'unavailable' }

export type EnvelopeReadResult =
  | { kind: 'valid'; envelope: AttemptSubmitEnvelopeV1 }
  | { kind: 'none' }
  | {
      kind: 'corrupt'
      rawRecordKey: string
      reason: EnvelopeFailureReason
    }
  | { kind: 'unavailable' }

export type EnvelopeWriteResult =
  | { kind: 'ok'; envelope: AttemptSubmitEnvelopeV1 }
  | { kind: 'conflict'; envelope: AttemptSubmitEnvelopeV1 }
  | { kind: 'unavailable' }

export type SubmittedReadResult =
  | { kind: 'valid'; cache: AttemptSubmittedCacheV2 }
  | { kind: 'none' }
  | { kind: 'unavailable' }

export type WriteResult = { kind: 'ok' } | { kind: 'unavailable' }

/* ---------- 草稿 ---------- */

export function readDraft(
  userId: number,
  examPaperId: number,
  now = Date.now(),
): DraftReadResult {
  const storage = getStorage()
  if (!storage) {
    return { kind: 'unavailable' }
  }
  const key = draftKey(userId, examPaperId)
  const raw = safeGet(storage, key)
  if (raw === null) {
    return { kind: 'empty' }
  }
  const parsed = parseDraft(raw, userId, examPaperId)
  if (!parsed.ok) {
    safeRemove(storage, key)
    return { kind: 'invalid', reason: parsed.reason }
  }
  if (isExpired(parsed.value.updatedAt, DRAFT_TTL_MS, now)) {
    safeRemove(storage, key)
    return { kind: 'empty' }
  }
  return { kind: 'valid', draft: parsed.value }
}

export function writeDraft(draft: AttemptDraftV2): WriteResult {
  const storage = getStorage()
  if (!storage) {
    return { kind: 'unavailable' }
  }
  return safeSet(storage, draftKey(draft.userId, draft.examPaperId), JSON.stringify(draft))
    ? { kind: 'ok' }
    : { kind: 'unavailable' }
}

/** 写入后读回校验；N04 重建草稿只有校验成功才允许清信封。 */
export function writeDraftVerified(draft: AttemptDraftV2): WriteResult {
  const written = writeDraft(draft)
  if (written.kind !== 'ok') {
    return written
  }
  const read = readDraft(draft.userId, draft.examPaperId)
  if (read.kind !== 'valid') {
    return { kind: 'unavailable' }
  }
  const sameQuestions = draftMatchesQuestionSet(read.draft, draft.loadedQuestionIds)
  const sameAnswers =
    JSON.stringify(read.draft.answers) === JSON.stringify(draft.answers)
  return sameQuestions && sameAnswers ? { kind: 'ok' } : { kind: 'unavailable' }
}

export function removeDraft(userId: number, examPaperId: number): void {
  const storage = getStorage()
  if (storage) {
    safeRemove(storage, draftKey(userId, examPaperId))
  }
}

export function draftQuestionIds(draft: AttemptDraftV2): number[] {
  return draft.loadedQuestionIds
}

/** 每用户最多 10 份普通草稿；超出按 updatedAt 淘汰最旧。信封不参与。 */
export function enforceDraftLimit(userId: number, now = Date.now()): void {
  const storage = getStorage()
  if (!storage) {
    return
  }
  const prefix = `ssre.attemptDraft.v2.${userId}.`
  const drafts: Array<{ paperId: number; updatedAt: string }> = []
  const keys: string[] = []
  try {
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index)
      if (key !== null && key.startsWith(prefix)) {
        keys.push(key)
      }
    }
  } catch {
    return
  }
  for (const key of keys) {
    const raw = safeGet(storage, key)
    if (raw === null) {
      continue
    }
    const paperId = Number(key.slice(prefix.length))
    const parsed = parseDraft(raw, userId, paperId)
    if (!parsed.ok || isExpired(parsed.value.updatedAt, DRAFT_TTL_MS, now)) {
      safeRemove(storage, key)
      removeIndexEntry(userId, paperId)
      continue
    }
    drafts.push({ paperId, updatedAt: parsed.value.updatedAt })
  }
  if (drafts.length <= MAX_DRAFTS_PER_USER) {
    return
  }
  drafts.sort((left, right) => Date.parse(left.updatedAt) - Date.parse(right.updatedAt))
  for (const oldest of drafts.slice(0, drafts.length - MAX_DRAFTS_PER_USER)) {
    safeRemove(storage, draftKey(userId, oldest.paperId))
    removeIndexEntry(userId, oldest.paperId)
  }
}

/* ---------- 提交信封 ---------- */

export function readEnvelope(
  userId: number,
  examPaperId: number,
): EnvelopeReadResult {
  const storage = getStorage()
  if (!storage) {
    return { kind: 'unavailable' }
  }
  const key = envelopeKey(userId, examPaperId)
  const raw = safeGet(storage, key)
  if (raw === null) {
    return { kind: 'none' }
  }
  const parsed = parseEnvelope(raw, userId, examPaperId)
  if (!parsed.ok) {
    return { kind: 'corrupt', rawRecordKey: key, reason: parsed.reason }
  }
  return { kind: 'valid', envelope: parsed.value }
}

/**
 * 写信封并读回：已有合法信封时不覆盖；读回 key 不一致视为另一标签先写。
 * 单次读回不是原子互斥锁，竞争最终由后端幂等/限次裁决。
 */
export function writeEnvelopeVerified(
  envelope: AttemptSubmitEnvelopeV1,
): EnvelopeWriteResult {
  const storage = getStorage()
  if (!storage) {
    return { kind: 'unavailable' }
  }
  const current = readEnvelope(envelope.userId, envelope.examPaperId)
  if (current.kind === 'valid') {
    return { kind: 'conflict', envelope: current.envelope }
  }
  if (current.kind === 'corrupt') {
    // 损坏信封不被覆盖：交由页面进入受保护状态，禁止构造合法信封。
    return { kind: 'unavailable' }
  }
  const key = envelopeKey(envelope.userId, envelope.examPaperId)
  if (!safeSet(storage, key, JSON.stringify(envelope))) {
    return { kind: 'unavailable' }
  }
  const readBack = readEnvelope(envelope.userId, envelope.examPaperId)
  if (readBack.kind === 'valid') {
    return readBack.envelope.key === envelope.key
      ? { kind: 'ok', envelope: readBack.envelope }
      : { kind: 'conflict', envelope: readBack.envelope }
  }
  return { kind: 'unavailable' }
}

export function markEnvelopeUnknown(
  userId: number,
  examPaperId: number,
): EnvelopeReadResult {
  const storage = getStorage()
  if (!storage) {
    return { kind: 'unavailable' }
  }
  const current = readEnvelope(userId, examPaperId)
  if (current.kind !== 'valid') {
    return current
  }
  const next: AttemptSubmitEnvelopeV1 = { ...current.envelope, state: 'unknown' }
  safeSet(storage, envelopeKey(userId, examPaperId), JSON.stringify(next))
  return { kind: 'valid', envelope: next }
}

export function removeEnvelope(userId: number, examPaperId: number): void {
  const storage = getStorage()
  if (storage) {
    safeRemove(storage, envelopeKey(userId, examPaperId))
  }
}

/* ---------- 提交标记 ---------- */

export function readSubmitted(
  userId: number,
  examPaperId: number,
  now = Date.now(),
): SubmittedReadResult {
  const storage = getStorage()
  if (!storage) {
    return { kind: 'unavailable' }
  }
  const key = submittedKey(userId, examPaperId)
  const raw = safeGet(storage, key)
  if (raw === null) {
    return { kind: 'none' }
  }
  const parsed = parseSubmitted(raw, userId, examPaperId)
  if (!parsed.ok) {
    safeRemove(storage, key)
    return { kind: 'none' }
  }
  if (isExpired(parsed.value.savedAt, SUBMITTED_TTL_MS, now)) {
    safeRemove(storage, key)
    return { kind: 'none' }
  }
  return { kind: 'valid', cache: parsed.value }
}

export function writeSubmitted(cache: AttemptSubmittedCacheV2): WriteResult {
  const storage = getStorage()
  if (!storage) {
    return { kind: 'unavailable' }
  }
  return safeSet(
    storage,
    submittedKey(cache.userId, cache.examPaperId),
    JSON.stringify(cache),
  )
    ? { kind: 'ok' }
    : { kind: 'unavailable' }
}

export function removeSubmitted(userId: number, examPaperId: number): void {
  const storage = getStorage()
  if (storage) {
    safeRemove(storage, submittedKey(userId, examPaperId))
  }
}

/**
 * 写入前终态检查：普通防抖保存与 pagehide flush 必须先同步调用。
 * 存在有效提交标记即返回 true（禁止写草稿/索引）。
 */
export function hasSubmittedMarker(
  userId: number,
  examPaperId: number,
  now = Date.now(),
): boolean {
  return readSubmitted(userId, examPaperId, now).kind === 'valid'
}

/* ---------- 索引 ---------- */

export function readIndex(userId: number, now = Date.now()): AttemptDraftIndexV2 {
  const storage = getStorage()
  if (!storage) {
    return { entries: [] }
  }
  const raw = safeGet(storage, indexKey(userId))
  if (raw === null) {
    return { entries: [] }
  }
  const index = parseIndex(raw)
  const entries = index.entries.filter(
    (entry) => !isExpired(entry.updatedAt, DRAFT_TTL_MS, now),
  )
  return { entries }
}

export function writeIndexEntry(
  userId: number,
  entry: AttemptDraftIndexEntryV2,
): WriteResult {
  const storage = getStorage()
  if (!storage) {
    return { kind: 'unavailable' }
  }
  const index = readIndex(userId)
  const entries = index.entries.filter(
    (item) => item.examPaperId !== entry.examPaperId,
  )
  entries.push(entry)
  return safeSet(storage, indexKey(userId), JSON.stringify({ entries }))
    ? { kind: 'ok' }
    : { kind: 'unavailable' }
}

export function removeIndexEntry(userId: number, examPaperId: number): void {
  const storage = getStorage()
  if (!storage) {
    return
  }
  const index = readIndex(userId)
  const entries = index.entries.filter(
    (item) => item.examPaperId !== examPaperId,
  )
  safeSet(storage, indexKey(userId), JSON.stringify({ entries }))
}

export function answeredCount(answers: Record<string, OptionLetter>): number {
  return Object.keys(answers).length
}

/** 保存草稿 + 索引（含 hasPending 一致性）。 */
export function persistDraft(draft: AttemptDraftV2): WriteResult {
  const written = writeDraft(draft)
  if (written.kind !== 'ok') {
    return written
  }
  const envelope = readEnvelope(draft.userId, draft.examPaperId)
  const hasPending = envelope.kind === 'valid'
  writeIndexEntry(draft.userId, {
    examPaperId: draft.examPaperId,
    paperLabel: draft.paperLabel,
    updatedAt: draft.updatedAt,
    answeredCount: answeredCount(draft.answers),
    totalCount: draft.loadedQuestionIds.length,
    hasPending,
  })
  enforceDraftLimit(draft.userId)
  return { kind: 'ok' }
}

/** 信封创建/变更后同步索引提示（不存在草稿时也保留 pending 入口）。 */
export function syncIndexPending(
  userId: number,
  examPaperId: number,
  paperLabel: string,
  hasPending: boolean,
  updatedAt = new Date().toISOString(),
): void {
  const index = readIndex(userId).entries.find(
    (entry) => entry.examPaperId === examPaperId,
  )
  if (!hasPending && index === undefined) {
    removeIndexEntry(userId, examPaperId)
    return
  }
  writeIndexEntry(userId, {
    examPaperId,
    paperLabel,
    updatedAt,
    answeredCount: index?.answeredCount ?? 0,
    totalCount: index?.totalCount ?? 0,
    hasPending,
  })
}

export function clearDraftAndIndex(userId: number, examPaperId: number): void {
  removeDraft(userId, examPaperId)
  removeIndexEntry(userId, examPaperId)
}

export function clearEnvelopeAndIndex(userId: number, examPaperId: number): void {
  removeEnvelope(userId, examPaperId)
  removeIndexEntry(userId, examPaperId)
}

/** 供测试与页面共用：仅判断草稿能否用于恢复。 */
export function usableDraft(
  result: DraftReadResult,
  questionIds: number[],
): AttemptDraftV2 | null {
  if (result.kind !== 'valid') {
    return null
  }
  return draftMatchesQuestionSet(result.draft, questionIds) ? result.draft : null
}
