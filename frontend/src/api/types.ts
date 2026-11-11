/**
 * 后端接口 DTO 类型，字段与 backend/app/schemas.py 逐字对应（snake_case）。
 * 本文件只描述「后端返回什么」，组件使用的 camelCase 模型在 api/adapters.ts 中转换。
 */

/** 统一响应外壳：{ code, msg, data }。 */
export interface ApiResponse<T> {
  code: number
  msg: string
  data: T | null
}

/* ---------- 认证 ---------- */

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginData {
  token: string
  token_type: string
  expires_in: number
}

export interface UserInfoDto {
  user_id: number
  username: string
  nickname: string
}

export interface GetInfoData {
  user: UserInfoDto
  roles: string[]
  is_admin: boolean
}

/* ---------- 听力试卷（模块二） ---------- */

/** 试卷列表项，接口 ① 与 ④ 的公共部分。 */
export interface PaperListItemDto {
  exam_paper_id: number
  exam_paper_code: string
  exam_level: string
  exam_year: number
  exam_month: number
  paper_set: number
  content_scope: string
  audio_url: string
  duration_ms: number | null
}

export interface PaperListData {
  items: PaperListItemDto[]
}

export interface OptionDto {
  label: string
  text: string
}

export interface QuestionStudentDto {
  question_no: number
  question_id: number
  question_text: string
  options: OptionDto[]
}

export interface PassageStudentDto {
  passage_id: number
  passage_index: number
  passage_type: string
  topic: string
  questions: QuestionStudentDto[]
}

/** 学生视角整卷（接口 ②）：不含答案、解析与听力正文。 */
export interface PaperDetailStudentDto extends PaperListItemDto {
  passages: PassageStudentDto[]
}

export interface SegmentDto {
  segment_id: number
  segment_index: number
  segment_type: string
  text: string
  speaker_code: string
  start_ms: number
  end_ms: number
}

/** 管理员题目（接口 ④）：在学生字段上追加答案、解析与审核状态。 */
export interface QuestionAdminDto extends QuestionStudentDto {
  correct_option: string
  correct_option_base: string
  explanation_text: string
  explanation_source: string
  question_index: number | null
  content_state: string
  review_status: string
}

export interface PassageAdminDto {
  passage_id: number
  passage_index: number
  passage_type: string
  topic: string
  scene: string
  accent: string
  review_status: string
  start_ms: number
  body_end_ms: number | null
  end_ms: number | null
  segments: SegmentDto[]
  questions: QuestionAdminDto[]
}

/** 管理员配套内容（接口 ④）。 */
export interface PaperCompanionDto extends PaperListItemDto {
  batch_code: string | null
  is_current: boolean
  check_passed: boolean
  is_visible: boolean
  is_pending_confirmation: boolean
  mapping_source: string
  review_status: string
  passages: PassageAdminDto[]
}

export interface CheckIssueDto {
  kind: string
  message: string
}

/** 最低内容检查结果（接口 ⑥）：只读最近一次持久化记录。 */
export interface CheckResultDto {
  exam_paper_id: number
  batch_code: string | null
  is_passed: boolean
  issues: CheckIssueDto[]
  checked_at: string | null
}

export type VisibilityAction = 'confirm' | 'cancel'

export interface VisibilityRequest {
  action: VisibilityAction
  reason?: string
}

/** 可见性操作结果（接口 ⑤）。 */
export interface VisibilityStateDto {
  exam_paper_id: number
  batch_code: string | null
  is_visible: boolean
  check_passed: boolean
  action: string
}
