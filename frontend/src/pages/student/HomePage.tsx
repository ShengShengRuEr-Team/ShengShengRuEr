import { Card, Space, Tag, Typography } from 'antd'
import { useAuth } from '../../auth/useAuth'

/** 学生端首页。学生端不出现任何管理入口。 */
export default function StudentHomePage() {
  const { user } = useAuth()

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" size={4}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            学生端
          </Typography.Title>
          <Typography.Text type="secondary">
            当前登录：
            {user?.nickname || user?.username}
            <Tag color="blue" style={{ marginLeft: 8 }}>
              学生
            </Tag>
          </Typography.Text>
        </Space>
      </Card>

      <Card>
        <Typography.Paragraph style={{ marginBottom: 0 }} type="secondary">
          模块一仅提供登录、退出、身份区分与页面框架。听力练习等功能在后续模块中实现。
        </Typography.Paragraph>
      </Card>
    </Space>
  )
}
