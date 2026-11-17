import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { usePermission } from '../auth/usePermission'
import { ROUTES } from '../constants/routes'

/** 页面级权限守卫：无权限进 403 页，不跳登录。 */
export default function RequirePermission({
  code,
  children,
}: {
  code: string
  children: ReactNode
}) {
  const allowed = usePermission(code)
  if (!allowed) {
    return <Navigate to={ROUTES.FORBIDDEN} replace />
  }
  return <>{children}</>
}
