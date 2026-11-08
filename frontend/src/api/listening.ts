import {
  toContentCheck,
  toPaperCompanion,
  toPaperDetail,
  toPaperSummary,
  toVisibilityResult,
} from './adapters'
import type {
  ContentCheck,
  PaperCompanion,
  PaperDetail,
  PaperSummary,
  VisibilityResult,
} from './adapters'
import { API_BASE_URL, request } from './client'
import type {
  CheckResultDto,
  PaperCompanionDto,
  PaperDetailStudentDto,
  PaperListData,
  VisibilityAction,
  VisibilityStateDto,
} from './types'

/** 单次请求的可选覆盖项：列表补调状态时用于限制超时与取消。 */
export interface RequestOptions {
  signal?: AbortSignal
  timeout?: number
}

/** 接口 ①：试卷列表。管理员返回全部，学生只返回可访问的。 */
export async function getListeningPapers(options: RequestOptions = {}): Promise<PaperSummary[]> {
  const data = await request<PaperListData>({
    method: 'GET',
    url: '/api/v1/listening-papers',
    signal: options.signal,
    timeout: options.timeout,
  })
  return data.items.map(toPaperSummary)
}

/** 接口 ②：学生视角整卷详情（不含答案、解析与听力正文）。 */
export async function getListeningPaper(examPaperId: number): Promise<PaperDetail> {
  const data = await request<PaperDetailStudentDto>({
    method: 'GET',
    url: `/api/v1/listening-papers/${examPaperId}`,
  })
  return toPaperDetail(data)
}

/** 接口 ④：管理员配套内容（答案、解析、原文、批次与状态）。 */
export async function getAdminCompanion(
  examPaperId: number,
  options: RequestOptions = {},
): Promise<PaperCompanion> {
  const data = await request<PaperCompanionDto>({
    method: 'GET',
    url: `/api/v1/admin/listening-papers/${examPaperId}/companion`,
    signal: options.signal,
    timeout: options.timeout,
  })
  return toPaperCompanion(data)
}

/** 接口 ⑥：读取最近一次持久化的最低内容检查结果（不触发新检查）。 */
export async function getContentCheck(
  examPaperId: number,
  options: RequestOptions = {},
): Promise<ContentCheck> {
  const data = await request<CheckResultDto>({
    method: 'GET',
    url: `/api/v1/admin/listening-papers/${examPaperId}/checks`,
    signal: options.signal,
    timeout: options.timeout,
  })
  return toContentCheck(data)
}

/** 接口 ⑤：确认或取消学生可见。理由选填，最长 255 字。 */
export async function setPaperVisibility(
  examPaperId: number,
  action: VisibilityAction,
  reason = '',
): Promise<VisibilityResult> {
  const data = await request<VisibilityStateDto>({
    method: 'POST',
    url: `/api/v1/admin/listening-papers/${examPaperId}/visibility`,
    data: { action, reason },
  })
  return toVisibilityResult(data)
}

/** 把接口返回的相对路径拼成可直接请求的绝对地址（音频走独立的二进制模块）。 */
export function toAbsoluteApiUrl(path: string): string {
  return path.startsWith('http') ? path : `${API_BASE_URL}${path}`
}
