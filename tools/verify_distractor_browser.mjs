// Synthetic V7 desktop verification. This never approves real audio or content.
import {createRequire} from 'node:module'
import fs from 'node:fs/promises'
import path from 'node:path'
const require=createRequire(new URL('../frontend/package.json',import.meta.url))
const {chromium}=require('playwright-core')
const output=path.resolve(process.env.M3_BROWSER_OUTPUT||'backend/var/verification/distractor-browser')
await fs.mkdir(output,{recursive:true})
const base=process.env.M3_BROWSER_URL||'http://127.0.0.1:5198'
const root='/api/v1/admin/processing-workflows',wid='11111111-1111-4111-8111-111111111111',rid='22222222-2222-4222-8222-222222222222',sid='33333333-3333-4333-8333-333333333333'
const hash='a'.repeat(64),checks=[],errors=[],mediaRequests=[],writes=[]
let completed=false
const ev=(id,start,end)=>({_src_id:id,relation_src_id:`ce:${id}`,evidence_text:`Synthetic independent source ${id}.`,start_ms:start,end_ms:end})
const makeQuestion=n=>({question_src_id:`q:${n}`,question_no:n,question_text:'Which source supports Alpha?',explanation_text:'Synthetic comparison only.',correct_option_base:'A',correct_option_display:'A',generation_state:n===1?'generation_incomplete':'generated_empty',assessment_summary:{expected:3,assessed:3,resolved:n===1?2:3},
  options:['Alpha','Beta','Gamma','Delta'].map((text,i)=>({text,display_letter:'ABCD'[i],base_option_letter:'ABCD'[i],assessment:i?{_src_id:`da:${n}:${i}`,status:n===1&&i===1?'SUPPORTED':n===1&&i===3?'INSUFFICIENT_EVIDENCE':'NO_SUPPORTED_CANDIDATE',reason:`Synthetic ${text}: source comparison reason.`,comparison_evidence:[],unresolved_points:n===1&&i===3?['缺少先行词来源，保持待核']:[]}:null,error_causes:n===1&&i===1?[{relation_src_id:'qc:one',code:'E4.2',name:'来源归属',rationale:'若把不同说话人的信息转归，可能误选Beta。',personal_verification_needed:'需后续学生复述，两段信息分别核对。',evidence:[ev('one',100,600),ev('two',2100,2600)]}]:[]})),
  skills:[],answer_evidence:[],candidate_changes:n===1?[{reference:'diff:one',diff:{semantic_deletion_review_required:true,changes:[{kind:'deleted',option_letter:'C',error_cause_code:'E4.3',before:{rationale:'Earlier synthetic mechanism'},after:null}]}}]:[],
  review_requirements:{primary_skills:[],answer_evidence:[],error_causes:n===1?['qc:one','ce:one','ce:two']:[],distractor_assessments:[1,2,3].map(i=>`da:${n}:${i}`),candidate_changes:n===1?['diff:one']:[]}})
const workflow={workflow_id:wid,revision_id:rid,row_version:7,exam_level:'CET4',exam_year:2025,exam_month:6,paper_set:1,exam_paper_id:null,processing_state:'awaiting_review',content_review_state:'pending',error_review_state:'pending',publication_state:'unpublished',created_at:'2026-11-17T00:00:00Z',updated_at:'2026-11-17T00:01:00Z',task_id:wid,result_hash:hash,document_mode:'text',listening_pages:{paper:[1],answer:[1]},materials:[],current_batch_id:null,is_student_visible:false,
  stages:{final:{task_id:wid,artifact_id:1,artifact_hash:hash,dependency_hash:hash}},review_session_id:sid,review_session_version:1,error_generation_summary:{assessed:6,expected:6,resolved:5,reviewed:0},progress:{stage:'review',completed_count:2,total_count:2,elapsed_ms:12000,checkpoint:null},gates:[],issues:[],allowed_actions:[],usage:{known_usd:'0',reserved_usd:'0',has_unknown_charges:false}}
