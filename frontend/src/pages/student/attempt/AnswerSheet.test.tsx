import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AnswerSheet from './AnswerSheet'
import { makeDetail } from '../../../test/fixtures'

describe('C-02 AnswerSheet', () => {
  it('按篇分组、状态文字、当前题高亮', () => {
    render(
      <AnswerSheet
        detail={makeDetail()}
        answers={{ 11: 'A' }}
        flaggedQuestionIds={[12]}
        currentQuestionId={11}
        mode="answering"
        onJump={() => undefined}
      />,
    )
    expect(screen.getByRole('navigation', { name: '答题卡' })).toBeInTheDocument()
    expect(screen.getByText('第 1 篇')).toBeInTheDocument()
    expect(screen.getByText('第 2 篇')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '第1题，已答，当前题' }),
    ).toHaveAttribute('aria-current', 'true')
    expect(
      screen.getByRole('button', { name: '第2题，未答，已标记' }),
    ).toBeInTheDocument()
  })

  it('点击题号回调题号与篇索引；翻篇不跳音频（组件无音频依赖）', async () => {
    const onJump = vi.fn()
    const user = userEvent.setup()
    render(
      <AnswerSheet
        detail={makeDetail()}
        answers={{}}
        flaggedQuestionIds={[]}
        currentQuestionId={null}
        mode="answering"
        onJump={onJump}
      />,
    )
    await user.click(screen.getByRole('button', { name: '第3题，未答' }))
    expect(onJump).toHaveBeenCalledWith(13, 1)
  })

  it('已提交中性模式：只保留题号与当前题，不显示已答/标记/进度', () => {
    render(
      <AnswerSheet
        detail={makeDetail()}
        answers={{ 11: 'A' }}
        flaggedQuestionIds={[12]}
        currentQuestionId={13}
        mode="neutral"
        onJump={() => undefined}
      />,
    )
    expect(screen.queryByText(/已答/)).not.toBeInTheDocument()
    expect(screen.queryByText('标记')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '第3题，当前题' })).toHaveAttribute(
      'aria-current',
      'true',
    )
    expect(screen.getByRole('button', { name: '第1题' })).toBeInTheDocument()
  })
})
