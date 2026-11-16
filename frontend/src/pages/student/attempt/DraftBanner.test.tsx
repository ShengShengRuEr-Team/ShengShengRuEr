import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DraftBanner from './DraftBanner'

describe('C-04 DraftBanner', () => {
  it('恢复态显示保存时间/已答数/隐私说明', () => {
    render(
      <DraftBanner
        kind="restored"
        savedAt="2026-11-14T06:30:00.000Z"
        answered={2}
        total={4}
      />,
    )
    expect(screen.getByText('已恢复本机草稿')).toBeInTheDocument()
    expect(screen.getByText('已答 2/4')).toBeInTheDocument()
    expect(screen.getByText(/仅当前浏览器保存/)).toBeInTheDocument()
  })

  it('重新开始仅在有回调且允许时渲染', async () => {
    const onRestart = vi.fn()
    const user = userEvent.setup()
    render(
      <DraftBanner kind="saved" canRestart onRestart={onRestart} />,
    )
    await user.click(screen.getByRole('button', { name: '重新开始' }))
    expect(onRestart).toHaveBeenCalledTimes(1)
  })

  it('pending 态不显示重新开始', () => {
    render(<DraftBanner kind="pending" canRestart onRestart={() => undefined} />)
    expect(screen.getByText(/本页已冻结编辑/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新开始' })).not.toBeInTheDocument()
  })

  it('存储不可用提示刷新后可能无法恢复', () => {
    render(<DraftBanner kind="unavailable" />)
    expect(screen.getByText(/本机暂存不可用/)).toBeInTheDocument()
    expect(screen.getByText(/刷新或关闭后可能无法恢复/)).toBeInTheDocument()
  })
})
