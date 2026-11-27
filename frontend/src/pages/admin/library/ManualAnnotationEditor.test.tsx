import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { request } from '../../../api/client'
import { sendOperation } from '../../../api/processing'
import type { Entity, LibraryDraft, Snapshot } from '../../../api/library'
import ManualAnnotationEditor from './ManualAnnotationEditor'

vi.mock('../../../api/client', () => ({request: vi.fn()}))
vi.mock('../../../api/processing', () => ({sendOperation: vi.fn()}))
const question: Entity = {_src_id:'q1',passage_src_id:'p1',question_text:'What is the answer?',correct_option:'A'}
const evidence = {_src_id:'ev1',passage_src_id:'p1',segment_src_ids:['s1'],evidence_text:'The answer is Alpha.'}
const snapshot: Snapshot = {
  questions:[question],passages:[{_src_id:'p1'}],transcript_segments:[{_src_id:'s1',passage_src_id:'p1',segment_type:'body',segment_index:1,text:'The answer is Alpha.',alignment_status:'aligned'}],
  evidences:[evidence],skill_question_relations:[{_src_id:'sk1',question_src_id:'q1',relation_kind:'QUESTION_SKILL',skill_code:'S08',role:'PRIMARY',attributes_json:{annotation_reason:'Synthetic source annotation'}},{_src_id:'se1',owner_relation_src_id:'sk1',evidence_src_id:'ev1',attributes_json:{support_note:'Synthetic skill support'}}],
  error_question_relations:[],other_relations:[{_src_id:'ae1',question_src_id:'q1',relation_kind:'ANSWER_EVIDENCE',evidence_src_id:'ev1',attributes_json:{support_note:'Synthetic answer support'}}],
  distractor_assessments:'BCD'.split('').map(letter=>({_src_id:`da${letter}`,question_src_id:'q1',option_letter:letter,status:'NO_SUPPORTED_CANDIDATE',reason:`Synthetic ${letter} comparison`,unresolved_points:[],comparison_evidence_refs:[{evidence_src_id:'ev1',support_note:'Synthetic comparison support'}]})),
}
const draft = {row_version:7,content_hash:'a'.repeat(64)} as LibraryDraft
beforeEach(()=>{
  vi.mocked(request).mockResolvedValue({skills:[{code:'S08',name:'识别细节'}],errors:[]})
  vi.mocked(sendOperation).mockReset();vi.mocked(sendOperation).mockResolvedValue({} as never)
})
describe('人工标注证据表单',()=>{
  it('从现有关系正确恢复各层证据，不重复 Form.List 的路径',async()=>{
    render(<ManualAnnotationEditor workflowId="wf1" owner={1} draft={draft} snapshot={snapshot} question={question} disabled={false} onSaved={()=>{}}/>)
    expect(await screen.findAllByDisplayValue('The answer is Alpha.')).toHaveLength(5)
    expect(screen.getByDisplayValue('Synthetic skill support')).toBeInTheDocument()
    expect(sendOperation).not.toHaveBeenCalled()
  })
  it('保存包含独立答案、三个错误基准选项及其证据，并保留并发前置条件',async()=>{
    const saved=vi.fn(), user=userEvent.setup()
    render(<ManualAnnotationEditor workflowId="wf1" owner={1} draft={draft} snapshot={snapshot} question={question} disabled={false} onSaved={saved}/>)
    await user.type(screen.getByLabelText('本次人工修改原因'),'Synthetic correction')
    await user.click(screen.getByRole('button',{name:'保存本题标注为新版本'}))
    await waitFor(()=>expect(sendOperation).toHaveBeenCalledTimes(1))
    const operation=vi.mocked(sendOperation).mock.calls[0][2]
    const candidate=operation.body.candidate as {skills:Array<{evidence_segment_src_ids:string[];quote:string}>;answer_evidence:unknown[];distractor_assessments:Array<{option_letter:string;comparison_evidence:unknown[]}>}
    expect(operation.body.expected_row_version).toBe(7)
    expect(candidate.skills[0].evidence_segment_src_ids).toEqual(['s1'])
    expect(candidate.skills[0].quote).toBe('The answer is Alpha.')
    expect(candidate.answer_evidence).toHaveLength(1)
    expect(candidate.distractor_assessments.map(a=>a.option_letter)).toEqual(['B','C','D'])
    expect(candidate.distractor_assessments.every(a=>a.comparison_evidence.length===1)).toBe(true)
    expect(saved).toHaveBeenCalledTimes(1)
  })
})
