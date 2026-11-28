import type { ReactNode } from 'react'
import { ArrowRightOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Divider,
  Space,
  Tag,
  Typography,
} from 'antd'
import type { DictionaryNode } from '../../../api/skill-error-query'

interface CategoryStats {
  leafCount: number
  questionCount: number
  optionRelationCount?: number | null
}

interface EntryDetailCardProps {
  node: DictionaryNode
  allNodes: DictionaryNode[]
  categoryStats?: CategoryStats
  onOpenQuestions: () => void
}

function Section({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <div className="skill-query-detail-section">
      <div className="skill-query-section-title">{title}</div>
      <div className="skill-query-section-body">{children}</div>
    </div>
  )
}

function descendantLeaves(node: DictionaryNode, allNodes: DictionaryNode[]): number {
  return allNodes.filter(
    (candidate) =>
      candidate.level === 3 &&
      candidate.path.some((part) => part.code === node.code),
  ).length
}

export default function EntryDetailCard({
  node,
  allNodes,
  categoryStats,
  onOpenQuestions,
}: EntryDetailCardProps) {
  const isSkill = node.kind === 'skill'
  const isCategory = node.level < 3
  const children = allNodes
    .filter((candidate) => candidate.parent_id === node.id)
    .sort((a, b) =>
      a.display_code.localeCompare(b.display_code, 'zh-CN', { numeric: true }),
    )
  const specialDiagnosis = isSkill && node.usage_scope.includes('专项诊断')
  const pendingTrial =
    node.review_status.includes('待试标') ||
    (node.notes ?? '').includes('待试标') ||
    (!isSkill &&
      (node.maturity.includes('待试标') || node.maturity.includes('候选细类')))
  const questionsUnavailable =
    isCategory && categoryStats !== undefined && categoryStats.questionCount === 0
  const countText = isCategory
    ? categoryStats
      ? `${categoryStats.leafCount} 个三级条目 / ${categoryStats.questionCount} 道正式题目${
          categoryStats.optionRelationCount != null
            ? ` / ${categoryStats.optionRelationCount} 条选项—错因关系`
            : ''
        }`
      : '加载中…'
    : isSkill
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
          <Tag color="blue">{node.code}</Tag>
          <Tag>{node.display_code}</Tag>
          <Tag color="green">{node.status}</Tag>
          <Tag>{isCategory ? `${node.level === 1 ? '一级' : '二级'}分类` : '三级条目'}</Tag>
          {!isCategory && isSkill ? (
            <>
              <Tag>{node.usage_scope}</Tag>
              <Tag>{node.exam_level_scope}</Tag>
            </>
          ) : null}
          {!isCategory && !isSkill ? <Tag>{node.maturity}</Tag> : null}
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
          style={{ marginBottom: 16 }}
        />
      ) : null}
      {pendingTrial ? (
        <Alert
          type="warning"
          showIcon
          message="待试标：尚未完成测量验证，不构成对学生个人的诊断结论。"
          style={{ marginBottom: 16 }}
        />
      ) : null}

      {isCategory ? (
        <>
          <Section title="定义">
            <Typography.Paragraph>{node.definition}</Typography.Paragraph>
          </Section>
          <Section title="分类关系">
            <Typography.Paragraph type="secondary">
              完整路径：{node.path.map((part) => part.name).join(' / ')}
            </Typography.Paragraph>
            {children.length === 0 ? (
              <Typography.Text type="secondary">暂无直接子节点</Typography.Text>
            ) : (
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                {children.map((child) => {
                  const count =
                    child.level === 3
                      ? child.question_count ?? 0
                      : descendantLeaves(child, allNodes)
                  return (
                    <div key={child.code} className="skill-query-child-row">
                      <Space wrap>
                        <Tag color="blue">{child.code}</Tag>
                        <Typography.Text>{child.name}</Typography.Text>
                        <Typography.Text type="secondary">
                          {child.level === 2 ? '二级分类' : '三级条目'}
                        </Typography.Text>
                      </Space>
                      <Tag>{child.level === 3 ? `${count} 题` : `${count} 个三级条目`}</Tag>
                    </div>
                  )
                })}
              </Space>
            )}
          </Section>
        </>
      ) : (
        <>
          <Section title="定义">
            <Typography.Paragraph>{node.definition}</Typography.Paragraph>
          </Section>
          <Section title={isSkill ? '可观察行为' : '确认规则'}>
            <Typography.Paragraph>
              {isSkill
                ? node.observable_behavior || '暂无'
                : node.confirmation_rule || '暂无'}
            </Typography.Paragraph>
          </Section>
          <Section title={isSkill ? '不应标注的情形' : '判定边界'}>
            <Typography.Paragraph>
              {isSkill ? node.counter_example || '暂无' : node.boundary_rule || '暂无'}
            </Typography.Paragraph>
          </Section>
          {!isSkill ? (
            <Section title="成熟度">
              <Tag color={node.maturity.includes('待试标') ? 'gold' : 'default'}>
                {node.maturity}
              </Tag>
            </Section>
          ) : null}
        </>
      )}

      <Divider />
      <Collapse
        size="small"
        items={[
          {
            key: 'metadata',
            label: (
              <Space wrap>
                <Typography.Text strong>元数据与来源</Typography.Text>
                <Tag>字典状态：{node.review_status}</Tag>
              </Space>
            ),
            children: (
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Typography.Text>
                  启用状态：<Tag color="green">{node.status}</Tag>
                </Typography.Text>
                <Typography.Text>审核状态：{node.review_status}</Typography.Text>
                <Typography.Text>历史编码：{node.legacy_codes || '暂无'}</Typography.Text>
                <Typography.Text>备注：{node.notes || '暂无'}</Typography.Text>
                {isSkill && !isCategory ? (
                  <>
                    <Typography.Text>使用范围：{node.usage_scope}</Typography.Text>
                    <Typography.Text>适用考试级别：{node.exam_level_scope}</Typography.Text>
                  </>
                ) : null}
                <Typography.Text>查询统计：{countText}</Typography.Text>
              </Space>
            ),
          },
        ]}
      />
      <Typography.Paragraph type="secondary" className="skill-query-boundary">
        分类用于浏览，三级条目用于标注。条目审核状态来自词典；“正式审核通过”是题目列表的标注状态。
      </Typography.Paragraph>
    </Card>
  )
}
