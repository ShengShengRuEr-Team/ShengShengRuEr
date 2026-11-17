import {
  BookOutlined,
  FileSearchOutlined,
  HomeOutlined,
  SolutionOutlined,
} from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import type { MenuProps } from 'antd'
import type { ReactNode } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ROUTES } from '../constants/routes'
import { PERM_LOG_READ } from '../generated/adminConstants'
import UserActions from '../ui/UserActions'

const { Header, Sider, Content } = Layout

interface AdminMenuItem {
  key: string
  icon: ReactNode
  label: string
  permission?: string
}

const ADMIN_MENU: AdminMenuItem[] = [
  { key: ROUTES.ADMIN_HOME, icon: <HomeOutlined />, label: '首页' },
  { key: ROUTES.ADMIN_LISTENING_PAPERS, icon: <BookOutlined />, label: '题库管理' },
  {
    key: ROUTES.ADMIN_LOGIN_LOGS,
    icon: <SolutionOutlined />,
    label: '登录日志',
    permission: PERM_LOG_READ,
  },
  {
    key: ROUTES.ADMIN_OPERATION_LOGS,
    icon: <FileSearchOutlined />,
    label: '操作日志',
    permission: PERM_LOG_READ,
  },
]

/** 当前路由属于哪个菜单项：详情页也高亮「题库管理」。 */
function resolveSelectedKey(pathname: string): string {
  if (pathname.startsWith(ROUTES.ADMIN_LISTENING_PAPERS)) {
    return ROUTES.ADMIN_LISTENING_PAPERS
  }
  if (pathname.startsWith(ROUTES.ADMIN_LOGIN_LOGS)) {
    return ROUTES.ADMIN_LOGIN_LOGS
  }
  if (pathname.startsWith(ROUTES.ADMIN_OPERATION_LOGS)) {
    return ROUTES.ADMIN_OPERATION_LOGS
  }
  return ROUTES.ADMIN_HOME
}

/** 管理端布局：左侧菜单 + 顶部用户区 + 内容区；菜单按权限过滤。 */
export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { hasPermission } = useAuth()

  const items: MenuProps['items'] = ADMIN_MENU.filter(
    (item) => !item.permission || hasPermission(item.permission),
  ).map((item) => ({
    key: item.key,
    icon: item.icon,
    label: item.label,
  }))

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
          selectedKeys={[resolveSelectedKey(location.pathname)]}
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
