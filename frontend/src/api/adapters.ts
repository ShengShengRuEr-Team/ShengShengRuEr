import type { GetInfoData } from './types'

/* ---------- 认证视图模型 ---------- */

export interface AuthUser {
  userId: number
  username: string
  nickname: string
}

export interface AuthProfile {
  user: AuthUser
  roles: string[]
  isAdmin: boolean
}

export function toAuthProfile(data: GetInfoData): AuthProfile {
  return {
    user: {
      userId: data.user.user_id,
      username: data.user.username,
      nickname: data.user.nickname,
    },
    roles: data.roles,
    isAdmin: data.is_admin,
  }
}
