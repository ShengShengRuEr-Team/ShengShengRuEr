import type {
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
