import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import SubmitSummaryPanel from './SubmitSummaryPanel'
import { makeSummary } from '../../../test/fixtures'

describe('C-05/C-06 SubmitSummaryPanel', () => {
  it('显示正确数/率/估分/时间/编号，不显示逐题与未答数', () => {
    render(
      <SubmitSummaryPanel
        summary={makeSummary()}
        submittedAt={null}
        authoritative
      />,
    )
    expect(screen.getByText('3 / 4')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
    expect(screen.getByText('30 / 40')).toBeInTheDocument()
    expect(screen.getByText('练习估分，非官方成绩')).toBeInTheDocument()
    expect(
      screen.getByText('0f5c2a1e-9d4b-4f6a-9c77-2b1e8a3d5c40'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/未答/)).not.toBeInTheDocument()
    expect(screen.queryByText(/答错/)).not.toBeInTheDocument()
    expect(screen.queryByText(/解析/)).not.toBeInTheDocument()
  })

  it('估分不可用显示「暂不可用」不显示 0；汇总缺失也不显示伪时间', () => {
    const summary = makeSummary({
      practiceScore: {
        available: false,
        value: null,
        max: null,
        label: '练习估分，非官方成绩',
        reason: '判分数据不完整',
      },
      submittedAt: '2026-11-14T06:30:00.000Z',
    })
    render(
      <SubmitSummaryPanel
        summary={summary}
        submittedAt={null}
        authoritative
      />,
    )
    expect(screen.getByText('暂不可用')).toBeInTheDocument()
    expect(screen.queryByText('0 / 40')).not.toBeInTheDocument()
  })

  it('本机缓存必须标注「本机保存，仅供参考」', () => {
    render(
      <SubmitSummaryPanel
        summary={makeSummary()}
        submittedAt={null}
        authoritative={false}
        cacheOnly
      />,
    )
    expect(screen.getByText('本机保存，仅供参考')).toBeInTheDocument()
  })

  it('汇总不可用且无提交时间时不渲染提交时间行', () => {
    render(
      <SubmitSummaryPanel summary={null} submittedAt={null} authoritative />,
    )
    expect(screen.getByText('暂不可用')).toBeInTheDocument()
    expect(screen.queryByText('提交时间')).not.toBeInTheDocument()
  })
})
