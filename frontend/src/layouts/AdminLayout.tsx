import { BookOutlined, HomeOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { ROUTES } from '../constants/routes'
import UserActions from '../ui/UserActions'

const { Header, Sider, Content } = Layout

const ADMIN_ITEMS: MenuProps['items'] = [
  { key: ROUTES.ADMIN_HOME, icon: <HomeOutlined />, label: '首页' },
  { key: ROUTES.ADMIN_LISTENING_PAPERS, icon: <BookOutlined />, label: '题库管理' },
]

/** 当前路由属于哪个菜单项：详情页也高亮「题库管理」。 */
function resolveSelectedKey(pathname: string): string {
  if (pathname.startsWith(ROUTES.ADMIN_LISTENING_PAPERS)) {
    return ROUTES.ADMIN_LISTENING_PAPERS
  }
  return ROUTES.ADMIN_HOME
}

/** 管理端布局：左侧菜单 + 顶部用户区 + 内容区。 */
export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()

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
          items={ADMIN_ITEMS}
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
