import { describe, expect, it, vi } from 'vitest'
import { request } from '../client'
import {
  changeMyPassword,
  changeUserStatus,
  createUser,
  fetchUser,
  fetchUsers,
  resetUserPassword,
  updateMyNickname,
  updateUserNickname,
} from './users'

vi.mock('../client', () => ({
  request: vi.fn().mockResolvedValue({}),
}))

const mockedRequest = vi.mocked(request)

describe('用户接口调用', () => {
  it('列表清洗空参数并保留分页', async () => {
    await fetchUsers({ username: '', nickname: '昵称', role: '', page: 2, page_size: 50 })
    expect(mockedRequest).toHaveBeenCalledWith({
      method: 'GET',
      url: '/api/v1/admin/users',
      params: { nickname: '昵称', page: 2, page_size: 50 },
    })
  })

  it('详情与写操作路径正确', async () => {
    await fetchUser(7)
    expect(mockedRequest).toHaveBeenCalledWith({
      method: 'GET',
      url: '/api/v1/admin/users/7',
    })

    await createUser({ username: 'abc', password: 'abcd123456', role: 'student' })
    expect(mockedRequest).toHaveBeenCalledWith({
      method: 'POST',
      url: '/api/v1/admin/users',
      data: { username: 'abc', password: 'abcd123456', role: 'student' },
    })

    await updateUserNickname(7, '新昵称')
    expect(mockedRequest).toHaveBeenCalledWith({
      method: 'PATCH',
      url: '/api/v1/admin/users/7',
      data: { nickname: '新昵称' },
    })

    await changeUserStatus(7, { status: 'disabled', reason: '违规' })
    expect(mockedRequest).toHaveBeenCalledWith({
      method: 'POST',
      url: '/api/v1/admin/users/7/status',
      data: { status: 'disabled', reason: '违规' },
    })

    await resetUserPassword(7, { new_password: 'abcd123456', reason: '遗忘' })
    expect(mockedRequest).toHaveBeenCalledWith({
      method: 'POST',
      url: '/api/v1/admin/users/7/reset-password',
      data: { new_password: 'abcd123456', reason: '遗忘' },
    })
  })

  it('本人接口路径正确', async () => {
    await updateMyNickname('昵称')
    expect(mockedRequest).toHaveBeenCalledWith({
      method: 'PATCH',
      url: '/api/v1/admin/me',
      data: { nickname: '昵称' },
    })

    await changeMyPassword({ old_password: 'old', new_password: 'abcd123456' })
    expect(mockedRequest).toHaveBeenCalledWith({
      method: 'POST',
      url: '/api/v1/admin/me/password',
      data: { old_password: 'old', new_password: 'abcd123456' },
    })
  })
})
