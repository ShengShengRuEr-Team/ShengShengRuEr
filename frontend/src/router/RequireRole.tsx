import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ROUTES } from '../constants/routes'
import FullPageLoading from '../ui/FullPageLoading'

/**
 * 角色守卫：用于 /admin/**（文档 5.3）。角色来自后端 getInfo，前端只做跳转展示；
 * 学生 token 越权请求最终由后端返回 403。
 */
export default function RequireRole({
  role,
  children,
}: {
  role: string
  children: ReactNode
}) {
  const { status, roles } = useAuth()

  if (status === 'loading') {
    return <FullPageLoading />
  }

  if (!roles.includes(role)) {
    return <Navigate to={ROUTES.FORBIDDEN} replace />
  }

  return <>{children}</>
}
