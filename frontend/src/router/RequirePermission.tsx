import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ROUTES } from '../constants/routes'
import FullPageLoading from '../ui/FullPageLoading'

/** 权限码守卫：权限码不在后端下发的 permissions 中 → /403。 */
export default function RequirePermission({
  permission,
  children,
}: {
  permission: string
  children: ReactNode
}) {
  const { status, permissions } = useAuth()

  if (status === 'loading') {
    return <FullPageLoading />
  }

  if (!permissions.includes(permission)) {
    return <Navigate to={ROUTES.FORBIDDEN} replace />
  }

  return <>{children}</>
}
