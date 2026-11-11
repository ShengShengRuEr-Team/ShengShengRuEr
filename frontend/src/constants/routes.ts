/** 路由路径常量，避免各处硬编码字符串。 */
export const ROUTES = {
  LOGIN: '/login',
  FORBIDDEN: '/403',
  ADMIN_HOME: '/admin',
  ADMIN_LISTENING_PAPERS: '/admin/listening-papers',
  ADMIN_LISTENING_PAPER_DETAIL: '/admin/listening-papers/:examPaperId',
  STUDENT_HOME: '/student',
  STUDENT_LISTENING_PAPERS: '/student/listening-papers',
  STUDENT_LISTENING_PAPER_DETAIL: '/student/listening-papers/:examPaperId',
} as const

/** 登录后 / 根路径的默认落地页，由后端下发的角色决定。 */
export function homePathForRole(isAdmin: boolean): string {
  return isAdmin ? ROUTES.ADMIN_HOME : ROUTES.STUDENT_HOME
}

/** 管理端试卷详情实际路径。 */
export function adminListeningPaperPath(examPaperId: number | string): string {
  return `${ROUTES.ADMIN_LISTENING_PAPERS}/${examPaperId}`
}

/** 学生端整卷页实际路径。 */
export function studentListeningPaperPath(examPaperId: number | string): string {
  return `${ROUTES.STUDENT_LISTENING_PAPERS}/${examPaperId}`
}
