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
  makeDraft,
  makeEnvelope,
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

/**
 * PR #16 独立验收报告（F01–F06）的定向回归。
 * 每个用例对应报告中的一个已复现问题，断言的是“修复后的保护行为”。
 */
describe('PR16 独立验收回归', () => {
  it('F01 损坏信封 + API-3 malformed 仍进入 pending-unrecoverable，不放开编辑', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue({
      kind: 'status-unavailable',
      reason: 'malformed',
    })
    window.localStorage.setItem(
      attemptStorage.envelopeKey(7, 1),
      '{"schemaVersion":1}',
    )

    renderPage()

    expect(await screen.findByText(/提交记录无法解析/)).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /交\s*卷/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '查询提交状态' }),
    ).toBeInTheDocument()
    expect(
      window.localStorage.getItem(attemptStorage.envelopeKey(7, 1)),
    ).not.toBeNull()
  })

  it('F01b 无信封 malformed 冻结编辑（AC-48），重新查询 false 后解除', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus)
      .mockResolvedValueOnce({ kind: 'status-unavailable', reason: 'malformed' })
      .mockResolvedValueOnce(notSubmitted())
    const user = userEvent.setup()

    renderPage()

    expect(
      await screen.findByText(/已冻结编辑，请重新查询提交状态/),
    ).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /交\s*卷/ })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: '查询提交状态' }))

    expect(
      await screen.findByText(/服务端确认尚未提交，已解除冻结/),
    ).toBeInTheDocument()
    expect((await screen.findAllByRole('radiogroup')).length).toBeGreaterThan(0)
  })

  it('F02 手动查询返回矛盾状态后冻结编辑与交卷', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus)
      .mockResolvedValueOnce(notSubmitted())
      .mockResolvedValueOnce({
        kind: 'status-conflict',
        reason: 'true-without-count',
        examPaperId: 1,
        attemptCount: 0,
      })
    vi.mocked(submitAttempt).mockResolvedValue({
      kind: 'http-error',
      status: 400,
      msg: '缺少或非法的提交键 Idempotency-Key',
    })
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    await user.click(screen.getByRole('button', { name: /交\s*卷/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认\s*交\s*卷/ }))
    await user.click(await screen.findByRole('button', { name: '查询提交状态' }))

    expect(
      (await screen.findAllByText(/提交状态自相矛盾/)).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /交\s*卷/ })).toBeDisabled()
  })

  it('F03 E09 后 API-3 false 先恢复冻结答案，再清信封', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus)
      .mockResolvedValueOnce(notSubmitted())
      .mockResolvedValueOnce(notSubmitted())
    vi.mocked(submitAttempt).mockResolvedValue({
      kind: 'http-error',
      status: 400,
      msg: '提交键已用于其他提交，请使用新键',
    })
    attemptStorage.writeEnvelopeVerified(makeEnvelope())
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: '重试提交（同键）' })
    await user.click(screen.getByRole('button', { name: '重试提交（同键）' }))
    await user.click(
      screen.getByRole('checkbox', {
        name: '我已知悉风险，确认使用原提交编号重试',
      }),
    )
    await user.click(screen.getByRole('button', { name: '我已知悉，重试' }))

    expect(await screen.findByText(/提交结果尚未确认/)).toBeInTheDocument()
    expect(
      (await screen.findAllByText(/服务端尚无成功提交记录/)).length,
    ).toBeGreaterThan(0)
    // 冻结答案未被丢弃：草稿读回含第 1 题 A，且信封已清理。
    const draft = attemptStorage.readDraft(7, 1)
    expect(draft.kind).toBe('valid')
    if (draft.kind === 'valid') {
      expect(draft.draft.answers).toEqual({ 11: 'A' })
    }
    expect(attemptStorage.readEnvelope(7, 1).kind).toBe('none')
    expect(
      await screen.findByRole('radio', { name: /选项 A.*已选/ }),
    ).toBeInTheDocument()
  })

  it('F04 重新开始需二次确认，取消旧 timer 后旧答案不再复活', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    attemptStorage.writeDraft(makeDraft())
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('已恢复本机草稿')
    await user.click(screen.getAllByRole('radio', { name: /选项 B/ })[0])
    await user.click(screen.getByRole('button', { name: '重新开始' }))
    expect(await screen.findByText('重新开始作答？')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '确认重新开始' }))

    await waitFor(
      () => {
        expect(attemptStorage.readDraft(7, 1).kind).toBe('empty')
      },
      { timeout: 2000 },
    )
    // 超过防抖窗口后再确认没有被旧 timer 复活。
    await new Promise((resolve) => setTimeout(resolve, 700))
    expect(attemptStorage.readDraft(7, 1).kind).toBe('empty')
    expect(screen.queryByRole('radio', { name: /已选/ })).not.toBeInTheDocument()
  })

  it('F05 站内卸载前 flush 最后一次作答', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    const user = userEvent.setup()
    const view = renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    await user.click(screen.getAllByRole('radio', { name: /选项 B/ })[0])
    view.unmount()

    const draft = attemptStorage.readDraft(7, 1)
    expect(draft.kind).toBe('valid')
    if (draft.kind === 'valid') {
      expect(draft.draft.answers).toEqual({ 11: 'B' })
    }
  })

  it('F06 同题数换批也提示“汇总对应提交时版本”', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(submitted())

    renderPage()

    expect(await screen.findByText('已提交 · 只读回看')).toBeInTheDocument()
    expect(
      await screen.findByText(/汇总对应提交时的试卷版本/),
    ).toBeInTheDocument()
  })

  it('F08A 冲突后一致 false 解除普通草稿冻结并恢复可作答', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus)
      .mockResolvedValueOnce({
        kind: 'status-conflict',
        reason: 'true-without-count',
        examPaperId: 1,
        attemptCount: 0,
      })
      .mockResolvedValueOnce(notSubmitted())
    attemptStorage.writeDraft(makeDraft())
    const user = userEvent.setup()
    renderPage()

    expect(
      (await screen.findAllByText(/提交状态自相矛盾/)).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '查询提交状态' }))

    expect(
      await screen.findByText(/服务端确认尚未提交，已解除冻结/),
    ).toBeInTheDocument()
    expect((await screen.findAllByRole('radiogroup')).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /交\s*卷/ })).toBeEnabled()
    expect(
      await screen.findByRole('radio', { name: /选项 C.*已选/ }),
    ).toBeInTheDocument()
  })

  it('F08B pending 冲突后一致 false 解除重试禁用且保留信封', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus)
      .mockResolvedValueOnce({
        kind: 'status-conflict',
        reason: 'false-with-count',
        examPaperId: 1,
        attemptCount: 2,
      })
      .mockResolvedValueOnce(notSubmitted())
    attemptStorage.writeEnvelopeVerified(makeEnvelope())
    const user = userEvent.setup()
    renderPage()

    expect(
      (await screen.findAllByText(/提交状态自相矛盾/)).length,
    ).toBeGreaterThan(0)
    const retry = screen.getByRole('button', { name: '重试提交（同键）' })
    expect(retry).toBeDisabled()

    await user.click(screen.getByRole('button', { name: '查询提交状态' }))

    expect(
      await screen.findByText(/已保留原提交编号与冻结答案/),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '重试提交（同键）' }),
    ).toBeEnabled()
    expect(attemptStorage.readEnvelope(7, 1).kind).toBe('valid')
  })

  it('F09 手动查询 malformed 必须冻结可编辑页面', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus)
      .mockResolvedValueOnce({
        kind: 'status-unavailable',
        reason: 'server',
        httpStatus: 500,
      })
      .mockResolvedValueOnce({
        kind: 'status-unavailable',
        reason: 'malformed',
      })
    attemptStorage.writeDraft(makeDraft())
    const user = userEvent.setup()
    renderPage()

    expect(
      await screen.findByText(/无法确认提交状态/),
    ).toBeInTheDocument()
    expect((await screen.findAllByRole('radiogroup')).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /交\s*卷/ })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: '查询提交状态' }))

    expect(
      await screen.findByText(/已冻结编辑，请重新查询提交状态/),
    ).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /交\s*卷/ })).toBeDisabled()
  })

  it('补充：初次加载矛盾状态（无信封）冻结且提供查询入口', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue({
      kind: 'status-conflict',
      reason: 'false-with-count',
      examPaperId: 1,
      attemptCount: 2,
    })

    renderPage()

    expect(
      (await screen.findAllByText(/提交状态自相矛盾/)).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '查询提交状态' }),
    ).toBeInTheDocument()
  })

  it('补充：API-3 true 且汇总不可用提供“查询提交状态”入口', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue({
      kind: 'submitted-summary-unavailable',
      examPaperId: 1,
      attemptCount: 1,
      submittedAt: null,
    })

    renderPage()

    expect(await screen.findByText('已提交 · 只读回看')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '查询提交状态' }),
    ).toBeInTheDocument()
  })
})
