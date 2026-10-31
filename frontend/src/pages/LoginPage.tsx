import { useRef, useState } from 'react'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/api-error'
import { useAuth } from '../auth/useAuth'
import { ROUTES, homePathForRole } from '../constants/routes'
import FullPageLoading from '../ui/FullPageLoading'

interface LoginFormValues {
  username: string
  password: string
}

/**
 * 只接受站内绝对路径作为登录后跳转目标，避免 ?redirect=//evil.com 之类的开放重定向，
 * 也避免登录成功后又被弹回 /login。
 */
function getSafeRedirect(raw: string | null): string | null {
  if (!raw) {
    return null
  }
  if (!raw.startsWith('/') || raw.startsWith('//')) {
    return null
  }
  if (raw === ROUTES.LOGIN || raw.startsWith(`${ROUTES.LOGIN}?`)) {
    return null
  }
  return raw
}

export default function LoginPage() {
  const { status, isAdmin, login } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 登录提交过程中，AuthProvider 会先变成 authenticated；此时不能走「已登录自动跳首页」，
  // 否则会丢掉 ?redirect= 指定的目标（如 401 后回跳原页面）。
  const redirectingRef = useRef(false)

  if (status === 'loading') {
    return <FullPageLoading />
  }

  if (status === 'authenticated' && !redirectingRef.current) {
    return <Navigate to={homePathForRole(isAdmin)} replace />
  }

  const handleFinish = async (values: LoginFormValues) => {
    setSubmitting(true)
    setError(null)
    try {
      const profile = await login(values.username, values.password)
      redirectingRef.current = true
      const target =
        getSafeRedirect(searchParams.get('redirect')) ??
        homePathForRole(profile.isAdmin)
      navigate(target, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '登录失败，请稍后重试')
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-page">
      <Card className="auth-card">
        <Typography.Title level={2} style={{ textAlign: 'center', marginBottom: 4 }}>
          声声入耳
        </Typography.Title>
        <Typography.Paragraph
          type="secondary"
          style={{ textAlign: 'center', marginBottom: 24 }}
        >
          英语四六级听力学习系统
        </Typography.Paragraph>

        {error && (
          <Alert
            type="error"
            showIcon
            message={error}
            style={{ marginBottom: 16 }}
          />
        )}

        <Form<LoginFormValues>
          layout="vertical"
          requiredMark={false}
          onFinish={handleFinish}
          disabled={submitting}
        >
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="请输入用户名"
              autoComplete="username"
              size="large"
            />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请输入密码"
              autoComplete="current-password"
              size="large"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              block
              loading={submitting}
            >
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
