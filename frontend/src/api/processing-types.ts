export interface Operation {
  operation_id: string; workflow_id: string; revision_id: string; action: string
  state: string; failure_code: string | null; result: Record<string, unknown>; created_at: string
}
export interface WorkflowSummary {
  workflow_id: string; revision_id: string; row_version: number
  exam_level: string; exam_year: number; exam_month: number; paper_set: number
  exam_paper_id: number | null; processing_state: string; content_review_state: string
  error_review_state: string; publication_state: string; created_at: string; updated_at: string
}
export interface WorkflowMaterial {
  kind: 'paper' | 'answer' | 'audio'; upload_id: string | null; upload_version: number
  state: string; material_id: number | null; lease_expired: boolean; failure_code: string | null
  filename: string | null
}
export interface Projection { task_id: string; artifact_id: number; artifact_hash: string; dependency_hash: string }
export interface WorkflowDetail extends WorkflowSummary {
  task_id: string | null; result_hash: string | null; document_mode: 'text' | 'scan'
  listening_pages: { paper: number[]; answer: number[] }; materials: WorkflowMaterial[]
  current_batch_id: number | null; is_student_visible: boolean; stages: Record<string, Projection>
  review_session_id: string | null; review_session_version: number | null
  progress: {stage: string; completed_count: number; total_count: number | null; elapsed_ms: number; checkpoint: string | null}
  gates: Array<{kind: string; state: string; dependency_hash: string | null}>
  issues: Array<{code: string; message: string; retryable: boolean}>
  allowed_actions: Array<{action: string; enabled: boolean; blocked_reason: string | null}>
  usage: {known_usd: string; reserved_usd: string; has_unknown_charges: boolean}
}
export interface Evidence {
  _src_id: string; relation_src_id: string; evidence_text: string; start_ms: number; end_ms: number
  support_note?: string
}
export interface QuestionView {
  question_src_id: string; question_no: number; question_text: string; explanation_text: string
  correct_option_base: string; correct_option_display: string; generation_state: string
  options: Array<{display_letter: string; base_option_letter: string; text: string; error_causes: Array<{
    relation_src_id: string; code: string; rationale: string; evidence: Evidence[]
  }>}>
  skills: Array<{_src_id: string; skill_code: string; role: string; attributes_json?: {annotation_reason?: string}; evidence: Evidence[]}>
  answer_evidence: Evidence[]; review_requirements: Record<string, string[]>
}
export interface ReviewItem {
  question_src_id: string; content: 'approved' | 'changes_required'
  primary_skills: Array<{reference: string; decision: string}>; answer_evidence: Array<{reference: string; decision: string}>
  error_causes: Array<{reference: string; decision: string}>; empty_errors_confirmed: boolean
  note: string; issues: Array<Record<string, unknown>>
}
export interface PendingOperation {action: string; url: string; method: 'POST' | 'PATCH'; key: string; body: Record<string, unknown>}
export interface Page<T> { items: T[]; next_cursor: string | null }
export interface Capabilities { max_upload_bytes: number; processing_ready: boolean; blocked_reason: string | null }
