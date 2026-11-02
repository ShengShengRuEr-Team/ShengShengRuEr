import { Layout, Menu, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { Outlet, useNavigate } from 'react-router-dom'
import { ROUTES } from '../constants/routes'
import UserActions from '../ui/UserActions'

const { Header, Content } = Layout

const STUDENT_ITEMS: MenuProps['items'] = [
  { key: ROUTES.STUDENT_HOME, label: '首页' },
]

/** 学生端布局：顶部导航 + 内容区；不出现任何管理端菜单。 */
export default function StudentLayout() {
  const navigate = useNavigate()

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key)
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          background: '#fff',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 24,
          borderBottom: '1px solid #f0f0f0',
        }}
      >
        <Typography.Title level={4} style={{ margin: 0, whiteSpace: 'nowrap' }}>
          声声入耳
        </Typography.Title>
        <Menu
          mode="horizontal"
          selectedKeys={[ROUTES.STUDENT_HOME]}
          items={STUDENT_ITEMS}
          onClick={handleMenuClick}
          style={{ flex: 1, minWidth: 0, borderBottom: 'none' }}
        />
        <UserActions />
      </Header>
      <Content style={{ padding: 24 }}>
        <Outlet />
      </Content>
    </Layout>
  )
}
