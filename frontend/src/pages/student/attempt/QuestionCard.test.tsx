import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import QuestionCard from './QuestionCard'
import { makeDetail } from '../../../test/fixtures'

const question = makeDetail().passages[0].questions[0]

describe('C-01 QuestionCard', () => {
  it('整行点选、清除、标记回调', async () => {
    const onSelect = vi.fn()
    const onClear = vi.fn()
    const onToggleFlag = vi.fn()
    const user = userEvent.setup()
    render(
      <QuestionCard
        question={question}
        selected={undefined}
        flagged={false}
        onSelect={onSelect}
        onClear={onClear}
        onToggleFlag={onToggleFlag}
      />,
    )
    expect(screen.getByRole('radiogroup')).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: /选项 B/ }))
    expect(onSelect).toHaveBeenCalledWith('B')
    expect(screen.getByRole('button', { name: /清除本题/ })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /标记/ }))
    expect(onToggleFlag).toHaveBeenCalledTimes(1)
  })

  it('选中态不只靠颜色：aria-checked + 文字提示', () => {
    render(
      <QuestionCard
        question={question}
        selected="B"
        flagged
        onSelect={() => undefined}
        onClear={() => undefined}
        onToggleFlag={() => undefined}
      />,
    )
    expect(screen.getByRole('radio', { name: /选项 B.*已选/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(screen.getByRole('radio', { name: /选项 A/ })).toHaveAttribute(
      'aria-checked',
      'false',
    )
    expect(screen.getByText('已标记')).toBeInTheDocument()
  })

  it('方向键在选项间移动并选中', async () => {
    const onSelect = vi.fn()
    render(
      <QuestionCard
        question={question}
        selected="A"
        flagged={false}
        onSelect={onSelect}
        onClear={() => undefined}
        onToggleFlag={() => undefined}
      />,
    )
    const group = screen.getByRole('radiogroup')
    const firstOption = screen.getByRole('radio', { name: /选项 A/ })
    firstOption.focus()
    expect(group.contains(firstOption)).toBe(true)
    await userEvent.keyboard('{ArrowDown}')
    expect(onSelect).toHaveBeenCalledWith('B')
  })

  it('只读模式无选中态、无清除/标记按钮', () => {
    render(<QuestionCard question={question} flagged selected="B" readonly />)
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /清除本题/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /标记/ })).not.toBeInTheDocument()
    expect(screen.getByText('Question one')).toBeInTheDocument()
  })
})
