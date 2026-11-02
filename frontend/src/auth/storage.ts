/** token 的唯一读写入口：localStorage key 固定为 ssre_access_token。 */

export const ACCESS_TOKEN_KEY = 'ssre_access_token'

export function getAccessToken(): string | null {
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_KEY)
  } catch {
    // 隐私模式等场景可能抛异常，按未登录处理。
    return null
  }
}

export function setAccessToken(token: string): void {
  try {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, token)
  } catch {
    // 写入失败不阻断登录流程；后续请求会因缺少 token 得到 401。
  }
}

export function removeAccessToken(): void {
  try {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY)
  } catch {
    // 忽略清理失败。
  }
}
