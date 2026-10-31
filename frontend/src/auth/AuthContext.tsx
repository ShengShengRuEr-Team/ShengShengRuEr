import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { getInfo, login as loginRequest, logout as logoutRequest } from '../api/auth'
import { toAuthProfile } from '../api/adapters'
import type { AuthProfile, AuthUser } from '../api/adapters'
import { getAccessToken, removeAccessToken, setAccessToken } from './storage'

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

export interface AuthContextValue {
  /** loading：有 token 正在拉 getInfo；anonymous：未登录。 */
  status: AuthStatus
  token: string | null
  user: AuthUser | null
  roles: string[]
  permissions: string[]
  isAdmin: boolean
  login: (username: string, password: string) => Promise<AuthProfile>
  logout: () => Promise<void>
  hasRole: (role: string) => boolean
  hasPermission: (permission: string) => boolean
}

interface AuthState {
  status: AuthStatus
  token: string | null
  profile: AuthProfile | null
}

export const AuthContext = createContext<AuthContextValue | null>(null)

const ANONYMOUS: AuthState = { status: 'anonymous', token: null, profile: null }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const token = getAccessToken()
    return token
      ? { status: 'loading', token, profile: null }
      : ANONYMOUS
  })

  // 刷新页面时：有 token 就先拉 getInfo，失败则清 token 按未登录处理。
  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      return
    }

    let active = true
    getInfo()
      .then((data) => {
        if (!active) {
          return
        }
        setState({ status: 'authenticated', token, profile: toAuthProfile(data) })
      })
      .catch(() => {
        if (!active) {
          return
        }
        removeAccessToken()
        setState(ANONYMOUS)
      })

    return () => {
      active = false
    }
  }, [])

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
        // 返回角色信息，供登录页决定跳转目标（此时组件里的 isAdmin 还是旧值）。
        return nextProfile
      } catch (error) {
        // 登录成功但取用户信息失败：不留下半登录状态。
        removeAccessToken()
        setState(ANONYMOUS)
        throw error
      }
    },
    [],
  )

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

  const profile = state.profile
  const hasRole = useCallback(
    (role: string) => profile?.roles.includes(role) ?? false,
    [profile],
  )
  const hasPermission = useCallback(
    (permission: string) => profile?.permissions.includes(permission) ?? false,
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
      hasRole,
      hasPermission,
    }),
    [state.status, state.token, profile, login, logout, hasRole, hasPermission],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
