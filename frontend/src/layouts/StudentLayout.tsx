import { Layout, Menu, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { ROUTES } from '../constants/routes'
import UserActions from '../ui/UserActions'

const { Header, Content } = Layout

const STUDENT_ITEMS: MenuProps['items'] = [
  { key: ROUTES.STUDENT_HOME, label: '首页' },
  { key: ROUTES.STUDENT_LISTENING_PAPERS, label: '听力练习' },
]

/** 当前路由属于哪个菜单项：整卷页也高亮「听力练习」。 */
function resolveSelectedKey(pathname: string): string {
  if (pathname.startsWith(ROUTES.STUDENT_LISTENING_PAPERS)) {
    return ROUTES.STUDENT_LISTENING_PAPERS
  }
  return ROUTES.STUDENT_HOME
}

/** 学生端布局：顶部导航 + 内容区；不出现任何管理端菜单。 */
export default function StudentLayout() {
  const navigate = useNavigate()
  const location = useLocation()

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
          selectedKeys={[resolveSelectedKey(location.pathname)]}
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
