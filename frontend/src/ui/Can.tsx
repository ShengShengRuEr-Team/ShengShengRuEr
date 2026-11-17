import type { ReactNode } from 'react'
import { usePermission } from '../auth/usePermission'

interface CanProps {
  code: string
  fallback?: ReactNode
  children: ReactNode
}

/** 权限显隐组件：无权限时不渲染 children。 */
export default function Can({ code, fallback = null, children }: CanProps) {
  const allowed = usePermission(code)
  return <>{allowed ? children : fallback}</>
}
