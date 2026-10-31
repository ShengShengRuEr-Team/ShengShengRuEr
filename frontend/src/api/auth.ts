import { request } from './client'
import type { GetInfoData, LoginData, LoginRequest } from './types'

/* ---------- 认证（接口 1–3） ---------- */

export function login(payload: LoginRequest): Promise<LoginData> {
  return request<LoginData>({
    method: 'POST',
    url: '/api/v1/login',
    data: payload,
  })
}

export function logout(): Promise<null> {
  return request<null>({
    method: 'POST',
    url: '/api/v1/logout',
  })
}

export function getInfo(): Promise<GetInfoData> {
  return request<GetInfoData>({
    method: 'GET',
    url: '/api/v1/getInfo',
  })
}
