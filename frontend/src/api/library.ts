import { request } from './client'
import type { Operation } from './processing-types'

export const LIBRARY = '/api/v1/admin/listening-papers'
export const workflowUrl = (id: string) => `/api/v1/admin/processing-workflows/${id}`
export interface LibraryPaper {
  exam_paper_id: number; code: string; exam_level: string; exam_year: number; exam_month: number; paper_set: number
  question_count: number; expected_question_count: number; current_batch_id: number | null; current_batch_code: string | null
  workflow_id: string | null; processing_state: string; review_state: string; publication_state: string
  check_passed: boolean; is_visible: boolean; version_no: number; row_version: number
  archived_at: string | null; archive_reason: string | null
}
export interface Entity { _src_id: string; [key: string]: unknown }
export type Snapshot = Record<string, Entity[]>
export interface LibraryDraft {
  exam_paper_id: number; workflow_id: string; revision_id: string; row_version: number
  content_hash: string; save_version_id: string | null; version_no: number; snapshot: Snapshot
  issues: {issue_code: string; message: string; src_id?: string}[]; archived: boolean; workflow_contract: string
  source_materials?: {material_id:number; kind:string; sha256:string}[]
}
export interface LibraryVersion {
  id: string; version_no: number; saved_at: string; reason: string; origin_type: string
  protection_reasons: string[]; eligible_after: string | null; can_restore: boolean
  snapshot_pruned_at: string | null
}
export interface LibraryChange {section: string; src_id: string; fields: string[]; before: unknown; after: unknown}
export interface Preview {changes: LibraryChange[]; impact: {final_review_invalidated: boolean; source_review_invalidated: boolean; alignment_required: boolean}; issues: LibraryDraft['issues']}
export interface LibraryCandidate { id: string; question_src_id: string; method_hash: string; dependency_hash: string; payload: Record<string, unknown>; created_at: string; provider: string; requested_model: string; response_model: string | null; region: string; evaluation_only: boolean }
export interface LibraryProvider {
  provider: string; requested_model: string; region: string; credentials_configured: boolean; configuration_ready: boolean
  issues: Array<{code: string; message: string}>; currency: string | null; usd_per_currency: string | null
  exchange_rate_source: string | null; exchange_rate_effective_at: string | null
}
export const getProviders = (signal?: AbortSignal) => request<{items: LibraryProvider[]; connectivity_checked: boolean}>({url:'/api/v1/admin/library-providers',signal})
export const getDraft = (id: string, signal?: AbortSignal) => request<LibraryDraft>({url: `${workflowUrl(id)}/edit-draft`, signal})
export const listLibrary = (params: Record<string, unknown>, signal?: AbortSignal) => request<{items: LibraryPaper[]; total: number; page: number; page_size: number}>({url: LIBRARY, params, signal})
export const getVersions = (id: string) => request<{items: LibraryVersion[]}>({url: `${workflowUrl(id)}/versions`})
export const getCandidates = (id: string) => request<{items: LibraryCandidate[]}>({url: `${workflowUrl(id)}/candidates`})
export const previewDraft = (id: string, data: unknown) => request<Preview>({url: `${workflowUrl(id)}/edit-draft/preview`, method: 'POST', data})
export const libraryWrite = (url: string, data: unknown, key: string, method = 'POST') => request<Operation>({url, data, method, headers: {'Idempotency-Key': key}})
export const text = (row: Entity | undefined, field: string) => typeof row?.[field] === 'string' ? row[field] as string : ''
