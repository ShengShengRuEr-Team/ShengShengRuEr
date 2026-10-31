import { request } from './client'

/** 管理端首页占位数据，见 backend/app/schemas.py 的 AdminOverviewData。 */
export interface AdminOverviewData {
  role: string
  message: string
}

/** 管理端接口：仅管理员可用，学生 token 调用返回 403。 */
export function getAdminOverview(): Promise<AdminOverviewData> {
  return request<AdminOverviewData>({
    method: 'GET',
    url: '/api/v1/admin/overview',
  })
}
