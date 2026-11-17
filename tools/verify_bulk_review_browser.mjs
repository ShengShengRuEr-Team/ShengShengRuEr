// Synthetic 25-question reviewer actions; never write to the real acceptance DB.
import {createRequire} from 'node:module'
import fs from 'node:fs/promises'
import path from 'node:path'
const {chromium}=createRequire(process.env.M3_PLAYWRIGHT_PACKAGE)('playwright')
const output=path.resolve(process.env.M3_BROWSER_OUTPUT||'backend/var/verification/bulk-final-review')
await fs.mkdir(output,{recursive:true})
const root='/api/v1/admin/processing-workflows',wid='11111111-1111-4111-8111-111111111111',rid='22222222-2222-4222-8222-222222222222',sid='33333333-3333-4333-8333-333333333333',hash='a'.repeat(64)
const questions=Array.from({length:25},(_,i)=>{
 const n=i+1,ev={_src_id:`ev:${n}`,relation_src_id:`skill-ev:${n}`,evidence_text:'Synthetic body states Alpha.',start_ms:1000,end_ms:2000}
 return {question_src_id:`q:${n}`,question_no:n,question_text:`Synthetic question ${n}`,explanation_text:'Synthetic source only.',correct_option_base:'A',correct_option_display:'A',generation_state:n===1?'generated_empty':'generated',
  options:'ABCD'.split('').map(letter=>({display_letter:letter,base_option_letter:letter,text:`Synthetic ${letter}`,error_causes:letter==='B'&&n!==1?[{relation_src_id:`error:${n}`,code:'E4.3',rationale:'Synthetic distractor',evidence:[{...ev,relation_src_id:`error-ev:${n}`}]}]:[]})),
  skills:[{_src_id:`skill:${n}`,skill_code:'S21',role:'PRIMARY',evidence:[ev]}],answer_evidence:[{...ev,relation_src_id:`answer:${n}`}],
  review_requirements:{primary_skills:[`skill:${n}`,`skill-ev:${n}`],answer_evidence:[`answer:${n}`],error_causes:n===1?[]:[`error:${n}`,`error-ev:${n}`]}}
})
const workflow={workflow_id:wid,revision_id:rid,row_version:7,exam_level:'CET4',exam_year:2025,exam_month:6,paper_set:1,exam_paper_id:null,
 processing_state:'awaiting_review',content_review_state:'pending',error_review_state:'pending',publication_state:'unpublished',created_at:'2026-11-17T00:00:00Z',updated_at:'2026-11-17T00:00:01Z',
 task_id:wid,result_hash:hash,current_batch_id:null,is_student_visible:false,document_mode:'text',listening_pages:{paper:[1],answer:[1]},materials:[],
 stages:{final:{task_id:wid,artifact_id:1,artifact_hash:hash,dependency_hash:hash}},review_session_id:sid,review_session_version:1,
 progress:{stage:'review',description:'Synthetic final result',completed_count:25,total_count:25,unit:'题',elapsed_ms:10000,active:false,checkpoint:null},gates:[],issues:[],allowed_actions:[],usage:{known_usd:'0.02',reserved_usd:'0.01',has_unknown_charges:true}}
