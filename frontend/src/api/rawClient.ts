import axios from 'axios'
import { API_BASE_URL } from './client'
import { ApiError } from './api-error'
import { clearSessionAndRedirect } from '../auth/session'
import { getAccessToken } from '../auth/storage'
import { showError } from '../ui/message'

/**
 * 原始响应通道：不做 {code,msg,data} 解包，供私有 schema 与 CSV 使用。
 * 与 client.ts 复用同一套 token 注入与 401/403 规则，但成功响应不校验外壳，
 * 因此普通 JSON 接口继续走 client.ts，两者互不影响。
 */
export const rawHttp = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})

rawHttp.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

/** 从错误响应体解析后端 {code,msg}（CSV 通道失败时也可能是 JSON blob）。 */
export async function extractErrorMessage(data: unknown): Promise<string> {
  if (typeof Blob !== 'undefined' && data instanceof Blob) {
    try {
      const text = await data.text()
      const parsed: unknown = JSON.parse(text)
      if (parsed && typeof parsed === 'object' && 'msg' in parsed) {
        const message = (parsed as { msg?: unknown }).msg
        if (typeof message === 'string' && message) {
          return message
        }
      }
    } catch {
      return '导出失败'
    }
    return '导出失败'
  }
  if (data && typeof data === 'object' && 'msg' in data) {
    const message = (data as { msg?: unknown }).msg
    if (typeof message === 'string' && message) {
      return message
    }
  }
  return '网络请求失败'
}

rawHttp.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      return Promise.reject(error)
    }
    const status = error.response?.status ?? 0
    const message = await extractErrorMessage(error.response?.data)

    if (status === 401) {
      clearSessionAndRedirect()
    } else if (status === 403) {
      showError(message)
    }

    return Promise.reject(new ApiError(message, status || -1, status))
  },
)
