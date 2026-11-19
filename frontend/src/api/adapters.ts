import type {
  AttemptStatusDto,
  AttemptSummaryDto,
  CheckIssueDto,
  CheckResultDto,
  GetInfoData,
  PaperCompanionDto,
  PaperDetailStudentDto,
  PaperListItemDto,
  PassageAdminDto,
  PassageStudentDto,
  QuestionAdminDto,
  QuestionStudentDto,
  SegmentDto,
  VisibilityStateDto,
} from './types'

/* ---------- 认证视图模型 ---------- */

export interface AuthUser {
  userId: number
  username: string
  nickname: string
}

export interface AuthProfile {
  user: AuthUser
  roles: string[]
  isAdmin: boolean
}

export function toAuthProfile(data: GetInfoData): AuthProfile {
  return {
    user: {
      userId: data.user.user_id,
      username: data.user.username,
      nickname: data.user.nickname,
    },
    roles: data.roles,
    isAdmin: data.is_admin,
  }
}

/* ---------- 听力试卷视图模型 ---------- */

export interface PaperSummary {
  examPaperId: number
  code: string
  level: string
  year: number
  month: number
  paperSet: number
  contentScope: string
  audioUrl: string
  durationMs: number | null
}

export interface PaperOption {
  label: string
  text: string
}

export interface PaperQuestion {
  questionNo: number
  questionId: number
  questionText: string
  options: PaperOption[]
}

export interface PaperPassage {
  passageId: number
  passageIndex: number
  passageType: string
  topic: string
  questions: PaperQuestion[]
}

export interface PaperDetail extends PaperSummary {
  passages: PaperPassage[]
}

export interface PaperSegment {
  segmentId: number
  segmentIndex: number
  segmentType: string
  text: string
  speakerCode: string
  startMs: number
  endMs: number
}

export interface AdminQuestion extends PaperQuestion {
  correctOption: string
  correctOptionBase: string
  explanationText: string
  explanationSource: string
  questionIndex: number | null
  contentState: string
  reviewStatus: string
}

export interface AdminPassage {
  passageId: number
  passageIndex: number
  passageType: string
  topic: string
  scene: string
  accent: string
  reviewStatus: string
  startMs: number
  bodyEndMs: number | null
  endMs: number | null
  segments: PaperSegment[]
  questions: AdminQuestion[]
}

export interface PaperCompanion extends PaperSummary {
  batchId: number | null
  resultHash: string | null
  batchCode: string | null
  isCurrent: boolean
  checkPassed: boolean
  isVisible: boolean
  isPendingConfirmation: boolean
  mappingSource: string
  reviewStatus: string
  passages: AdminPassage[]
}

export interface CheckIssue {
  kind: string
  message: string
}

export interface ContentCheck {
  examPaperId: number
  batchCode: string | null
  isPassed: boolean
  issues: CheckIssue[]
  checkedAt: string | null
}

export interface VisibilityResult {
  examPaperId: number
  batchCode: string | null
  isVisible: boolean
  checkPassed: boolean
  action: string
}

export function toPaperSummary(dto: PaperListItemDto): PaperSummary {
  return {
    examPaperId: dto.exam_paper_id,
    code: dto.exam_paper_code,
    level: dto.exam_level,
    year: dto.exam_year,
    month: dto.exam_month,
    paperSet: dto.paper_set,
    contentScope: dto.content_scope,
    audioUrl: dto.audio_url,
    durationMs: dto.duration_ms,
  }
}

function toQuestion(dto: QuestionStudentDto): PaperQuestion {
  return {
    questionNo: dto.question_no,
    questionId: dto.question_id,
    questionText: dto.question_text,
    options: dto.options.map((option) => ({ label: option.label, text: option.text })),
  }
}

function toPassage(dto: PassageStudentDto): PaperPassage {
  return {
    passageId: dto.passage_id,
    passageIndex: dto.passage_index,
    passageType: dto.passage_type,
    topic: dto.topic,
    questions: dto.questions.map(toQuestion),
  }
}

export function toPaperDetail(dto: PaperDetailStudentDto): PaperDetail {
  return {
    ...toPaperSummary(dto),
    passages: dto.passages.map(toPassage),
  }
}

function toSegment(dto: SegmentDto): PaperSegment {
  return {
    segmentId: dto.segment_id,
    segmentIndex: dto.segment_index,
    segmentType: dto.segment_type,
    text: dto.text,
    speakerCode: dto.speaker_code,
    startMs: dto.start_ms,
    endMs: dto.end_ms,
  }
}

function toAdminQuestion(dto: QuestionAdminDto): AdminQuestion {
  return {
    ...toQuestion(dto),
    correctOption: dto.correct_option,
    correctOptionBase: dto.correct_option_base,
    explanationText: dto.explanation_text,
    explanationSource: dto.explanation_source,
    questionIndex: dto.question_index,
    contentState: dto.content_state,
    reviewStatus: dto.review_status,
  }
}

