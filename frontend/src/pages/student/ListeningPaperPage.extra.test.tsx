import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import StudentListeningPaperPage from './ListeningPaperPage'
import { getListeningPaper } from '../../api/listening'
import { getAttemptStatus, submitAttempt } from '../../api/attempts'
import * as attemptStorage from '../../attempt/storage'
import {
  makeDetail,
  makeEnvelope,
  makeSubmittedCache,
  makeSummary,
} from '../../test/fixtures'

vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({
    user: { userId: 7, username: 'student', nickname: '学生' },
    isAdmin: false,
  }),
}))

vi.mock('../../api/listening', () => ({ getListeningPaper: vi.fn() }))
vi.mock('../../api/attempts', () => ({
  getAttemptStatus: vi.fn(),
  submitAttempt: vi.fn(),
}))
vi.mock('../../ui/AudioPlayer', () => ({
  default: () => <div data-testid="audio-player" />,
}))

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/student/listening-papers/1']}>
      <Routes>
        <Route
          path="/student/listening-papers/:examPaperId"
          element={<StudentListeningPaperPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

function notSubmitted() {
  return {
    kind: 'not-submitted' as const,
    status: {
      examPaperId: 1,
      submitted: false,
      attemptCount: 0,
      latestAttempt: null,
    },
  }
}

function submitted() {
  return {
    kind: 'submitted' as const,
    status: {
      examPaperId: 1,
      submitted: true,
      attemptCount: 1,
      latestAttempt: makeSummary(),
    },
  }
}

const nativeLocalStorage = window.localStorage

afterEach(() => {
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: nativeLocalStorage,
  })
  vi.restoreAllMocks()
})

describe('FE-06 补充：结果分支与多标签兜底', () => {
  it('E08：写 e08 无时间标记并转只读，随后查询补全汇总', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus)
      .mockResolvedValueOnce(notSubmitted())
      .mockResolvedValueOnce(submitted())
    vi.mocked(submitAttempt).mockResolvedValue({
      kind: 'http-error',
      status: 400,
      msg: '本轮同一试卷仅允许提交一次',
    })
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    await user.click(screen.getByRole('button', { name: /交\s*卷/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认\s*交\s*卷/ }))

    expect(await screen.findByText('已提交 · 只读回看')).toBeInTheDocument()
    await screen.findByText('3 / 4')
    const marker = attemptStorage.readSubmitted(7, 1)
    expect(marker.kind).toBe('valid')
    if (marker.kind === 'valid') {
      expect(marker.cache.source).toBe('api3')
      expect(marker.cache.summary?.correctCount).toBe(3)
    }
  })

  it('E09 false：查询为未提交后清信封，回到可作答（下次新键）', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    vi.mocked(submitAttempt).mockResolvedValue({
      kind: 'http-error',
      status: 400,
      msg: '提交键已用于其他提交，请使用新键',
    })
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    await user.click(screen.getByRole('button', { name: /交\s*卷/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认\s*交\s*卷/ }))

    expect(await screen.findByText(/提交结果尚未确认/)).toBeInTheDocument()
    expect(await screen.findByText(/服务端尚无成功提交记录/)).toBeInTheDocument()
    await waitFor(() => {
      expect(vi.mocked(getAttemptStatus).mock.calls.length).toBeGreaterThanOrEqual(2)
    })
    // 未提交：旧键作废，回到可作答；下次交卷生成新键。
    expect(attemptStorage.readEnvelope(7, 1).kind).toBe('none')
    expect((await screen.findAllByRole('radiogroup')).length).toBeGreaterThan(0)
  })

  it('矛盾响应：保护性冻结、保留信封、禁止重试提交', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue({
      kind: 'status-conflict',
      reason: 'false-with-latest',
      examPaperId: 1,
      attemptCount: 0,
    })
    attemptStorage.writeEnvelopeVerified(makeEnvelope())

    renderPage()

    expect(
      (await screen.findAllByText(/提交状态自相矛盾/)).length,
    ).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: '重试提交（同键）' })).toBeDisabled()
    expect(attemptStorage.readEnvelope(7, 1).kind).toBe('valid')
    expect(attemptStorage.readSubmitted(7, 1).kind).toBe('none')
  })

  it('信封损坏：进入 pending-unrecoverable，不提供重试提交', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    window.localStorage.setItem(
      attemptStorage.envelopeKey(7, 1),
      '{"schemaVersion":1}',
    )

    renderPage()

    expect(await screen.findByText(/提交记录无法解析/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /重试提交/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查询提交状态' })).toBeInTheDocument()
    expect(window.localStorage.getItem(attemptStorage.envelopeKey(7, 1))).not.toBeNull()
  })

  it('API-3 true 但汇总不可用：只读、不显示 0/伪时间', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue({
      kind: 'submitted-summary-unavailable',
      examPaperId: 1,
      attemptCount: 1,
      submittedAt: null,
    })

    renderPage()

    expect(await screen.findByText('已提交 · 只读回看')).toBeInTheDocument()
    expect(screen.getByText('暂不可用')).toBeInTheDocument()
    expect(screen.queryByText('提交时间')).not.toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /交\s*卷/ })).not.toBeInTheDocument()
  })

  it('终态写入前检查（事件未处理兜底）：已有标记时保存不复活草稿', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    // 模拟另一个标签页已写入标记，但本页没有收到 storage 事件。
    attemptStorage.writeSubmitted(makeSubmittedCache())
    await user.click(screen.getAllByRole('radio', { name: /选项 B/ })[0])

    await waitFor(
      () => {
        expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
      },
      { timeout: 5000 },
    )
    await waitFor(() => {
      expect(attemptStorage.readDraft(7, 1).kind).toBe('empty')
    })
    expect(screen.getByText('3 / 4')).toBeInTheDocument()
  })
})
