import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PendingPanel from './PendingPanel'
import { canAutoRetry } from '../../../attempt/retention'
import { makeEnvelope } from '../../../test/fixtures'

const envelope = makeEnvelope({ state: 'unknown' })
const retention = canAutoRetry(envelope.requestedAt, { kind: 'unknown' })

describe('C-07 PendingPanel', () => {
  it('冻结态：无答题卡/进度/所选，显示静态上次已答计数', () => {
    render(
      <PendingPanel
        envelope={envelope}
        statusUnknown
        conflict={false}
        retention={retention}
        counts={{ answered: 2, total: 4 }}
        onRetry={() => undefined}
        onQuery={() => undefined}
        onClear={() => undefined}
      />,
    )
    expect(screen.getByText(/答案已冻结/)).toBeInTheDocument()
    expect(screen.getByText(/上次已答 2\/4（静态记录/)).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    expect(screen.queryByText(/已选/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /交卷/ })).not.toBeInTheDocument()
  })

  it('同键重试需勾选风险确认后才可执行', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    render(
      <PendingPanel
        envelope={envelope}
        statusUnknown
        conflict={false}
        retention={retention}
        onRetry={onRetry}
        onQuery={() => undefined}
        onClear={() => undefined}
      />,
    )
    await user.click(screen.getByRole('button', { name: '重试提交（同键）' }))
    const confirm = screen.getByRole('button', { name: '我已知悉，重试' })
    expect(confirm).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    expect(confirm).toBeEnabled()
    await user.click(confirm)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('强警告清除：未勾选风险时禁用，勾选后才可清除', async () => {
    const onClear = vi.fn()
    const user = userEvent.setup()
    render(
      <PendingPanel
        envelope={envelope}
        statusUnknown
        conflict={false}
        retention={retention}
        onRetry={() => undefined}
        onQuery={() => undefined}
        onClear={onClear}
      />,
    )
    await user.click(screen.getByRole('button', { name: '强警告清除' }))
    expect(screen.getByText(/清除后可能无法确认上次提交结果/)).toBeInTheDocument()
    const confirm = screen.getByRole('button', { name: '仍要清除' })
    expect(confirm).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    await user.click(confirm)
    expect(onClear).toHaveBeenCalledTimes(1)
  })

  it('信封损坏：只提供查询/强警告清除，不提供重试提交', () => {
    render(
      <PendingPanel
        envelope={null}
        unrecoverableReason="missing-key"
        statusUnknown
        conflict={false}
        retention={retention}
        onRetry={() => undefined}
        onQuery={() => undefined}
        onClear={() => undefined}
      />,
    )
    expect(screen.getByText(/提交记录无法解析/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /重试提交/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查询提交状态' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '强警告清除' })).toBeInTheDocument()
  })

  it('矛盾响应：禁止重试提交，可重新查询', () => {
    render(
      <PendingPanel
        envelope={envelope}
        statusUnknown
        conflict
        retention={retention}
        onRetry={() => undefined}
        onQuery={() => undefined}
        onClear={() => undefined}
      />,
    )
    expect(screen.getByText(/状态自相矛盾/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试提交（同键）' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '查询提交状态' })).toBeEnabled()
  })
})
