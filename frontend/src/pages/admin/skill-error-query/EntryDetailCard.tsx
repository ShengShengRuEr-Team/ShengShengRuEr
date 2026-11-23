import { ArrowRightOutlined, TagOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Space, Tag, Typography } from 'antd'
import type { DictionaryNode } from '../../../api/skill-error-query'

interface CategoryStats {
  leafCount: number
  questionCount: number
  optionRelationCount?: number | null
}

interface EntryDetailCardProps {
  node: DictionaryNode
  categoryStats?: CategoryStats
  onOpenQuestions: () => void
}

export default function EntryDetailCard({
  node,
  categoryStats,
  onOpenQuestions,
}: EntryDetailCardProps) {
  const isSkill = node.kind === 'skill'
  const isCategory = node.level < 3
  const countText = isCategory
    ? categoryStats
      ? `分类汇总：${categoryStats.leafCount} 个三级条目 / ${categoryStats.questionCount} 道正式题目${
          categoryStats.optionRelationCount != null
            ? ` / ${categoryStats.optionRelationCount} 条选项—错因关系`
            : ''
        }`
      : '分类汇总：加载中…'
    : isSkill
      ? `关联题目 ${node.question_count ?? 0}（主要 ${node.primary_question_count ?? 0} / 辅助 ${node.auxiliary_question_count ?? 0}）`
      : `关联题目 ${node.question_count ?? 0} · 选项—错因关系 ${node.option_relation_count ?? 0}`
  const specialDiagnosis = isSkill && node.usage_scope.includes('专项诊断')
  const questionsUnavailable =
    isCategory && categoryStats !== undefined && categoryStats.questionCount === 0
  const pendingTrial =
    node.review_status.includes('待试标') ||
    (node.notes ?? '').includes('待试标') ||
    (!isSkill &&
      ['设计已确认待试标', '候选细类'].includes(node.maturity))

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
        <Button type="primary" disabled={questionsUnavailable} onClick={onOpenQuestions}>
          查看相关题目 <ArrowRightOutlined />
        </Button>
      }
    >
      <Typography.Paragraph type="secondary" className="skill-query-path">
        {node.path.map((part) => part.name).join(' / ')}
      </Typography.Paragraph>
      {specialDiagnosis ? (
        <Alert
          type="info"
          showIcon
          message="专项诊断说明"
          description="该技能用于专项诊断，不因单题对错直接判定。"
          style={{ marginBottom: 12 }}
        />
      ) : null}
      {pendingTrial ? (
        <Alert
          type="warning"
          showIcon
          message="待试标条目说明"
          description="该条目为教学与标注参考口径，尚未完成测量验证，不构成对学生个人的诊断结论。"
          style={{ marginBottom: 12 }}
        />
      ) : null}
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
              {node.observable_behavior || '暂无'}
            </Descriptions.Item>
            <Descriptions.Item label="反例">{node.counter_example || '暂无'}</Descriptions.Item>
          </>
        ) : (
          <>
            <Descriptions.Item label="确认规则">
              {node.confirmation_rule || '暂无'}
            </Descriptions.Item>
            <Descriptions.Item label="边界规则">
              {node.boundary_rule || '暂无'}
            </Descriptions.Item>
            <Descriptions.Item label="成熟度">{node.maturity}</Descriptions.Item>
          </>
        )}
        <Descriptions.Item label="审核状态">
          <Tag icon={<TagOutlined />}>{node.review_status}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="历史编码">{node.legacy_codes || '暂无'}</Descriptions.Item>
        <Descriptions.Item label="备注">{node.notes || '暂无'}</Descriptions.Item>
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
