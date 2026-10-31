import { Card, Typography } from 'antd'

/** 第 5 步实现：试卷列表、进入题目页。 */
export default function AdminPaperListPage() {
  return (
    <Card>
      <Typography.Title level={4}>试卷管理</Typography.Title>
      <Typography.Paragraph type="secondary">
        第 5 步实现：全部试卷列表，点击进入题目页（含答案 / 解析 / 原文）。
      </Typography.Paragraph>
    </Card>
  )
}