const wav=Buffer.alloc(44+8000);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(8000,24);wav.writeUInt32LE(16000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(8000,40)
function check(value,message){if(!value)throw Error(message);checks.push(message)}
const browser=await chromium.launch({headless:true,executablePath:process.env.M3_BROWSER_EXECUTABLE})
try{
 for(const [width,height] of [[1440,900],[1280,720]]){
  const context=await browser.newContext({viewport:{width,height}}),page=await context.newPage()
  await page.addInitScript(()=>localStorage.setItem('ssre_access_token','synthetic-v7-token'))
  page.on('pageerror',e=>errors.push(e.message))
  let version=1,saved=[],conflict=false,failedSource=false
  await page.route('**/api/v1/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname
   if(req.method()==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}})
   let data
   if(p==='/api/v1/getInfo')data={user:{user_id:1,username:'synthetic-admin',nickname:'V7技术验证'},roles:['admin'],is_admin:true,permissions:[]}
   else if(p===root+'/capabilities')data={max_upload_bytes:536870912,processing_ready:true,blocked_reason:null}
   else if(p===`${root}/${wid}`)data=failedSource?{...workflow,processing_state:'failed',result_hash:null,reprocess_result_hash:hash,review_session_id:null,stages:{source:workflow.stages.final}}:{...workflow,review_session_version:version}
   else if(p.endsWith('/operations'))data={items:[]}
   else if(p.endsWith('/questions'))data={items:[makeQuestion(1),makeQuestion(2)],total:2,result_hash:hash,next_cursor:null}
   else if(p.endsWith(`/review-sessions/${sid}`))data={row_version:version,items:saved,state:'draft',total:2,result_hash:hash,next_cursor:null}
   else if(p.endsWith('/audio')){mediaRequests.push({path:p,auth:Boolean(req.headers().authorization)});return route.fulfill({status:200,contentType:'audio/wav',body:wav})}
   else if(p.endsWith('/items')&&req.method()==='PATCH'){
    const body=req.postDataJSON();writes.push(body)
    check(body.items[0].distractor_assessments.length===3,`${width}: save covers three assessments`)
    check(body.items[0].candidate_changes.length===1,`${width}: save separately reviews deletion diff`)
    if(conflict)return route.fulfill({status:409,json:{code:409,msg:'Synthetic version conflict',error_code:'VERSION_CONFLICT',data:null}})
    saved=body.items;version++;data={operation_id:rid,workflow_id:wid,revision_id:rid,action:'review_save',state:'succeeded',failure_code:null,result:{session_version:version},created_at:workflow.created_at}
   }else if(p.endsWith('/reprocess-preview')){
    const body=req.postDataJSON();check(body.expected_result_hash===hash,`${width}: failed restart binds frozen source hash`)
    data={plan_hash:hash,sample_valid:false,generation_count:25,review_count:25,affected_question_ids:['q:1','q:2'],reusable_question_ids:[]}
   }else throw Error(`Unexpected request ${req.method()} ${p}`)
   await route.fulfill({status:200,json:{code:200,msg:'Synthetic V7 contract',data}})
  })
  await page.goto(`${base}/admin/listening-papers/processing/${wid}`)
  await page.getByText('第1题审核意见',{exact:true}).waitFor()
  for(const text of ['有支持候选','检查后无支持候选','依据不足待核'])check(await page.getByText(text,{exact:true}).isVisible(),`${width}: ${text} visible`)
  check(await page.getByText('干扰项检查 3 / 3 · 结论完整 2 / 3',{exact:true}).isVisible(),`${width}: resolved and covered counts differ`)
  await page.getByText('错因 E4.2 · 来源归属',{exact:true}).click()
  await page.getByText('个人核验要求：需后续学生复述，两段信息分别核对。',{exact:true}).waitFor()
  for(const label of ['试听证据 0.10—0.60 秒','试听证据 2.10—2.60 秒']){
   await page.getByRole('button',{name:label,exact:true}).click()
   await page.locator('audio').waitFor();await page.waitForFunction(()=>document.querySelector('audio')?.readyState>=1)
   check(Math.abs(await page.locator('audio').evaluate(a=>a.duration)-0.5)<0.01,`${width}: ${label} decodes as separate clip`)
   await page.keyboard.press('Escape')
  }
  await page.getByText('候选删改（含删除，须复核材料理由）',{exact:true}).click()
  await page.getByText('C · E4.3 · deleted',{exact:true}).waitFor()
  await page.getByRole('checkbox',{name:'全选全部题目',exact:true}).check()
  check(await page.getByRole('button',{name:'提交整套审核',exact:true}).isDisabled(),`${width}: unresolved assessment cannot submit`)
  await page.getByLabel('审核意见 / 退回原因',{exact:true}).fill('Synthetic Codex technical opinion, not real audio review')
  await page.getByRole('button',{name:'保存本题意见',exact:true}).click()
  await page.getByText('本题意见已保存到服务器',{exact:true}).waitFor()
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#review-note')?.disabled)
  check((await page.getByLabel('审核意见 / 退回原因',{exact:true}).inputValue()).includes('Synthetic Codex'),`${width}: same-version opinions survive reload`)
  conflict=true;await page.getByLabel('审核意见 / 退回原因',{exact:true}).fill('Retain on version conflict')
  await page.getByRole('button',{name:'保存本题意见',exact:true}).click();await page.getByText('Synthetic version conflict',{exact:false}).first().waitFor()
  check(await page.getByLabel('审核意见 / 退回原因',{exact:true}).inputValue()==='Retain on version conflict',`${width}: conflict preserves local input`)
  await page.getByText('题目与标注（只读）',{exact:true}).scrollIntoViewIfNeeded()
  await page.screenshot({path:path.join(output,`${width}-distractor-review.png`),fullPage:true})
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width}: desktop has no horizontal overflow`)
  check(await page.locator('input:not([type=checkbox]):not([type=radio]),textarea').count()>0,`${width}: review opinion controls remain reachable`)
  failedSource=true;await page.reload()
  await page.getByText('退回后局部重生成',{exact:true}).click()
  check(await page.getByText('本次标注失败，尚无完整结果',{exact:true}).isVisible(),`${width}: failed annotation is not presented as an empty sample`)
  await page.getByLabel('待修复题目',{exact:true}).click()
  await page.getByText('第1题',{exact:true}).last().click();await page.keyboard.press('Escape')
  await page.getByLabel('重生成具体反馈',{exact:true}).fill('Synthetic bounded-failure restart from frozen source')
  await page.getByRole('button',{name:'预览修复范围和小样影响',exact:true}).click()
  check(await page.getByText('本次生成 25 题；最终审核 25 题',{exact:true}).isVisible(),`${width}: restart previews full regeneration and whole-paper review`)
  await page.screenshot({path:path.join(output,`${width}-failed-restart.png`),fullPage:true})
  await context.close()
 }
 check(errors.length===0,'no browser runtime errors')
 check(mediaRequests.length===4&&mediaRequests.every(r=>r.auth),'all four evidence requests authenticate')
 completed=true
}catch(error){errors.push(error.message);throw error}
finally{await browser.close();await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({status:completed&&!errors.length?'PASS':'FAIL',scope:'synthetic technical desktop checks; no real semantic/audio approval',checks,errors,mediaRequests,writes},null,2))}
console.log(JSON.stringify({status:'PASS',checks:checks.length,output}))
