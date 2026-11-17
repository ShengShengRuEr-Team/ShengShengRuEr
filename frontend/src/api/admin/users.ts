import { request } from '../client'
import type {
  PasswordResetResultDto,
  ResetPasswordRequest,
  SelfPasswordRequest,
  SelfPasswordResultDto,
  UserCreateRequest,
  UserDto,
  UserPageDto,
  UserQuery,
  UserStatusRequest,
  UserStatusResultDto,
} from './types'

function cleanParams(query: UserQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params[key] = value
    }
  }
  return params
}

export function fetchUsers(query: UserQuery): Promise<UserPageDto> {
  return request<UserPageDto>({
    method: 'GET',
    url: '/api/v1/admin/users',
    params: cleanParams(query),
  })
}

export function fetchUser(userId: number): Promise<UserDto> {
  return request<UserDto>({
    method: 'GET',
    url: `/api/v1/admin/users/${userId}`,
  })
}

export function createUser(payload: UserCreateRequest): Promise<UserDto> {
  return request<UserDto>({
    method: 'POST',
    url: '/api/v1/admin/users',
    data: payload,
  })
}

export function updateUserNickname(
  userId: number,
  nickname: string,
): Promise<UserDto> {
  return request<UserDto>({
    method: 'PATCH',
    url: `/api/v1/admin/users/${userId}`,
    data: { nickname },
  })
}

export function changeUserStatus(
  userId: number,
  payload: UserStatusRequest,
): Promise<UserStatusResultDto> {
  return request<UserStatusResultDto>({
    method: 'POST',
    url: `/api/v1/admin/users/${userId}/status`,
    data: payload,
  })
}

export function resetUserPassword(
  userId: number,
  payload: ResetPasswordRequest,
): Promise<PasswordResetResultDto> {
  return request<PasswordResetResultDto>({
    method: 'POST',
    url: `/api/v1/admin/users/${userId}/reset-password`,
    data: payload,
  })
}

export function fetchMe(): Promise<UserDto> {
  return request<UserDto>({ method: 'GET', url: '/api/v1/admin/me' })
}

export function updateMyNickname(nickname: string): Promise<UserDto> {
  return request<UserDto>({
    method: 'PATCH',
    url: '/api/v1/admin/me',
    data: { nickname },
  })
}

export function changeMyPassword(
  payload: SelfPasswordRequest,
): Promise<SelfPasswordResultDto> {
  return request<SelfPasswordResultDto>({
    method: 'POST',
    url: '/api/v1/admin/me/password',
    data: payload,
  })
}
