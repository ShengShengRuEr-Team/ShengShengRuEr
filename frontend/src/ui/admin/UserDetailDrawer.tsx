import { Alert, Button, Descriptions, Drawer, Spin } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { fetchUser } from '../../api/admin/users'
import type { UserDto } from '../../api/admin/types'
import { ApiError } from '../../api/api-error'
import { ACCOUNT_STATUS_LABELS, ROLE_LABELS } from '../../generated/adminConstants'
import { labelOf } from '../../utils/adminLabels'

function text(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

interface Props {
  userId: number | null
  onClose: () => void
}

export default function UserDetailDrawer({ userId, onClose }: Props) {
  const [user, setUser] = useState<UserDto | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (id: number) => {
    setLoading(true)
    setError(null)
    try {
      setUser(await fetchUser(id))
    } catch (cause) {
      setUser(null)
      if (cause instanceof ApiError && cause.status === 404) {
        setError('用户不存在或已被删除')
      } else {
        setError(cause instanceof ApiError ? cause.message : '加载详情失败')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (userId === null) {
      setUser(null)
      setError(null)
      return
    }
    void load(userId)
  }, [load, userId])

  return (
    <Drawer
      open={userId !== null}
      onClose={onClose}
      width={480}
      title="用户详情"
      destroyOnHidden
    >
      {loading && <Spin />}
      {error && (
        <Alert
          type="error"
          showIcon
          title={error}
          action={
            userId !== null ? (
              <Button size="small" onClick={() => void load(userId)}>
                重试
              </Button>
            ) : null
          }
        />
      )}
      {user && !loading && (
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="用户ID">{user.id}</Descriptions.Item>
          <Descriptions.Item label="用户名">{user.username}</Descriptions.Item>
          <Descriptions.Item label="昵称">{text(user.nickname)}</Descriptions.Item>
          <Descriptions.Item label="角色">
            {user.role ? labelOf(ROLE_LABELS, user.role) : '未知'}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            {labelOf(ACCOUNT_STATUS_LABELS, user.status)}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{text(user.created_at)}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{text(user.updated_at)}</Descriptions.Item>
        </Descriptions>
      )}
    </Drawer>
  )
}
