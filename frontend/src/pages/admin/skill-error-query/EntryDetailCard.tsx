import { ArrowRightOutlined, TagOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Space, Tag, Typography } from 'antd'
import type { DictionaryNode } from '../../../api/skill-error-query'

interface EntryDetailCardProps {
  node: DictionaryNode
  onOpenQuestions: () => void
}

export default function EntryDetailCard({ node, onOpenQuestions }: EntryDetailCardProps) {
  const isSkill = node.kind === 'skill'
  const countText = isSkill
    ? `关联题目 ${node.question_count ?? 0}（主要 ${node.primary_question_count ?? 0} / 辅助 ${node.auxiliary_question_count ?? 0}）`
    : `关联题目 ${node.question_count ?? 0} · 选项—错因关系 ${node.option_relation_count ?? 0}`

  return (
    <Card
      className="skill-query-entry-card"
      title={
        <Space wrap>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {node.name}
          </Typography.Title>
          <Tag color="blue">{node.display_code}</Tag>
          <Tag>{node.level === 3 ? '三级条目' : node.level === 2 ? '二级分类' : '一级分类'}</Tag>
        </Space>
      }
      extra={
        <Button type="primary" onClick={onOpenQuestions}>
          查看相关题目 <ArrowRightOutlined />
        </Button>
      }
    >
      <Typography.Paragraph type="secondary" className="skill-query-path">
        {node.path.map((part) => part.name).join(' / ')}
      </Typography.Paragraph>
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="稳定代码">
          <Typography.Text code>{node.code}</Typography.Text>
        </Descriptions.Item>
        <Descriptions.Item label="定义">{node.definition}</Descriptions.Item>
        {isSkill ? (
          <>
            <Descriptions.Item label="适用范围">{node.usage_scope}</Descriptions.Item>
            <Descriptions.Item label="考试级别">{node.exam_level_scope}</Descriptions.Item>
            <Descriptions.Item label="可观察行为">
              {node.observable_behavior || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="反例">{node.counter_example || '—'}</Descriptions.Item>
          </>
        ) : (
          <>
            <Descriptions.Item label="确认规则">
              {node.confirmation_rule || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="边界规则">
              {node.boundary_rule || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="成熟度">{node.maturity}</Descriptions.Item>
          </>
        )}
        <Descriptions.Item label="审核状态">
          <Tag icon={<TagOutlined />}>{node.review_status}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="历史编码">{node.legacy_codes || '—'}</Descriptions.Item>
        <Descriptions.Item label="备注">{node.notes || '—'}</Descriptions.Item>
        <Descriptions.Item label="查询统计">
          <Typography.Text strong>{countText}</Typography.Text>
        </Descriptions.Item>
      </Descriptions>
      <Typography.Paragraph type="secondary" className="skill-query-boundary">
        条目审核状态来自词典；“正式审核通过”是下方题目列表的标注状态，两者不能混用。
      </Typography.Paragraph>
    </Card>
  )
}
