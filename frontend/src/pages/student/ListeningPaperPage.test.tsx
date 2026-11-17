import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  makeSubmittedCache,
  makeSummary,
} from '../../test/fixtures'

vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({
    user: { userId: 7, username: 'student', nickname: '学生' },
    isAdmin: false,
  }),
}))

vi.mock('../../api/listening', () => ({
  getListeningPaper: vi.fn(),
}))

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

describe('FE-05 页面容器与状态门禁', () => {
  it('详情 + API-3 未完成前不渲染可交互选项（加载门禁）', async () => {
    vi.mocked(getListeningPaper).mockReturnValue(new Promise(() => undefined))
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    const { container } = renderPage()
    expect(container.querySelector('.ant-skeleton')).not.toBeNull()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /交\s*卷/ })).not.toBeInTheDocument()
  })

  it('API-3 true：只读汇总、清除草稿/信封、写提交标记', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(submitted())
    attemptStorage.writeDraft(makeDraft())
    attemptStorage.writeEnvelopeVerified(makeEnvelope())

    renderPage()

    expect(await screen.findByText('3 / 4')).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /交\s*卷/ })).not.toBeInTheDocument()
    expect(attemptStorage.readSubmitted(7, 1).kind).toBe('valid')
    expect(attemptStorage.readDraft(7, 1).kind).toBe('empty')
    expect(attemptStorage.readEnvelope(7, 1).kind).toBe('none')
    expect(vi.mocked(getAttemptStatus)).toHaveBeenCalledTimes(1)
  })

  it('API-3 false + 普通草稿：恢复答案/标记/当前篇', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    attemptStorage.writeDraft(makeDraft())

    renderPage()

    expect(await screen.findByText('已恢复本机草稿')).toBeInTheDocument()
    expect(
      await screen.findByRole('radio', { name: /选项 C.*已选/ }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /标\s*记/ }).length).toBeGreaterThan(0)
    expect(screen.getByTestId('audio-player')).toBeInTheDocument()
  })

  it('API-3 false + 信封：pending 冻结，无答题卡/进度/交卷', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    attemptStorage.writeEnvelopeVerified(makeEnvelope())
    attemptStorage.writeDraft(makeDraft())

    renderPage()

    expect(await screen.findByText(/上次提交结果待确认/)).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '答题卡' })).not.toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /交\s*卷/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查询提交状态' })).toBeInTheDocument()
  })

  it('API-3 404 + 本机标记：只读且不展示汇总、不提供重开', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue({
      kind: 'status-unavailable',
      reason: 'not-accessible',
      httpStatus: 404,
    })
    attemptStorage.writeSubmitted(makeSubmittedCache())

    renderPage()

    expect(
      await screen.findByText(/当前试卷不可访问，无法确认最新状态/),
    ).toBeInTheDocument()
    expect(screen.queryByText('3 / 4')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /重新开始/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /交\s*卷/ })).not.toBeInTheDocument()
  })
})

