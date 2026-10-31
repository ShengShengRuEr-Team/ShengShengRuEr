/**
 * 角色常量，与 backend/app/core/permissions.py 逐字一致。
 * 前端只用于菜单显隐与路由分流；真正的鉴权由后端完成。
 */

export const ROLES = {
  ADMIN: 'admin',
  STUDENT: 'student',
} as const

export type RoleKey = (typeof ROLES)[keyof typeof ROLES]
