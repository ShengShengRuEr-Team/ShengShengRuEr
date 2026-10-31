import { HomeOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { Outlet, useNavigate } from 'react-router-dom'
import { ROUTES } from '../constants/routes'
import UserActions from '../ui/UserActions'

const { Header, Sider, Content } = Layout

const ADMIN_ITEMS: MenuProps['items'] = [
  { key: ROUTES.ADMIN_HOME, icon: <HomeOutlined />, label: '首页' },
]

/** 管理端布局：左侧菜单 + 顶部用户区 + 内容区。 */
export default function AdminLayout() {
  const navigate = useNavigate()

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
          selectedKeys={[ROUTES.ADMIN_HOME]}
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
