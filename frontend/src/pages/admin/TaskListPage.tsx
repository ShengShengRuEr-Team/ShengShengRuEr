import { Card, Typography } from 'antd'

/** 第 5 步实现：任务列表、启动任务、状态 / 进度 / 结果 / 异常。 */
export default function AdminTaskListPage() {
  return (
    <Card>
      <Typography.Title level={4}>任务管理</Typography.Title>
      <Typography.Paragraph type="secondary">
        第 5 步实现：启动处理任务，查看状态、进度、结果与异常信息。
      </Typography.Paragraph>
    </Card>
  )
}
