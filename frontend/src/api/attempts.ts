import type { AttemptStatusResult, AttemptSubmitSuccess } from './adapters'
import { toAttemptStatusResult, toAttemptSubmitSuccess } from './adapters'
import { ApiError } from './api-error'
import { request } from './client'
import type { AttemptSubmitRequestDto } from './types'

/** API-1 调用结果：HTTP 错误保留 status+msg，供 errors.ts 精确匹配。 */
export type AttemptSubmitApiResult =
  | { kind: 'success'; value: AttemptSubmitSuccess }
  | { kind: 'http-error'; status: number; msg: string }
  | { kind: 'network' }
  | { kind: 'unauthorized' }

export interface RequestOptions {
  signal?: AbortSignal
}

/** API-1：提交整卷作答；同键重试复用同一个 Idempotency-Key。 */
export async function submitAttempt(
  paperId: number,
  payload: AttemptSubmitRequestDto,
  idempotencyKey: string,
  options: RequestOptions = {},
): Promise<AttemptSubmitApiResult> {
  try {
    const data = await request<unknown>({
      method: 'POST',
      url: `/api/v1/listening-papers/${paperId}/attempts`,
      data: payload,
      headers: { 'Idempotency-Key': idempotencyKey },
      signal: options.signal,
    })
    return { kind: 'success', value: toAttemptSubmitSuccess(data, paperId) }
  } catch (error) {
    if (!(error instanceof ApiError)) {
      return { kind: 'network' }
    }
    if (error.status === 401) {
      return { kind: 'unauthorized' }
    }
    if (error.status === 0) {
      return { kind: 'network' }
    }
    return { kind: 'http-error', status: error.status, msg: error.message }
  }
}

/**
 * API-3：查询本人本卷状态。
 * 401/403 交由全局（登录跳转/权限提示）；404/500/网络/字段非法转分层结果。
 */
export async function getAttemptStatus(
  paperId: number,
  options: RequestOptions = {},
): Promise<AttemptStatusResult> {
  try {
    const data = await request<unknown>({
      method: 'GET',
      url: `/api/v1/listening-papers/${paperId}/attempt-status`,
      signal: options.signal,
    })
    return toAttemptStatusResult(data, paperId)
  } catch (error) {
    if (!(error instanceof ApiError)) {
      return { kind: 'status-unavailable', reason: 'network' }
    }
    if (error.status === 401 || error.status === 403) {
      throw error
    }
    if (error.status === 404) {
      return {
        kind: 'status-unavailable',
        reason: 'not-accessible',
        httpStatus: 404,
      }
    }
    if (error.status === 0) {
      return { kind: 'status-unavailable', reason: 'network' }
    }
    return {
      kind: 'status-unavailable',
      reason: 'server',
      httpStatus: error.status,
    }
  }
}
