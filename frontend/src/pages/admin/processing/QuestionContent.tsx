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
  const statusLabels = {SUPPORTED:'有支持候选',NO_SUPPORTED_CANDIDATE:'检查后无支持候选',INSUFFICIENT_EVIDENCE:'依据不足待核'}
  return <Space orientation="vertical" size={16} style={{width:'100%'}}>
    <Typography.Title level={5}>第 {question.question_no} 题 · {question.question_text}</Typography.Title>
    {question.assessment_summary && <Typography.Text>干扰项检查 {question.assessment_summary.assessed} / {question.assessment_summary.expected} · 结论完整 {question.assessment_summary.resolved} / {question.assessment_summary.expected}</Typography.Text>}
    {question.options.map(option => <div className="processing-option" key={option.display_letter}>
      <Space align="start"><Typography.Text strong>{option.display_letter}.</Typography.Text><Typography.Text>{option.text}</Typography.Text>
        {option.display_letter === question.correct_option_display && <Tag color="green">正确答案</Tag>}</Space>
      {option.display_letter !== question.correct_option_display && <div>
        <Tag color={option.assessment?.status==='INSUFFICIENT_EVIDENCE'?'orange':undefined}>{option.assessment?statusLabels[option.assessment.status]:'待逐项评估'}</Tag>
        {option.assessment && <><Typography.Paragraph>{option.assessment.reason}</Typography.Paragraph>
          {option.assessment.unresolved_points.map((point,index)=><Typography.Paragraph key={index} type="warning">待核：{point}</Typography.Paragraph>)}
          {evidence(option.assessment.comparison_evidence)}</>}
      </div>}
      {option.error_causes.length > 0 && <Collapse size="small" items={option.error_causes.map(error => ({key:error.relation_src_id,
        label:`错因 ${error.code}${'name' in error ? ` · ${String(error.name)}` : ''}`,
        children:<Space orientation="vertical"><Typography.Paragraph>{error.rationale}</Typography.Paragraph>{evidence(error.evidence)}
          {error.personal_verification_needed&&<Typography.Paragraph>个人核验要求：{error.personal_verification_needed}</Typography.Paragraph>}</Space>}))} />}
    </div>)}
    {!hasErrors && <Typography.Text type="secondary">{question.generation_state === 'generated_empty' ? '无有依据的错因标注（审核页仍须明确确认）' : question.generation_state==='generation_incomplete'?'评估结论尚有待核项':'错因待生成'}</Typography.Text>}
    {!!question.candidate_changes?.length&&<Collapse items={question.candidate_changes.map(change=>({key:change.reference,label:change.diff.semantic_deletion_review_required?'候选删改（含删除，须复核材料理由）':'候选修订对照',children:change.diff.changes.map((row,index)=><div key={index}>
      <Typography.Text strong>{row.option_letter} · {row.error_cause_code??'评估'} · {row.kind}</Typography.Text>
      <Typography.Paragraph>修订前：{JSON.stringify(row.before)}</Typography.Paragraph><Typography.Paragraph>修订后：{JSON.stringify(row.after)}</Typography.Paragraph>
    </div>)}))}/>}
    <Typography.Paragraph><Typography.Text strong>来源解析：</Typography.Text>{question.explanation_text}</Typography.Paragraph>
    <Typography.Text strong>技能与证据</Typography.Text>
    {question.skills.map(skill => <div key={skill._src_id}><Tag style={{whiteSpace:'normal'}}>{skill.role === 'PRIMARY' ? '主要技能' : '辅助技能'} · {skill.skill_code} · {skillName(skill)}</Tag>
      <Typography.Paragraph>{skill.attributes_json?.annotation_reason}</Typography.Paragraph>{evidence(skill.evidence)}</div>)}
    <Typography.Text strong>答案证据</Typography.Text>{evidence(question.answer_evidence)}
  </Space>
}
