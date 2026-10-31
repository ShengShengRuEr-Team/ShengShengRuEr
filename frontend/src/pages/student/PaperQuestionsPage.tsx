import { Card, Typography } from 'antd'

/** 第 6 步实现：学生端题目页，只有题干与选项，不渲染答案 / 解析 / 原文。 */
export default function StudentPaperQuestionsPage() {
  return (
    <Card>
      <Typography.Title level={4}>学生端题目页</Typography.Title>
      <Typography.Paragraph type="secondary">
        第 6 步实现：题干与选项（无答案 / 解析 / 原文）。
      </Typography.Paragraph>
    </Card>
  )
}
