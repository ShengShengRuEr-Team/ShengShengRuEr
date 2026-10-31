import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { FileTextOutlined, SyncOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { PERMISSIONS } from '../constants/permissions'
import { ROUTES } from '../constants/routes'
import UserActions from '../ui/UserActions'

const { Header, Sider, Content } = Layout

interface AdminMenuItem {
  key: string
  icon: ReactNode
  label: string
  permission: string
}

const ADMIN_ITEMS: AdminMenuItem[] = [
  {
    key: ROUTES.ADMIN_PAPERS,
    icon: <FileTextOutlined />,
    label: '试卷管理',
    permission: PERMISSIONS.PAPER_READ,
  },
  {
    key: ROUTES.ADMIN_TASKS,
    icon: <SyncOutlined />,
    label: '任务管理',
    permission: PERMISSIONS.TASK_READ,
  },
]

/** 管理端布局：左侧菜单 + 顶部用户区 + 内容区。菜单项按后端 permissions 显示。 */
export default function AdminLayout() {
  const { hasPermission } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  const items = useMemo<MenuProps['items']>(
    () =>
      ADMIN_ITEMS.filter((item) => hasPermission(item.permission)).map((item) => ({
        key: item.key,
        icon: item.icon,
        label: item.label,
      })),
    [hasPermission],
  )

  const selectedKey = location.pathname.startsWith(ROUTES.ADMIN_TASKS)
    ? ROUTES.ADMIN_TASKS
    : ROUTES.ADMIN_PAPERS

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key)
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="light" width={220} style={{ borderRight: '1px solid #f0f0f0' }}>
        <div style={{ padding: '20px 24px 12px' }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            声声入耳
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            管理端
          </Typography.Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={items}
          onClick={handleMenuClick}
          style={{ borderInlineEnd: 'none' }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <UserActions />
        </Header>
        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
