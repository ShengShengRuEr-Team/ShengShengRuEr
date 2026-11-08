import axios from 'axios'
import { clearSessionAndRedirect } from '../auth/session'
import { getAccessToken } from '../auth/storage'
import { ApiError } from './api-error'
import { API_BASE_URL } from './client'

/**
 * 音频二进制请求。
 *
 * 后端音频接口返回文件流而不是 {code,msg,data} 外壳，因此不能复用 client.ts 的
 * JSON 拦截器（它会以"缺少统一响应外壳"拒绝 200 响应）。这里单独建实例，
 * 只共享 baseURL、token 与 401 处理。
 */
const AUDIO_TIMEOUT_MS = 60_000

const audioHttp = axios.create({
  baseURL: API_BASE_URL,
  timeout: AUDIO_TIMEOUT_MS,
  responseType: 'blob',
})

export interface AudioSource {
  /** 可直接赋给 <audio src> 的对象 URL。 */
  objectUrl: string
  /** 释放对象 URL；重复调用无副作用。 */
  release: () => void
}

/**
 * 下载整段音频并返回对象 URL。
 * 调用方负责在组件卸载、切换试卷或重试时 release()，并可用 signal 取消请求。
 */
export async function loadAudioSource(
  examPaperId: number,
  signal?: AbortSignal,
): Promise<AudioSource> {
  try {
    const token = getAccessToken()
    const response = await audioHttp.get<Blob>(
      `/api/v1/listening-papers/${examPaperId}/audio`,
      {
        responseType: 'blob',
        signal,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      },
    )

    const objectUrl = URL.createObjectURL(response.data)
    let released = false
    return {
      objectUrl,
      release: () => {
        if (!released) {
          URL.revokeObjectURL(objectUrl)
          released = true
        }
      },
    }
  } catch (error) {
    // 主动取消不转换成业务错误，交给调用方忽略。
    if (isAborted(error)) {
      throw error
    }
    if (!axios.isAxiosError(error)) {
      throw error
    }

    const status = error.response?.status ?? 0
    if (status === 401) {
      clearSessionAndRedirect()
    }
    const message = await readErrorMessage(error.response?.data)
    throw new ApiError(message, status || -1, status)
  }
}

/** 取消判定：axios 的 CanceledError 与原生 AbortError 都算。 */
function isAborted(error: unknown): boolean {
  if (axios.isCancel(error)) {
    return true
  }
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    (error as { name?: unknown }).name === 'AbortError'
  )
}

/**
 * 错误响应仍是 JSON，但 responseType=blob 时会装进 Blob：
 * 先读文本再解析，取不到 msg 时退回通用提示。
 */
async function readErrorMessage(data: unknown): Promise<string> {
  if (data instanceof Blob) {
    try {
      const text = await data.text()
      const body = JSON.parse(text) as { msg?: unknown }
      if (typeof body.msg === 'string' && body.msg.trim()) {
        return body.msg
      }
    } catch {
      // 非 JSON 或空响应体：走下面的通用提示。
    }
    return '音频加载失败，请稍后重试'
  }

  if (data && typeof data === 'object' && 'msg' in data) {
    const msg = (data as { msg?: unknown }).msg
    if (typeof msg === 'string' && msg.trim()) {
      return msg
    }
  }
  return '音频加载失败，请稍后重试'
}
