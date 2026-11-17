// Run only against an explicitly supplied isolated instance with approved papers.
// Does not upload, generate candidates, or create human review approvals.
import { createRequire } from 'node:module'
import fs from 'node:fs/promises'
import path from 'node:path'

const { chromium } = createRequire(new URL('../frontend/package.json', import.meta.url))('playwright-core')
const app = process.env.M3_E2E_APP_URL
if (!app || process.env.M3_E2E_ISOLATED !== '1') {
  throw Error('Set M3_E2E_APP_URL and M3_E2E_ISOLATED=1 for the disposable instance')
}
const paperIds = (process.env.M3_E2E_PAPER_IDS || '').split(',').map(Number).filter(id => id > 0)
if (!paperIds.length) throw Error('Set M3_E2E_PAPER_IDS to the approved real paper IDs')
const output = path.resolve(process.env.M3_BROWSER_OUTPUT || 'backend/var/verification/integrated-attempt-browser')
await fs.mkdir(output, { recursive: true })
const checks = [], results = [], errors = []
function check(condition, name) {
  if (!condition) throw Error(name)
  checks.push(name)
}
const browser = await chromium.launch({ headless: true, executablePath: process.env.M3_BROWSER_EXECUTABLE })
let activePage
try {
  const adminContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const logged = await adminContext.request.post(`${app}/api/v1/login`, {
    data: { username: process.env.M3_E2E_ADMIN || 'admin', password: process.env.M3_E2E_ADMIN_PASSWORD || 'admin123' },
  })
  check(logged.status() === 200, 'administrator authenticates against integrated API')
  const adminHeaders = { Authorization: `Bearer ${(await logged.json()).data.token}` }
  const adminPage = await adminContext.newPage()
  await adminPage.addInitScript(token => localStorage.setItem('ssre_access_token', token), adminHeaders.Authorization.slice(7))
  adminPage.on('pageerror', error => errors.push(error.message))
  const expected = new Map()
  for (const id of paperIds) {
    const companion = await adminContext.request.get(`${app}/api/v1/admin/listening-papers/${id}/companion`, { headers: adminHeaders })
    check(companion.status() === 200, `paper ${id}: current formal content is readable`)
    const paper = (await companion.json()).data
    const annotation = await adminContext.request.get(`${app}/api/v1/admin/listening-papers/${id}/annotations?expected_batch_id=${paper.batch_id}&limit=100`, { headers: adminHeaders })
    check(annotation.status() === 200, `paper ${id}: annotation API succeeds`)
    const annotations = (await annotation.json()).data
    check(annotations.annotation_state === 'approved' && annotations.items.length === 25, `paper ${id}: 25 reviewed annotations remain readable`)
    check(paper.passages.length === 8 && paper.passages.flatMap(p => p.questions).length === 25, `paper ${id}: 8 passages and 25 questions`)
    expected.set(id, paper)
    activePage = adminPage
    await adminPage.goto(`${app}/admin/listening-papers/${id}`)
    await adminPage.getByText('当前正式批次标注（管理员）', { exact: true }).waitFor()
    await adminPage.getByText('主要技能', { exact: false }).first().waitFor()
    await adminPage.screenshot({ path: path.join(output, `admin-paper-${id}.png`), fullPage: true })
  }

  for (const [width, height] of [[1440, 900], [1280, 720]]) {
    const context = await browser.newContext({ viewport: { width, height } })
    const page = await context.newPage()
    activePage = page
    page.on('pageerror', error => errors.push(error.message))
    await page.goto(`${app}/login`)
    await page.getByPlaceholder('请输入用户名').fill(`${process.env.M3_E2E_STUDENT_PREFIX || 'integration_student_'}${width}`)
    await page.getByPlaceholder('请输入密码').fill(process.env.M3_E2E_STUDENT_PASSWORD || 'attempt123')
    await page.getByRole('button', { name: /登\s*录/ }).click()
    await page.waitForURL(/\/student$/)
    const token = await page.evaluate(() => localStorage.getItem('ssre_access_token'))
    const studentHeaders = { Authorization: `Bearer ${token}` }
    check(Boolean(token), `${width}: student login through browser`)
    for (const id of paperIds) {
      const paper = expected.get(id)
      // Exercise independent visibility; all mutations target the disposable DB.
      const changeVisibility = async action => {
        const r = await adminContext.request.post(`${app}/api/v1/admin/listening-papers/${id}/visibility`, {
          headers: adminHeaders, data: { action, expected_batch_id: paper.batch_id, reason: 'Isolated integrated browser acceptance' },
        })
        check(r.status() === 200, `${width} paper ${id}: visibility ${action}`)
      }
      await changeVisibility('cancel')
      for (const suffix of ['', '/audio', '/attempt-status']) {
        const hidden = await context.request.get(`${app}/api/v1/listening-papers/${id}${suffix}`, { headers: studentHeaders })
        check(hidden.status() === 404, `${width} paper ${id}: hidden ${suffix || 'detail'} denied`)
      }
      await changeVisibility('confirm')
      const statusBefore = await context.request.get(`${app}/api/v1/listening-papers/${id}/attempt-status`, { headers: studentHeaders })
      check(statusBefore.status() === 200 && !(await statusBefore.json()).data.submitted, `${width} paper ${id}: fresh student status`)
      const detail = await context.request.get(`${app}/api/v1/listening-papers/${id}`, { headers: studentHeaders })
      const body = (await detail.json()).data
      for (const passage of body.passages) {
        for (const question of passage.questions) {
          check(Object.keys(question).sort().join(',') === 'options,question_id,question_no,question_text', `${width} paper ${id} q${question.question_no}: pre-answer field whitelist`)
        }
      }
      const forbidden = await context.request.get(`${app}/api/v1/admin/listening-papers/${id}/annotations`, { headers: studentHeaders })
      check(forbidden.status() === 403, `${width} paper ${id}: student cannot read annotations`)
      const audio = await context.request.get(`${app}/api/v1/listening-papers/${id}/audio`, { headers: { ...studentHeaders, Range: 'bytes=0-4095' } })
      check([200, 206].includes(audio.status()) && (await audio.body()).length > 0, `${width} paper ${id}: authenticated source audio readable`)
      await page.goto(`${app}/student/listening-papers`)
      await page.getByRole('button', { name: '开始作答' }).first().waitFor()
      const row = page.locator('tr').filter({ hasText: `${paper.exam_year} 年 ${paper.exam_month} 月 · 第 ${paper.paper_set} 套` })
      const entry = row.getByRole('button', { name: '开始作答' })
      check(await entry.count() === 1, `${width} paper ${id}: student list exposes start entry`)
      await entry.click()
      await page.getByText('本卷仅可提交一次；提交后不可修改，可只读回看题目与汇总。', { exact: true }).waitFor()
      await page.getByRole('radiogroup').first().waitFor()
      const questions = paper.passages.flatMap(p => p.questions)
      const first = questions[0]
      await page.getByRole('radio', { name: new RegExp(`^选项 ${first.correct_option}：`) }).first().click()
      await page.locator('.question-card').first().getByRole('button', { name: /标\s*记/ }).click()
      await page.waitForFunction(() => Object.keys(localStorage).some(k => k.startsWith('ssre.attemptDraft.v2.')))
      await page.reload()
      await page.getByText('已恢复本机草稿', { exact: true }).waitFor()
      check(await page.getByRole('radio', { checked: true }).count() === 1, `${width} paper ${id}: selected answer restored after reload`)
      for (let i = 0; i < paper.passages.length; i++) {
        const passage = paper.passages[i]
        if (i > 0) await page.getByRole('button', { name: '下一篇', exact: true }).click()
        for (const q of passage.questions) {
          const card = page.locator('.question-card').filter({ has: page.locator(`#question-${q.question_id}-title`) })
          await card.getByRole('radio', { name: new RegExp(`^选项 ${q.correct_option}：`) }).click()
        }
      }
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${width} paper ${id}: no horizontal overflow during answering`)
      await page.screenshot({ path: path.join(output, `${width}-paper-${id}-answered.png`), fullPage: true })
      const pendingResponse = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`/listening-papers/${id}/attempts`))
      await page.getByRole('button', { name: /交\s*卷/ }).click()
      await page.getByRole('dialog').getByText(/共 25 题 · 已答 25 题 · 未答 0 题/).waitFor()
      await page.getByRole('button', { name: '确认交卷', exact: true }).click()
      const submitted = await pendingResponse
      check(submitted.status() === 200, `${width} paper ${id}: browser submits all questions`)
      const summary = (await submitted.json()).data
      check(summary.question_count === 25 && summary.correct_count === 25 && summary.correct_rate === 100, `${width} paper ${id}: all declared correct choices grade correctly`)
      check(summary.practice_score.available && summary.practice_score.value === 249, `${width} paper ${id}: standard 25-question score is 249`)
      await page.getByText('已提交 · 只读回看', { exact: true }).waitFor()
      const retry = await context.request.post(submitted.url(), { headers: { ...studentHeaders, 'Idempotency-Key': submitted.request().headers()['idempotency-key'] }, data: submitted.request().postDataJSON() })
      check(retry.status() === 200 && (await retry.json()).data.attempt_code === summary.attempt_code, `${width} paper ${id}: same-key retry returns original summary`)
      await page.reload()
      await page.getByText('已提交 · 只读回看', { exact: true }).waitFor()
      check(await page.getByRole('radio').count() === 0 && await page.getByRole('button', { name: /交\s*卷/ }).count() === 0, `${width} paper ${id}: submitted page remains read only after reload`)
      const after = await context.request.get(`${app}/api/v1/listening-papers/${id}/attempt-status`, { headers: studentHeaders })
      const state = (await after.json()).data
      check(state.submitted && state.attempt_count === 1 && state.latest_attempt.attempt_code === summary.attempt_code, `${width} paper ${id}: authoritative status has one attempt`)
      await page.screenshot({ path: path.join(output, `${width}-paper-${id}-submitted.png`), fullPage: true })
      results.push({ width, height, paper_id: id, batch_id: paper.batch_id, question_count: summary.question_count, correct_count: summary.correct_count, practice_score: summary.practice_score, attempt_code: summary.attempt_code })
    }
    await context.close()
  }
  check(errors.length === 0, 'no browser runtime errors')
} catch (error) {
  errors.push(String(error.stack || error))
  if (activePage && !activePage.isClosed()) await activePage.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {})
} finally {
  await browser.close()
  const report = { status: errors.length ? 'FAIL' : 'PASS', scope: 'existing approved real papers on an isolated snapshot; no new OCR, generation or human approval', checks, results, errors }
  await fs.writeFile(path.join(output, 'summary.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify({ status: report.status, assertions: checks.length, results, errors, output }))
  if (errors.length) process.exitCode = 1
}
