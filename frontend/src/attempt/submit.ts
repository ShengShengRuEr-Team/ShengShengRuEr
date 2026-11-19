import type { AttemptSubmitApiResult } from '../api/attempts'
import type { AttemptSummary, PaperDetail } from '../api/adapters'
import { classifySubmitError } from './errors'
import { rebuildDraftFromEnvelope } from './payload'
import type {
  AttemptDraftV2,
  AttemptSubmitEnvelopeV1,
  EnvelopeFailureReason,
  FrozenSubmitPayload,
  SubmitErrorPlan,
} from './types'
import type {
  EnvelopeReadResult,
  EnvelopeWriteResult,
} from './storage'

export interface SubmitStoragePort {
  readEnvelope(userId: number, examPaperId: number): EnvelopeReadResult
  writeEnvelopeVerified(
    envelope: AttemptSubmitEnvelopeV1,
  ): EnvelopeWriteResult
  markEnvelopeUnknown(userId: number, examPaperId: number): void
  writeDraftVerified(draft: AttemptDraftV2): { kind: 'ok' } | { kind: 'unavailable' }
}

export interface SubmitApiPort {
  submit(
    paperId: number,
    payload: FrozenSubmitPayload,
    key: string,
  ): Promise<AttemptSubmitApiResult>
}

export type SubmitFlowResult =
  | { kind: 'submitted'; summary: AttemptSummary }
  | { kind: 'submitted-without-summary'; examPaperId: number }
  | { kind: 'terminal-e08' }
  | { kind: 'unauthorized' }
  | {
      kind: 'check-status'
      message: string
      envelope: AttemptSubmitEnvelopeV1
    }
  | {
      kind: 'unknown'
      message: string
      envelope: AttemptSubmitEnvelopeV1
    }
  | {
      kind: 'explicit-failure'
      plan: SubmitErrorPlan
      envelope: AttemptSubmitEnvelopeV1
    }
  | {
      kind: 'envelope-corrupt'
      rawRecordKey: string
      reason: EnvelopeFailureReason
    }
  | {
      kind: 'needs-storage-confirmation'
      envelope: AttemptSubmitEnvelopeV1
    }

/** 生成 UUIDv4（Web Crypto；服务端与前端都以版本/变体校验）。 */
export function generateUuidV4(): string {
  const cryptoApi = globalThis.crypto
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }
  const bytes = new Uint8Array(16)
  if (cryptoApi && typeof cryptoApi.getRandomValues === 'function') {
    cryptoApi.getRandomValues(bytes)
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256)
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0'))
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex
    .slice(6, 8)
    .join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10, 16).join('')}`
}

export function createEnvelope(params: {
  userId: number
  examPaperId: number
  payload: FrozenSubmitPayload
  key?: string
  requestedAt?: string
}): AttemptSubmitEnvelopeV1 {
  return {
    schemaVersion: 1,
    userId: params.userId,
    examPaperId: params.examPaperId,
    state: 'pending',
    key: params.key ?? generateUuidV4(),
    frozenPayload: params.payload,
    requestedAt: params.requestedAt ?? new Date().toISOString(),
  }
}

function toFlowResult(
  result: AttemptSubmitApiResult,
  envelope: AttemptSubmitEnvelopeV1,
  storage: SubmitStoragePort,
): SubmitFlowResult {
  if (result.kind === 'success') {
    if (result.value.kind === 'submitted') {
      return { kind: 'submitted', summary: result.value.summary }
    }
    return {
      kind: 'submitted-without-summary',
      examPaperId: result.value.examPaperId,
    }
  }
  if (result.kind === 'unauthorized') {
    return { kind: 'unauthorized' }
  }
  if (result.kind === 'network') {
    storage.markEnvelopeUnknown(envelope.userId, envelope.examPaperId)
    return {
      kind: 'unknown',
      message: '网络异常或超时，结果未确认；已保留提交信封，请同键重试或查询状态',
      envelope,
    }
  }
  const plan = classifySubmitError(result.status, result.msg)
  if (plan.action === 'terminal-e08') {
    return { kind: 'terminal-e08' }
  }
  if (plan.action === 'check-status') {
    return { kind: 'check-status', message: plan.message, envelope }
  }
  if (plan.action === 'unknown-retry') {
    storage.markEnvelopeUnknown(envelope.userId, envelope.examPaperId)
    return { kind: 'unknown', message: plan.message, envelope }
  }
  if (plan.action === 'unauthorized') {
    return { kind: 'unauthorized' }
  }
  return { kind: 'explicit-failure', plan, envelope }
}

/**
 * 提交编排：读已有信封或写新信封并读回 → 发送。
 * 存储不可用时只返回内存信封，必须由页面弹 P-12 让用户确认后才发送。
 */
export async function runSubmit(params: {
  userId: number
  examPaperId: number
  payload: FrozenSubmitPayload
  storage: SubmitStoragePort
  api: SubmitApiPort
}): Promise<SubmitFlowResult> {
  const { userId, examPaperId, payload, storage, api } = params
  const existing = storage.readEnvelope(userId, examPaperId)
  let envelope: AttemptSubmitEnvelopeV1
  if (existing.kind === 'corrupt') {
    return {
      kind: 'envelope-corrupt',
      rawRecordKey: existing.rawRecordKey,
      reason: existing.reason,
    }
  }
  if (existing.kind === 'valid') {
    envelope = existing.envelope
  } else {
    const candidate = createEnvelope({ userId, examPaperId, payload })
    const written = storage.writeEnvelopeVerified(candidate)
    if (written.kind === 'unavailable') {
      return { kind: 'needs-storage-confirmation', envelope: candidate }
    }
    envelope = written.envelope
  }
  return toFlowResult(
    await api.submit(examPaperId, envelope.frozenPayload, envelope.key),
    envelope,
    storage,
  )
}

/** P-12 用户选择「仍要提交」后：用内存信封发送，不再尝试写存储。 */
export async function sendMemoryEnvelope(params: {
  envelope: AttemptSubmitEnvelopeV1
  storage: SubmitStoragePort
  api: SubmitApiPort
}): Promise<SubmitFlowResult> {
  const { envelope, storage, api } = params
  return toFlowResult(
    await api.submit(
      envelope.examPaperId,
      envelope.frozenPayload,
      envelope.key,
    ),
    envelope,
    storage,
  )
}

/** pending 同键重试：只用原 key/frozenPayload，不读当前答案。 */
export async function retryEnvelope(params: {
  envelope: AttemptSubmitEnvelopeV1
  storage: SubmitStoragePort
  api: SubmitApiPort
}): Promise<SubmitFlowResult> {
  return sendMemoryEnvelope(params)
}

export type RebuildResult =
  | { kind: 'rebuilt'; draft: AttemptDraftV2 }
  | { kind: 'incompatible' }
  | { kind: 'write-failed' }

/**
 * N04：明确失败且需保留答案时，先从 frozenPayload 重建草稿并读回校验；
 * 成功才允许页面删除信封。题目集合已变化则返回 incompatible（保留信封）。
 */
export function rebuildDraftForExplicitFailure(params: {
  envelope: AttemptSubmitEnvelopeV1
  detail: PaperDetail
  paperLabel: string
  storage: SubmitStoragePort
}): RebuildResult {
  const draft = rebuildDraftFromEnvelope(params.envelope, params.detail)
  if (draft === null) {
    return { kind: 'incompatible' }
  }
  draft.paperLabel = params.paperLabel
  const written = params.storage.writeDraftVerified(draft)
  if (written.kind !== 'ok') {
    return { kind: 'write-failed' }
  }
  return { kind: 'rebuilt', draft }
}
