import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

export interface UserFilterState {
  username: string
  nickname: string
  role: string
  status: string
  page: number
  pageSize: number
}

const DEFAULT_FILTERS: UserFilterState = {
  username: '',
  nickname: '',
  role: '',
  status: '',
  page: 1,
  pageSize: 20,
}

const PAGE_SIZES = [10, 20, 50, 100]

function readFilters(params: URLSearchParams): UserFilterState {
  const pageSize = Number(params.get('page_size') ?? DEFAULT_FILTERS.pageSize)
  const page = Number(params.get('page') ?? 1)
  return {
    username: params.get('username') ?? '',
    nickname: params.get('nickname') ?? '',
    role: params.get('role') ?? '',
    status: params.get('status') ?? '',
    page: Number.isFinite(page) && page >= 1 ? page : 1,
    pageSize: PAGE_SIZES.includes(pageSize) ? pageSize : 20,
  }
}

function toParams(state: UserFilterState): Record<string, string> {
  const params: Record<string, string> = {}
  if (state.username) params.username = state.username
  if (state.nickname) params.nickname = state.nickname
  if (state.role) params.role = state.role
  if (state.status) params.status = state.status
  if (state.page > 1) params.page = String(state.page)
  if (state.pageSize !== 20) params.page_size = String(state.pageSize)
  return params
}

/** 用户列表筛选与分页：URL 为唯一来源，刷新/返回保留条件。 */
export function useUserFilters() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(() => readFilters(searchParams), [searchParams])

  const update = useCallback(
    (partial: Partial<UserFilterState>) => {
      setSearchParams(toParams({ ...filters, ...partial }), { replace: true })
    },
    [filters, setSearchParams],
  )

  const reset = useCallback(() => {
    setSearchParams({}, { replace: true })
  }, [setSearchParams])

  return { filters, update, reset }
}
