import type { AttemptSummary, OptionLetter } from '../api/adapters'

export type { OptionLetter }

/* ---------- 本机三对象（需求 §8） ---------- */

export interface AttemptDraftV2 {
  schemaVersion: 2
  userId: number
  examPaperId: number
  paperLabel: string
  createdAt: string
  updatedAt: string
  loadedQuestionIds: number[]
  answers: Record<string, OptionLetter>
  flaggedQuestionIds: number[]
  currentPassageIndex: number
}

export interface FrozenSubmitPayload {
  loaded_question_ids: number[]
  answers: Array<{ question_id: number; selected_option: OptionLetter }>
}

export interface AttemptSubmitEnvelopeV1 {
  schemaVersion: 1
  userId: number
  examPaperId: number
  state: 'pending' | 'unknown'
  key: string
  frozenPayload: FrozenSubmitPayload
  requestedAt: string
}

export interface AttemptSubmittedCacheV2 {
  schemaVersion: 2
  userId: number
  examPaperId: number
  submitted: true
  /** 服务端真实提交时间；未知为 null，不得用 now()/requestedAt 冒充。 */
  submittedAt: string | null
  source: 'api1' | 'api3' | 'e08'
  summary: AttemptSummary | null
  savedAt: string
}

export interface AttemptDraftIndexEntryV2 {
  examPaperId: number
  paperLabel: string
  updatedAt: string
  answeredCount: number
  totalCount: number
  hasPending: boolean
}

/** 索引是内部包装：不引入 schemaVersion，数组本身即数据。 */
export interface AttemptDraftIndexV2 {
  entries: AttemptDraftIndexEntryV2[]
}

export type EnvelopeFailureReason =
  | 'bad-json'
  | 'missing-key'
  | 'invalid-payload'
  | 'unknown-version'
  | 'legacy-v1'

/* ---------- 页面状态（开发文档 §2.3） ---------- */

export type PageErrorReason = 'not-accessible' | 'server' | 'network' | 'forbidden'

export type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; reason: PageErrorReason; message?: string }
  | { kind: 'answering'; draft: AttemptDraftV2; statusUnknown: boolean; frozen: boolean }
  | {
      kind: 'pending'
      envelope: AttemptSubmitEnvelopeV1
      statusUnknown: boolean
      conflict: boolean
    }
  | {
      kind: 'pending-unrecoverable'
      rawRecordKey: string
      reason: EnvelopeFailureReason
    }
  | {
      kind: 'submitted'
      summary: AttemptSummary | null
      source: 'api1' | 'api3' | 'e08' | 'cache'
      authoritative: boolean
      submittedAt: string | null
      cacheOnly: boolean
      versionNotice: boolean
    }

/* ---------- 保留期（需求 §3.6） ---------- */

export type KeyRetentionPolicy =
  | { kind: 'unknown' }
  | { kind: 'days'; days: number }
  | { kind: 'permanent' }

export type RetentionReason =
  | 'unknown-policy'
  | 'expired'
  | 'invalid-time'
  | 'allowed'

export interface RetentionDecision {
  autoRetry: boolean
  manualRetry: boolean
  warning: 'none' | 'strong'
  reason: RetentionReason
}

/* ---------- 错误白名单（需求 §9.1） ---------- */

export type SubmitErrorAction =
  | 'terminal-e08'
  | 'reload-clear'
  | 'restore-answer'
  | 'check-status'
  | 'unknown-retry'
  | 'unauthorized'

export interface SubmitErrorPlan {
  action: SubmitErrorAction
  message: string
  /** 是否清空答案/标记（E04）。 */
  clearDraft: boolean
  /** 是否清信封；restore-answer 类需重建草稿成功后才可清。 */
  clearEnvelope: boolean
  /** restore-answer 类必须先由 frozenPayload 重建草稿并读回校验。 */
  rebuildDraftFirst: boolean
}
