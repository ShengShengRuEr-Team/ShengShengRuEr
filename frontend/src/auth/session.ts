import { removeAccessToken } from './storage'

export const LOGIN_PATH = '/login'

/** 当前路径（含查询串与 hash），用于 401 后的 redirect 参数。 */
export function getCurrentPath(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`
}

/**
 * 跳到登录页并带上 redirect。已在登录页时不再跳，避免登录失败时刷新页面。
 * 使用 location.replace 而不是路由跳转：401 发生在 React 树之外，
 * 且登录态需要整体重置，整页重载最可靠。
 */
export function redirectToLogin(): void {
  if (window.location.pathname === LOGIN_PATH) {
    return
  }
  const redirect = encodeURIComponent(getCurrentPath())
  window.location.replace(`${LOGIN_PATH}?redirect=${redirect}`)
}

/** 401 统一处理：清 token，再跳登录（不在拦截器里弹窗）。 */
export function clearSessionAndRedirect(): void {
  removeAccessToken()
  redirectToLogin()
}
