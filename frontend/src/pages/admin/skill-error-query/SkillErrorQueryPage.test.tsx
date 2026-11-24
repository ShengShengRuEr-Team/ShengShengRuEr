import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/api-error'
import ErrorQuestionList from './ErrorQuestionList'
import SkillErrorQueryPage from './SkillErrorQueryPage'
import type {
  DictionaryData,
  ErrorCauseNode,
  QuestionDetailData,
  QuestionListData,
  QuestionListItem,
  SkillNode,
} from '../../../api/skill-error-query'

const api = vi.hoisted(() => ({
  getDictionary: vi.fn(),
  listQuestions: vi.fn(),
  getQuestionDetail: vi.fn(),
}))

vi.mock('../../../api/skill-error-query', () => ({
  getDictionary: api.getDictionary,
  listQuestions: api.listQuestions,
  getQuestionDetail: api.getQuestionDetail,
}))

const baseSkill = {
  kind: 'skill' as const,
  legacy_codes: null,
  notes: null,
  status: '启用',
  review_status: '已审核',
  usage_scope: '听力',
  exam_level_scope: 'CET4/CET6',
  definition: '定义',
  observable_behavior: null,
  counter_example: null,
  question_count: null,
  primary_question_count: null,
  auxiliary_question_count: null,
  path: [],
}

const dictionary: DictionaryData = {
  dictionary_version: '2026-10-24',
  dictionary_snapshot_id: 1,
  scope_version: 'scope-1',
  skills: [
    {
      ...baseSkill,
      id: 1,
      code: 'K5',
      display_code: '3',
      name: '篇章理解',
      level: 1,
      parent_id: null,
      parent_code: null,
      path: [{ code: 'K5', display_code: '3', name: '篇章理解' }],
    } as SkillNode,
    {
      ...baseSkill,
      id: 2,
      code: 'SKG_3_1',
      display_code: '3.1',
      name: '内容衔接与结构理解',
      level: 2,
      parent_id: 1,
      parent_code: 'K5',
      path: [
        { code: 'K5', display_code: '3', name: '篇章理解' },
        { code: 'SKG_3_1', display_code: '3.1', name: '内容衔接与结构理解' },
      ],
    } as SkillNode,
    {
      ...baseSkill,
      id: 3,
      code: 'S26',
      display_code: '3.1.2',
      name: '跨句指代对象识别',
      level: 3,
      parent_id: 2,
      parent_code: 'SKG_3_1',
      path: [
        { code: 'K5', display_code: '3', name: '篇章理解' },
        { code: 'SKG_3_1', display_code: '3.1', name: '内容衔接与结构理解' },
        { code: 'S26', display_code: '3.1.2', name: '跨句指代对象识别' },
      ],
      question_count: 1,
      primary_question_count: 1,
      auxiliary_question_count: 0,
    } as SkillNode,
  ],
  error_causes: [
    {
      kind: 'error_cause',
      id: 10,
      code: 'E4',
      display_code: '4',
      name: '语义理解错误',
      level: 1,
      parent_id: null,
      parent_code: null,
      path: [{ code: 'E4', display_code: '4', name: '语义理解错误' }],
      definition: '定义',
      confirmation_rule: null,
      boundary_rule: null,
      maturity: '稳定',
      status: '启用',
      review_status: '已审核',
      legacy_codes: null,
      notes: null,
      question_count: null,
      option_relation_count: null,
    },
    {
      kind: 'error_cause',
      id: 11,
      code: 'E4.3',
      display_code: '4.3',
      name: '无关信息误选',
      level: 3,
      parent_id: 10,
      parent_code: 'E4',
      path: [
        { code: 'E4', display_code: '4', name: '语义理解错误' },
        { code: 'E4.3', display_code: '4.3', name: '无关信息误选' },
      ],
      definition: '定义',
      confirmation_rule: '规则',
      boundary_rule: '边界',
      maturity: '稳定',
      status: '启用',
      review_status: '已审核',
      legacy_codes: null,
      notes: null,
      question_count: 1,
      option_relation_count: 1,
    } as ErrorCauseNode,
  ],
}

