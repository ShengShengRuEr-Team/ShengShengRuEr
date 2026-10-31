import { Card, Typography } from 'antd'

/** 第 6 步实现：学生端试卷列表（仅已发布试卷）。 */
export default function StudentPaperListPage() {
  return (
    <Card>
      <Typography.Title level={4}>试卷列表</Typography.Title>
      <Typography.Paragraph type="secondary">
        第 6 步实现：学生可见的已发布试卷列表。
      </Typography.Paragraph>
    </Card>
  )
}
