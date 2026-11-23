import { Card, Col, Row, Space, Tag, Typography } from 'antd'
import type { QuestionListData } from '../../../api/skill-error-query'
import ErrorQuestionList from './ErrorQuestionList'
import QuestionTable from './QuestionTable'

interface CategorySummaryProps {
  data: QuestionListData
  mode: 'by-leaf' | 'all'
  onOpenLeaf: (code: string) => void
  onOpenDetail: (questionId: number) => void
  onScopeRefresh: () => void
}

export default function CategorySummary({
  data,
  mode,
  onOpenLeaf,
  onOpenDetail,
  onScopeRefresh,
}: CategorySummaryProps) {
  const isSkill = data.subject.type === 'skill_category'
  const leafSum = isSkill
    ? data.items.reduce((total, item) => total + item.matched_skills.length, 0)
    : (data.option_relation_count ?? 0)

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title={`${data.subject.name} · ${data.subject.display_code}`}
        extra={
          <Space>
            <Tag color="blue">分类汇总</Tag>
            <Tag>{data.question_count} 道题（去重）</Tag>
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          分类节点只用于汇总和导航，不直接作为题目标注；题目按叶子归组，同一题命中多个叶子时只在
          “全部题目”中计一次。
        </Typography.Paragraph>
        <Row gutter={[12, 12]}>
          {data.matched_leaves.map((leaf) => {
            const count = data.items.filter((item) =>
              item.matched_skills.some((skill) => skill.code === leaf.code),
            ).length
            return (
              <Col xs={24} md={12} key={leaf.code}>
                <Card size="small" hoverable onClick={() => onOpenLeaf(leaf.code)}>
                  <Space direction="vertical" size={2}>
                    <Space>
                      <Tag color="blue">{leaf.display_code}</Tag>
                      <Typography.Text strong>{leaf.name}</Typography.Text>
                    </Space>
                    <Typography.Text type="secondary">
                      当前页命中 {count} 道题 · 点击进入该条目
                    </Typography.Text>
                  </Space>
                </Card>
              </Col>
            )
          })}
        </Row>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          {isSkill
            ? `当前页叶子命中计数之和 ${leafSum} 可能大于分类去重总数 ${data.question_count}；以“全部题目”去重数为准。`
            : `当前分类共 ${data.question_count} 道题（去重），选项—错因关系 ${data.option_relation_count ?? 0} 条。`}
        </Typography.Paragraph>
      </Card>

      <Card
        title={mode === 'by-leaf' ? '当前页题目（按命中叶子标注）' : '全部题目（按题目去重）'}
        extra={<Typography.Text type="secondary">共 {data.question_count} 条</Typography.Text>}
      >
        {isSkill ? (
          <QuestionTable items={data.items} onOpenDetail={onOpenDetail} />
        ) : (
          <ErrorQuestionList
            key={data.subject.code}
            items={data.items}
            scopeVersion={data.scope_version}
            onOpenDetail={onOpenDetail}
            onScopeRefresh={onScopeRefresh}
          />
        )}
      </Card>
    </Space>
  )
}