const item: QuestionListItem = {
  question_id: 101,
  question_code: 'Q101',
  question_text: 'What does the speaker imply?',
  paper: {
    exam_paper_id: 5,
    exam_paper_code: 'CET4-2025-06-1',
    question_no: 3,
    paper_count: 1,
  },
  annotation_status: 'approved',
  annotation_status_label: '正式审核通过',
  has_audio: true,
  answer_state: 'available',
  matched_skills: [{ code: 'S26', name: '跨句指代对象识别', role: 'PRIMARY' }],
  skills: [{ code: 'S26', name: '跨句指代对象识别', role: 'PRIMARY' }],
  error_options: [],
  warnings: [],
}

const page: QuestionListData = {
  scope_version: 'scope-1',
  subject: {
    type: 'skill',
    code: 'S26',
    name: '跨句指代对象识别',
    display_code: '3.1.2',
  },
  matched_leaves: [
    {
      code: 'S26',
      name: '跨句指代对象识别',
      display_code: '3.1.2',
      question_count: 1,
      primary_question_count: 1,
      auxiliary_question_count: 0,
      option_relation_count: null,
    },
  ],
  question_count: 1,
  primary_question_count: 1,
  auxiliary_question_count: 0,
  option_relation_count: null,
  items: [item],
  next_cursor: null,
}

const detail: QuestionDetailData = {
  scope_version: 'scope-1',
  question: {
    id: 101,
    code: 'Q101',
    text: 'What does the speaker imply?',
    content_state: 'content_ready',
    review_status: '已审核',
    explanation_text: '解析正文',
    explanation_source: 'answer',
  },
  paper: {
    exam_paper_id: 5,
    exam_paper_code: 'CET4-2025-06-1',
    exam_level: 'CET4',
    exam_year: 2025,
    exam_month: 6,
    paper_set: 1,
    question_no: 3,
    question_index: 3,
    option_mapping_state: '已知',
    option_mapping_reordered: false,
    mapping_source: 'fixture',
    audio_url: '/api/v1/listening-papers/5/audio',
    audio_batch_id: 9,
    duration_ms: 1000,
    paper_count: 1,
  },
  papers: [
    {
      exam_paper_id: 5,
      exam_paper_code: 'CET4-2025-06-1',
      question_no: 3,
      option_mapping_state: '已知',
      option_mapping_reordered: false,
      is_default: true,
    },
  ],
  options: [
    { display_letter: 'A', base_letter: 'A', text: 'A text' },
    { display_letter: 'B', base_letter: 'B', text: 'B text' },
    { display_letter: 'C', base_letter: 'C', text: 'C text' },
    { display_letter: 'D', base_letter: 'D', text: 'D text' },
  ],
  correct_option: { display_letter: 'B', base_letter: 'B' },
  answer_state: 'available',
  passage: null,
  answer_evidence: [
    { evidence_id: 1, text: '答案证据正文', start_ms: 1, end_ms: 2, source: 'answer', support_note: null },
  ],
  skills: [
    {
      code: 'S26',
      name: '跨句指代对象识别',
      role: 'PRIMARY',
      definition: '技能定义',
      evidence: [
        { evidence_id: 2, text: '技能证据正文', start_ms: 1, end_ms: 2, source: 'transcript', support_note: null },
      ],
    },
  ],
  error_options: [
    {
      display_letter: 'D',
      base_letter: 'D',
      text: 'D text',
      candidate_causes: [
        {
          code: 'E4.3',
          name: '无关信息误选',
          rationale: '与截止日期无关',
          evidence: [
            { evidence_id: 3, text: '候选证据正文', start_ms: 1, end_ms: 2, source: 'transcript', support_note: '说明' },
          ],
        },
      ],
    },
  ],
  personal_error: {
    state: 'not_in_scope',
    message: '未确认个人错因（本查询不涉及个人）',
    explanation:
      '题目候选错因只描述错误选项的可能机制；学生答错某题不等于确认其个人错因；不得根据作答结果自动生成个人错因；个人错因需在错题本（需求二）按本人作答确认后查看。',
  },
  warnings: [],
}

const errorItem: QuestionListItem = {
  ...item,
  question_id: 102,
  question_text: 'Why does the woman mention the deadline?',
  error_options: [
    {
      base_option_letter: 'D',
      display_option_letter: 'D',
      option_mapping_state: '已知',
      option_mapping_reordered: false,
      option_text: 'It is unrelated to the deadline.',
      matched_error_codes: ['E4.3'],
      candidate_causes: [
        { code: 'E4.3', name: '无关信息误选', rationale: '与截止日期无关', is_match: true, evidence_count: 1 },
      ],
    },
  ],
}