function toAdminPassage(dto: PassageAdminDto): AdminPassage {
  return {
    passageId: dto.passage_id,
    passageIndex: dto.passage_index,
    passageType: dto.passage_type,
    topic: dto.topic,
    scene: dto.scene,
    accent: dto.accent,
    reviewStatus: dto.review_status,
    startMs: dto.start_ms,
    bodyEndMs: dto.body_end_ms,
    endMs: dto.end_ms,
    segments: dto.segments.map(toSegment),
    questions: dto.questions.map(toAdminQuestion),
  }
}

export function toPaperCompanion(dto: PaperCompanionDto): PaperCompanion {
  return {
    ...toPaperSummary(dto),
    batchId: dto.batch_id,
    resultHash: dto.result_hash,
    batchCode: dto.batch_code,
    isCurrent: dto.is_current,
    checkPassed: dto.check_passed,
    isVisible: dto.is_visible,
    isPendingConfirmation: dto.is_pending_confirmation,
    mappingSource: dto.mapping_source,
    reviewStatus: dto.review_status,
    passages: dto.passages.map(toAdminPassage),
  }
}

function toCheckIssue(dto: CheckIssueDto): CheckIssue {
  return { kind: dto.kind, message: dto.message }
}

export function toContentCheck(dto: CheckResultDto): ContentCheck {
  return {
    examPaperId: dto.exam_paper_id,
    batchCode: dto.batch_code,
    isPassed: dto.is_passed,
    issues: dto.issues.map(toCheckIssue),
    checkedAt: dto.checked_at,
  }
}

export function toVisibilityResult(dto: VisibilityStateDto): VisibilityResult {
  return {
    examPaperId: dto.exam_paper_id,
    batchCode: dto.batch_code,
    isVisible: dto.is_visible,
    checkPassed: dto.check_passed,
    action: dto.action,
  }
}

/* ---------- 作答视图模型（前端只从本文件导入） ---------- */

/** 原卷展示字母；契约只接受大写 A–D。 */
export type OptionLetter = 'A' | 'B' | 'C' | 'D'

export function isOptionLetter(value: unknown): value is OptionLetter {
  return value === 'A' || value === 'B' || value === 'C' || value === 'D'
}

export interface AttemptPracticeScore {
  available: boolean
  value: number | null
  max: number | null
  label: string
  reason: string | null
}

/** API-1 成功汇总 / API-3 最新汇总（camelCase）。 */
export interface AttemptSummary {
  attemptCode: string
  examPaperId: number
  submittedAt: string
  questionCount: number
  correctCount: number
  correctRate: number
  practiceScore: AttemptPracticeScore
}

export interface AttemptStatus {
  examPaperId: number
  submitted: boolean
  attemptCount: number
  latestAttempt: AttemptSummary | null
}

/**
 * API-3 分层结果（需求 §3.7）：
 * - submitted：确定已提交且有完整汇总；
 * - submitted-summary-unavailable：确定已提交、仅汇总不可用（仍只读）；
 * - not-submitted：确定未提交；
 * - status-conflict：契约自相矛盾，保护性冻结；
 * - status-unavailable：查询失败/结构非法，按原因降级。
 */
export type AttemptStatusResult =
  | { kind: 'submitted'; status: AttemptStatus }
  | {
      kind: 'submitted-summary-unavailable'
      examPaperId: number
      attemptCount: number
      submittedAt: string | null
    }
  | { kind: 'not-submitted'; status: AttemptStatus }
  | {
      kind: 'status-conflict'
      reason: 'false-with-latest' | 'false-with-count' | 'true-without-count' | 'paper-id-mismatch'
      examPaperId: number
      attemptCount: number
    }
  | {
      kind: 'status-unavailable'
      reason: 'not-accessible' | 'server' | 'network' | 'malformed'
      httpStatus?: number
    }

