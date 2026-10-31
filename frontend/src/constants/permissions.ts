/**
 * 权限码与角色常量，与 backend/app/core/permissions.py 逐字一致。
 * 前端只用于菜单显隐与路由守卫；真正的鉴权由后端完成。
 */

export const ROLES = {
  ADMIN: 'admin',
  STUDENT: 'student',
} as const

export type RoleKey = (typeof ROLES)[keyof typeof ROLES]

export const PERMISSIONS = {
  PAPER_READ: 'paper:read',
  QUESTION_READ: 'question:read',
  QUESTION_READ_SENSITIVE: 'question:read_sensitive',
  TASK_START: 'task:start',
  TASK_READ: 'task:read',
} as const

export type PermissionCode = (typeof PERMISSIONS)[keyof typeof PERMISSIONS]
