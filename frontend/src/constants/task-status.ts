import type { TaskStatus } from '../api/types'

/** 任务状态展示文案与标签色，枚举值与后端 constants.py 一致。 */
export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  pending: '等待中',
  running: '处理中',
  failed: '失败',
  pending_confirm: '待确认',
  completed: '已完成',
}

export const TASK_STATUS_COLORS: Record<TaskStatus, string> = {
  pending: 'default',
  running: 'processing',
  failed: 'error',
  pending_confirm: 'warning',
  completed: 'success',
}
