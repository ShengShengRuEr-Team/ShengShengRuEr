import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SubmitConfirmModal from './SubmitConfirmModal'

describe('C-03 SubmitConfirmModal', () => {
  it('显示计数、仅一次与全部未答强提示，不列题号', () => {
    render(
      <SubmitConfirmModal
        open
        counts={{ total: 4, answered: 0, unanswered: 4, flagged: 0 }}
        onCancel={() => undefined}
        onConfirm={() => undefined}
      />,
    )
    expect(screen.getByText(/共 4 题 · 已答 0 题 · 未答 4 题 · 标记 0 题/)).toBeInTheDocument()
    expect(screen.getByText(/所有题目均未作答/)).toBeInTheDocument()
    expect(screen.getByText(/本卷仅可提交一次/)).toBeInTheDocument()
    expect(screen.queryByText(/第\s*1\s*题/)).not.toBeInTheDocument()
  })

  it('取消不提交；确认触发一次', async () => {
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    const user = userEvent.setup()
    render(
      <SubmitConfirmModal
        open
        counts={{ total: 4, answered: 2, unanswered: 2, flagged: 1 }}
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    )
    await user.click(screen.getByRole('button', { name: /取\s*消/ }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: /确\s*认\s*交\s*卷/ }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('提交中按钮禁用/加载，不提供取消提交', () => {
    render(
      <SubmitConfirmModal
        open
        submitting
        counts={{ total: 4, answered: 4, unanswered: 0, flagged: 0 }}
        onCancel={() => undefined}
        onConfirm={() => undefined}
      />,
    )
    expect(screen.getByRole('button', { name: /提交中/ })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /取消提交/ })).not.toBeInTheDocument()
  })
})
