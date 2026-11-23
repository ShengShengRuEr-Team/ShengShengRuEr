import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/api-error'
import { loadAuthenticatedAudio } from '../../api/audio'
import { getListeningPapers } from '../../api/listening'
import {
  getWrongAnswer,
  listWrongAnswers,
  updateWrongAnswer,
} from '../../api/wrong-answers'
import type { WrongAnswerDetail, WrongAnswerItem } from '../../api/wrong-answers'
import WrongAnswersPage from './WrongAnswersPage'

vi.mock('../../api/listening', () => ({
  getListeningPapers: vi.fn(),
}))

vi.mock('../../api/audio', () => ({
  loadAuthenticatedAudio: vi.fn(),
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
  exam_paper_id: 42,
  paper_title: 'CET4 2025 年 6 月第 1 套',
  submitted_at: '2026-11-21T09:00:00Z',
  answer_type: 'incorrect',
  learning_status: 'pending',
  is_hidden: false,
  updated_at: '2026-11-21T09:00:00Z',
  reviewed_at: null,
}

const notebookDetail: WrongAnswerDetail = {
  ...pendingAnswer,
  question_text: 'Where does the conversation take place?',
  options: { A: 'At a library', B: 'At a station' },
  selected_option: 'A',
  correct_option: 'B',
  explanation_text: null,
  explanation_status: 'missing',
  has_explanation: false,
  snapshot_note: '交卷时内容快照',
  audio: { status: 'missing', url: null },
  skills: [{
    code: 'LISTEN-1',
    name: '辨识场景',
    role: 'PRIMARY',
    definition: '从对话线索辨识场景',
    evidence_status: 'restricted',
  }],
  candidate_causes: [{
    code: 'OPTION-2',
    name: '混淆地点',
    option_letter: 'A',
    basis_summary: '混淆相近的场景线索',
    evidence_status: 'restricted',
  }],
  evidence_access: 'restricted',
  personal_cause_status: 'unconfirmed',
  annotation_note: '候选错因不代表个人已确认的错因',
  annotation_source_note: '关联标注来自交卷来源批次的当前有效审核结果，可能与交卷时不同。',
  annotation_reviewed_at: '2026-11-21T07:30:00Z',
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
    expect(screen.getByText('已隐藏，恢复后可查看详情')).toBeVisible()
    expect(screen.queryByRole('button', { name: '查看详情' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^恢\s*复$/ }))
    expect(await screen.findByText('暂无已隐藏的错题')).toBeVisible()
    expect(updateWrongAnswer).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({ is_hidden: true, learning_status: 'mastered' }),
      { is_hidden: false },
    )

    await user.click(screen.getByRole('radio', { name: /^错题$/ }))
    expect(await screen.findByRole('button', { name: '查看详情' })).toBeVisible()
    await user.click(await screen.findByRole('button', { name: '重新标记待复习' }))
    expect(await screen.findByText('待复习')).toBeVisible()
    expect(updateWrongAnswer).toHaveBeenNthCalledWith(
      4, expect.objectContaining({ is_hidden: false }), { learning_status: 'pending' },
    )
  })

  it('全部筛选仍要求恢复已隐藏记录后才能查看详情', async () => {
    const user = userEvent.setup()
    vi.mocked(listWrongAnswers).mockImplementation(async ({ visibility }) => ({
      items: visibility === 'all' ? [{ ...pendingAnswer, is_hidden: true }] : [],
      total: Number(visibility === 'all'),
      state_writes_enabled: true,
    }))
    renderNotebook()

    await user.click(screen.getByRole('radio', { name: '全部' }))
    expect(await screen.findByText('已隐藏，恢复后可查看详情')).toBeVisible()
    expect(screen.queryByRole('button', { name: '查看详情' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^恢\s*复$/ })).toBeVisible()
    expect(getWrongAnswer).not.toHaveBeenCalled()
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
    expect(screen.getByText('第 1 题')).toBeVisible()
    expect(screen.getByText('答错')).toBeVisible()
    expect(screen.queryByText(notebookDetail.question_text)).not.toBeInTheDocument()
    expect(screen.queryByText('选了 A')).not.toBeInTheDocument()
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
    vi.mocked(getWrongAnswer).mockResolvedValue(notebookDetail)

    renderNotebook()

    await user.click(await screen.findByRole('button', { name: '查看详情' }))
    const detail = await screen.findByRole('dialog')
    expect(await within(detail).findByText(/交卷时内容快照/)).toBeVisible()
    expect(within(detail).getByText('暂无解析')).toBeVisible()
    expect(within(detail).getByText('辨识场景（LISTEN-1）')).toBeVisible()
    expect(within(detail).getByText('从对话线索辨识场景')).toBeVisible()
    expect(within(detail).getByText(/混淆地点/)).toBeVisible()
    expect(within(detail).getByText(notebookDetail.annotation_source_note)).toBeVisible()
    const reviewTime = within(detail).getByText(/标注审核时间/).querySelector('time')
    expect(reviewTime).toHaveAttribute('datetime', notebookDetail.annotation_reviewed_at)
    expect(within(detail).getByText(notebookDetail.annotation_note)).toBeVisible()
    expect(within(detail).getByText('暂无音频')).toBeVisible()
    expect(within(detail).getByText('存在受限证据，暂不可查看')).toBeVisible()
  })

  it.each([409, 404])('音频返回 %d 时清除详情并重新校验权限', async (status) => {
    const user = userEvent.setup()
    const audioUrl = '/api/v1/listening-papers/42/audio?expected_batch_id=12'
    vi.mocked(getWrongAnswer).mockResolvedValueOnce({
      ...notebookDetail,
      explanation_status: 'restricted',
      audio: { status: 'available', url: audioUrl },
    })
    let finishRefresh: (value: WrongAnswerDetail) => void = () => undefined
    let rejectRefresh: (reason: ApiError) => void = () => undefined
    vi.mocked(getWrongAnswer).mockReturnValueOnce(new Promise((resolve, reject) => {
      finishRefresh = resolve
      rejectRefresh = reject
    }))
    vi.mocked(loadAuthenticatedAudio).mockRejectedValue(new ApiError('音频不可用', status, status))

    renderNotebook()
    await user.click(await screen.findByRole('button', { name: '查看详情' }))
    const detail = await screen.findByRole('dialog')
    expect(await within(detail).findByText('历史解析暂不可查看')).toBeVisible()
    await user.click(within(detail).getByRole('button', { name: '加载音频' }))
    await waitFor(() => expect(getWrongAnswer).toHaveBeenCalledTimes(2))
    expect(within(detail).queryByText('At a station', { exact: false })).not.toBeInTheDocument()

    if (status === 409) {
      finishRefresh({
        ...notebookDetail,
        audio: { status: 'batch_mismatch', url: null },
        skills: [],
        candidate_causes: [],
        evidence_access: 'none',
        annotation_reviewed_at: null,
      })
      expect(await within(detail).findByText('当前音频与交卷批次无法对应')).toBeVisible()
      expect(within(detail).queryByText(/标注审核时间/)).not.toBeInTheDocument()
    } else {
      rejectRefresh(new ApiError('记录不可查看', 404, 404))
      expect(await within(detail).findByText('该错题记录已不可查看')).toBeVisible()
    }
    expect(loadAuthenticatedAudio).toHaveBeenCalledExactlyOnceWith(audioUrl, expect.any(AbortSignal))
  })

  it('切换列表页时请求下一页', async () => {
    const user = userEvent.setup()
    const nextAnswer = { ...pendingAnswer, question_no: 21 }
    vi.mocked(listWrongAnswers).mockImplementation(async (_filters, page) => ({
      items: [page === 1 ? pendingAnswer : nextAnswer],
      total: 21,
      state_writes_enabled: true,
    }))

    renderNotebook()

    expect(await screen.findByText('第 1 题')).toBeVisible()
    await user.click(screen.getByTitle('2'))
    expect(await screen.findByText('第 21 题')).toBeVisible()
    expect(listWrongAnswers).toHaveBeenLastCalledWith(
      expect.objectContaining({ visibility: 'visible' }), 2, expect.any(AbortSignal),
    )
    await user.click(screen.getByRole('radio', { name: '全部' }))
    await waitFor(() => expect(listWrongAnswers).toHaveBeenLastCalledWith(
      expect.objectContaining({ visibility: 'all' }), 1, expect.any(AbortSignal),
    ))
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

    expect(await screen.findByText('第 1 题')).toBeVisible()
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
    expect(await screen.findByText('第 1 题')).toBeVisible()
  })
})
