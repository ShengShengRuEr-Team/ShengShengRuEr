import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/api-error'
import { getListeningPapers } from '../../api/listening'
import {
  getWrongAnswer,
  listWrongAnswers,
  updateWrongAnswer,
} from '../../api/wrong-answers'
import type { WrongAnswerItem } from '../../api/wrong-answers'
import WrongAnswersPage from './WrongAnswersPage'

vi.mock('../../api/listening', () => ({
  getListeningPapers: vi.fn(),
}))

vi.mock('../../api/wrong-answers', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../api/wrong-answers')>(),
  listWrongAnswers: vi.fn(),
  getWrongAnswer: vi.fn(),
  updateWrongAnswer: vi.fn(),
}))

const pendingAnswer: WrongAnswerItem = {
  attempt_code: '12345678-1234-4234-8234-123456789abc',
  question_no: 1,
  question_text: 'Where does the conversation take place?',
  exam_paper_id: 42,
  paper_title: 'CET4 2025 年 6 月第 1 套',
  submitted_at: '2026-11-21T09:00:00Z',
  selected_option: 'A',
  learning_status: 'pending',
  is_hidden: false,
  reviewed_at: null,
}

function renderNotebook() {
  return render(
    <MemoryRouter>
      <WrongAnswersPage />
    </MemoryRouter>,
  )
}

