import { PERMISSIONS, ROLES } from './permissions'

/** 路由路径常量，避免各处硬编码字符串。 */
export const ROUTES = {
  LOGIN: '/login',
  FORBIDDEN: '/403',
  ADMIN_PAPERS: '/admin/papers',
  ADMIN_PAPER_DETAIL: '/admin/papers/:id',
  ADMIN_TASKS: '/admin/tasks',
  STUDENT_PAPERS: '/papers',
  STUDENT_PAPER_DETAIL: '/papers/:id',
} as const

/** 登录后 / 根路径的默认落地页，由后端下发的角色决定。 */
export function homePathForRole(isAdmin: boolean): string {
  return isAdmin ? ROUTES.ADMIN_PAPERS : ROUTES.STUDENT_PAPERS
}

/** 菜单与守卫使用的权限码（与后端 permissions.py 一致）。 */
export const MENU_PERMISSIONS = {
  adminPapers: PERMISSIONS.PAPER_READ,
  adminQuestions: PERMISSIONS.QUESTION_READ_SENSITIVE,
  adminTasks: PERMISSIONS.TASK_READ,
  studentPapers: PERMISSIONS.PAPER_READ,
  studentQuestions: PERMISSIONS.QUESTION_READ,
} as const

export const ADMIN_ROLE = ROLES.ADMIN
export const STUDENT_ROLE = ROLES.STUDENT
