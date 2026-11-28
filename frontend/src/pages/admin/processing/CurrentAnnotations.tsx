import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Select, Space } from 'antd'
import { request } from '../../../api/client'
import { binary } from '../../../api/processing'
import type { Evidence, QuestionView } from '../../../api/processing-types'
import QuestionContent from './QuestionContent'
import './processing.css'

export default function CurrentAnnotations({paperId,batchId}:{paperId:number;batchId:number|null}) {
  const [items,setItems]=useState<QuestionView[]>([]);const [state,setState]=useState('');const [error,setError]=useState('')
  const [selected,setSelected]=useState('');const [audio,setAudio]=useState('');const media=useRef<string|null>(null)
  const controller=useRef<AbortController|null>(null)
  useEffect(()=>{const abort=new AbortController();setItems([]);setState('');setError('')
    if(batchId)void request<{items:QuestionView[];annotation_state:string}>({url:`/api/v1/admin/listening-papers/${paperId}/annotations`,params:{expected_batch_id:batchId,limit:100},signal:abort.signal})
      .then(value=>{setItems([...value.items].sort((a,b)=>a.question_no-b.question_no));setState(value.annotation_state)})
      .catch(cause=>{if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:'正式标注读取失败')})
    return()=>abort.abort()
  },[paperId,batchId])
  useEffect(()=>()=>{controller.current?.abort();if(media.current)URL.revokeObjectURL(media.current)},[])
  async function play(evidence:Evidence){controller.current?.abort();const abort=new AbortController();controller.current=abort
    try{const blob=await binary(`/api/v1/admin/listening-papers/${paperId}/evidences/${encodeURIComponent(evidence._src_id)}/audio?expected_batch_id=${batchId}`,abort.signal)
      if(abort.signal.aborted)return;if(media.current)URL.revokeObjectURL(media.current);media.current=URL.createObjectURL(blob);setAudio(media.current)
    }catch(cause){if(!abort.signal.aborted)setError(cause instanceof Error?cause.message:'证据播放失败')}
  }
  const question=items.find(item=>item.question_src_id===selected)??items[0]
  return <Card title="当前正式批次标注（管理员）" extra={question&&<Select aria-label="正式标注题目" value={question.question_src_id} onChange={setSelected} options={items.map(item=>({value:item.question_src_id,label:`第${item.question_no}题`}))}/>}>
    <Space orientation="vertical" style={{width:'100%'}} size={16}>
      {error&&<Alert type="error" title={error} action={<Button onClick={()=>window.location.reload()}>整体刷新详情</Button>}/>}
      {state==='legacy_pending'&&<Alert type="info" title="当前正式批次尚无新规则标注" description="原试卷的开放状态保留。评测结果和未审核草稿不会自动成为正式标注；需完成整套审核与正式入库后在此展示。"/>}
      {state==='method_pending'&&<Alert type="info" title="标注方法已更新，待重新标注" description="既有试卷的开放状态继续保留；新标注须重新生成并整套审核。"/>}
      {audio&&<audio controls key={audio} src={audio} style={{width:'100%'}}/>}
      {question&&<QuestionContent question={question} play={evidence=>void play(evidence)}/>}
    </Space>
  </Card>
}
