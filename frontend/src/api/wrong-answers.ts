import { request } from './client'

export type WrongAnswerLearningStatus = 'pending' | 'mastered'
export type WrongAnswerVisibility = 'visible' | 'hidden' | 'all'

export interface WrongAnswerFilters {
  exam_paper_id?: number
  answer_type?: 'incorrect' | 'unanswered'
  learning_status?: WrongAnswerLearningStatus
  visibility: WrongAnswerVisibility
}

export interface WrongAnswerItem {
  attempt_code: string
  question_no: number
  question_text: string
  exam_paper_id: number
  paper_title: string
  submitted_at: string
  selected_option: string | null
  learning_status: WrongAnswerLearningStatus
  is_hidden: boolean
  updated_at: string
  reviewed_at: string | null
}

interface Annotation {
  code: string
  name: string
  evidence_status: 'restricted'
}

type AudioStatus =
  | { status: 'available'; url: string }
  | { status: 'missing' | 'batch_mismatch'; url: null }

export interface WrongAnswerDetail extends WrongAnswerItem {
  snapshot_note: string
  options: Record<string, string>
  correct_option: string
  explanation_text: string | null
  explanation_status: 'available' | 'missing' | 'restricted'
  has_explanation: boolean
  audio: AudioStatus
  skills: (Annotation & { role: string; definition: string | null })[]
  candidate_causes: (Annotation & { option_letter: string; basis_summary: string | null })[]
  evidence_access: 'none' | 'restricted'
  annotation_note: string
  annotation_source_note: string
  personal_cause_status: 'unconfirmed'
}

export interface WrongAnswerPage {
  items: WrongAnswerItem[]
  total: number
  state_writes_enabled: boolean
}

export type WrongAnswerChange =
  | { learning_status: WrongAnswerLearningStatus; is_hidden?: boolean }
  | { is_hidden: boolean; learning_status?: WrongAnswerLearningStatus }

const notebookUrl = '/api/v1/wrong-answers'
export const WRONG_ANSWER_PAGE_SIZE = 20

function entryUrl(item: WrongAnswerItem) {
  return `${notebookUrl}/${item.attempt_code}/${item.question_no}`
}

export function listWrongAnswers(filters: WrongAnswerFilters, page: number, signal: AbortSignal) {
  return request<WrongAnswerPage>({
    url: notebookUrl,
    params: { ...filters, page, limit: WRONG_ANSWER_PAGE_SIZE },
    signal,
  })
}

export function getWrongAnswer(item: WrongAnswerItem, signal: AbortSignal) {
  return request<WrongAnswerDetail>({ url: entryUrl(item), signal })
}

export function updateWrongAnswer(item: WrongAnswerItem, change: WrongAnswerChange) {
  return request<WrongAnswerItem>({ method: 'PATCH', url: entryUrl(item), data: change })
}