describe('skill/error query page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getDictionary.mockResolvedValue(dictionary)
    api.listQuestions.mockResolvedValue(page)
    api.getQuestionDetail.mockResolvedValue(detail)
  })

  it('shows the dictionary and opens the question detail drawer', async () => {
    const user = userEvent.setup()
    render(<SkillErrorQueryPage />)
    await waitFor(() => expect(api.listQuestions).toHaveBeenCalled())
    expect(await screen.findByText('What does the speaker imply?')).toBeInTheDocument()
    expect(await screen.findByText('正式审核通过')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /详情/ }))
    expect(await screen.findByText('第 3 题 · CET4-2025-06-1')).toBeInTheDocument()
    expect(await screen.findByText('候选证据正文')).toBeInTheDocument()
    expect(api.getQuestionDetail).toHaveBeenCalledWith(101, {
      expectedScopeVersion: 'scope-1',
      examPaperId: 5,
    })
  })

  it('shows a reorder warning when the selected paper mapping is non-identity', async () => {
    api.getQuestionDetail.mockResolvedValue({
      ...detail,
      paper: { ...detail.paper, option_mapping_reordered: true },
    })
    const user = userEvent.setup()
    render(<SkillErrorQueryPage />)
    await waitFor(() => expect(api.listQuestions).toHaveBeenCalled())
    await screen.findByText('What does the speaker imply?')
    await user.click(screen.getByRole('button', { name: /详情/ }))
    expect(await screen.findByText('该套试卷存在选项重排')).toBeInTheDocument()
  })

  it('uses the new page size in a single first-page request', async () => {
    const user = userEvent.setup()
    render(<SkillErrorQueryPage />)
    await waitFor(() => expect(api.listQuestions).toHaveBeenCalled())
    await screen.findByText('What does the speaker imply?', {}, { timeout: 5000 })
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByText('50 条/页'))
    await waitFor(() => {
      const calls = api.listQuestions.mock.calls
      expect(calls.some(([params]) => params.limit === 50 && params.cursor === 0)).toBe(true)
    })
    const last = api.listQuestions.mock.calls.at(-1)?.[0]
    expect(last.limit).toBe(50)
    expect(last.cursor).toBe(0)
  })

  it('reloads the dictionary and first page after a scope conflict', async () => {
    api.listQuestions
      .mockRejectedValueOnce(
        new ApiError('scope changed', 409, 409, 'SCOPE_CHANGED'),
      )
      .mockResolvedValue(page)
    render(<SkillErrorQueryPage />)
    await waitFor(() => expect(api.getDictionary).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(api.listQuestions).toHaveBeenCalled())
    await screen.findByText('What does the speaker imply?', {}, { timeout: 5000 })
  })

  it('loads candidate evidence when an error row expands', async () => {
    const user = userEvent.setup()
    render(
      <ErrorQuestionList
        items={[errorItem]}
        scopeVersion="scope-1"
        onOpenDetail={vi.fn()}
        onScopeRefresh={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /Expand row/i }))
    expect(await screen.findByText('候选证据正文')).toBeInTheDocument()
    expect(screen.getByText('题目候选错因（非个人错因）')).toBeInTheDocument()
    expect(api.getQuestionDetail).toHaveBeenCalledWith(102, {
      expectedScopeVersion: 'scope-1',
      examPaperId: 5,
    })
  })

  it('shows a retry path when evidence loading fails', async () => {
    api.getQuestionDetail
      .mockRejectedValueOnce(new Error('证据服务暂不可用'))
      .mockResolvedValueOnce(detail)
    const user = userEvent.setup()
    render(
      <ErrorQuestionList
        items={[errorItem]}
        scopeVersion="scope-1"
        onOpenDetail={vi.fn()}
        onScopeRefresh={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /Expand row/i }))
    expect(await screen.findByText('证据服务暂不可用')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /重\s*试/ }))
    await waitFor(() => expect(screen.getByText('候选证据正文')).toBeInTheDocument())
  })
})
