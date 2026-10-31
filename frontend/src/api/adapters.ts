import type {
  AdminQuestionDto,
  GetInfoData,
  PaperDto,
  StudentQuestionDto,
  TaskDto,
  TaskListData,
  TaskListItemDto,
  TaskStatus,
} from './types'
import { isTaskStatus } from './types'

/* ---------- 认证视图模型 ---------- */

export interface AuthUser {
  userId: number
  username: string
  nickname: string
}

export interface AuthProfile {
  user: AuthUser
  roles: string[]
  permissions: string[]
  isAdmin: boolean
}

export function toAuthProfile(data: GetInfoData): AuthProfile {
  return {
    user: {
      userId: data.user.user_id,
      username: data.user.username,
      nickname: data.user.nickname,
    },
    roles: data.roles,
    permissions: data.permissions,
    isAdmin: data.is_admin,
  }
}

/* ---------- 试卷 / 题目视图模型 ---------- */

export interface Paper {
  id: number
  title: string
  examLevel: string
  examYear: number
  examMonth: number
  setNo: number
}

export function toPaper(dto: PaperDto): Paper {
  return {
    id: dto.id,
    title: dto.title,
    examLevel: dto.exam_level,
    examYear: dto.exam_year,
    examMonth: dto.exam_month,
    setNo: dto.set_no,
  }
}

export interface StudentQuestion {
  id: number
  questionNo: number
  promptText: string | null
  optionA: string | null
  optionB: string | null
  optionC: string | null
  optionD: string | null
}

export function toStudentQuestion(dto: StudentQuestionDto): StudentQuestion {
  return {
    id: dto.id,
    questionNo: dto.question_no,
    promptText: dto.prompt_text,
    optionA: dto.option_a,
    optionB: dto.option_b,
    optionC: dto.option_c,
    optionD: dto.option_d,
  }
}

/** 管理端题目视图：在非敏感字段基础上带答案 / 解析 / 原文。 */
export interface AdminQuestion extends StudentQuestion {
  correctOption: string | null
  explanationText: string | null
  transcriptText: string | null
}

export function toAdminQuestion(dto: AdminQuestionDto): AdminQuestion {
  return {
    ...toStudentQuestion(dto),
    correctOption: dto.correct_option,
    explanationText: dto.explanation_text,
    transcriptText: dto.transcript_text,
  }
}

/* ---------- 任务视图模型 ---------- */

export interface Task {
  id: number
  paperId: number | null
  taskType: string
  status: string
  progress: number
  message: string | null
  result: Record<string, unknown> | null
  createdBy: number | null
  startedAt: string | null
  finishedAt: string | null
  createdAt: string
  updatedAt: string
}

export function toTask(dto: TaskDto): Task {
  return {
    id: dto.id,
    paperId: dto.paper_id,
    taskType: dto.task_type,
    status: dto.status,
    progress: dto.progress,
    message: dto.message,
    result: dto.result,
    createdBy: dto.created_by,
    startedAt: dto.started_at,
    finishedAt: dto.finished_at,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

export interface TaskListItem {
  id: number
  paperId: number | null
  taskType: string
  status: string
  progress: number
  message: string | null
  createdAt: string
}

export function toTaskListItem(dto: TaskListItemDto): TaskListItem {
  return {
    id: dto.id,
    paperId: dto.paper_id,
    taskType: dto.task_type,
    status: dto.status,
    progress: dto.progress,
    message: dto.message,
    createdAt: dto.created_at,
  }
}

export interface TaskList {
  items: TaskListItem[]
  total: number
}

export function toTaskList(data: TaskListData): TaskList {
  return {
    items: data.items.map(toTaskListItem),
    total: data.total,
  }
}

/** 把后端任意字符串收窄成任务状态；未知值返回 null，由页面显示原文。 */
export function parseTaskStatus(value: string): TaskStatus | null {
  return isTaskStatus(value) ? value : null
}
