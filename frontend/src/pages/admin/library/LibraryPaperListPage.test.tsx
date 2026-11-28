import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { listLibrary, libraryWrite } from '../../../api/library'
import { request } from '../../../api/client'
import LibraryPaperListPage from './LibraryPaperListPage'

vi.mock('../../../api/library',()=>({LIBRARY:'/api/v1/admin/listening-papers',listLibrary:vi.fn(),libraryWrite:vi.fn()}))
vi.mock('../../../api/client',()=>({request:vi.fn()}))
beforeEach(()=>{vi.mocked(listLibrary).mockReset();vi.mocked(libraryWrite).mockReset();vi.mocked(request).mockReset()})
it('从 URL 恢复服务端筛选和页码，列表不再逐卷补查状态',async()=>{
  vi.mocked(listLibrary).mockResolvedValue({items:[],total:44,page:3,page_size:20})
  render(<MemoryRouter initialEntries={['/admin/listening-papers?archived=true&page=3&exam_level=CET6&keyword=CET6']}><LibraryPaperListPage/></MemoryRouter>)
  await waitFor(()=>expect(listLibrary).toHaveBeenCalledTimes(1))
  expect(vi.mocked(listLibrary).mock.calls[0][0]).toMatchObject({archived:'true',page:3,exam_level:'CET6',keyword:'CET6',page_size:20})
  expect(await screen.findByText('题库管理 · 回收站')).toBeInTheDocument()
  expect(request).not.toHaveBeenCalled()
  expect(libraryWrite).not.toHaveBeenCalled()
})
