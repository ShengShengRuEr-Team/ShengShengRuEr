/**
 * 受限 GET 调试的白名单判定（与后端 core/docs_debug.py 同规则）。
 * 后端仍会二次校验；这里只决定 Swagger UI 是否允许发起请求。
 */

export interface DebugAllowEntry {
  method: string
  path_template: string
  permission: string
}

const PARAM_PATTERN = /\{[^}]+\}/g

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function templateMatches(template: string, path: string): boolean {
  const pattern = new RegExp(
    '^' +
      template
        .split(PARAM_PATTERN)
        .map((part) => escapeRegExp(part))
        .join('[^/]+') +
      '$',
  )
  return pattern.test(path)
}

/** 只解码一次；双斜杠、尾斜杠、编码斜杠与二次编码一律拒绝。 */
export function normalizeDebugPath(rawPath: string): string | null {
  if (!rawPath.startsWith('/')) {
    return null
  }
  if (/%2f|%5c/i.test(rawPath) || /%25/i.test(rawPath)) {
    return null
  }
  let decoded: string
  try {
    decoded = decodeURIComponent(rawPath)
  } catch {
    return null
  }
  if (decoded.includes('%') || decoded.includes('\\')) {
    return null
  }
  if (decoded.includes('//')) {
    return null
  }
  if (decoded.length > 1 && decoded.endsWith('/')) {
    return null
  }
  return decoded
}

export function isAllowedDebugRequest(
  entries: DebugAllowEntry[],
  method: string,
  url: string,
  origin: string,
): boolean {
  if (method.toUpperCase() !== 'GET') {
    return false
  }
  let parsed: URL
  try {
    parsed = new URL(url, origin)
  } catch {
    return false
  }
  if (parsed.origin !== origin) {
    return false
  }
  const path = normalizeDebugPath(parsed.pathname)
  if (path === null) {
    return false
  }
  return entries.some(
    (entry) => entry.method === 'GET' && templateMatches(entry.path_template, path),
  )
}
