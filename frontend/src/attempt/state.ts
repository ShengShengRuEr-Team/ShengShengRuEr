import type { AttemptSummary, OptionLetter, PaperDetail } from '../api/adapters'
import { countAnswered, countFlagged, detailQuestions } from './payload'
import type {
  AttemptSubmittedCacheV2,
  PageState,
} from './types'

export interface AttemptCounts {
  total: number
  answered: number
  unanswered: number
  flagged: number
}

export function countsFor(
  detail: PaperDetail,
  answers: Record<string, OptionLetter>,
  flaggedQuestionIds: number[],
): AttemptCounts {
  const total = detailQuestions(detail).length
  const answered = countAnswered(detail, answers)
  return {
    total,
    answered,
    unanswered: Math.max(total - answered, 0),
    flagged: countFlagged(detail, flaggedQuestionIds),
  }
}

export function isTerminalState(state: PageState): boolean {
  return state.kind === 'submitted'
}

/** 终态共享信号：先写本对象，再冻结本页、删草稿/信封。 */
export function submittedCacheFor(params: {
  userId: number
  examPaperId: number
  source: AttemptSubmittedCacheV2['source']
  summary: AttemptSummary | null
  submittedAt: string | null
  now?: string
}): AttemptSubmittedCacheV2 {
  return {
    schemaVersion: 2,
    userId: params.userId,
    examPaperId: params.examPaperId,
    submitted: true,
    submittedAt: params.submittedAt,
    source: params.source,
    summary: params.summary,
    savedAt: params.now ?? new Date().toISOString(),
  }
}

/** 由本机标记进入只读；authoritative=false 时必须标注「仅供参考」。 */
export function submittedStateFromCache(
  cache: AttemptSubmittedCacheV2,
  options: { cacheOnly: boolean; versionNotice?: boolean },
): PageState {
  return {
    kind: 'submitted',
    summary: cache.summary,
    source: 'cache',
    authoritative: false,
    submittedAt: cache.submittedAt,
    cacheOnly: options.cacheOnly,
    versionNotice: options.versionNotice ?? false,
  }
}

export function pageError(
  reason: 'not-accessible' | 'server' | 'network' | 'forbidden',
  message?: string,
): PageState {
  return { kind: 'error', reason, message }
}
