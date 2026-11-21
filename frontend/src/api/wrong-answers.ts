import { request } from './client'

export interface WrongAnswerItem {
  attempt_code: string
  question_no: number
  question_text: string
  paper_title: string
  submitted_at: string
  selected_option: string | null
}

interface Annotation {
  code: string
  name: string
  reason: string | null
  evidence: { text: string; note: string | null }[]
}

export interface WrongAnswerDetail extends WrongAnswerItem {
  options: Record<string, string>
  correct_option: string
  explanation_text: string
  transcript: string[]
  audio_url: string | null
  skills: (Annotation & { role: string | null })[]
  candidate_causes: (Annotation & { option_letter: string })[]
  personal_cause_status: 'unconfirmed'
}

const notebookUrl = '/api/v1/wrong-answers'

function entryUrl(item: WrongAnswerItem) {
  return `${notebookUrl}/${item.attempt_code}/${item.question_no}`
}

export function listWrongAnswers(keyword: string, page: number, signal: AbortSignal) {
  return request<{ items: WrongAnswerItem[]; total: number }>({
    url: notebookUrl,
    params: { keyword, page, limit: 20 },
    signal,
  })
}

export function getWrongAnswer(item: WrongAnswerItem, signal: AbortSignal) {
  return request<WrongAnswerDetail>({ url: entryUrl(item), signal })
}

export function dismissWrongAnswer(item: WrongAnswerItem) {
  return request<null>({ method: 'DELETE', url: entryUrl(item) })
}