describe('学生错题本', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(getListeningPapers).mockResolvedValue([])
    vi.mocked(listWrongAnswers).mockResolvedValue({
      items: [pendingAnswer],
      total: 1,
      state_writes_enabled: true,
    })
  })

  it('在隐藏和恢复之间保留掌握状态，并可重新标记待复习', async () => {
    const user = userEvent.setup()
    let saved = pendingAnswer
    vi.mocked(listWrongAnswers).mockImplementation(async (filters) => {
      const matches = saved.is_hidden === (filters.visibility === 'hidden')
      return {
        items: matches ? [saved] : [],
        total: matches ? 1 : 0,
        state_writes_enabled: true,
      }
    })
    vi.mocked(updateWrongAnswer).mockImplementation(async (_item, change) => {
      saved = { ...saved, ...change }
      return saved
    })

    renderNotebook()

    await user.click(await screen.findByRole('button', { name: '标记已掌握' }))
    expect(await screen.findByText('已掌握')).toBeVisible()
    expect(updateWrongAnswer).toHaveBeenNthCalledWith(1, pendingAnswer, { learning_status: 'mastered' })

    await user.click(screen.getByRole('button', { name: /^隐\s*藏$/ }))
    await user.click(await screen.findByRole('button', { name: '确认隐藏' }))
    expect(await screen.findByText('暂无错题')).toBeVisible()
    expect(updateWrongAnswer).toHaveBeenNthCalledWith(
      2, expect.objectContaining({ learning_status: 'mastered' }), { is_hidden: true },
    )

    await user.click(screen.getByRole('radio', { name: '已隐藏' }))
    expect(await screen.findByText('已掌握')).toBeVisible()
    await user.click(screen.getByRole('button', { name: /^恢\s*复$/ }))
    expect(await screen.findByText('暂无已隐藏的错题')).toBeVisible()
    expect(updateWrongAnswer).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({ is_hidden: true, learning_status: 'mastered' }),
      { is_hidden: false },
    )

    await user.click(screen.getByRole('radio', { name: /^错题$/ }))
    await user.click(await screen.findByRole('button', { name: '重新标记待复习' }))
    expect(await screen.findByText('待复习')).toBeVisible()
    expect(updateWrongAnswer).toHaveBeenNthCalledWith(
      4, expect.objectContaining({ is_hidden: false }), { learning_status: 'pending' },
    )
  })

  it('状态写入关闭时仍可读取记录，并提示详情未开放', async () => {
    const user = userEvent.setup()
    vi.mocked(listWrongAnswers).mockResolvedValue({
      items: [pendingAnswer],
      total: 1,
      state_writes_enabled: false,
    })
    vi.mocked(getWrongAnswer).mockRejectedValue(new ApiError('错题详情暂未开放', 503, 503))

    renderNotebook()

    expect(await screen.findByText('错题管理暂未开放')).toBeVisible()
    expect(screen.queryByRole('button', { name: '标记已掌握' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^隐\s*藏$/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '查看详情' }))
    expect(await screen.findByText('错题详情暂未开放')).toBeVisible()
    expect(screen.queryByText('正确答案')).not.toBeInTheDocument()
    expect(updateWrongAnswer).not.toHaveBeenCalled()
  })

  it('记录下线后，在详情中显示中性说明', async () => {
    const user = userEvent.setup()
    vi.mocked(getWrongAnswer).mockRejectedValue(new ApiError('资源不存在', 404, 404))

    renderNotebook()

    await user.click(await screen.findByRole('button', { name: '查看详情' }))
    const detail = await screen.findByRole('dialog')
    expect(await within(detail).findByText('该错题记录已不可查看')).toBeVisible()
    expect(within(detail).queryByText('资源不存在')).not.toBeInTheDocument()
  })

  it('显示获准查看的交卷快照及受限证据提示', async () => {
    const user = userEvent.setup()
    vi.mocked(getWrongAnswer).mockResolvedValue({
      ...pendingAnswer,
      options: { A: 'At a library', B: 'At a station' },
      correct_option: 'B',
      explanation_text: '',
      snapshot_note: '交卷时内容快照',
      audio_url: null,
      skills: [{
        code: 'LISTEN-1',
        name: '辨识场景',
        role: 'PRIMARY',
        has_restricted_evidence: true,
      }],
      candidate_causes: [{
        code: 'OPTION-2',
        name: '混淆地点',
        option_letter: 'A',
        has_restricted_evidence: false,
      }],
      personal_cause_status: 'unconfirmed',
    })

    renderNotebook()

    await user.click(await screen.findByRole('button', { name: '查看详情' }))
    const detail = await screen.findByRole('dialog')
    expect(await within(detail).findByText(/交卷时内容快照/)).toBeVisible()
    expect(within(detail).getByText('暂无解析')).toBeVisible()
    expect(within(detail).getByText(/辨识场景/)).toBeVisible()
    expect(within(detail).getByText(/混淆地点/)).toBeVisible()
    expect(within(detail).getByText('存在受限证据，暂不可查看')).toBeVisible()
  })

  it('切换列表页时请求下一页', async () => {
    const user = userEvent.setup()
    const nextAnswer = { ...pendingAnswer, question_no: 21, question_text: 'What happened next?' }
    vi.mocked(listWrongAnswers).mockImplementation(async (_filters, page) => ({
      items: [page === 1 ? pendingAnswer : nextAnswer],
      total: 21,
      state_writes_enabled: true,
    }))

    renderNotebook()

    expect(await screen.findByText(pendingAnswer.question_text)).toBeVisible()
    await user.click(screen.getByTitle('2'))
    expect(await screen.findByText(nextAnswer.question_text)).toBeVisible()
    expect(listWrongAnswers).toHaveBeenLastCalledWith(
      expect.objectContaining({ visibility: 'visible' }), 2, expect.any(AbortSignal),
    )
  })

  it('筛选未作答记录，区分筛选为空与没有错题', async () => {
    const user = userEvent.setup()
    vi.mocked(listWrongAnswers).mockImplementation(async (filters) => {
      const matches = filters.answer_type !== 'unanswered'
      return {
        items: matches ? [pendingAnswer] : [],
        total: matches ? 1 : 0,
        state_writes_enabled: true,
      }
    })

    renderNotebook()

    expect(await screen.findByText(pendingAnswer.question_text)).toBeVisible()
    await user.click(screen.getByRole('combobox', { name: '按错题类型筛选' }))
    await user.click(await screen.findByText('未作答'))
    expect(await screen.findByText('没有符合筛选条件的错题')).toBeVisible()
    expect(listWrongAnswers).toHaveBeenLastCalledWith(
      expect.objectContaining({ answer_type: 'unanswered' }), 1, expect.any(AbortSignal),
    )
  })

  it('列表首次加载失败后可以重试', async () => {
    const user = userEvent.setup()
    vi.mocked(listWrongAnswers).mockRejectedValueOnce(new Error('错题列表加载失败'))

    renderNotebook()

    expect(await screen.findByText('错题列表加载失败')).toBeVisible()
    await user.click(screen.getByRole('button', { name: /^重\s*试$/ }))
    await waitFor(() => expect(listWrongAnswers).toHaveBeenCalledTimes(2))
    expect(await screen.findByText(pendingAnswer.question_text)).toBeVisible()
  })
})
