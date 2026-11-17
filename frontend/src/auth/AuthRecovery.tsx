import { Alert, Button, Space, Typography } from 'antd'
import { useState } from 'react'
import { useAuth } from './useAuth'

/**
 * 登录态恢复失败页：getInfo 500/网络错误时保留 token、不授予任何管理权限，
 * 提供手动重试；不自动重放写操作，也不因 500 清登录态。
 */
export default function AuthRecovery() {
  const { retry, logout } = useAuth()
  const [pending, setPending] = useState(false)

  const handleRetry = async () => {
    setPending(true)
    try {
      await retry()
    } finally {
      setPending(false)
    }
  }

  return (
    <div style={{ maxWidth: 560, margin: '80px auto', padding: 24 }}>
      <Space orientation="vertical" size="large" style={{ width: '100%' }}>
        <Typography.Title level={3}>无法验证登录状态</Typography.Title>
        <Alert
          type="warning"
          showIcon
          title="暂时无法确认当前登录状态"
          description="已保留本地登录凭证，但不会开放任何管理权限。请稍后重试；如持续失败，请联系管理员。"
        />
        <Space>
          <Button type="primary" loading={pending} onClick={handleRetry}>
            重试验证
          </Button>
          <Button onClick={() => void logout()}>退出登录</Button>
        </Space>
      </Space>
    </div>
  )
}
