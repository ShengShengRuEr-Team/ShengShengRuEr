import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ROUTES } from '../constants/routes'
import FullPageLoading from '../ui/FullPageLoading'

/**
 * 登录守卫：未登录（无 token 或 getInfo 失败）→ /login?redirect=<原路径>。
 * 恢复登录态期间显示整页加载，避免闪一下登录页。
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return <FullPageLoading />
  }

  if (status === 'anonymous') {
    const redirect = `${location.pathname}${location.search}${location.hash}`
    return (
      <Navigate
        to={`${ROUTES.LOGIN}?redirect=${encodeURIComponent(redirect)}`}
        replace
      />
    )
  }

  return <>{children}</>
}