const checks=[],errors=[]
function check(ok,label){if(!ok)throw Error(label);checks.push(label)}
const browser=await chromium.launch({headless:true,executablePath:process.env.M3_BROWSER_EXECUTABLE})
try{
 for(const [width,height] of [[1440,900],[1280,720]]){
  const context=await browser.newContext({viewport:{width,height}}),page=await context.newPage()
  await page.addInitScript(()=>localStorage.setItem('ssre_access_token','synthetic-bulk-review-token'))
  page.on('pageerror',e=>errors.push(e.message))
  let version=1,saves=0,conflict=false,history=[],saved=[{question_src_id:'q:3',content:'changes_required',primary_skills:[],answer_evidence:[],error_causes:[],empty_errors_confirmed:false,note:'Existing individual note',issues:[]}]
  await page.route('**/api/v1/**',async route=>{
   const request=route.request(),u=new URL(request.url()),p=u.pathname
   if(request.method()==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}})
   let data
   if(p==='/api/v1/getInfo')data={user:{user_id:1,username:'synthetic-admin',nickname:'合成批量验证'},roles:['admin'],is_admin:true,permissions:[]}
   else if(p===root+'/capabilities')data={max_upload_bytes:536870912,processing_ready:true,blocked_reason:null}
   else if(p===`${root}/${wid}`)data={...workflow,review_session_version:version}
   else if(p.endsWith('/operations'))data={items:[]}
   else if(p.endsWith('/questions'))data={items:questions,total:25,result_hash:hash,next_cursor:null}
   else if(p.endsWith(`/review-sessions/${sid}`))data={row_version:version,items:saved,state:'draft',total:25,result_hash:hash,next_cursor:null}
   else if(p.endsWith('/items')&&request.method()==='PATCH'){
    saves++;const body=request.postDataJSON();history.push(body)
    check(body.expected_result_hash===hash&&body.expected_session_version===version,`${width}: immutable result and session version accompany bulk save`)
    check(Boolean(request.headers()['idempotency-key']),`${width}: bulk save retains original idempotency key`)
    if(conflict)return route.fulfill({status:409,json:{code:409,msg:'Synthetic version conflict; inputs retained',error_code:'VERSION_CONFLICT',data:null}})
    saved=body.items;version++
    data={operation_id:rid,workflow_id:wid,revision_id:rid,action:'review_save',state:'succeeded',failure_code:null,result:{session_version:version},created_at:workflow.created_at}
   }else throw Error(`Unexpected synthetic request: ${request.method()} ${p}`)
   await route.fulfill({status:200,json:{code:200,msg:'Synthetic response',data}})
  })
  const base=process.env.M3_BROWSER_URL||'http://127.0.0.1:5173'
  await page.goto(`${base}/admin/listening-papers/processing/${wid}?question=25`)
  const all=page.getByRole('checkbox',{name:'全选全部题目',exact:true}),apply=page.getByRole('button',{name:'一键填入全部题目',exact:true}),save=page.getByRole('button',{name:'保存全部题目意见',exact:true})
  await page.waitForFunction(()=>!document.querySelector('#bulk-review-note')?.disabled)
  check(await save.isDisabled(),`${width}: bulk review starts without automatic changes`)
  await all.check();await page.getByText('已完整勾选 25 / 25 题',{exact:true}).waitFor()
  const drafts=()=>page.evaluate(()=>JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith('m3-review:')&&!k.includes(':conflict:')))).drafts)
  let values=await drafts()
  check(Object.keys(values).length===25&&values['q:1'].empty_errors_confirmed,`${width}: selection covers all 25 questions and the empty-error confirmation`)
  check(values['q:3'].note==='Existing individual note',`${width}: selecting all preserves existing notes`)
  await page.getByLabel('建议审核意见（可修改）',{exact:true}).fill('Synthetic basis for all 25 questions')
  await page.getByRole('button',{name:'只填空白意见',exact:true}).click()
  values=await drafts()
  check(values['q:3'].note==='Existing individual note'&&values['q:25'].note==='Synthetic basis for all 25 questions',`${width}: fill-empty preserves individual opinions`)
  await page.getByLabel('主要技能 S21 · 明确事实与细节提取',{exact:true}).uncheck()
  check(await all.evaluate(el=>el.indeterminate),`${width}: one individual change makes bulk selection partial`)
  await all.check()
  await all.uncheck();values=await drafts()
  check(Object.values(values).every(v=>v.content==='changes_required'&&!v.primary_skills.length&&!v.answer_evidence.length&&!v.error_causes.length&&!v.empty_errors_confirmed),`${width}: clear-all resets decisions while retaining text`)
  await all.check();await apply.click()
  check(Object.values(await drafts()).every(v=>v.note==='Synthetic basis for all 25 questions'),`${width}: explicit apply-all replaces every opinion`)
  await page.getByLabel('审核意见 / 退回原因',{exact:true}).fill('Individual opinion for question 25')
  await page.getByRole('checkbox',{name:'已完成当前最终版本的原音核听确认',exact:true}).check()
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#bulk-review-note')?.disabled)
  check(await page.getByLabel('审核意见 / 退回原因',{exact:true}).inputValue()==='Individual opinion for question 25',`${width}: reload restores unsaved individual edits`)
  check(await page.getByRole('checkbox',{name:'已完成当前最终版本的原音核听确认',exact:true}).isChecked(),`${width}: reload restores the user's audio checkbox`)
  check(await page.getByLabel('整套审核实际依据',{exact:true}).inputValue()==='Synthetic basis for all 25 questions',`${width}: unified note also fills and restores final review basis`)
  check(await page.getByRole('button',{name:'提交整套审核',exact:true}).isDisabled(),`${width}: unsaved bulk opinions cannot submit`)
  await page.getByRole('region',{name:'整套批量审核'}).scrollIntoViewIfNeeded()
  await page.screenshot({path:path.join(output,`${width}-bulk.png`)})
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width}: no horizontal overflow`)
  check(saves===0,`${width}: selection, templates and reload perform no server writes`)
  await save.click();await page.getByText('全部25题意见已保存到服务器',{exact:true}).waitFor()
  check(saves===1&&history[0].items.length===25,`${width}: one save carries all 25 questions`)
  for(const q of questions){const item=history[0].items.find(v=>v.question_src_id===q.question_src_id)
   check(item.content==='approved'&&Object.entries(q.review_requirements).every(([field,refs])=>item[field].length===refs.length&&refs.every(ref=>item[field].some(r=>r.reference===ref&&r.decision==='approved'))),`${width}: ${q.question_src_id} contains its own required references`)}
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#bulk-review-note')?.disabled)
  check(await page.getByRole('button',{name:'提交整套审核',exact:true}).isEnabled(),`${width}: saved full coverage and explicit audio/basis enable final submit`)
  await page.getByLabel('审核意见 / 退回原因',{exact:true}).fill('Conflict must retain this input')
  conflict=true
  await save.click();await page.getByText('Synthetic version conflict; inputs retained',{exact:true}).waitFor()
  check((await drafts())['q:25'].note==='Conflict must retain this input',`${width}: CAS failure preserves unsaved bulk drafts`)
  check(saves===2,`${width}: failed save is not automatically retried`)
  await context.close()
 }
 check(errors.length===0,'no browser runtime errors')
 await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({status:'PASS',scope:'synthetic 25-question bulk review; no real approvals, publication, or model calls',checks,errors},null,2))
 console.log(JSON.stringify({status:'PASS',checks:checks.length,output}))
}finally{await browser.close()}
