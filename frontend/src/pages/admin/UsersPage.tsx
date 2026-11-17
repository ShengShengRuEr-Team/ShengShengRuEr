import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Input, Select, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useCallback, useEffect, useState } from 'react'
import { fetchUsers } from '../../api/admin/users'
import type { UserDto, UserPageDto } from '../../api/admin/types'
import { ApiError } from '../../api/api-error'
import { usePermission } from '../../auth/usePermission'
import Can from '../../ui/Can'
import {
  ACCOUNT_STATUS_LABELS,
  PERM_USER_CREATE,
  PERM_USER_READ,
  PERM_USER_RESET_PASSWORD,
  PERM_USER_STATUS,
  PERM_USER_UPDATE,
  ROLE_LABELS,
} from '../../generated/adminConstants'
import { labelOf } from '../../utils/adminLabels'
import ResetPasswordModal from '../../ui/admin/ResetPasswordModal'
import UserCreateModal from '../../ui/admin/UserCreateModal'
import UserDetailDrawer from '../../ui/admin/UserDetailDrawer'
import UserNicknameModal from '../../ui/admin/UserNicknameModal'
import UserStatusModal from '../../ui/admin/UserStatusModal'
import { useUserFilters } from '../../ui/admin/useUserFilters'

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

export default function UsersPage() {
  const canRead = usePermission(PERM_USER_READ)
  const { filters, update, reset } = useUserFilters()

  const [data, setData] = useState<UserPageDto | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [nicknameUser, setNicknameUser] = useState<UserDto | null>(null)
  const [statusUser, setStatusUser] = useState<UserDto | null>(null)
  const [resetUser, setResetUser] = useState<UserDto | null>(null)
  const [detailUserId, setDetailUserId] = useState<number | null>(null)

  const load = useCallback(async () => {
    if (!canRead) {
      return
    }
    setLoading(true)
    setError(null)
    try {
      const page = await fetchUsers({
        username: filters.username || undefined,
        nickname: filters.nickname || undefined,
        role: filters.role || undefined,
        status: filters.status || undefined,
        page: filters.page,
        page_size: filters.pageSize,
      })
      setData(page)
    } catch (cause) {
      setData(null)
      setError(cause instanceof ApiError ? cause.message : '加载用户失败')
    } finally {
      setLoading(false)
    }
  }, [
    canRead,
    filters.nickname,
    filters.page,
    filters.pageSize,
    filters.role,
    filters.status,
    filters.username,
  ])

  useEffect(() => {
    void load()
  }, [load])

  const refresh = () => void load()

  const columns: ColumnsType<UserDto> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '用户名', dataIndex: 'username', width: 160 },
    {
      title: '昵称',
      dataIndex: 'nickname',
      width: 160,
      render: (value: string) => value || '—',
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 100,
      render: (value: string | null) => (value ? labelOf(ROLE_LABELS, value) : '未知'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => (
        <Tag color={value === 'active' ? 'green' : 'red'}>
          {labelOf(ACCOUNT_STATUS_LABELS, value)}
        </Tag>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 220 },
    {
      title: '操作',
      key: 'actions',
      width: 320,
      render: (_, row) => (
        <Space wrap>
          <Button size="small" onClick={() => setDetailUserId(row.id)}>
            详情
          </Button>
          <Can code={PERM_USER_UPDATE}>
            <Button size="small" onClick={() => setNicknameUser(row)}>
              改昵称
            </Button>
          </Can>
          <Can code={PERM_USER_STATUS}>
            <Button size="small" onClick={() => setStatusUser(row)}>
              启停
            </Button>
          </Can>
          <Can code={PERM_USER_RESET_PASSWORD}>
            <Button size="small" danger onClick={() => setResetUser(row)}>
              重置密码
            </Button>
          </Can>
        </Space>
      ),
    },
  ]

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title="用户管理"
        extra={
          <Can code={PERM_USER_CREATE}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateOpen(true)}
            >
              创建用户
            </Button>
          </Can>
        }
      >
        <Space wrap size="middle">
          <Input
            allowClear
            maxLength={50}
            placeholder="用户名"
            value={filters.username}
            onChange={(event) => update({ username: event.target.value, page: 1 })}
            onPressEnter={() => update({ page: 1 })}
            style={{ width: 170 }}
          />
          <Input
            allowClear
            maxLength={50}
            placeholder="昵称"
            value={filters.nickname}
            onChange={(event) => update({ nickname: event.target.value, page: 1 })}
            onPressEnter={() => update({ page: 1 })}
            style={{ width: 170 }}
          />
          <Select
            allowClear
            placeholder="角色"
            options={Object.entries(ROLE_LABELS).map(([value, label]) => ({
              value,
              label,
            }))}
            value={filters.role || undefined}
            onChange={(value) => update({ role: value ?? '', page: 1 })}
            style={{ width: 120 }}
          />
          <Select
            allowClear
            placeholder="状态"
            options={Object.entries(ACCOUNT_STATUS_LABELS).map(([value, label]) => ({
              value,
              label,
            }))}
            value={filters.status || undefined}
            onChange={(value) => update({ status: value ?? '', page: 1 })}
            style={{ width: 120 }}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={() => update({ page: 1 })}
          >
            查询
          </Button>
          <Button icon={<ReloadOutlined />} onClick={reset}>
            重置
          </Button>
        </Space>
      </Card>

      {error && (
        <Space orientation="vertical" size="small" style={{ width: '100%' }}>
          <Alert type="error" showIcon title={error} />
          <Button onClick={refresh}>重试</Button>
        </Space>
      )}

      <Table<UserDto>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={data?.items ?? []}
        scroll={{ x: 1080 }}
        locale={{ emptyText: '暂无用户' }}
        pagination={{
          current: filters.page,
          pageSize: filters.pageSize,
          total: data?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: PAGE_SIZE_OPTIONS,
          showTotal: (value) => `共 ${value} 条`,
          onChange: (page, pageSize) => update({ page, pageSize }),
        }}
      />

      <UserCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false)
          update({ page: 1 })
          refresh()
        }}
      />
      <UserNicknameModal
        user={nicknameUser}
        onClose={() => setNicknameUser(null)}
        onSaved={() => {
          setNicknameUser(null)
          refresh()
        }}
      />
      <UserStatusModal
        user={statusUser}
        onClose={() => setStatusUser(null)}
        onChanged={() => {
          setStatusUser(null)
          refresh()
        }}
      />
      <ResetPasswordModal
        user={resetUser}
        onClose={() => setResetUser(null)}
        onChanged={() => {
          setResetUser(null)
          refresh()
        }}
      />
      <UserDetailDrawer
        userId={detailUserId}
        onClose={() => setDetailUserId(null)}
      />
    </Space>
  )
}
