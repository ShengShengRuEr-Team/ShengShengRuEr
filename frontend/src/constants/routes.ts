/** 路由路径常量，避免各处硬编码字符串。 */
export const ROUTES = {
  LOGIN: '/login',
  FORBIDDEN: '/403',
  ADMIN_HOME: '/admin',
  STUDENT_HOME: '/student',
} as const

/** 登录后 / 根路径的默认落地页，由后端下发的角色决定。 */
export function homePathForRole(isAdmin: boolean): string {
  return isAdmin ? ROUTES.ADMIN_HOME : ROUTES.STUDENT_HOME
}
