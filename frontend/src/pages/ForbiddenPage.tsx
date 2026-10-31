import { Button, Result } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ROUTES, homePathForRole } from '../constants/routes'

/**
 * 第 3 步先给可用的占位实现（正常返回路径 + 提示）。
 * 第 7 步再补统一视觉与「谁无权限」的说明文案。
 */
export default function ForbiddenPage() {
  const navigate = useNavigate()
  const { status, isAdmin } = useAuth()

  const handleBack = () => {
    if (status === 'authenticated') {
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
          <Button type="primary" onClick={handleBack}>
            返回首页
          </Button>
        }
      />
    </div>
  )
}