/** API-1 成功结果：200 但汇总不可解析仍视为已提交（不重试）。 */
export type AttemptSubmitSuccess =
  | { kind: 'submitted'; summary: AttemptSummary }
  | { kind: 'submitted-without-summary'; examPaperId: number }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonNegativeInt(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

function isIsoDateTime(value: unknown): value is string {
  return typeof value === 'string' && !Number.isNaN(Date.parse(value))
}

function parsePracticeScore(value: unknown): AttemptPracticeScore | null {
  if (!isRecord(value)) {
    return null
  }
  if (typeof value.available !== 'boolean') {
    return null
  }
  if (typeof value.max !== 'number' || !Number.isFinite(value.max)) {
    return null
  }
  if (typeof value.label !== 'string') {
    return null
  }
  if (value.reason !== null && typeof value.reason !== 'string') {
    return null
  }
  if (value.available) {
    if (typeof value.value !== 'number' || !Number.isFinite(value.value)) {
      return null
    }
  } else if (value.value !== null) {
    return null
  }
  return {
    available: value.available,
    value: value.value as number | null,
    max: value.max,
    label: value.label,
    reason: value.reason as string | null,
  }
}

/** 严格解析 API-1/API-3 汇总；任一必填字段缺失或类型非法返回 null。 */
export function parseAttemptSummary(
  dto: AttemptSummaryDto | Record<string, unknown> | null | undefined,
): AttemptSummary | null {
  if (!isRecord(dto)) {
    return null
  }
  const {
    attempt_code,
    exam_paper_id,
    submitted_at,
    question_count,
    correct_count,
    correct_rate,
    practice_score,
  } = dto
  if (typeof attempt_code !== 'string' || attempt_code.length === 0) {
    return null
  }
  if (typeof exam_paper_id !== 'number' || !Number.isInteger(exam_paper_id)) {
    return null
  }
  if (!isIsoDateTime(submitted_at)) {
    return null
  }
  if (
    !isNonNegativeInt(question_count) ||
    !isNonNegativeInt(correct_count) ||
    !isNonNegativeInt(correct_rate)
  ) {
    return null
  }
  if (correct_rate > 100 || correct_count > question_count) {
    return null
  }
  const practiceScore = parsePracticeScore(practice_score)
  if (practiceScore === null) {
    return null
  }
  return {
    attemptCode: attempt_code,
    examPaperId: exam_paper_id,
    submittedAt: submitted_at,
    questionCount: question_count,
    correctCount: correct_count,
    correctRate: correct_rate,
    practiceScore,
  }
}

export function toAttemptSummary(dto: AttemptSummaryDto): AttemptSummary {
  const summary = parseAttemptSummary(dto)
  if (summary === null) {
    throw new Error('作答汇总字段非法')
  }
  return summary
}

/**
 * API-3 分层解析（N02/AC-47/AC-48）：
 * 先校验结构与语义不变量，再区分「确定已提交」与「状态冲突」。
 */
export function toAttemptStatusResult(
  data: unknown,
  expectedPaperId: number,
): AttemptStatusResult {
  if (!isRecord(data)) {
    return { kind: 'status-unavailable', reason: 'malformed' }
  }
  const dto = data as unknown as AttemptStatusDto
  if (dto.exam_paper_id !== expectedPaperId) {
    return { kind: 'status-unavailable', reason: 'malformed' }
  }
  if (typeof dto.submitted !== 'boolean') {
    return { kind: 'status-unavailable', reason: 'malformed' }
  }
  if (!isNonNegativeInt(dto.attempt_count)) {
    return { kind: 'status-unavailable', reason: 'malformed' }
  }

  const latestRaw = dto.latest_attempt
  if (latestRaw !== null && latestRaw !== undefined && !isRecord(latestRaw)) {
    return { kind: 'status-unavailable', reason: 'malformed' }
  }
  const conflict = (
    reason:
      | 'false-with-latest'
      | 'false-with-count'
      | 'true-without-count'
      | 'paper-id-mismatch',
  ): AttemptStatusResult => ({
    kind: 'status-conflict',
    reason,
    examPaperId: expectedPaperId,
    attemptCount: dto.attempt_count,
  })

  if (latestRaw !== null && latestRaw !== undefined) {
    const nestedPaperId = (latestRaw as Record<string, unknown>).exam_paper_id
    if (typeof nestedPaperId !== 'number') {
      return { kind: 'status-unavailable', reason: 'malformed' }
    }
    if (nestedPaperId !== expectedPaperId) {
      return conflict('paper-id-mismatch')
    }
  }
  if (!dto.submitted && latestRaw !== null && latestRaw !== undefined) {
    return conflict('false-with-latest')
  }
  if (!dto.submitted && dto.attempt_count > 0) {
    return conflict('false-with-count')
  }
  if (dto.submitted && dto.attempt_count === 0) {
    return conflict('true-without-count')
  }

  if (!dto.submitted) {
    return {
      kind: 'not-submitted',
      status: {
        examPaperId: expectedPaperId,
        submitted: false,
        attemptCount: 0,
        latestAttempt: null,
      },
    }
  }

  const summary = parseAttemptSummary(latestRaw)
  if (summary === null) {
    return {
      kind: 'submitted-summary-unavailable',
      examPaperId: expectedPaperId,
      attemptCount: dto.attempt_count,
      submittedAt: isIsoDateTime(
        (latestRaw as Record<string, unknown> | null)?.submitted_at,
      )
        ? ((latestRaw as Record<string, unknown>).submitted_at as string)
        : null,
    }
  }
  return {
    kind: 'submitted',
    status: {
      examPaperId: expectedPaperId,
      submitted: true,
      attemptCount: dto.attempt_count,
      latestAttempt: summary,
    },
  }
}

/** API-1 成功解析：汇总不可解析或试卷 ID 不符时按「已提交、无汇总」处理。 */
export function toAttemptSubmitSuccess(
  data: unknown,
  examPaperId: number,
): AttemptSubmitSuccess {
  const summary = parseAttemptSummary(
    isRecord(data) ? (data as Record<string, unknown>) : null,
  )
  if (summary !== null && summary.examPaperId === examPaperId) {
    return { kind: 'submitted', summary }
  }
  return { kind: 'submitted-without-summary', examPaperId }
}
