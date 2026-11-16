import { request, API_BASE_URL } from './client'
import { getAccessToken } from '../auth/storage'
import { clearSessionAndRedirect } from '../auth/session'
import { ApiError } from './api-error'
import type { Capabilities, Operation, Page, PendingOperation, QuestionView, WorkflowDetail, WorkflowSummary } from './processing-types'

export const WORKFLOWS = '/api/v1/admin/processing-workflows'
export function getCapabilities() { return request<Capabilities>({ url: `${WORKFLOWS}/capabilities` }) }
export function getWorkflow(id: string, signal?: AbortSignal) { return request<WorkflowDetail>({url: `${WORKFLOWS}/${id}`, signal}) }
export function listWorkflows(params: Record<string, unknown>, signal?: AbortSignal) {
  return request<Page<WorkflowSummary>>({url: WORKFLOWS, params, signal})
}
export function getQuestions(id: string, revision: string, signal?: AbortSignal) {
  return request<{items: QuestionView[]; result_hash: string | null; total: number}>({
    url: `${WORKFLOWS}/${id}/revisions/${revision}/questions`, params: {limit: 100}, signal})
}
export function pendingKey(owner: number, target: string) { return `m3-pending:${owner}:${target}` }
export function readPending(owner: number, target: string): PendingOperation | null {
  try { return JSON.parse(localStorage.getItem(pendingKey(owner, target)) ?? 'null') as PendingOperation | null } catch { return null }
}
export async function sendOperation(owner: number, target: string, operation: PendingOperation) {
  localStorage.setItem(pendingKey(owner, target), JSON.stringify(operation))
  const data = await request<Operation>({url: operation.url, method: operation.method,
    headers: {'Idempotency-Key': operation.key}, data: operation.body})
  localStorage.removeItem(pendingKey(owner, target))
  return data
}
export function findOperation(operation: PendingOperation) {
  return request<Operation>({url: `${WORKFLOWS}/operations/by-key`,
    params: {action: operation.action, idempotency_key: operation.key}})
}
export async function binary(path: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`, {headers: {Authorization: `Bearer ${getAccessToken() ?? ''}`}, signal})
  if (!response.ok) {
    if (response.status === 401) clearSessionAndRedirect()
    const body = await response.json().catch(() => ({msg: '媒体请求失败'})) as {msg?: string; error_code?: string}
    throw new ApiError(body.msg ?? '媒体请求失败', response.status, response.status, body.error_code)
  }
  return response.blob()
}
export async function putMaterial(id: string, revision: string, kind: string, uploadId: string, version: number, file: File) {
  const response = await fetch(`${API_BASE_URL}${WORKFLOWS}/${id}/materials/${kind}`, {method: 'PUT',
    headers: {Authorization: `Bearer ${getAccessToken() ?? ''}`, 'X-Upload-Id': uploadId,
      'X-Expected-Revision-Id': revision, 'X-Expected-Upload-Version': String(version), 'Content-Type': 'application/octet-stream'}, body: file})
  const body = await response.json() as {data: unknown; msg: string; error_code?: string}
  if (!response.ok) {
    if (response.status === 401) clearSessionAndRedirect()
    throw new ApiError(body.msg, response.status, response.status, body.error_code)
  }
  return body.data
}
