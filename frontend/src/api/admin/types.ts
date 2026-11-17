/** 管理端日志 DTO（与 backend/app/schemas_admin/logs.py 逐字对应）。 */

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface LoginLogDto {
  event_id: string
  request_id: string
  occurred_at: string
  event_type: string
  username_attempted: string
  actor_user_id: number | null
  actor_name: string
  role_snapshot: string | null
  result: string
  reason_code: string | null
  ip: string | null
  user_agent_summary: string
  duration_ms: number
}

export interface OperationLogDto {
  event_id: string
  request_id: string
  occurred_at: string
  event_type: string
  actor_user_id: number | null
  actor_name: string
  role_snapshot: string | null
  target_type: string | null
  target_id: string | null
  result: string
  reason_code: string | null
  summary: Record<string, unknown>
  ip: string | null
  user_agent_summary: string
  duration_ms: number
  run_id: string | null
}

export type LoginLogPageDto = PageResult<LoginLogDto>
export type OperationLogPageDto = PageResult<OperationLogDto>

/* ---------- 用户与本人（T03-FE） ---------- */

export interface UserDto {
  id: number
  username: string
  nickname: string
  role: string | null
  status: string
  created_at: string
  updated_at: string
}

export type UserPageDto = PageResult<UserDto>

export interface UserQuery {
  username?: string
  nickname?: string
  role?: string
  status?: string
  page?: number
  page_size?: number
}

export interface UserCreateRequest {
  username: string
  password: string
  nickname?: string
  role?: 'admin' | 'student'
}

export interface UserStatusRequest {
  status: 'active' | 'disabled'
  reason: string
}

export interface UserStatusResultDto {
  id: number
  status: string
  changed: boolean
  revoked_session_count: number
}

export interface PasswordResetResultDto {
  id: number
  changed: boolean
  revoked_session_count: number
}

export interface ResetPasswordRequest {
  new_password: string
  reason: string
}

export interface SelfPasswordRequest {
  old_password: string
  new_password: string
}

export interface SelfPasswordResultDto {
  changed: boolean
  reauth_required: boolean
}
