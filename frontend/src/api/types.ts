/**
 * 后端接口 DTO 类型，字段与 backend/app/schemas.py 逐字对应（snake_case）。
 * 本文件只描述「后端返回什么」，不要在这里加前端视图字段；
 * 组件使用的 camelCase 模型在 api/adapters.ts 中转换。
 */

/** 统一响应外壳：{ code, msg, data }。 */
export interface ApiResponse<T> {
  code: number
  msg: string
  data: T | null
}

/* ---------- 认证（接口 1–3） ---------- */

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
  permissions: string[]
  is_admin: boolean
}

/* ---------- 学生可读内容（接口 4–5） ---------- */

export interface PaperDto {
  id: number
  title: string
  exam_level: string
  exam_year: number
  exam_month: number
  set_no: number
}

export interface PaperListData {
  items: PaperDto[]
  total: number
}

/** 学生视图白名单：不含 correct_option / explanation_text / transcript_text。 */
export interface StudentQuestionDto {
  id: number
  question_no: number
  prompt_text: string | null
  option_a: string | null
  option_b: string | null
  option_c: string | null
  option_d: string | null
}

export interface StudentQuestionListData {
  items: StudentQuestionDto[]
  total: number
}

/* ---------- 管理端敏感内容（接口 6） ---------- */

/** 管理端视图：在学生字段基础上显式增加答案、解析与听力原文。 */
export interface AdminQuestionDto extends StudentQuestionDto {
  correct_option: string | null
  explanation_text: string | null
  transcript_text: string | null
}

export interface AdminQuestionListData {
  items: AdminQuestionDto[]
  total: number
}

/* ---------- 管理端处理任务（接口 7–9） ---------- */

/** 任务状态枚举，与 backend/app/core/constants.py 保持一致。 */
export const TASK_STATUSES = [
  'pending',
  'running',
  'failed',
  'pending_confirm',
  'completed',
] as const

export type TaskStatus = (typeof TASK_STATUSES)[number]

export interface TaskCreateRequest {
  paper_id: number
}

/**
 * 任务详情。后端 schema 中 status 为普通字符串（枚举校验在接口层），
 * 这里保留 string，展示前用 isTaskStatus 收窄。
 */
export interface TaskDto {
  id: number
  paper_id: number | null
  task_type: string
  status: string
  progress: number
  message: string | null
  result: Record<string, unknown> | null
  created_by: number | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

/** 任务列表项，字段比详情少（见 schemas.TaskListItem）。 */
export interface TaskListItemDto {
  id: number
  paper_id: number | null
  task_type: string
  status: string
  progress: number
  message: string | null
  created_at: string
}

export interface TaskListData {
  items: TaskListItemDto[]
  total: number
}

/** 任务列表可选查询参数；非法值由后端返回 400。 */
export interface TaskListQuery {
  status?: TaskStatus
}

export function isTaskStatus(value: string): value is TaskStatus {
  return (TASK_STATUSES as readonly string[]).includes(value)
}
