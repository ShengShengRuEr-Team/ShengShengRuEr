import { request } from '../client'
import type {
  LoginLogDto,
  LoginLogPageDto,
  OperationLogDto,
  OperationLogPageDto,
} from './types'

/** 日志筛选：与后端查询参数同名；时间必须是带时区 ISO 字符串。 */
export interface LogQuery {
  username?: string
  actor_username?: string
  result?: string
  failure_type?: string
  event_type?: string
  target_type?: string
  ip?: string
  start_at?: string
  end_at?: string
  page?: number
  page_size?: number
}

function cleanParams(query: LogQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params[key] = value
    }
  }
  return params
}

export function fetchLoginLogs(query: LogQuery): Promise<LoginLogPageDto> {
  return request<LoginLogPageDto>({
    method: 'GET',
    url: '/api/v1/admin/logs/login',
    params: cleanParams(query),
  })
}

export function fetchLoginLog(eventId: string): Promise<LoginLogDto> {
  return request<LoginLogDto>({
    method: 'GET',
    url: `/api/v1/admin/logs/login/${eventId}`,
  })
}

export function fetchOperationLogs(query: LogQuery): Promise<OperationLogPageDto> {
  return request<OperationLogPageDto>({
    method: 'GET',
    url: '/api/v1/admin/logs/operation',
    params: cleanParams(query),
  })
}

export function fetchOperationLog(eventId: string): Promise<OperationLogDto> {
  return request<OperationLogDto>({
    method: 'GET',
    url: `/api/v1/admin/logs/operation/${eventId}`,
  })
}
