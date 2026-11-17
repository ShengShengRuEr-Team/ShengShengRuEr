// 本文件由 backend/scripts/generate_admin_constants.py 生成，请勿手工修改。
// 修改后端枚举或权限码后运行：python scripts/generate_admin_constants.py
// 只用于前端展示与显隐，不替代服务端鉴权。

export const ADMIN_PERMISSIONS = [
  'admin:user:read',
  'admin:user:create',
  'admin:user:update',
  'admin:user:status',
  'admin:user:resetPassword',
  'admin:self:read',
  'admin:self:update',
  'admin:self:password',
  'admin:session:read',
  'admin:session:revoke',
  'admin:log:read',
  'admin:docs:read',
  'admin:docs:debug',
  'admin:monitor:read',
  'admin:job:read',
  'admin:job:control',
  'admin:cache:clear',
  'admin:dashboard:read',
  'admin:export:users',
  'admin:export:loginLogs',
  'admin:export:operationLogs',
] as const

export const PERM_CACHE_CLEAR = 'admin:cache:clear'

export const PERM_DASHBOARD_READ = 'admin:dashboard:read'

export const PERM_DOCS_DEBUG = 'admin:docs:debug'

export const PERM_DOCS_READ = 'admin:docs:read'

export const PERM_EXPORT_LOGIN_LOGS = 'admin:export:loginLogs'

export const PERM_EXPORT_OPERATION_LOGS = 'admin:export:operationLogs'

export const PERM_EXPORT_USERS = 'admin:export:users'

export const PERM_JOB_CONTROL = 'admin:job:control'

export const PERM_JOB_READ = 'admin:job:read'

export const PERM_LOG_READ = 'admin:log:read'

export const PERM_MONITOR_READ = 'admin:monitor:read'

export const PERM_SELF_PASSWORD = 'admin:self:password'

export const PERM_SELF_READ = 'admin:self:read'

export const PERM_SELF_UPDATE = 'admin:self:update'

export const PERM_SESSION_READ = 'admin:session:read'

export const PERM_SESSION_REVOKE = 'admin:session:revoke'

export const PERM_USER_CREATE = 'admin:user:create'

export const PERM_USER_READ = 'admin:user:read'

export const PERM_USER_RESET_PASSWORD = 'admin:user:resetPassword'

export const PERM_USER_STATUS = 'admin:user:status'

export const PERM_USER_UPDATE = 'admin:user:update'

export const EVENT_TYPES = [
  'CACHE_CLEARED',
  'CACHE_CLEAR_STARTED',
  'DOC_GET_DEBUG',
  'EXPORT_COMPLETED',
  'EXPORT_FAILED',
  'JOB_FINISHED',
  'JOB_PAUSED',
  'JOB_RESUMED',
  'JOB_TRIGGERED',
  'LOGIN_FAILED',
  'LOGIN_SUCCEEDED',
  'LOGOUT',
  'PASSWORD_RESET',
  'PROFILE_UPDATED',
  'SELF_PASSWORD_CHANGED',
  'SESSION_REVOKED',
  'USER_CREATED',
  'USER_STATUS_CHANGED',
] as const

export const LOG_RESULTS = [
  'SUCCESS',
  'FAILURE',
] as const

export const LOGIN_FAILURE_TYPES = [
  'UNKNOWN_ACCOUNT',
  'BAD_PASSWORD',
  'DISABLED',
] as const

export const ACCOUNT_STATUSES = [
  'active',
  'disabled',
] as const

export const ROLE_KEYS = [
  'admin',
  'student',
] as const

export const REVOKE_REASONS = [
  'account_disabled',
  'password_changed',
  'password_reset',
  'kicked',
  'logout',
] as const

export const TARGET_TYPES = [
  'user',
  'session',
  'job',
  'cache',
  'export',
  'docs',
] as const

export const MONITOR_STATES = [
  'ok',
  'error',
  'unknown',
  'stale',
  'not_configured',
  'not_applicable',
] as const

export const SEVERITIES = [
  'normal',
  'warning',
  'critical',
  'none',
] as const

export const RUN_STATES = [
  'QUEUED',
  'RUNNING',
  'SUCCEEDED',
  'PARTIAL',
  'FAILED',
  'INTERRUPTED',
] as const

export const SEGMENT_TYPES = [
  'body',
  'question',
] as const

export const VISIBILITY_ACTIONS = [
  'confirm',
  'cancel',
] as const

export const EXAM_LEVELS = [
  'CET4',
] as const

export const EVENT_TYPE_LABELS: Record<string, string> = {
  CACHE_CLEARED: '缓存清理完成',
  CACHE_CLEAR_STARTED: '缓存清理开始',
  DOC_GET_DEBUG: '文档调试请求',
  EXPORT_COMPLETED: '导出生成完成',
  EXPORT_FAILED: '导出失败',
  JOB_FINISHED: '任务结束',
  JOB_PAUSED: '任务暂停',
  JOB_RESUMED: '任务恢复',
  JOB_TRIGGERED: '任务触发',
  LOGIN_FAILED: '登录失败',
  LOGIN_SUCCEEDED: '登录成功',
  LOGOUT: '退出登录',
  PASSWORD_RESET: '重置密码',
  PROFILE_UPDATED: '更新资料',
  SELF_PASSWORD_CHANGED: '本人改密',
  SESSION_REVOKED: '强制下线',
  USER_CREATED: '创建用户',
  USER_STATUS_CHANGED: '启停账号',
}

export const LOGIN_FAILURE_LABELS: Record<string, string> = {
  BAD_PASSWORD: '密码错误',
  DISABLED: '账号停用',
  UNKNOWN_ACCOUNT: '账号不存在',
}

export const LOG_RESULT_LABELS: Record<string, string> = {
  FAILURE: '失败',
  SUCCESS: '成功',
}

export const ACCOUNT_STATUS_LABELS: Record<string, string> = {
  active: '启用',
  disabled: '停用',
}

export const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  student: '学生',
}

export const REVOKE_REASON_LABELS: Record<string, string> = {
  account_disabled: '账号停用',
  kicked: '管理员强制下线',
  logout: '主动退出',
  password_changed: '本人改密',
  password_reset: '管理员重置密码',
}

export const TARGET_TYPE_LABELS: Record<string, string> = {
  cache: '缓存',
  docs: '接口文档',
  export: '导出',
  job: '任务',
  session: '会话',
  user: '用户',
}

export const MONITOR_STATE_LABELS: Record<string, string> = {
  error: '错误',
  not_applicable: '不适用',
  not_configured: '未配置',
  ok: '正常',
  stale: '过期',
  unknown: '未知',
}

export const SEVERITY_LABELS: Record<string, string> = {
  critical: '严重',
  none: '无',
  normal: '正常',
  warning: '告警',
}

export const RUN_STATE_LABELS: Record<string, string> = {
  FAILED: '失败',
  INTERRUPTED: '已中断',
  PARTIAL: '部分完成',
  QUEUED: '排队中',
  RUNNING: '运行中',
  SUCCEEDED: '成功',
}

export const SEGMENT_TYPE_LABELS: Record<string, string> = {
  body: '正文',
  question: '题目',
}

export const VISIBILITY_ACTION_LABELS: Record<string, string> = {
  cancel: '取消开放',
  confirm: '开放',
}

export const EXAM_LEVEL_LABELS: Record<string, string> = {
  CET4: '四级',
}
