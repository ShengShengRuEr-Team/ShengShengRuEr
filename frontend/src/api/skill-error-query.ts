import { request } from './client'

export type QueryType = 'skill' | 'error_cause'
export type SubjectType = QueryType | 'skill_category' | 'error_category'
export type RoleFilter = 'all' | 'primary' | 'auxiliary'

export interface PathNode {
  code: string
  display_code: string
  name: string
}

export interface SkillNode {
  kind: 'skill'
  id: number
  code: string
  display_code: string
  name: string
  level: number
  parent_id: number | null
  parent_code: string | null
  path: PathNode[]
  definition: string
  observable_behavior: string | null
  counter_example: string | null
  usage_scope: string
  exam_level_scope: string
  status: string
  review_status: string
  legacy_codes: string | null
  notes: string | null
  question_count: number | null
  primary_question_count: number | null
  auxiliary_question_count: number | null
}

export interface ErrorCauseNode {
  kind: 'error_cause'
  id: number
  code: string
  display_code: string
  name: string
  level: number
  parent_id: number | null
  parent_code: string | null
  path: PathNode[]
  definition: string
  confirmation_rule: string | null
  boundary_rule: string | null
  maturity: string
  status: string
  review_status: string
  legacy_codes: string | null
  notes: string | null
  question_count: number | null
  option_relation_count: number | null
}

export type DictionaryNode = SkillNode | ErrorCauseNode

export interface DictionaryData {
  dictionary_version: string
  dictionary_snapshot_id: number
  scope_version: string
  skills: SkillNode[]
  error_causes: ErrorCauseNode[]
}

export interface PaperRef {
  exam_paper_id: number
  exam_paper_code: string
  question_no: number
  paper_count: number
}

export interface MatchedSkill {
  code: string
  name: string
  role: string
}

export interface SkillRoleItem {
  code: string
  name: string
  role: string
}

export interface CandidateCauseSummary {
  code: string
  name: string
  rationale: string
  is_match: boolean
  evidence_count: number
}

export interface ErrorOptionSummary {
  base_option_letter: string
  display_option_letter: string | null
  option_mapping_state: string
  option_text: string
  matched_error_codes: string[]
  candidate_causes: CandidateCauseSummary[]
}

export interface WarningItem {
  code: string
  message: string
}

export interface QuestionListItem {
  question_id: number
  question_code: string
  question_text: string
  paper: PaperRef
  annotation_status: 'approved'
  annotation_status_label: string
  has_audio: boolean
  answer_state: 'available' | 'unavailable'
  matched_skills: MatchedSkill[]
  skills: SkillRoleItem[]
  error_options: ErrorOptionSummary[]
  warnings: WarningItem[]
}

export interface MatchedLeaf {
  code: string
  name: string
  display_code: string
}

export interface SubjectRef {
  type: SubjectType
  code: string
  name: string
  display_code: string
}

export interface QuestionListData {
  scope_version: string
  subject: SubjectRef
  matched_leaves: MatchedLeaf[]
  question_count: number
  primary_question_count: number | null
  auxiliary_question_count: number | null
  option_relation_count: number | null
  items: QuestionListItem[]
  next_cursor: number | null
}

export interface QuestionContent {
  id: number
  code: string
  text: string
  content_state: string
  review_status: string
  explanation_text: string
  explanation_source: string
}

export interface PaperDetail {
  exam_paper_id: number
  exam_paper_code: string
  exam_level: string
  exam_year: number
  exam_month: number
  paper_set: number
  question_no: number
  question_index: number | null
  option_mapping_state: string
  mapping_source: string
  audio_url: string | null
  audio_batch_id: number | null
  duration_ms: number | null
  paper_count: number
}

export interface PaperOptionRef {
  exam_paper_id: number
  exam_paper_code: string
  question_no: number
  option_mapping_state: string
  is_default: boolean
}

export interface OptionDisplay {
  display_letter: string
  base_letter: string
  text: string
}

export interface CorrectOption {
  display_letter: string | null
  base_letter: string | null
}

export interface SegmentView {
  segment_id: number
  segment_index: number
  segment_type: string
  text: string
  speaker_code: string | null
  start_ms: number
  end_ms: number
}

export interface PassageView {
  passage_id: number
  passage_index: number
  passage_type: string
  topic: string
  start_ms: number
  body_end_ms: number | null
  end_ms: number | null
  segments: SegmentView[]
}

export interface EvidenceView {
  evidence_id: number
  text: string
  start_ms: number
  end_ms: number
  source: string
  support_note: string | null
}

export interface SkillDetail {
  code: string
  name: string
  role: string
  definition: string
  evidence: EvidenceView[]
}

export interface CandidateCauseDetail {
  code: string
  name: string
  rationale: string
  evidence: EvidenceView[]
}

export interface ErrorOptionDetail {
  display_letter: string | null
  base_letter: string
  text: string
  candidate_causes: CandidateCauseDetail[]
}

export interface PersonalError {
  state: string
  message: string
}

export interface QuestionDetailData {
  scope_version: string
  question: QuestionContent
  paper: PaperDetail
  papers: PaperOptionRef[]
  options: OptionDisplay[]
  correct_option: CorrectOption | null
  answer_state: 'available' | 'unavailable'
  passage: PassageView | null
  answer_evidence: EvidenceView[]
  skills: SkillDetail[]
  error_options: ErrorOptionDetail[]
  personal_error: PersonalError
  warnings: WarningItem[]
}

export interface QuestionListParams {
  subject_type: SubjectType
  subject_code: string
  role?: RoleFilter
  cursor?: number
  limit?: number
  expected_scope_version?: string
}

export function getDictionary(): Promise<DictionaryData> {
  return request<DictionaryData>({
    url: '/api/v1/admin/skill-error-query/dictionary',
    method: 'get',
  })
}

export function listQuestions(params: QuestionListParams): Promise<QuestionListData> {
  return request<QuestionListData>({
    url: '/api/v1/admin/skill-error-query/questions',
    method: 'get',
    params,
  })
}

export function getQuestionDetail(
  questionId: number,
  options: { expectedScopeVersion?: string; examPaperId?: number } = {},
): Promise<QuestionDetailData> {
  return request<QuestionDetailData>({
    url: `/api/v1/admin/skill-error-query/questions/${questionId}`,
    method: 'get',
    params: {
      expected_scope_version: options.expectedScopeVersion,
      exam_paper_id: options.examPaperId,
    },
  })
}
