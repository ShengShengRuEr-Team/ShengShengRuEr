import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { getInfo, login as loginRequest, logout as logoutRequest } from '../api/auth'
import { toAuthProfile } from '../api/adapters'
import type { AuthProfile, AuthUser } from '../api/adapters'
import { ApiError } from '../api/api-error'
import { getAccessToken, removeAccessToken, setAccessToken } from './storage'

/**
 * loading：有 token 正在拉 getInfo；
 * anonymous：未登录（或 401 已清 token）；
 * authenticated：登录态有效；
 * recovery-error：已有 token 但 getInfo 遇 500/网络错误——保留 token、不授予任何
 * 管理权限，展示「无法验证登录状态」与手动重试，只有 401 才清 token。
 */
export type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'recovery-error'

export interface AuthContextValue {
  status: AuthStatus
  token: string | null
  user: AuthUser | null
  roles: string[]
  /** 仅来自 getInfo.permissions；旧服务未返回时为空数组，不按 isAdmin 补齐。 */
  permissions: string[]
  isAdmin: boolean
  login: (username: string, password: string) => Promise<AuthProfile>
  logout: () => Promise<void>
  /** 只清本地 token/用户/权限，不请求服务端；用于本人改密成功后强制重登。 */
  clearLocalSession: () => void
  retry: () => Promise<void>
  hasRole: (role: string) => boolean
  hasPermission: (code: string) => boolean
}

interface AuthState {
  status: AuthStatus
  token: string | null
  profile: AuthProfile | null
}

export const AuthContext = createContext<AuthContextValue | null>(null)

const ANONYMOUS: AuthState = { status: 'anonymous', token: null, profile: null }

function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const token = getAccessToken()
    return token ? { status: 'loading', token, profile: null } : ANONYMOUS
  })

  /** 拉取 getInfo：401 清 token；500/网络错误保留 token 并进入恢复态。 */
  const loadProfile = useCallback(async (token: string): Promise<boolean> => {
    setState({ status: 'loading', token, profile: null })
    try {
      const info = await getInfo()
      setState({ status: 'authenticated', token, profile: toAuthProfile(info) })
      return true
    } catch (error) {
      if (isUnauthorized(error)) {
        removeAccessToken()
        setState(ANONYMOUS)
        return false
      }
      // 无法验证登录状态：保留 token，但权限为空，管理入口全部关闭。
      setState({ status: 'recovery-error', token, profile: null })
      return false
    }
  }, [])

  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      return
    }
    void loadProfile(token)
  }, [loadProfile])

  const login = useCallback(
    async (username: string, password: string): Promise<AuthProfile> => {
      const data = await loginRequest({ username, password })
      setAccessToken(data.token)
      try {
        const info = await getInfo()
        const nextProfile = toAuthProfile(info)
        setState({
          status: 'authenticated',
          token: data.token,
          profile: nextProfile,
        })
        return nextProfile
      } catch (error) {
        if (isUnauthorized(error)) {
          removeAccessToken()
          setState(ANONYMOUS)
        } else {
          // 登录已成功取得 token，但暂时无法验证：保留 token 等待重试。
          setState({ status: 'recovery-error', token: data.token, profile: null })
        }
        throw error
      }
    },
    [],
  )

  const retry = useCallback(async (): Promise<void> => {
    const token = getAccessToken()
    if (!token) {
      setState(ANONYMOUS)
      return
    }
    await loadProfile(token)
  }, [loadProfile])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } catch {
      // 退出接口失败（token 已失效 / 网络异常）不阻断本地清理。
    } finally {
      removeAccessToken()
      setState(ANONYMOUS)
    }
  }, [])

  const clearLocalSession = useCallback(() => {
    removeAccessToken()
    setState(ANONYMOUS)
  }, [])

  const profile = state.profile
  const hasRole = useCallback(
    (role: string) => profile?.roles.includes(role) ?? false,
    [profile],
  )
  const hasPermission = useCallback(
    (code: string) => profile?.permissions.includes(code) ?? false,
    [profile],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      status: state.status,
      token: state.token,
      user: profile?.user ?? null,
      roles: profile?.roles ?? [],
      permissions: profile?.permissions ?? [],
      isAdmin: profile?.isAdmin ?? false,
      login,
      logout,
      clearLocalSession,
      retry,
      hasRole,
      hasPermission,
    }),
    [
      state.status,
      state.token,
      profile,
      login,
      logout,
      clearLocalSession,
      retry,
      hasRole,
      hasPermission,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
