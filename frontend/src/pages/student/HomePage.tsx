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
        <Typography.Paragraph type="secondary">
          从左侧「听力练习」进入可作答的试卷：可听音频、点选答案、标记题目、查看答题卡并交卷。本机草稿仅保存在当前浏览器，不跨设备；同一试卷仅可提交一次，提交后可只读回看题目与汇总。
        </Typography.Paragraph>
        <Typography.Paragraph style={{ marginBottom: 0 }} type="secondary">
          仅支持桌面浏览器（≥1024px）；小于 1024px 不承诺可用。手机/平板不保证。
        </Typography.Paragraph>
      </Card>
    </Space>
  )
}
