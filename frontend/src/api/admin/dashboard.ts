import { request } from '../client'
import type { DashboardDto } from './types'

export function fetchDashboard(): Promise<DashboardDto> {
  return request<DashboardDto>({ method: 'GET', url: '/api/v1/admin/dashboard' })
}
