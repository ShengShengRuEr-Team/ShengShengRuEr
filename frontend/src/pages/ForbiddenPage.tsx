import { Button, Result, Space, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ROUTES, homePathForRole } from '../constants/routes'

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  student: '学生',
}

/**
 * 无权限页：
 * - 由 RequireRole / RequirePermission 拦截后跳入，或用户直接访问
 * - 已登录显示当前身份，并按角色给出「返回首页」；未登录只给「去登录」
 * - 有站内历史时提供「返回上一页」
 */
export default function ForbiddenPage() {
  const navigate = useNavigate()
  const { status, user, roles, isAdmin } = useAuth()
  const authenticated = status === 'authenticated'

  // React Router 的 BrowserRouter 会在 history.state.idx 记录站内历史深度；
  // 直接打开 /403（idx 为 0）时不显示「返回上一页」，避免退出站点。
  const canGoBack = (window.history.state?.idx ?? 0) > 0

  const goHome = () => {
    if (authenticated) {
      navigate(homePathForRole(isAdmin), { replace: true })
      return
    }
    navigate(ROUTES.LOGIN, { replace: true })
  }

  return (
    <div className="full-page-center">
      <Result
        status="403"
        title="403"
        subTitle="没有访问该页面的权限"
        extra={
          <Space>
            <Button type="primary" onClick={goHome}>
              {authenticated ? '返回首页' : '去登录'}
            </Button>
            {canGoBack && (
              <Button onClick={() => navigate(-1)}>返回上一页</Button>
            )}
          </Space>
        }
      >
        {authenticated ? (
          <div className="forbidden-detail">
            <Typography.Paragraph style={{ marginBottom: 8 }}>
              当前登录：
              <Typography.Text strong>
                {user?.nickname || user?.username || '未知用户'}
              </Typography.Text>
              {roles.map((role) => (
                <Tag
                  key={role}
                  color={role === 'admin' ? 'gold' : 'blue'}
                  style={{ marginLeft: 8 }}
                >
                  {ROLE_LABELS[role] ?? role}
                </Tag>
              ))}
            </Typography.Paragraph>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              页面访问权限由后端下发的角色与权限码决定。如需访问，请联系管理员，或切换有权限的账号。
            </Typography.Paragraph>
          </div>
        ) : (
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            你尚未登录，请先登录后再访问该页面。
          </Typography.Paragraph>
        )}
      </Result>
    </div>
  )
}
