import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowLeftOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Empty,
  Modal,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import { Link, useParams } from 'react-router-dom'
import type {
  AttemptStatusResult,
  AttemptSummary,
  OptionLetter,
  PaperDetail,
  PaperQuestion,
} from '../../api/adapters'
import { ApiError } from '../../api/api-error'
import { getAttemptStatus, submitAttempt } from '../../api/attempts'
import type { AttemptSubmitApiResult } from '../../api/attempts'
import { getListeningPaper } from '../../api/listening'
import {
  answeredCount,
  clearDraftAndIndex,
  hasSubmittedMarker,
  markEnvelopeUnknown,
  persistDraft,
  readDraft,
  readEnvelope,
  readSubmitted,
  removeDraft,
  removeEnvelope,
  removeIndexEntry,
  removeSubmitted,
  submittedKey,
  syncIndexPending,
  writeDraftVerified,
  writeEnvelopeVerified,
  writeSubmitted,
} from '../../attempt/storage'
import { draftMatchesQuestionSet } from '../../attempt/codec'
import {
  buildSubmitPayload,
  createDraft,
  detailQuestionIds,
  detailQuestions,
  rebuildDraftFromEnvelope,
} from '../../attempt/payload'
import {
  canAutoRetry,
  KEY_RETENTION_POLICY,
} from '../../attempt/retention'
import { countsFor, submittedCacheFor } from '../../attempt/state'
import {
  retryEnvelope,
  runSubmit,
  sendMemoryEnvelope,
} from '../../attempt/submit'
import type {
  SubmitApiPort,
  SubmitFlowResult,
  SubmitStoragePort,
} from '../../attempt/submit'
import type {
  AttemptSubmitEnvelopeV1,
  AttemptSubmittedCacheV2,
  EnvelopeFailureReason,
} from '../../attempt/types'
import { useAuth } from '../../auth/useAuth'
import { ROUTES } from '../../constants/routes'
import AnswerSheet from './attempt/AnswerSheet'
import DraftBanner from './attempt/DraftBanner'
import type { DraftBannerKind } from './attempt/DraftBanner'
import PendingPanel from './attempt/PendingPanel'
import QuestionCard from './attempt/QuestionCard'
import SubmitConfirmModal from './attempt/SubmitConfirmModal'
import SubmitResultAlert from './attempt/SubmitResultAlert'
import SubmitSummaryPanel from './attempt/SubmitSummaryPanel'
import AudioPlayer from '../../ui/AudioPlayer'
import { isAbortError } from '../../utils/concurrency'
import {
  formatContentScope,
  formatDuration,
  formatPaperLabel,
} from '../../utils/format'

type PageMode = 'answering' | 'pending' | 'unrecoverable' | 'submitted' | 'inaccessible'

interface SubmitAlert {
  type: 'success' | 'info' | 'warning' | 'error'
  message: string
  description?: string
}

const SAVE_DEBOUNCE_MS = 300

/** 响应式断点：>=1280 右侧 sticky 答题卡；[1024,1280) 顶部折叠答题卡。 */
function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) {
      return true
    }
    return window.matchMedia(query).matches
  })
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) {
      return
    }
    const media = window.matchMedia(query)
    const onChange = () => setMatches(media.matches)
    media.addEventListener?.('change', onChange)
    return () => media.removeEventListener?.('change', onChange)
  }, [query])
  return matches
}

