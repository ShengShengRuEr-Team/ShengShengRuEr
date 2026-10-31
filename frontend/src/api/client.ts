import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { ApiError } from './api-error'
import type { ApiResponse } from './types'
import { getAccessToken } from '../auth/storage'
import { clearSessionAndRedirect } from '../auth/session'
import { showError } from '../ui/message'

/** 后端基础地址：env 优先，未配置时回退本地后端（与文档 4.3.1 一致）。 */
export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
).replace(/\/+$/, '')

export const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
})

// 请求拦截：统一注入 Bearer token。
http.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

// 响应拦截：只认 {code,msg,data} 外壳；401 清登录态跳登录；403 只提示不跳转。
http.interceptors.response.use(
  (response) => {
    const body = response.data as Partial<ApiResponse<unknown>> | undefined
    if (!body || typeof body.code !== 'number') {
      return Promise.reject(
        new ApiError('响应格式异常：缺少统一响应外壳', -1, response.status),
      )
    }
    if (body.code !== 200) {
      return Promise.reject(
        new ApiError(body.msg || '请求失败', body.code, response.status),
      )
    }
    return response
  },
  (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      return Promise.reject(error)
    }

    const status = error.response?.status ?? 0
    const body = error.response?.data as Partial<ApiResponse<unknown>> | undefined
    const message =
      (typeof body?.msg === 'string' && body.msg) || error.message || '网络请求失败'

    // 顺序与后端鉴权一致：先 401 后 403。
    if (status === 401) {
      clearSessionAndRedirect()
    } else if (status === 403) {
      showError(message)
    }

    return Promise.reject(new ApiError(message, body?.code ?? status, status))
  },
)

/** 发起请求并解包 data 字段；非 200 已在拦截器转成 ApiError。 */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request<ApiResponse<T>>(config)
  return response.data.data as T
}
