import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Checkbox, Input, Space, Typography } from 'antd'
import { request } from '../../../api/client'
import { binary, WORKFLOWS } from '../../../api/processing'
import type { Projection, WorkflowDetail } from '../../../api/processing-types'

interface StageItem {_src_id: string; segment_type?: string; text?: string; question_text?: string; start_ms?: number; end_ms?: number}
type StageData = Projection & {items: StageItem[]; next_cursor: number | null; total: number}
export default function StageApprovalPanel({workflow, stage, busy, command}: {
  workflow: WorkflowDetail; stage: string; busy: boolean
  command: (action: string, path: string, body: Record<string, unknown>) => Promise<unknown>
}) {
  const [items, setItems] = useState<StageItem[]>([]); const [notes, setNotes] = useState<Record<string,string>>({})
  const [checked, setChecked] = useState<Record<string,boolean>>({}); const [error, setError] = useState('')
  const [audio,setAudio] = useState<{url:string;label:string}|null>(null)
  const audioUrl=useRef<string|null>(null);const audioController=useRef<AbortController|null>(null)
  useEffect(()=>()=>{audioController.current?.abort();if(audioUrl.current)URL.revokeObjectURL(audioUrl.current)},[])
  async function play(item:StageItem) {
    audioController.current?.abort();const controller=new AbortController();audioController.current=controller
    try {const blob=await binary(`${WORKFLOWS}/${workflow.workflow_id}/revisions/${workflow.revision_id}/segments/${encodeURIComponent(item._src_id)}/audio`,controller.signal)
      if(controller.signal.aborted)return;if(audioUrl.current)URL.revokeObjectURL(audioUrl.current)
      audioUrl.current=URL.createObjectURL(blob);setAudio({url:audioUrl.current,label:`原音 ${(Number(item.start_ms)/1000).toFixed(2)}—${(Number(item.end_ms)/1000).toFixed(2)} 秒`})
    } catch(cause){if(!controller.signal.aborted)setError(cause instanceof Error?cause.message:'原音片段读取失败')}
  }
  const projection = workflow.stages[stage]
  const gate = workflow.gates.find(gate => gate.kind === stage)
  const approved = gate?.state === 'approved' && gate.dependency_hash === projection?.dependency_hash
  const selectedCount = items.filter(item => checked[item._src_id]).length
  const allSelected = items.length > 0 && selectedCount === items.length
  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      const combined: StageItem[] = []; let cursor: number | null = 0
      for (let page = 0; cursor !== null && page < 10; page++) {
        const result: StageData = await request<StageData>({url:`${WORKFLOWS}/${workflow.workflow_id}/revisions/${workflow.revision_id}/stages/${stage}`,
          params:{limit:100,cursor,expected_artifact_hash:projection.artifact_hash},signal:controller.signal})
        combined.push(...result.items); cursor = result.next_cursor
      }
      if (cursor !== null) throw new Error('阶段内容超过单次审核范围，请联系维护人员分批核对')
      if (!controller.signal.aborted) setItems(stage === 'sample' ? combined.slice(0,5) : combined.filter(item => stage !== 'align' || item.segment_type === 'body'))
    }
    void load().catch(cause => {if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '阶段读取失败')})
    return () => controller.abort()
  }, [workflow.workflow_id, workflow.revision_id, stage, projection.artifact_hash])
  async function approve() {
    if (items.some(item => !checked[item._src_id] || !notes[item._src_id]?.trim())) {setError('请逐项确认并填写实际核对依据'); return}
    await command('stage_approval', 'stage-approvals', {stage, artifact_hash:projection.artifact_hash,
      expected_stage_dependency_hash:projection.dependency_hash,decision:'approved',
      items:items.map(item => ({reference:item._src_id,decision:'approved',reason:notes[item._src_id]}))})
  }
  return <Card title={stage === 'align' ? '核听对齐确认' : stage === 'source' ? '来源内容确认' : '前5题试标复核'}>
    <Space orientation="vertical" size={12} style={{width:'100%'}}>
      <Alert type="info" showIcon title="确认只保存审核依据；继续处理需另行点击" description={stage === 'align' ? '请结合原音逐句核听。此处记录人工确认，不冒充独立毫秒精度测量。' : '请结合原件、题目与证据逐项核对。任何新内容结果仍须整套重新审核。'} />
      {error && <Alert type="error" title={error} />}
      {audio&&<div className="processing-stage-audio"><Typography.Text>{audio.label}</Typography.Text><audio key={audio.url} src={audio.url} controls preload="metadata" style={{width:'100%'}}/></div>}
      {!approved && <Space wrap>
        <Checkbox checked={allSelected} indeterminate={selectedCount > 0 && !allSelected} disabled={busy || !items.length}
          onChange={event => setChecked(Object.fromEntries(items.map(item => [item._src_id, event.target.checked])))}>
          {allSelected ? '取消全选' : '全选'}</Checkbox>
        <Typography.Text type="secondary" aria-live="polite">已选 {selectedCount} / {items.length} 项</Typography.Text>
      </Space>}
      {!approved && items.map((item,index) => <div className="processing-stage-item" key={item._src_id}>
        <Checkbox checked={Boolean(checked[item._src_id])} onChange={event => setChecked(value => ({...value,[item._src_id]:event.target.checked}))}>
          第 {index+1} 项：{item.text ?? item.question_text}</Checkbox>
        {stage==='align'&&<Space wrap style={{marginTop:8}}><Typography.Text type="secondary">原音 {(Number(item.start_ms)/1000).toFixed(2)}—{(Number(item.end_ms)/1000).toFixed(2)} 秒</Typography.Text>
          <Button size="small" onClick={()=>void play(item)}>试听本句</Button></Space>}
        <Input aria-label={`第${index+1}项核对依据`} placeholder="填写本项的原件定位、核听或证据核对依据" value={notes[item._src_id] ?? ''}
          onChange={event => setNotes(value => ({...value,[item._src_id]:event.target.value}))} />
      </div>)}
      {approved && <Typography.Text type="success">当前阶段已确认，可以显式继续下一阶段。</Typography.Text>}
      <Space wrap><Button disabled={busy || approved || !items.length} onClick={() => void approve()}>保存逐项确认</Button>
        <Button type="primary" disabled={busy || !approved} onClick={() => void command('continue','continue',{stage,expected_stage_dependency_hash:projection.dependency_hash})}>继续下一阶段</Button></Space>
    </Space>
  </Card>
}