describe('FE-06 提交流程', () => {
  it('未知 400：保留信封、冻结编辑、不自动新键', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    vi.mocked(submitAttempt).mockResolvedValue({
      kind: 'http-error',
      status: 400,
      msg: '未知业务文案',
    })
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    await user.click(screen.getByRole('button', { name: /交\s*卷/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认\s*交\s*卷/ }))

    expect(
      (await screen.findAllByText(/结果未确认，答案已冻结/)).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(attemptStorage.readEnvelope(7, 1).kind).toBe('valid')
    expect(attemptStorage.readSubmitted(7, 1).kind).toBe('none')
    expect(screen.queryByText(/提交失败，请重新作答/)).not.toBeInTheDocument()
  })

  it('跨标签终态：storage 事件后冻结并丢弃草稿，不复活', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    const optionB = screen.getAllByRole('radio', { name: /选项 B/ })[0]
    await user.click(optionB)
    expect(attemptStorage.hasSubmittedMarker(7, 1)).toBe(false)

    const cache = makeSubmittedCache()
    attemptStorage.writeSubmitted(cache)
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: attemptStorage.submittedKey(7, 1),
        newValue: JSON.stringify(cache),
      }),
    )

    expect(await screen.findByText('3 / 4')).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(attemptStorage.readDraft(7, 1).kind).toBe('empty')
    expect(screen.queryByRole('button', { name: /交\s*卷/ })).not.toBeInTheDocument()
  })

  it('API-3 500 + 本机标记：只读展示缓存并标注仅供参考', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue({
      kind: 'status-unavailable',
      reason: 'server',
      httpStatus: 500,
    })
    attemptStorage.writeSubmitted(makeSubmittedCache())

    renderPage()

    expect(await screen.findByText('本机保存，仅供参考')).toBeInTheDocument()
    expect(screen.getByText('3 / 4')).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
  })

  it('确认后提交成功：写入标记、删除草稿/信封、进入只读', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    vi.mocked(submitAttempt).mockResolvedValue({
      kind: 'success',
      value: { kind: 'submitted', summary: makeSummary() },
    })
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    await user.click(screen.getByRole('button', { name: /交\s*卷/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认\s*交\s*卷/ }))

    expect(await screen.findByText('提交成功')).toBeInTheDocument()
    const marker = attemptStorage.readSubmitted(7, 1)
    expect(marker.kind).toBe('valid')
    if (marker.kind === 'valid') {
      expect(marker.cache.source).toBe('api1')
      expect(marker.cache.summary?.correctCount).toBe(3)
    }
    expect(attemptStorage.readEnvelope(7, 1).kind).toBe('none')
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
  })

  it('双击确认只发送一次（AC-11）', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    // 请求悬挂：提交中按钮禁用 + inFlightRef 双重防抖。
    vi.mocked(submitAttempt).mockReturnValue(new Promise(() => undefined))
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    await user.click(screen.getByRole('button', { name: /交\s*卷/ }))
    const confirm = screen.getByRole('button', { name: /确\s*认\s*交\s*卷/ })
    fireEvent.click(confirm)
    fireEvent.click(confirm)

    await waitFor(() => {
      expect(vi.mocked(submitAttempt)).toHaveBeenCalledTimes(1)
    })
    expect(confirm).toBeDisabled()
  })

  it('API-1 404 E03：从信封重建草稿，保留答案并清旧信封（AC-14/AC-50）', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    vi.mocked(submitAttempt).mockResolvedValue({
      kind: 'http-error',
      status: 404,
      msg: '资源不存在',
    })
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    await user.click(screen.getAllByRole('radio', { name: /选项 B/ })[0])
    await user.click(screen.getByRole('button', { name: /交\s*卷/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认\s*交\s*卷/ }))

    expect(await screen.findByText(/试卷不可访问；作答已保留/)).toBeInTheDocument()
    const draft = attemptStorage.readDraft(7, 1)
    expect(draft.kind).toBe('valid')
    if (draft.kind === 'valid') {
      expect(draft.draft.answers).toEqual({ 11: 'B' })
    }
    expect(attemptStorage.readEnvelope(7, 1).kind).toBe('none')
    expect((await screen.findAllByRole('radiogroup')).length).toBeGreaterThan(0)
  })

  it('存储不可用：先弹确认框，未确认不发送请求', async () => {
    vi.mocked(getListeningPaper).mockResolvedValue(makeDetail())
    vi.mocked(getAttemptStatus).mockResolvedValue(notSubmitted())
    const real = window.localStorage
    const denied = {
      get length() {
        return real.length
      },
      key: (index: number) => real.key(index),
      getItem: (key: string) => real.getItem(key),
      removeItem: (key: string) => real.removeItem(key),
      clear: () => real.clear(),
      setItem: (key: string, value: string) => {
        if (key.startsWith('ssre.attemptEnvelope.v1.')) {
          throw new Error('quota exceeded')
        }
        real.setItem(key, value)
      },
    }
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: denied,
    })
    const user = userEvent.setup()
    renderPage()

    await screen.findByRole('button', { name: /交\s*卷/ })
    await user.click(screen.getByRole('button', { name: /交\s*卷/ }))
    await user.click(screen.getByRole('button', { name: /确\s*认\s*交\s*卷/ }))

    expect(await screen.findByText('本机暂存不可用')).toBeInTheDocument()
    expect(vi.mocked(submitAttempt)).not.toHaveBeenCalled()
    expect(
      screen.getByText(/刷新或关闭后可能无法恢复本次提交/),
    ).toBeInTheDocument()
  })
})
