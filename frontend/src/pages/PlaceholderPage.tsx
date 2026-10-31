import { Card, Tag, Typography } from 'antd'

interface PlaceholderPageProps {
  title: string
  /** 计划实现该页面的步骤，例如「第 5 步」。 */
  step: string
}

/** 临时占位页：第 3 步只接通路由，避免登录后跳转落到空白页。 */
export default function PlaceholderPage({ title, step }: PlaceholderPageProps) {
  return (
    <div className="scaffold-page">
      <Card className="scaffold-card">
        <Typography.Title level={2}>{title}</Typography.Title>
        <Typography.Paragraph type="secondary">
          路由已接通，页面内容在{step}实现。
        </Typography.Paragraph>
        <Tag>占位页</Tag>
      </Card>
    </div>
  )
}
