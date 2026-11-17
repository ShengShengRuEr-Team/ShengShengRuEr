// Desktop contract/interaction checks with explicit synthetic API responses.
import { createRequire } from 'node:module'
import fs from 'node:fs/promises'
import path from 'node:path'
const require = createRequire(process.env.M3_PLAYWRIGHT_PACKAGE)
const {chromium} = require('playwright')
const output=path.resolve(process.env.M3_BROWSER_OUTPUT || 'backend/var/verification/browser')
await fs.mkdir(output,{recursive:true})
const root='/api/v1/admin/processing-workflows',wid='11111111-1111-4111-8111-111111111111',rid='22222222-2222-4222-8222-222222222222'
const hash='a'.repeat(64),session='33333333-3333-4333-8333-333333333333'
const summary={workflow_id:wid,revision_id:rid,row_version:7,exam_level:'CET4',exam_year:2025,exam_month:6,paper_set:1,exam_paper_id:null,
  processing_state:'awaiting_review',content_review_state:'pending',error_review_state:'pending',publication_state:'unpublished',created_at:'2026-11-16T00:00:00Z',updated_at:'2026-11-16T00:01:00Z'}
const workflow={...summary,task_id:wid,result_hash:hash,document_mode:'text',listening_pages:{paper:[1],answer:[1]},
  materials:['paper','answer','audio'].map((kind,index)=>({kind,upload_id:wid,upload_version:1,state:'ready',material_id:index+1,lease_expired:false,failure_code:null,filename:`synthetic-${kind}.${kind==='audio'?'wav':'pdf'}`})),
  current_batch_id:null,is_student_visible:false,stages:{source:{task_id:wid,artifact_id:1,artifact_hash:hash,dependency_hash:hash},final:{task_id:wid,artifact_id:2,artifact_hash:hash,dependency_hash:hash}},
  review_session_id:session,review_session_version:1,progress:{stage:'review',completed_count:2,total_count:2,elapsed_ms:12000,checkpoint:null},gates:[],issues:[],
  allowed_actions:[{action:'start',enabled:false},{action:'reserve_upload',enabled:false}],usage:{known_usd:'0.002',reserved_usd:'0',has_unknown_charges:false}}
const question=(n)=>({question_src_id:`q:${n}`,question_no:n,question_text:'What is the correct answer?',explanation_text:'Synthetic source explicitly states Alpha.',correct_option_base:'A',correct_option_display:'A',generation_state:'generated_empty',
  options:['Alpha','Beta','Gamma','Delta'].map((text,i)=>({display_letter:'ABCD'[i],base_option_letter:'ABCD'[i],text,error_causes:[]})),skills:[],answer_evidence:[],review_requirements:{primary_skills:[],answer_evidence:[],error_causes:[]}})
