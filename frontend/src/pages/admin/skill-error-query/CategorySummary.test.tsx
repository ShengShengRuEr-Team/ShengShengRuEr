import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import CategorySummary from './CategorySummary'
import DictionaryTree from './DictionaryTree'
import type {
  DictionaryData,
  QuestionListData,
  QuestionListItem,
} from '../../../api/skill-error-query'

const emptyCategory: QuestionListData = {
  scope_version: 'scope-1',
  subject: {
    type: 'skill_category',
    code: 'SKG_1_1',
    name: '词语含义理解',
    display_code: '1.1',
  },
  matched_leaves: [
    {
      code: 'S07',
      name: '熟悉词汇的词义识别',
      display_code: '1.1.1',
      question_count: 0,
      primary_question_count: 0,
      auxiliary_question_count: 0,
      option_relation_count: null,
    },
    {
      code: 'S08',
      name: '具体语境中的词义理解',
      display_code: '1.1.2',
      question_count: 0,
      primary_question_count: 0,
      auxiliary_question_count: 0,
      option_relation_count: null,
    },
  ],
  question_count: 0,
  primary_question_count: null,
  auxiliary_question_count: null,
  option_relation_count: null,
  items: [],
  next_cursor: null,
}

const item: QuestionListItem = {
  question_id: 1,
  question_code: 'Q1',
  question_text: 'Question one',
  paper: {
    exam_paper_id: 1,
    exam_paper_code: 'CET4-2025-06-1',
    question_no: 1,
    paper_count: 1,
  },
  annotation_status: 'approved',
  annotation_status_label: '正式审核通过',
  has_audio: false,
  answer_state: 'available',
  matched_skills: [{ code: 'S08', name: '具体语境中的词义理解', role: 'PRIMARY' }],
  skills: [{ code: 'S08', name: '具体语境中的词义理解', role: 'PRIMARY' }],
  error_options: [],
  warnings: [],
}

const nonEmptyCategory: QuestionListData = {
  ...emptyCategory,
  matched_leaves: [
    {
      ...emptyCategory.matched_leaves[0],
      question_count: 1,
      primary_question_count: 1,
      auxiliary_question_count: 0,
    },
    emptyCategory.matched_leaves[1],
  ],
  question_count: 1,
  items: [item],
}

const dictionary: DictionaryData = {
  dictionary_version: 'v1',
  dictionary_snapshot_id: 1,
  scope_version: 'scope-1',
  skills: [
    {
      kind: 'skill',
      id: 1,
      code: 'K5',
      display_code: '1',
      name: '词汇与表达理解',
      level: 1,
      parent_id: null,
      parent_code: null,
      path: [],
      definition: '',
      observable_behavior: null,
      counter_example: null,
      usage_scope: '',
      exam_level_scope: '',
      status: '启用',
      review_status: '待审核',
      legacy_codes: null,
      notes: null,
      question_count: null,
      primary_question_count: null,
      auxiliary_question_count: null,
    },
    {
      kind: 'skill',
      id: 2,
      code: 'S08',
      display_code: '1.1.2',
      name: '具体语境中的词义理解',
      level: 3,
      parent_id: 1,
      parent_code: 'K5',
      path: [],
      definition: '',
      observable_behavior: null,
      counter_example: null,
      usage_scope: '',
      exam_level_scope: '',
      status: '启用',
      review_status: '待审核',
      legacy_codes: null,
      notes: null,
      question_count: 1,
      primary_question_count: 1,
      auxiliary_question_count: 0,
    },
  ],
  error_causes: [],
}

describe('category and tree empty states', () => {
  it('shows category coverage gap and keeps zero leaves without drill-down', () => {
    render(
      <CategorySummary
        data={emptyCategory}
        mode="by-leaf"
        onOpenLeaf={vi.fn()}
        onOpenDetail={vi.fn()}
        onScopeRefresh={vi.fn()}
      />,
    )
    expect(screen.getByText('该分类暂无正式题目（题库覆盖缺口）')).toBeInTheDocument()
    expect(screen.getAllByText('暂无题目')).toHaveLength(2)
    expect(screen.queryByText('全部题目（按题目去重）')).not.toBeInTheDocument()
  })

  it('uses the by-leaf table and drills down only to leaves with questions', async () => {
    const user = userEvent.setup()
    const onOpenLeaf = vi.fn()
    render(
      <CategorySummary
        data={nonEmptyCategory}
        mode="by-leaf"
        onOpenLeaf={onOpenLeaf}
        onOpenDetail={vi.fn()}
        onScopeRefresh={vi.fn()}
      />,
    )
    expect(screen.queryByText('全部题目（按题目去重）')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '查看条目' }))
    expect(onOpenLeaf).toHaveBeenCalledWith('S07')
    expect(screen.getAllByText('暂无题目')).toHaveLength(1)
  })

  it('shows no-result message and clears the tree search', async () => {
    const user = userEvent.setup()
    const onClearSearch = vi.fn()
    render(
      <DictionaryTree
        nodes={dictionary.skills}
        search="不存在的技能"
        onSelect={vi.fn()}
        onClearSearch={onClearSearch}
      />,
    )
    expect(screen.getByText('未找到匹配条目')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '清除搜索' }))
    expect(onClearSearch).toHaveBeenCalled()
  })
})