export default function StudentListeningPaperPage() {
  const { examPaperId } = useParams()
  const paperId = Number(examPaperId)
  const { user } = useAuth()
  const userId = user?.userId ?? 0
  const wide = useMediaQuery('(min-width: 1280px)')

  const [detail, setDetail] = useState<PaperDetail | null>(null)
  const [boot, setBoot] = useState<'loading' | 'ready' | 'error'>('loading')
  const [detailError, setDetailError] = useState<{
    message: string
    notFound: boolean
    forbidden: boolean
  } | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [mode, setMode] = useState<PageMode>('answering')
  const [frozen, setFrozen] = useState(false)
  const [statusUnknown, setStatusUnknown] = useState(false)
  const [conflict, setConflict] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const [envelope, setEnvelope] = useState<AttemptSubmitEnvelopeV1 | null>(null)
  const [envelopeReason, setEnvelopeReason] =
    useState<EnvelopeFailureReason | null>(null)

  const [answers, setAnswers] = useState<Record<string, OptionLetter>>({})
  const [flagged, setFlagged] = useState<number[]>([])
  const [passageIndex, setPassageIndex] = useState(0)
  const [currentQuestionId, setCurrentQuestionId] = useState<number | null>(null)
  const [banner, setBanner] = useState<DraftBannerKind | null>(null)
  const [savedAt, setSavedAt] = useState<string | null>(null)

  const [summary, setSummary] = useState<AttemptSummary | null>(null)
  const [submittedAt, setSubmittedAt] = useState<string | null>(null)
  const [cacheOnly, setCacheOnly] = useState(false)
  const [authoritative, setAuthoritative] = useState(true)
  const [versionNotice, setVersionNotice] = useState(false)

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [storageEnvelope, setStorageEnvelope] =
    useState<AttemptSubmitEnvelopeV1 | null>(null)
  const [submitAlert, setSubmitAlert] = useState<SubmitAlert | null>(null)
  const [busy, setBusy] = useState(false)

  const terminalRef = useRef(false)
  const inFlightRef = useRef(false)
  const autoTriedRef = useRef(false)
  const saveTimerRef = useRef<number | null>(null)
  const answersRef = useRef(answers)
  const flaggedRef = useRef(flagged)
  const passageRef = useRef(passageIndex)
  const modeRef = useRef(mode)
  const frozenRef = useRef(frozen)
  const detailRef = useRef<PaperDetail | null>(detail)
  const totalQuestionsRef = useRef(0)

  answersRef.current = answers
  flaggedRef.current = flagged
  passageRef.current = passageIndex
  modeRef.current = mode
  frozenRef.current = frozen
  detailRef.current = detail

  const passages = detail?.passages ?? []
  const totalPassages = passages.length
  const currentPassage = useMemo(() => {
    if (totalPassages === 0) {
      return null
    }
    const index = Math.min(Math.max(passageIndex, 0), totalPassages - 1)
    return passages[index]
  }, [passages, passageIndex, totalPassages])

  const allQuestions = useMemo(
    () => (detail ? detailQuestions(detail) : []),
    [detail],
  )
  totalQuestionsRef.current = allQuestions.length

  const currentQuestion: PaperQuestion | null = useMemo(() => {
    if (currentPassage === null) {
      return null
    }
    return (
      currentPassage.questions.find(
        (question) => question.questionId === currentQuestionId,
      ) ??
      currentPassage.questions[0] ??
      null
    )
  }, [currentPassage, currentQuestionId])

  const counts = useMemo(() => {
    if (!detail) {
      return { total: 0, answered: 0, unanswered: 0, flagged: 0 }
    }
    return countsFor(detail, answers, flagged)
  }, [detail, answers, flagged])

  const draftCounts = useMemo(() => {
    if (!envelope) {
      return undefined
    }
    const draft = readDraft(userId, paperId)
    const total = detail ? detailQuestionIds(detail).length : 0
    if (draft.kind !== 'valid' || total === 0) {
      return undefined
    }
    return { answered: answeredCount(draft.draft.answers), total }
  }, [envelope, userId, paperId, detail])

  const retention = useMemo(() => {
    if (!envelope) {
      return canAutoRetry(new Date(0).toISOString(), KEY_RETENTION_POLICY)
    }
    return canAutoRetry(envelope.requestedAt, KEY_RETENTION_POLICY)
  }, [envelope])

  const storagePort: SubmitStoragePort = useMemo(
    () => ({
      readEnvelope,
      writeEnvelopeVerified,
      markEnvelopeUnknown: (targetUserId: number, paper: number) => {
        markEnvelopeUnknown(targetUserId, paper)
      },
      writeDraftVerified,
    }),
    [],
  )

  const apiPort: SubmitApiPort = useMemo(
    () => ({
      submit: (
        targetPaperId: number,
        payload: {
          loaded_question_ids: number[]
          answers: Array<{ question_id: number; selected_option: OptionLetter }>
        },
        key: string,
      ): Promise<AttemptSubmitApiResult> =>
        submitAttempt(targetPaperId, payload, key),
    }),
    [],
  )

  const clearSaveTimer = useCallback(() => {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current)
      saveTimerRef.current = null
    }
  }, [])

  /** 终态：先写共享提交标记 → 置 terminalRef/取消 timer → 删草稿/信封。 */
  const applySubmitted = useCallback(
    (params: {
      summary: AttemptSummary | null
      submittedAt: string | null
      source: AttemptSubmittedCacheV2['source']
      authoritative: boolean
      cacheOnly: boolean
    }) => {
      const cache = submittedCacheFor({
        userId,
        examPaperId: paperId,
        source: params.source,
        summary: params.summary,
        submittedAt: params.submittedAt,
      })
      terminalRef.current = true
      writeSubmitted(cache)
      clearSaveTimer()
      setAnswers({})
      setFlagged([])
      setCurrentQuestionId(null)
      setEnvelope(null)
      setEnvelopeReason(null)
      setConflict(false)
      setStatusUnknown(false)
      setFrozen(false)
      clearDraftAndIndex(userId, paperId)
      removeEnvelope(userId, paperId)
      setMode('submitted')
      setSummary(params.summary)
      setSubmittedAt(params.submittedAt)
      setAuthoritative(params.authoritative)
      setCacheOnly(params.cacheOnly)
      setVersionNotice(
        params.summary !== null &&
          params.summary.questionCount !== totalQuestionsRef.current,
      )
      setNotice(null)
      setBanner(null)
    },
    [userId, paperId, clearSaveTimer],
  )

  const applySubmittedFromCache = useCallback(
    (cache: AttemptSubmittedCacheV2, options: { cacheOnly: boolean }) => {
      terminalRef.current = true
      clearSaveTimer()
      clearDraftAndIndex(userId, paperId)
      removeEnvelope(userId, paperId)
      setAnswers({})
      setFlagged([])
      setCurrentQuestionId(null)
      setEnvelope(null)
      setEnvelopeReason(null)
      setConflict(false)
      setStatusUnknown(false)
      setFrozen(false)
      setMode('submitted')
      setSummary(cache.summary)
      setSubmittedAt(cache.submittedAt)
      setAuthoritative(false)
      setCacheOnly(options.cacheOnly)
      setVersionNotice(
        cache.summary !== null &&
          cache.summary.questionCount !== totalQuestionsRef.current,
      )
      setNotice(null)
      setBanner(null)
    },
    [userId, paperId, clearSaveTimer],
  )

  const enrichAfterE08 = useCallback(async () => {
    try {
      const result = await getAttemptStatus(paperId)
      if (result.kind === 'submitted') {
        applySubmitted({
          summary: result.status.latestAttempt,
          submittedAt: result.status.latestAttempt?.submittedAt ?? null,
          source: 'api3',
          authoritative: true,
          cacheOnly: false,
        })
      } else if (result.kind === 'submitted-summary-unavailable') {
        applySubmitted({
          summary: null,
          submittedAt: result.submittedAt,
          source: 'api3',
          authoritative: true,
          cacheOnly: false,
        })
      }
    } catch {
      // E08 已确定终态：查询失败不改变只读结论。
    }
  }, [paperId, applySubmitted])

  const queryStatus = useCallback(
    async (origin: 'manual' | 'e09') => {
      setBusy(true)
      try {
        const result = await getAttemptStatus(paperId)
        if (result.kind === 'submitted') {
          applySubmitted({
            summary: result.status.latestAttempt,
            submittedAt: result.status.latestAttempt?.submittedAt ?? null,
            source: 'api3',
            authoritative: true,
            cacheOnly: false,
          })
        } else if (result.kind === 'submitted-summary-unavailable') {
          applySubmitted({
            summary: null,
            submittedAt: result.submittedAt,
            source: 'api3',
            authoritative: true,
            cacheOnly: false,
          })
        } else if (result.kind === 'not-submitted') {
          if (origin === 'e09') {
            removeEnvelope(userId, paperId)
            removeIndexEntry(userId, paperId)
            setEnvelope(null)
            setMode('answering')
            setStatusUnknown(false)
            setConflict(false)
            setFrozen(false)
            setSubmitAlert({
              type: 'warning',
              message: '提交结果尚未确认',
              description:
                '服务端尚无成功提交记录，请重新提交（将生成新的提交编号）。',
            })
          } else {
            setNotice('服务端尚无成功提交记录；可使用原提交编号重试。')
          }
        } else if (result.kind === 'status-conflict') {
          setConflict(true)
          setStatusUnknown(true)
          setNotice('提交状态自相矛盾，已保护性冻结；本机记录未做任何清理。')
        } else if (result.reason === 'not-accessible') {
          setNotice('当前试卷不可访问，无法确认最新状态')
        } else {
          setNotice('无法从服务端确认提交状态，请稍后重试。')
        }
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) {
          setNotice('当前账号无权查询该试卷的提交状态。')
        } else {
          setNotice('无法从服务端确认提交状态，请稍后重试。')
        }
      } finally {
        setBusy(false)
      }
    },
    [paperId, applySubmitted, userId],
  )

  const handleFlowResult = useCallback(
    (result: SubmitFlowResult) => {
      // 结果返回后才关闭确认框：提交中按钮禁用，配合 inFlightRef 防双击。
      setConfirmOpen(false)
      if (result.kind === 'submitted') {
        applySubmitted({
          summary: result.summary,
          submittedAt: result.summary.submittedAt,
          source: 'api1',
          authoritative: true,
          cacheOnly: false,
        })
        setSubmitAlert({
          type: 'success',
          message: '提交成功',
          description: '本卷已提交，可查看汇总并回看题目。',
        })
        return
      }
      if (result.kind === 'submitted-without-summary') {
        applySubmitted({
          summary: null,
          submittedAt: null,
          source: 'api1',
          authoritative: true,
          cacheOnly: false,
        })
        setSubmitAlert({
          type: 'success',
          message: '已提交，汇总暂不可用',
          description: '提交已成功，但当前无法解析汇总；可稍后刷新查看。',
        })
        return
      }
      if (result.kind === 'terminal-e08') {
        applySubmitted({
          summary: null,
          submittedAt: null,
          source: 'e08',
          authoritative: true,
          cacheOnly: false,
        })
        setSubmitAlert({
          type: 'info',
          message: '本卷已提交',
          description: '服务端记录本卷已提交，正在确认最新汇总。',
        })
        void enrichAfterE08()
        return
      }
      if (result.kind === 'unauthorized') {
        const existing = readEnvelope(userId, paperId)
        setMode(existing.kind === 'valid' ? 'pending' : 'answering')
        setStatusUnknown(existing.kind === 'valid')
        setSubmitAlert({
          type: 'warning',
          message: '登录失效',
          description: '已保留本机提交记录与答案；登录后可查询状态并按同键重试。',
        })
        return
      }
      if (result.kind === 'check-status') {
        setMode('pending')
        setEnvelope(result.envelope)
        setStatusUnknown(true)
        setSubmitAlert({
          type: 'warning',
          message: '提交状态未确认',
          description: result.message,
        })
        void queryStatus('e09')
        return
      }
      if (result.kind === 'needs-storage-confirmation') {
        setStorageEnvelope(result.envelope)
        return
      }
      if (result.kind === 'envelope-corrupt') {
        setMode('unrecoverable')
        setEnvelope(null)
        setEnvelopeReason(result.reason)
        return
      }
      if (result.kind === 'explicit-failure') {
        const plan = result.plan
        if (plan.action === 'reload-clear') {
          clearDraftAndIndex(userId, paperId)
          removeEnvelope(userId, paperId)
          setAnswers({})
          setFlagged([])
          setEnvelope(null)
          setMode('answering')
          setFrozen(false)
          setConflict(false)
          setStatusUnknown(false)
          setSubmitAlert({ type: 'error', message: plan.message })
          setReloadKey((key) => key + 1)
          return
        }
        if (plan.action === 'restore-answer') {
          const paper = detailRef.current
          if (paper === null) {
            return
          }
          // N04：先从 frozenPayload 重建普通草稿；题目集合不一致则不填旧答案。
          const rebuilt = rebuildDraftFromEnvelope(result.envelope, paper)
          const candidate =
            rebuilt === null
              ? null
              : {
                  ...rebuilt,
                  paperLabel: formatPaperLabel(
                    paper.year,
                    paper.month,
                    paper.paperSet,
                  ),
                }
          const written =
            candidate === null
              ? ({ kind: 'unavailable' } as const)
              : writeDraftVerified(candidate)
          if (candidate !== null && written.kind === 'ok') {
            removeEnvelope(userId, paperId)
            syncIndexPending(userId, paperId, candidate.paperLabel, false)
            setAnswers(candidate.answers)
            setFlagged(candidate.flaggedQuestionIds)
            setPassageIndex(candidate.currentPassageIndex)
            setEnvelope(null)
            setMode('answering')
            setFrozen(false)
            setSubmitAlert({ type: 'warning', message: plan.message })
          } else {
            setMode('pending')
            setEnvelope(result.envelope)
            setStatusUnknown(true)
            setSubmitAlert({
              type: 'warning',
              message: '提交未成功，且本机暂存不可用；已保留提交记录并冻结答案。',
            })
          }
          return
        }
        setEnvelope({ ...result.envelope, state: 'unknown' })
        setMode('pending')
        setStatusUnknown(true)
        setSubmitAlert({
          type: 'warning',
          message: '结果未确认，答案已冻结',
          description: plan.message,
        })
        return
      }
      if (result.kind === 'unknown') {
        setEnvelope({ ...result.envelope, state: 'unknown' })
        setMode('pending')
        setStatusUnknown(true)
        setSubmitAlert({
          type: 'warning',
          message: '结果未确认，答案已冻结',
          description: result.message,
        })
      }
    },
    [
      applySubmitted,
      enrichAfterE08,
      queryStatus,
      userId,
      paperId,
    ],
  )

  const doSubmit = useCallback(async () => {
    if (inFlightRef.current || detail === null || mode !== 'answering' || frozen) {
      return
    }
    inFlightRef.current = true
    setSubmitting(true)
    setSubmitAlert(null)
    clearSaveTimer()
    try {
      const payload = buildSubmitPayload(detail, answersRef.current)
      const result = await runSubmit({
        userId,
        examPaperId: paperId,
        payload,
        storage: storagePort,
        api: apiPort,
      })
      handleFlowResult(result)
    } finally {
      inFlightRef.current = false
      setSubmitting(false)
    }
  }, [
    detail,
    mode,
    frozen,
    clearSaveTimer,
    userId,
    paperId,
    storagePort,
    apiPort,
    handleFlowResult,
  ])

  const confirmMemorySubmit = useCallback(async () => {
    const pendingEnvelope = storageEnvelope
    if (pendingEnvelope === null) {
      return
    }
    setStorageEnvelope(null)
    setSubmitting(true)
    try {
      const result = await sendMemoryEnvelope({
        envelope: pendingEnvelope,
        storage: storagePort,
        api: apiPort,
      })
      handleFlowResult(result)
    } finally {
      setSubmitting(false)
    }
  }, [storageEnvelope, storagePort, apiPort, handleFlowResult])

  const retryPending = useCallback(async () => {
    if (envelope === null || busy) {
      return
    }
    setBusy(true)
    try {
      const result = await retryEnvelope({
        envelope,
        storage: storagePort,
        api: apiPort,
      })
      handleFlowResult(result)
    } finally {
      setBusy(false)
    }
  }, [envelope, busy, storagePort, apiPort, handleFlowResult])

  const clearLocalAttempt = useCallback(() => {
    removeEnvelope(userId, paperId)
    removeSubmitted(userId, paperId)
    clearDraftAndIndex(userId, paperId)
    setEnvelope(null)
    setEnvelopeReason(null)
    setAnswers({})
    setFlagged([])
    setPassageIndex(0)
    setCurrentQuestionId(null)
    setMode('answering')
    setFrozen(false)
    setConflict(false)
    setStatusUnknown(false)
    setBanner(null)
    setSubmitAlert({
      type: 'warning',
      message: '已清除本机提交记录',
      description: '请重新作答；下次交卷将生成新的提交编号。',
    })
  }, [userId, paperId])

  const freezeByTerminalMarker = useCallback(() => {
    const marker = readSubmitted(userId, paperId)
    if (marker.kind !== 'valid') {
      return false
    }
    applySubmittedFromCache(marker.cache, { cacheOnly: false })
    return true
  }, [userId, paperId, applySubmittedFromCache])

  const flushDraft = useCallback(
    (
      nextAnswers: Record<string, OptionLetter>,
      nextFlagged: number[],
      nextPassage: number,
    ) => {
      if (terminalRef.current || modeRef.current !== 'answering' || frozenRef.current) {
        return
      }
      if (hasSubmittedMarker(userId, paperId)) {
        freezeByTerminalMarker()
        return
      }
      const paper = detailRef.current
      if (paper === null) {
        return
      }
      const existing = readDraft(userId, paperId)
      const draft = createDraft({
        userId,
        detail: paper,
        paperLabel: formatPaperLabel(paper.year, paper.month, paper.paperSet),
        answers: nextAnswers,
        flaggedQuestionIds: nextFlagged,
        currentPassageIndex: nextPassage,
        createdAt: existing.kind === 'valid' ? existing.draft.createdAt : undefined,
      })
      const written = persistDraft(draft)
      if (written.kind !== 'ok') {
        setBanner('unavailable')
        return
      }
      setSavedAt(draft.updatedAt)
      setBanner('saved')
    },
    [userId, paperId, freezeByTerminalMarker],
  )

  const scheduleSave = useCallback(
    (
      nextAnswers: Record<string, OptionLetter>,
      nextFlagged: number[],
      nextPassage: number,
    ) => {
      if (terminalRef.current || modeRef.current !== 'answering' || frozenRef.current) {
        return
      }
      clearSaveTimer()
      saveTimerRef.current = window.setTimeout(() => {
        saveTimerRef.current = null
        flushDraft(nextAnswers, nextFlagged, nextPassage)
      }, SAVE_DEBOUNCE_MS)
    },
    [clearSaveTimer, flushDraft],
  )

  useEffect(() => {
    const flushLatest = () => {
      if (saveTimerRef.current !== null) {
        clearSaveTimer()
        flushDraft(answersRef.current, flaggedRef.current, passageRef.current)
      }
    }
    const onHidden = () => {
      if (document.visibilityState === 'hidden') {
        flushLatest()
      }
    }
    document.addEventListener('visibilitychange', onHidden)
    window.addEventListener('pagehide', flushLatest)
    return () => {
      document.removeEventListener('visibilitychange', onHidden)
      window.removeEventListener('pagehide', flushLatest)
    }
  }, [clearSaveTimer, flushDraft])

  useEffect(
    () => () => {
      clearSaveTimer()
    },
    [clearSaveTimer],
  )

  /* ---------- 跨标签终态（N01 必需） ---------- */
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== submittedKey(userId, paperId)) {
        return
      }
      const marker = readSubmitted(userId, paperId)
      if (marker.kind !== 'valid') {
        return
      }
      applySubmittedFromCache(marker.cache, { cacheOnly: false })
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [userId, paperId, applySubmittedFromCache])

  /* ---------- 进入页面：详情成功后再查 API-3 ---------- */
  useEffect(() => {
    if (!Number.isFinite(paperId) || paperId <= 0) {
      setDetailError({ message: '试卷 ID 无效', notFound: true, forbidden: false })
      setBoot('error')
      return
    }
    const controller = new AbortController()
    let cancelled = false
    setBoot('loading')
    setDetailError(null)
    setNotice(null)

    const restoreDraft = (
      draft: { answers: Record<string, OptionLetter>; flaggedQuestionIds: number[]; currentPassageIndex: number; updatedAt: string },
      passageTotal: number,
    ) => {
      setAnswers(draft.answers)
      setFlagged(draft.flaggedQuestionIds)
      setPassageIndex(
        Math.min(Math.max(draft.currentPassageIndex, 0), Math.max(passageTotal - 1, 0)),
      )
      setSavedAt(draft.updatedAt)
      setBanner('restored')
    }

    getListeningPaper(paperId)
      .then(async (paper) => {
        if (cancelled) {
          return
        }
        setDetail(paper)
        const ids = detailQuestionIds(paper)
        const envelopeRead = readEnvelope(userId, paperId)
        const draftRead = readDraft(userId, paperId)
        const draft =
          draftRead.kind === 'valid' &&
          draftMatchesQuestionSet(draftRead.draft, ids) &&
          !hasSubmittedMarker(userId, paperId)
            ? draftRead.draft
            : null

        let status: AttemptStatusResult
        try {
          status = await getAttemptStatus(paperId)
        } catch (error) {
          if (cancelled) {
            return
          }
          if (error instanceof ApiError && error.status === 403) {
            setDetailError({
              message: '当前账号无权作答该试卷',
              notFound: false,
              forbidden: true,
            })
            setBoot('error')
            return
          }
          status = {
            kind: 'status-unavailable',
            reason:
              error instanceof ApiError && error.status === 0 ? 'network' : 'server',
            httpStatus: error instanceof ApiError ? error.status : undefined,
          }
        }
        if (cancelled) {
          return
        }

        if (status.kind === 'submitted') {
          applySubmitted({
            summary: status.status.latestAttempt,
            submittedAt: status.status.latestAttempt?.submittedAt ?? null,
            source: 'api3',
            authoritative: true,
            cacheOnly: false,
          })
        } else if (status.kind === 'submitted-summary-unavailable') {
          applySubmitted({
            summary: null,
            submittedAt: status.submittedAt,
            source: 'api3',
            authoritative: true,
            cacheOnly: false,
          })
        } else if (status.kind === 'not-submitted') {
          if (readSubmitted(userId, paperId).kind === 'valid') {
            removeSubmitted(userId, paperId)
          }
          if (envelopeRead.kind === 'corrupt') {
            setMode('unrecoverable')
            setEnvelope(null)
            setEnvelopeReason(envelopeRead.reason)
          } else if (envelopeRead.kind === 'valid') {
            setMode('pending')
            setEnvelope(envelopeRead.envelope)
            setStatusUnknown(envelopeRead.envelope.state === 'unknown')
            setConflict(false)
            setBanner('pending')
          } else {
            setMode('answering')
            setFrozen(false)
            if (draft !== null) {
              restoreDraft(draft, paper.passages.length)
            } else {
              setBanner(draftRead.kind === 'valid' ? 'stale' : null)
            }
          }
        } else if (status.kind === 'status-conflict') {
          if (envelopeRead.kind === 'valid') {
            setMode('pending')
            setEnvelope(envelopeRead.envelope)
            setStatusUnknown(true)
            setConflict(true)
          } else if (envelopeRead.kind === 'corrupt') {
            setMode('unrecoverable')
            setEnvelopeReason(envelopeRead.reason)
            setConflict(true)
          } else {
            setMode('answering')
            setFrozen(true)
            setConflict(true)
            setNotice('提交状态自相矛盾，已保护性冻结；本机草稿与提交标记均保留。')
            if (draft !== null) {
              restoreDraft(draft, paper.passages.length)
            }
          }
        } else if (status.reason === 'not-accessible') {
          if (envelopeRead.kind === 'corrupt') {
            setMode('unrecoverable')
            setEnvelopeReason(envelopeRead.reason)
          } else if (envelopeRead.kind === 'valid') {
            setMode('pending')
            setEnvelope(envelopeRead.envelope)
            setStatusUnknown(true)
            setNotice(
              '当前试卷不可访问，无法确认最新状态；已保留未确认的提交记录并冻结答案。',
            )
          } else if (readSubmitted(userId, paperId).kind === 'valid') {
            setMode('inaccessible')
            setNotice('当前试卷不可访问，无法确认最新状态')
          } else {
            setMode('answering')
            setFrozen(false)
            if (draft !== null) {
              restoreDraft(draft, paper.passages.length)
            }
            setNotice('当前试卷不可访问，无法确认提交状态；可继续作答，提交时再确认。')
          }
        } else if (status.reason === 'malformed') {
          setNotice('服务端提交状态不可信；可继续作答，提交时再确认。')
          if (envelopeRead.kind === 'valid') {
            setMode('pending')
            setEnvelope(envelopeRead.envelope)
            setStatusUnknown(true)
          } else {
            setMode('answering')
            setFrozen(false)
            if (draft !== null) {
              restoreDraft(draft, paper.passages.length)
            }
          }
        } else if (envelopeRead.kind === 'corrupt') {
          setMode('unrecoverable')
          setEnvelopeReason(envelopeRead.reason)
        } else if (envelopeRead.kind === 'valid') {
          setMode('pending')
          setEnvelope(envelopeRead.envelope)
          setStatusUnknown(true)
          setNotice('无法从服务端确认提交状态；已保留未确认的提交记录并冻结答案。')
        } else {
          const marker = readSubmitted(userId, paperId)
          if (marker.kind === 'valid') {
            applySubmittedFromCache(marker.cache, { cacheOnly: true })
            setNotice('无法从服务端确认最新状态；以下汇总来自本机提交记录。')
          } else {
            setMode('answering')
            setFrozen(false)
            if (draft !== null) {
              restoreDraft(draft, paper.passages.length)
            }
            setNotice('无法确认提交状态；可继续作答，提交时再确认。')
          }
        }

        // 保留期允许时，pending 自动同键重试一次（P-03 未确认时恒为 false）。
        if (
          envelopeRead.kind === 'valid' &&
          status.kind === 'not-submitted' &&
          !autoTriedRef.current
        ) {
          const decision = canAutoRetry(envelopeRead.envelope.requestedAt)
          if (decision.autoRetry) {
            autoTriedRef.current = true
            const retried = await retryEnvelope({
              envelope: envelopeRead.envelope,
              storage: storagePort,
              api: apiPort,
            })
            if (!cancelled) {
              handleFlowResult(retried)
            }
          }
        }
        setBoot('ready')
      })
      .catch((loadError: unknown) => {
        if (cancelled || isAbortError(loadError)) {
          return
        }
        const notFound = loadError instanceof ApiError && loadError.status === 404
        setDetail(null)
        setDetailError({
          message: notFound
            ? '试卷不存在或暂不可用'
            : loadError instanceof Error
              ? loadError.message
              : '试卷加载失败',
          notFound,
          forbidden: false,
        })
        setBoot('error')
      })

    return () => {
      cancelled = true
      controller.abort()
    }
    // 只在试卷/用户/重载变化时重新进入；处理函数内部使用 ref 读取最新状态。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperId, userId, reloadKey])

  /* ---------- 作答交互 ---------- */

  const selectOption = (questionId: number, letter: OptionLetter) => {
    if (mode !== 'answering' || frozen) {
      return
    }
    const next = { ...answers, [String(questionId)]: letter }
    setAnswers(next)
    setCurrentQuestionId(questionId)
    scheduleSave(next, flagged, passageIndex)
  }

  const clearQuestion = (questionId: number) => {
    if (mode !== 'answering' || frozen) {
      return
    }
    const next = { ...answers }
    delete next[String(questionId)]
    setAnswers(next)
    scheduleSave(next, flagged, passageIndex)
  }

  const toggleFlag = (questionId: number) => {
    if (mode !== 'answering' || frozen) {
      return
    }
    const next = flagged.includes(questionId)
      ? flagged.filter((id) => id !== questionId)
      : [...flagged, questionId]
    setFlagged(next)
    scheduleSave(answers, next, passageIndex)
  }

  const navigatePassage = (next: number) => {
    const index = Math.min(Math.max(next, 0), Math.max(totalPassages - 1, 0))
    setPassageIndex(index)
    if (mode === 'answering' && !frozen) {
      scheduleSave(answers, flagged, index)
    }
    window.scrollTo(0, 0)
  }

  const jumpToQuestion = (questionId: number, nextPassageIndex: number) => {
    if (mode !== 'answering' && mode !== 'submitted') {
      return
    }
    setPassageIndex(nextPassageIndex)
    setCurrentQuestionId(questionId)
    const element = document.getElementById(`question-${questionId}`)
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const restart = () => {
    if (envelope !== null) {
      return
    }
    removeDraft(userId, paperId)
    removeIndexEntry(userId, paperId)
    setAnswers({})
    setFlagged([])
    setPassageIndex(0)
    setCurrentQuestionId(null)
    setBanner(null)
    setSavedAt(null)
    setNotice('已清空本机草稿，重新开始作答。')
  }

  /* ---------- 渲染 ---------- */

  if (boot === 'loading') {
    return (
      <Card>
        <Skeleton active paragraph={{ rows: 8 }} />
      </Card>
    )
  }

  if (boot === 'error' || detail === null) {
    return (
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Link to={ROUTES.STUDENT_LISTENING_PAPERS}>
          <ArrowLeftOutlined /> 返回听力练习
        </Link>
        <Alert
          type={detailError?.notFound ? 'warning' : 'error'}
          showIcon
          message={detailError?.message ?? '试卷加载失败'}
          description={
            detailError?.notFound
              ? '该试卷可能尚未开放，或已被老师取消开放。'
              : detailError?.forbidden
                ? '请确认登录账号具备学生作答权限。'
                : undefined
          }
          action={
            detailError?.notFound || detailError?.forbidden ? undefined : (
              <Button size="small" onClick={() => setReloadKey((key) => key + 1)}>
                重试
              </Button>
            )
          }
        />
      </Space>
    )
  }

  const paperLabel = formatPaperLabel(detail.year, detail.month, detail.paperSet)
  const isSubmitted = mode === 'submitted'
  const isPending = mode === 'pending' || mode === 'unrecoverable'
  const readOnly = isSubmitted || isPending || mode === 'inaccessible' || frozen

  const header = (
    <div className="attempt-header">
      <div className="breadcrumb-row">
        <Link to={ROUTES.STUDENT_LISTENING_PAPERS}>
          <ArrowLeftOutlined /> 返回听力练习
        </Link>
        <Typography.Text type="secondary" className="small-text">
          仅当前浏览器保存草稿，不跨设备
        </Typography.Text>
      </div>
      <div className="page-header" style={{ marginBottom: 0 }}>
        <Space direction="vertical" size={4}>
          <Space size={8} wrap>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {paperLabel} · {detail.level}
            </Typography.Title>
            <Tag color="red">仅一次</Tag>
            {isSubmitted && <Tag color="green">已提交</Tag>}
          </Space>
          <Typography.Text type="secondary">
            {formatContentScope(detail.contentScope)} · {formatDuration(detail.durationMs)}
            {` · 共 ${allQuestions.length} 题 / ${totalPassages} 篇`}
          </Typography.Text>
          <Typography.Text type="secondary" className="small-text">
            本卷仅可提交一次；提交后不可修改，可只读回看题目与汇总。
          </Typography.Text>
        </Space>
        {mode === 'answering' && !frozen && (
          <Typography.Text type="secondary" className="small-text">
            已答 {counts.answered}/{counts.total} · 标记 {counts.flagged}
          </Typography.Text>
        )}
      </div>
    </div>
  )

  const answerSheet = (
    <AnswerSheet
      detail={detail}
      answers={readOnly ? {} : answers}
      flaggedQuestionIds={readOnly ? [] : flagged}
      currentQuestionId={currentQuestion?.questionId ?? null}
      mode={isSubmitted ? 'neutral' : 'answering'}
      onJump={jumpToQuestion}
    />
  )

  const questionCards = (questions: PaperQuestion[]) =>
    questions.map((question) => (
      <div key={question.questionId} id={`question-${question.questionId}`}>
        <QuestionCard
          question={question}
          selected={readOnly ? undefined : answers[String(question.questionId)]}
          flagged={readOnly ? false : flagged.includes(question.questionId)}
          readonly={readOnly}
          disabled={submitting}
          onSelect={(letter) => selectOption(question.questionId, letter)}
          onClear={() => clearQuestion(question.questionId)}
          onToggleFlag={() => toggleFlag(question.questionId)}
        />
      </div>
    ))

  const currentPassageCard = (
    <Card>
      {currentPassage === null ? (
        <Empty description="该试卷暂无题目数据" />
      ) : (
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <Space size={8} wrap>
            <Tag color="blue">第 {currentPassage.passageIndex} 篇</Tag>
            <Tag>{currentPassage.passageType}</Tag>
            <Typography.Text strong>{currentPassage.topic || '—'}</Typography.Text>
          </Space>
          {currentPassage.questions.length === 0 ? (
            <Empty description="该篇章暂无题目" />
          ) : (
            questionCards(currentPassage.questions)
          )}
          {!isPending && mode !== 'inaccessible' && (
            <div className="passage-pager">
              <Button disabled={passageIndex <= 0} onClick={() => navigatePassage(passageIndex - 1)}>
                上一篇
              </Button>
              <Typography.Text type="secondary">
                第 {currentPassage.passageIndex} 篇 / 共 {totalPassages} 篇
              </Typography.Text>
              <Button
                type="primary"
                disabled={passageIndex >= totalPassages - 1}
                onClick={() => navigatePassage(passageIndex + 1)}
              >
                下一篇
              </Button>
            </div>
          )}
        </Space>
      )}
    </Card>
  )

  const pendingView = (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      <PendingPanel
        envelope={envelope}
        unrecoverableReason={
          mode === 'unrecoverable' ? (envelopeReason ?? 'invalid-payload') : undefined
        }
        statusUnknown={statusUnknown}
        conflict={conflict}
        retention={retention}
        counts={draftCounts}
        busy={busy}
        onRetry={() => void retryPending()}
        onQuery={() => void queryStatus('manual')}
        onClear={clearLocalAttempt}
      />
      {notice && <Alert type="info" showIcon message={notice} />}
      {submitAlert && (
        <SubmitResultAlert
          type={submitAlert.type}
          message={submitAlert.message}
          description={submitAlert.description}
        />
      )}
      {currentPassageCard}
    </Space>
  )

  const submittedView = (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      <Alert
        type="success"
        showIcon
        message="已提交 · 只读回看"
        description="本卷已提交，不能再修改答案；可回看题目与汇总。"
      />
      {submitAlert && (
        <SubmitResultAlert
          type={submitAlert.type}
          message={submitAlert.message}
          description={submitAlert.description}
        />
      )}
      <SubmitSummaryPanel
        summary={summary}
        submittedAt={submittedAt}
        authoritative={authoritative}
        cacheOnly={cacheOnly}
        versionNotice={versionNotice}
      />
      {currentPassageCard}
    </Space>
  )

  const inaccessibleView = (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      {notice && <Alert type="warning" showIcon message={notice} />}
      <Alert
        type="info"
        showIcon
        message="本机记录显示本卷可能已提交，但当前无法从服务端确认"
        description="为避免重复提交，本页只读；不展示本机汇总，也不会生成新的提交编号。"
      />
      <SubmitSummaryPanel
        summary={null}
        submittedAt={null}
        authoritative={false}
        cacheOnly={false}
      />
      {currentPassageCard}
    </Space>
  )

  const layoutWithSheet = (main: ReactNode) =>
    wide ? (
      <div className="attempt-layout">
        <div className="attempt-main">{main}</div>
        <aside className="attempt-side">
          <div className="attempt-side-sticky">{answerSheet}</div>
        </aside>
      </div>
    ) : (
      <Space direction="vertical" size={14} style={{ width: '100%' }}>
        <details className="answer-sheet-collapse" open>
          <summary>答题卡（可折叠）</summary>
          {answerSheet}
        </details>
        {main}
      </Space>
    )

  return (
    <Space direction="vertical" size={14} style={{ width: '100%' }}>
      {header}

      {mode === 'answering' && banner && (
        <DraftBanner
          kind={banner}
          savedAt={savedAt}
          answered={counts.answered}
          total={counts.total}
          canRestart={envelope === null && !frozen}
          onRestart={restart}
        />
      )}

      {mode === 'answering' && notice && (
        <Alert type="info" showIcon message={notice} />
      )}

      {mode === 'answering' && submitAlert && (
        <SubmitResultAlert
          type={submitAlert.type}
          message={submitAlert.message}
          description={submitAlert.description}
          actions={
            submitAlert.type === 'warning'
              ? [
                  {
                    key: 'query',
                    label: '查询提交状态',
                    onClick: () => void queryStatus('manual'),
                  },
                ]
              : undefined
          }
        />
      )}

      {mode === 'answering' && conflict && (
        <Alert
          type="error"
          showIcon
          message="提交状态自相矛盾，已保护性冻结"
          description="本机草稿、提交记录均保留；请重新查询提交状态，确认前不可修改答案。"
        />
      )}

      {/* 播放器页面级常驻：翻篇只换题目，不重载音频、不回到 0 秒 */}
      <AudioPlayer
        examPaperId={detail.examPaperId}
        fallbackDurationMs={detail.durationMs}
        sticky
      />

      {mode === 'pending' && pendingView}
      {mode === 'unrecoverable' && pendingView}
      {mode === 'submitted' && layoutWithSheet(submittedView)}
      {mode === 'inaccessible' && inaccessibleView}

      {mode === 'answering' && (
        <>
          {layoutWithSheet(currentPassageCard)}
          <div className="submit-bar">
            <Typography.Text type="secondary">
              已答 {counts.answered}/{counts.total} · 未答 {counts.unanswered} · 标记{' '}
              {counts.flagged}
            </Typography.Text>
            <Button
              type="primary"
              loading={submitting}
              disabled={submitting || frozen}
              onClick={() => setConfirmOpen(true)}
            >
              交卷
            </Button>
          </div>
        </>
      )}

      <SubmitConfirmModal
        open={confirmOpen}
        counts={counts}
        submitting={submitting}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => void doSubmit()}
      />

      <Modal
        open={storageEnvelope !== null}
        title="本机提交记录暂存失败"
        okText="仍要提交"
        cancelText="返回检查"
        onCancel={() => setStorageEnvelope(null)}
        onOk={() => void confirmMemorySubmit()}
        centered
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message="本机暂存不可用"
            description="浏览器禁用存储或空间已满。刷新或关闭后可能无法恢复本次提交记录；若已发出请求，仍可能提交成功。"
          />
          <Typography.Text type="secondary">
            选择“仍要提交”将使用内存中的提交编号发送，且不会写入本机。
          </Typography.Text>
        </Space>
      </Modal>
    </Space>
  )
}
