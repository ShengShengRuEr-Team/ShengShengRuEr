import { Button, Collapse, Space, Tag, Typography } from 'antd'
import type { Evidence, QuestionView } from '../../../api/processing-types'
import { skillName } from '../../../api/processing-adapters'

export default function QuestionContent({question, play}: {question: QuestionView; play: (evidence: Evidence) => void}) {
  function evidence(items: Evidence[]) { return <Space orientation="vertical" style={{width:'100%'}}>{items.map(row => <div key={row._src_id}>
    <Typography.Paragraph style={{marginBottom:4}}>“{row.evidence_text}”</Typography.Paragraph>
    {row.support_note && <Typography.Paragraph type="secondary" style={{marginBottom:4}}>{row.support_note}</Typography.Paragraph>}
    <Button size="small" onClick={() => play(row)}>试听证据 {(row.start_ms/1000).toFixed(2)}—{(row.end_ms/1000).toFixed(2)} 秒</Button>
  </div>)}</Space> }
  const hasErrors = question.options.some(option => option.error_causes.length > 0)
  return <Space orientation="vertical" size={16} style={{width:'100%'}}>
    <Typography.Title level={5}>第 {question.question_no} 题 · {question.question_text}</Typography.Title>
    {question.options.map(option => <div className="processing-option" key={option.display_letter}>
      <Space align="start"><Typography.Text strong>{option.display_letter}.</Typography.Text><Typography.Text>{option.text}</Typography.Text>
        {option.display_letter === question.correct_option_display && <Tag color="green">正确答案</Tag>}</Space>
      {option.error_causes.length > 0 && <Collapse size="small" items={option.error_causes.map(error => ({key:error.relation_src_id,
        label:`错因 ${error.code}${'name' in error ? ` · ${String(error.name)}` : ''}`,
        children:<Space orientation="vertical"><Typography.Paragraph>{error.rationale}</Typography.Paragraph>{evidence(error.evidence)}</Space>}))} />}
    </div>)}
    {!hasErrors && <Typography.Text type="secondary">{question.generation_state === 'generated_empty' ? '无有依据的错因标注（审核页仍须明确确认）' : '错因待生成'}</Typography.Text>}
    <Typography.Paragraph><Typography.Text strong>来源解析：</Typography.Text>{question.explanation_text}</Typography.Paragraph>
    <Typography.Text strong>技能与证据</Typography.Text>
    {question.skills.map(skill => <div key={skill._src_id}><Tag style={{whiteSpace:'normal'}}>{skill.role === 'PRIMARY' ? '主要技能' : '辅助技能'} · {skill.skill_code} · {skillName(skill)}</Tag>
      <Typography.Paragraph>{skill.attributes_json?.annotation_reason}</Typography.Paragraph>{evidence(skill.evidence)}</div>)}
    <Typography.Text strong>答案证据</Typography.Text>{evidence(question.answer_evidence)}
  </Space>
}
