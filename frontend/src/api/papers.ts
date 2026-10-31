import { request } from './client'
import type {
  AdminQuestionListData,
  GetInfoData,
  LoginData,
  LoginRequest,
  PaperListData,
  StudentQuestionListData,
} from './types'

/* ---------- 认证（接口 1–3） ---------- */

export function login(payload: LoginRequest): Promise<LoginData> {
  return request<LoginData>({
    method: 'POST',
    url: '/api/v1/login',
    data: payload,
  })
}

export function logout(): Promise<null> {
  return request<null>({
    method: 'POST',
    url: '/api/v1/logout',
  })
}

export function getInfo(): Promise<GetInfoData> {
  return request<GetInfoData>({
    method: 'GET',
    url: '/api/v1/getInfo',
  })
}

/* ---------- 试卷与题目（接口 4–6） ---------- */

export function getPapers(): Promise<PaperListData> {
  return request<PaperListData>({
    method: 'GET',
    url: '/api/v1/papers',
  })
}

/** 学生视图：后端不返回敏感字段，类型也用 StudentQuestionDto。 */
export function getStudentQuestions(paperId: number): Promise<StudentQuestionListData> {
  return request<StudentQuestionListData>({
    method: 'GET',
    url: `/api/v1/papers/${paperId}/questions`,
  })
}

/** 管理端视图：含答案 / 解析 / 原文，需 question:read_sensitive 权限。 */
export function getAdminQuestions(paperId: number): Promise<AdminQuestionListData> {
  return request<AdminQuestionListData>({
    method: 'GET',
    url: `/api/v1/admin/papers/${paperId}/questions`,
  })
}
