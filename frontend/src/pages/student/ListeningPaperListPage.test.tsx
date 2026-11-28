import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import StudentListeningPaperListPage from './ListeningPaperListPage'
import { getListeningPapers } from '../../api/listening'
import { writeDraft, writeEnvelopeVerified, writeSubmitted } from '../../attempt/storage'
import {
  makeDraft,
  makeEnvelope,
  makeSubmittedCache,
} from '../../test/fixtures'

vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({
    user: { userId: 7, username: 'student', nickname: '学生' },
    isAdmin: false,
  }),
}))

vi.mock('../../api/listening', () => ({
  getListeningPapers: vi.fn(),
}))

const papers = [1, 2, 3, 4].map((id) => ({
  examPaperId: id,
  code: `P${id}`,
  level: 'CET4',
  year: 2025,
  month: 6,
  paperSet: id,
  contentScope: 'listening',
  audioUrl: `/api/v1/listening-papers/${id}/audio`,
  durationMs: 5000,
}))

describe('C-09 列表入口四态', () => {
  it('按本机草稿/信封/标记显示继续、待确认、已提交、开始', async () => {
    vi.mocked(getListeningPapers).mockResolvedValue(papers)
    writeDraft(makeDraft({ examPaperId: 1 }))
    writeEnvelopeVerified(makeEnvelope({ examPaperId: 2 }))
    writeSubmitted(makeSubmittedCache({ examPaperId: 3 }))

    render(
      <MemoryRouter>
        <StudentListeningPaperListPage />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('button', { name: /继续作答/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '结果待确认' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '已提交' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '开始作答' })).toHaveLength(1)
    expect(screen.getByText('已答 2/4')).toBeInTheDocument()
  })

  it('清理过期文案，不提供「查看听力」', async () => {
    vi.mocked(getListeningPapers).mockResolvedValue(papers)
    render(
      <MemoryRouter>
        <StudentListeningPaperListPage />
      </MemoryRouter>,
    )
    await screen.findByText('听力练习')
    expect(screen.getByRole('link', { name: '错题本' }))
      .toHaveAttribute('href', '/student/listening-papers/wrong-answers')
    expect(screen.queryByText(/后续开放/)).not.toBeInTheDocument()
    expect(screen.queryByText(/查看听力/)).not.toBeInTheDocument()
    expect(
      screen.getByText(/列表状态只读取本机草稿\/提交记录/),
    ).toBeInTheDocument()
  })
})
