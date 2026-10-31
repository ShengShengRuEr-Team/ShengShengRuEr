import { request } from './client'
import type { TaskCreateRequest, TaskDto, TaskListData, TaskListQuery } from './types'

/* ---------- 管理端处理任务（接口 7–9） ---------- */

export function createTask(payload: TaskCreateRequest): Promise<TaskDto> {
  return request<TaskDto>({
    method: 'POST',
    url: '/api/v1/admin/processing-tasks',
    data: payload,
  })
}

export function getTasks(query: TaskListQuery = {}): Promise<TaskListData> {
  return request<TaskListData>({
    method: 'GET',
    url: '/api/v1/admin/processing-tasks',
    params: { status: query.status },
  })
}

export function getTask(taskId: number): Promise<TaskDto> {
  return request<TaskDto>({
    method: 'GET',
    url: `/api/v1/admin/processing-tasks/${taskId}`,
  })
}
