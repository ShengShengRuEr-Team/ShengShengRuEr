/**
 * 后端接口 DTO 类型，字段与 backend/app/schemas.py 逐字对应（snake_case）。
 * 本文件只描述「后端返回什么」，组件使用的 camelCase 模型在 api/adapters.ts 中转换。
 */

/** 统一响应外壳：{ code, msg, data }。 */
export interface ApiResponse<T> {
  code: number
  msg: string
  data: T | null
}

/* ---------- 认证 ---------- */

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginData {
  token: string
  token_type: string
  expires_in: number
}

export interface UserInfoDto {
  user_id: number
  username: string
  nickname: string
}

export interface GetInfoData {
  user: UserInfoDto
  roles: string[]
  is_admin: boolean
}
