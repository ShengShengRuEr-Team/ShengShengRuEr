import { useAuth } from './useAuth'

/** 按 getInfo.permissions 判断按钮/菜单显隐；不替代后端鉴权。 */
export function usePermission(code: string): boolean {
  const { hasPermission } = useAuth()
  return hasPermission(code)
}
