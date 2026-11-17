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


/* ---------- 首页汇总（T05） ---------- */

export interface DashboardCacheDto {
  enabled: boolean
  status: 'hit' | 'miss' | 'not_configured'
  ttl_seconds: number
  cached_at: string | null
  expires_at: string | null
  age_seconds: number | null
}

export interface DashboardCardsDto {
  paper_count: number
  awaiting_visibility_count: number
  failed_check_count: number
  active_student_count: number
  disabled_student_count: number
  successful_attempts_7d: number
}

export interface DashboardDto {
  as_of: string
  window_start: string
  window_end: string
  timezone: string
  cache: DashboardCacheDto
  cards: DashboardCardsDto
}


/* ---------- 留存调度（T07） ---------- */

export interface JobDefinitionDto {
  job_id: string
  enabled: boolean
  timezone: string
  next_scheduled_at: string | null
  last_scheduled_slot: string | null
  last_run_id: string | null
  active_run_id: string | null
  missed_slots: number
  updated_at: string
}

export interface SchedulerInstanceDto {
  instance_id: string
  booted_at: string
  heartbeat_at: string
  last_error_code: string | null
  state: string | null
  version: number
}

export interface JobOverviewDto {
  job: JobDefinitionDto
  scheduler_health: 'ok' | 'stale' | 'not_configured' | string
  instances: SchedulerInstanceDto[]
}

export interface JobRunDto {
  id: string
  job_id: string
  trigger: string
  slot_key: string | null
  actor_id: number | null
  state: string
  queued_at: string | null
  started_at: string | null
  finished_at: string | null
  heartbeat_at: string | null
  attempt_count: number
  retry_at: string | null
  retry_pending: boolean
  counts: Record<string, number>
  counts_complete: boolean
  error_code: string | null
  created_at: string
}

export type JobRunPageDto = PageResult<JobRunDto>
