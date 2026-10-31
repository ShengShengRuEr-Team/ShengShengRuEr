/**
 * 统一接口异常：页面 catch 后可拿 code / status / message 判断展示方式。
 * - code：响应外壳中的业务码（无外壳时为 HTTP 状态码或 -1）
 * - status：HTTP 状态码（网络层失败为 0）
 */
export class ApiError extends Error {
  readonly code: number
  readonly status: number

  constructor(message: string, code: number, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}
