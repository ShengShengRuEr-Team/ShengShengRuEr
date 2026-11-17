import { request } from '../client'
import type { JobOverviewDto, JobRunPageDto } from './types'

const BASE = '/api/v1/admin/monitor/jobs'
export const JOB_ID = 'admin.retention_cleanup'

export function fetchJobOverview(): Promise<JobOverviewDto> {
  return request<JobOverviewDto>({ method: 'GET', url: BASE })
}

export function fetchJobRuns(
  page: number,
  pageSize: number,
): Promise<JobRunPageDto> {
  return request<JobRunPageDto>({
    method: 'GET',
    url: `${BASE}/${JOB_ID}/runs`,
    params: { page, page_size: pageSize },
  })
}

export function setJobEnabled(
  enabled: boolean,
  reason: string,
): Promise<{ job_id: string; enabled: boolean; changed: boolean }> {
  return request({
    method: 'POST',
    url: `${BASE}/${JOB_ID}/enabled`,
    data: { enabled, reason },
  })
}

export function triggerJob(
  reason: string,
): Promise<{ run_id: string; state: string }> {
  return request({
    method: 'POST',
    url: `${BASE}/${JOB_ID}/run`,
    data: { reason },
  })
}
