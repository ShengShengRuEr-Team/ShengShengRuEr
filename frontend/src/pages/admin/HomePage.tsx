import { useEffect, useState } from 'react'
import { Alert, Card, Space, Tag, Typography } from 'antd'
import { getAdminOverview } from '../../api/admin'
import { useAuth } from '../../auth/useAuth'

/**
 * 管理端首页。
 *
 * 页面加载时调用 `/api/v1/admin/overview`：管理员返回 200，
 * 学生 token 调用会被后端拒绝（403）——用于验证「页面隐藏与后端接口权限保持一致」。
 */
export default function AdminHomePage() {
  const { user } = useAuth()
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getAdminOverview()
      .then((data) => {
        if (active) {
          setMessage(data.message)
        }
      })
      .catch((err: unknown) => {
        if (!active) {
          return
        }
        setError(err instanceof Error ? err.message : '管理端接口调用失败')
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" size={4}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            管理端
          </Typography.Title>
          <Typography.Text type="secondary">
            当前登录：
            {user?.nickname || user?.username}
            <Tag color="gold" style={{ marginLeft: 8 }}>
              管理员
            </Tag>
          </Typography.Text>
        </Space>
      </Card>

      {message && <Alert type="success" showIcon message={message} />}
      {error && <Alert type="error" showIcon message={error} />}

      <Card>
        <Typography.Paragraph style={{ marginBottom: 0 }} type="secondary">
          模块一仅提供登录、退出、身份区分与页面框架。题库管理、处理任务等功能在后续模块中实现。
        </Typography.Paragraph>
      </Card>
    </Space>
  )
}