const browser=await chromium.launch({headless:true,executablePath:process.env.M3_BROWSER_EXECUTABLE})
const checks=[],errors=[],requests=[]
function check(value,label){if(!value)throw Error(label);checks.push(label)}
try {
  for(const [width,height] of [[1440,900],[1280,720]]) {
    const context=await browser.newContext({viewport:{width,height}});const page=await context.newPage()
    await page.addInitScript(()=>localStorage.setItem('ssre_access_token','synthetic-browser-token'))
    page.on('pageerror',error=>errors.push(error.message))
    let sessionVersion=1,createKey=null,createCount=0,unknownRetry=false,retryCount=0,correcting=false,sourceIssue=false
    await page.route('**/api/v1/**',async route=>{
      const req=route.request(),url=new URL(req.url()),pathname=url.pathname
      if(req.method()==='OPTIONS'){await route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}});return}
      requests.push({method:req.method(),path:pathname})
      let data=null
      if(pathname==='/api/v1/getInfo')data={user:{user_id:1,username:'synthetic-admin',nickname:'交互验证'},roles:['admin'],is_admin:true,permissions:[]}
      else if(pathname===root+'/capabilities')data={max_upload_bytes:536870912,processing_ready:true,blocked_reason:null}
      else if(pathname===root&&req.method()==='GET')data={items:[sourceIssue?{...summary,processing_state:'failed',source_check_required:true}:summary],next_cursor:null}
      else if(pathname===root&&req.method()==='POST'){
        createCount++;createKey=req.headers()['idempotency-key'];
        await route.fulfill({status:504,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify({code:504,msg:'Synthetic lost response after commit',data:null})});return
      }
      else if(pathname===root+'/operations/by-key'){
        check(url.searchParams.get('idempotency_key')===createKey,'recovery queries the original operation key')
        data={operation_id:wid,workflow_id:wid,revision_id:rid,action:'create',state:'succeeded',failure_code:null,result:{},created_at:summary.created_at}
      }
      else if(pathname===`${root}/${wid}`)data=sourceIssue?{...workflow,processing_state:'failed',progress:{stage:'assemble',description:'处理失败，请查看问题记录',completed_count:0,total_count:null,active:false,elapsed_ms:12000},issues:[{code:'ASSEMBLY_ANSWER_UNRESOLVED',message:'第1题尚未从解析中确认答案',retryable:false},{code:'PROCESSING_FAILED',message:'处理失败',retryable:false}]}:correcting?{...workflow,processing_state:'running',progress:{stage:'annotate',description:'生成整套技能、答案证据和错因标注',completed_count:9,total_count:25,unit:'题',active:true,elapsed_ms:12000,current_item:'第10题，证据校验未通过，自动纠正 1/2',checkpoint:'workflow_annotation_progress'}}:unknownRetry?{...workflow,processing_state:'failed',usage:{known_usd:'0.002',reserved_usd:'0.02',has_unknown_charges:true}}:workflow
      else if(pathname.endsWith('/operations'))data={items:unknownRetry||sourceIssue?[{operation_id:wid,workflow_id:wid,revision_id:rid,action:'continue',state:'failed',failure_code:sourceIssue?'ASSEMBLY_ANSWER_UNRESOLVED':'LLM_TRANSPORT',result:{stage:sourceIssue?'assemble':'annotate_sample'},created_at:summary.created_at}]:[]}
      else if(pathname.endsWith('/retries')){retryCount++;const body=req.postDataJSON();check(body.retry_of_operation_id===wid&&body.expected_workflow_version===7,'retry retains failed operation and version');check(Boolean(req.headers()['idempotency-key']),'retry has an idempotency key');data={operation_id:rid,workflow_id:wid,revision_id:rid,action:'retry',state:'accepted',failure_code:null,result:{stage:'annotate_sample'},created_at:summary.created_at}}
      else if(pathname.endsWith('/questions'))data={items:[question(1),question(2)],total:2,result_hash:hash,next_cursor:null}
      else if(pathname.endsWith(`/review-sessions/${session}`))data={row_version:sessionVersion,items:[],result_hash:hash,state:'draft',total:2,next_cursor:null}
      else if(pathname.endsWith('/items')){const body=req.postDataJSON();check(Boolean(req.headers()['idempotency-key']),'review save carries original operation key');check(body.expected_result_hash===hash,'review save binds immutable final result');sessionVersion++;
        data={operation_id:wid,workflow_id:wid,revision_id:rid,action:'review_save',state:'succeeded',failure_code:null,result:{session_version:sessionVersion},created_at:summary.created_at}}
      else if(pathname==='/api/v1/listening-papers')data=[]
      else throw Error(`Unexpected synthetic API request: ${req.method()} ${pathname}`)
      await route.fulfill({status:200,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify({code:200,msg:'Synthetic contract response',data})})
    })
    const base=process.env.M3_BROWSER_URL||'http://127.0.0.1:5199'
    for(const [name,url,ready] of [
      ['new','/admin/listening-papers/processing/new','创建材料处理任务'],
      ['list','/admin/listening-papers/processing','处理任务与待审核'],
      ['review',`/admin/listening-papers/processing/${wid}`,'第1题审核意见'],
    ]){
      await page.goto(base+url);await page.getByText(ready,{exact:true}).waitFor()
      if(!process.env.M3_BROWSER_NO_SCREENSHOTS)await page.screenshot({path:path.join(output,`${width}-${name}.png`),fullPage:true})
      check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width} ${name}: no horizontal overflow`)
    }
    check(await page.getByRole('button',{name:'正式入库并激活',exact:true}).isDisabled(),`${width}: incomplete review cannot publish`)
    check(await page.getByRole('button',{name:'提交整套审核',exact:true}).isDisabled(),`${width}: unconfirmed audio cannot submit`)
    await page.getByLabel('审核意见 / 退回原因',{exact:true}).fill('Synthetic unsaved opinion one')
    await page.getByLabel('跳转题目').click();await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter')
    await page.getByText('第2题审核意见',{exact:true}).waitFor()
    await page.getByLabel('审核意见 / 退回原因',{exact:true}).fill('Synthetic unsaved opinion two')
    await page.getByRole('button',{name:'保存本题意见',exact:true}).click()
    await page.getByText('本题意见已保存到服务器',{exact:true}).waitFor()
    const changes=await page.evaluate(()=>JSON.parse(localStorage.getItem(Object.keys(localStorage).find(key=>key.startsWith('m3-review:')))).drafts)
    check(changes['q:1']?.note==='Synthetic unsaved opinion one'&&!changes['q:2'],`${width}: saving one question preserves other unsaved opinions`)
    check(await page.getByRole('button',{name:'提交整套审核',exact:true}).isDisabled(),`${width}: unsaved opinions still block full submission`)
    // A committed command whose HTTP response is lost must be recovered by key.
    await page.evaluate(()=>{for(const key of Object.keys(localStorage))if(key.startsWith('m3-review:'))localStorage.removeItem(key)})
    await page.goto(base+`/admin/listening-papers/processing/${wid}`);await page.getByText('第1题审核意见',{exact:true}).waitFor()
    await page.goto(base+'/admin/listening-papers/processing/new')
    await page.getByRole('button',{name:'创建并上传材料',exact:true}).click()
    await page.getByText('有一项操作尚未核对结果',{exact:true}).waitFor()
    await page.waitForTimeout(300)
    check(await page.getByRole('button').filter({hasText:'创建并上传材料'}).isDisabled(),`${width}: lost create response blocks a new key`)
    await page.getByRole('button',{name:'查询原操作',exact:true}).click()
    await page.getByText('第1题审核意见',{exact:true}).waitFor()
    check(createCount===1,`${width}: recovering creation does not create a second workflow`)
    sourceIssue=true
    await page.reload()
    await page.getByText('来源识别尚未完整，等待核对或重新识别',{exact:true}).waitFor()
    check(await page.getByRole('button',{name:'重新识别来源',exact:true}).isEnabled(),`${width}: unresolved source offers explicit recognition retry`)
    check(await page.locator('.ant-alert-warning').count()===1,`${width}: unresolved source uses one warning`)
    check(await page.locator('.ant-alert-error').count()===0,`${width}: unresolved source is not a runtime error`)
    check(!(await page.locator('body').innerText()).includes('PROCESSING_FAILED'),`${width}: generic failure does not duplicate source warning`)
    check(await page.getByText('待核对',{exact:true}).isVisible(),`${width}: source progress is waiting, not completed`)
    check(await page.getByRole('button',{name:'正式入库并激活',exact:true}).isDisabled(),`${width}: unresolved source cannot publish`)
    if(!process.env.M3_BROWSER_NO_SCREENSHOTS)await page.screenshot({path:path.join(output,`${width}-source-unresolved.png`),fullPage:true})
    await page.goto(base+'/admin/listening-papers/processing')
    await page.getByText('待核对来源识别',{exact:true}).waitFor()
    check(await page.locator('.ant-tag-warning').count()===1,`${width}: list shows source attention status`)
    sourceIssue=false
    correcting=true
    await page.goto(base+`/admin/listening-papers/processing/${wid}`)
    await page.getByText('正在处理：第10题，证据校验未通过，自动纠正 1/2 · 9 / 25 题',{exact:true}).waitFor()
    check(await page.getByText('36%',{exact:true}).isVisible(),`${width}: correction attempts do not inflate the percentage`)
    const clock=page.getByLabel('本次任务用时',{exact:true}),beforeClock=await clock.innerText()
    await page.waitForTimeout(1200)
    check(await clock.innerText()!==beforeClock,`${width}: elapsed timer continues during evidence correction`)
    check(!(await page.locator('body').innerText()).includes('本次任务用时（已暂停）'),`${width}: correction stays active`)
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width}: correction message has no horizontal overflow`)
    if(!process.env.M3_BROWSER_NO_SCREENSHOTS)await page.screenshot({path:path.join(output,`${width}-evidence-correction.png`),fullPage:true})
    correcting=false
    unknownRetry=true
    await page.reload();await page.getByText('有未确认计费',{exact:false}).waitFor()
    const retry=page.getByRole('button',{name:'重试失败阶段',exact:true})
    check(await retry.isEnabled(),`${width}: unknown charges do not disable explicit retry`)
    await retry.click();await page.getByText('操作已受理，状态以服务器记录为准',{exact:true}).waitFor()
    check(retryCount===1,`${width}: explicit retry sends only one command`)
    check((await page.locator('body').innerText()).includes('预留 $0.02'),`${width}: retry preserves unknown fee indicator`)
    await context.close()
  }
  check(errors.length===0,'no browser runtime errors')
  check(!requests.some(req=>req.path.endsWith('/start')||req.path.endsWith('/continue')||req.path.endsWith('/publish')),'reading and polling issue no processing commands')
  await fs.writeFile(path.join(output,'summary.json'),JSON.stringify({scope:'synthetic desktop UI contracts, not real-material acceptance',status:'PASS',checks,errors},null,2))
  console.log(JSON.stringify({status:'PASS',checks:checks.length,output}))
} finally {await browser.close()}
