import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import AuthRecovery from '../auth/AuthRecovery'
import { ROUTES } from '../constants/routes'
import FullPageLoading from '../ui/FullPageLoading'

/**
 * 登录守卫：未登录 → /login?redirect=<原路径>。
 * 恢复登录态期间整页加载；无法验证（500/网络）时保留 token 并展示重试页。
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return <FullPageLoading />
  }

  if (status === 'recovery-error') {
    return <AuthRecovery />
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
