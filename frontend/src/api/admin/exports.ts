import { rawHttp } from '../rawClient'
import { ApiError } from '../api-error'
import type { LogQuery } from './logs'

export const EXPORT_URLS = {
  users: '/api/v1/admin/exports/users',
  loginLogs: '/api/v1/admin/exports/login-logs',
  operationLogs: '/api/v1/admin/exports/operation-logs',
} as const

export type ExportKind = keyof typeof EXPORT_URLS

/** 从 Content-Disposition 取文件名；不信任响应里的其它内容。 */
export function parseFilename(disposition: string | undefined): string | null {
  if (!disposition) {
    return null
  }
  const match = /filename="?([^";]+)"?/i.exec(disposition)
  return match ? match[1] : null
}

export interface CsvDownload {
  blob: Blob
  filename: string
}

function cleanParams(params: LogQuery): Record<string, string | number> {
  const result: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      result[key] = value
    }
  }
  return result
}

/**
 * 下载 CSV：只有确认是附件响应时才返回 blob；JSON 错误体已在 rawClient 转成 ApiError。
 * 不把错误 JSON 当文件保存。
 */
export async function downloadCsv(
  kind: ExportKind,
  params: LogQuery,
): Promise<CsvDownload> {
  const response = await rawHttp.get<Blob>(EXPORT_URLS[kind], {
    params: cleanParams(params),
    responseType: 'blob',
  })
  const contentType = String(response.headers['content-type'] ?? '')
  if (!contentType.toLowerCase().startsWith('text/csv')) {
    throw new ApiError('响应不是 CSV 文件', -1, response.status)
  }
  const filename = parseFilename(
    String(response.headers['content-disposition'] ?? ''),
  )
  if (!filename) {
    throw new ApiError('缺少附件文件名', -1, response.status)
  }
  return { blob: response.data, filename }
}

/** 创建临时下载链接并立即释放；不做持久保存。 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}
