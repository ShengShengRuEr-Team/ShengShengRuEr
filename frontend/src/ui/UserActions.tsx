import { LogoutOutlined } from '@ant-design/icons'
import { Button, Space, Typography } from 'antd'
import { useAuth } from '../auth/useAuth'
import { ROUTES } from '../constants/routes'

/** 两套布局共用的「当前用户 + 退出登录」。 */
export default function UserActions() {
  const { user, logout } = useAuth()

  const handleLogout = async () => {
    await logout()
    // 退出后整页跳到登录页：避免 RequireAuth 在“已退出但还没导航”的间隙
    // 给 /login 加上 redirect 参数，导致下次登录又被带回刚才的页面。
    window.location.replace(ROUTES.LOGIN)
  }

  return (
    <Space size={12}>
      <Typography.Text>{user?.nickname || user?.username || '未登录'}</Typography.Text>
      <Button
        type="link"
        icon={<LogoutOutlined />}
        onClick={handleLogout}
        style={{ paddingInline: 0 }}
      >
        退出登录
      </Button>
    </Space>
  )
}
