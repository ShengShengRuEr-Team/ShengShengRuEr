import { rawHttp } from '../rawClient'
import type { DebugAllowEntry } from '../../utils/docsDebug'

export interface OpenapiSchema {
  openapi: string
  paths: Record<string, unknown>
  'x-admin-debug-allowlist': DebugAllowEntry[]
  [key: string]: unknown
}

/** 受保护 schema：原始 JSON，不经统一外壳解包。 */
export async function fetchOpenapiSchema(): Promise<OpenapiSchema> {
  const response = await rawHttp.get<OpenapiSchema>('/api/v1/admin/openapi.json')
  return response.data
}
