/* 针对 PR12 R1/R2 的浏览器回归。使用独立测试环境，不写数据库。
 * PLAYWRIGHT_MODULE 可指向已有 Playwright 安装，不改变项目依赖锁。
 * WEB_URL / API_URL / ADMIN_PASSWORD 必填；EVIDENCE_DIR 可保存 JSON 和截图。
 */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const WEB = process.env.WEB_URL
const API = process.env.API_URL
const PASSWORD = process.env.ADMIN_PASSWORD
const OUT = process.env.EVIDENCE_DIR
const results = []
if (!WEB || !API || !PASSWORD) throw new Error('WEB_URL / API_URL / ADMIN_PASSWORD 必填')
if (OUT) fs.mkdirSync(OUT, { recursive: true })
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
const wrapped = data => ({ code: 200, msg: '测试响应', data })

async function waitFor(check, message) {
  for (let i = 0; i < 100; i++) {
    if (await check()) return
    await pause(50)
  }
  throw new Error(message)
}

async function main() {
  const response = await fetch(API + '/api/v1/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: process.env.ADMIN_USER || 'admin', password: PASSWORD }),
  })
  assert.equal(response.status, 200)
  const token = (await response.json()).data.token
  const headers = { Authorization: 'Bearer ' + token }
  const list = await fetch(API + '/api/v1/listening-papers', { headers })
  const summary = (await list.json()).data.items[0]
  assert.ok(summary, '至少需要一套试卷')
  const id = summary.exam_paper_id
  const companion = (await (await fetch(API + `/api/v1/admin/listening-papers/${id}/companion`, { headers })).json()).data
  const browser = await chromium.launch({ headless: true })
  async function scenario(name, fn) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    await context.addInitScript(t => localStorage.setItem('ssre_access_token', t), token)
    const page = await context.newPage()
    page.setDefaultTimeout(10000)
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    try {
      const detail = await fn(page)
      assert.deepEqual(errors, [])
      if (OUT) await page.screenshot({ path: path.join(OUT, name + '.png'), fullPage: true })
      results.push({ name, status: 'PASS', detail })
      console.log('PASS', name)
    } catch (error) {
      results.push({ name, status: 'FAIL', error: error.stack })
      console.error('FAIL', name, error.message)
    } finally {
      await context.close()
    }
  }
  try {
    await scenario('R1-reload-select-return-history', async page => {
      await page.goto(WEB + '/admin/listening-papers?level=CET4&year=2025&keep=ok#list')
      await page.getByRole('button', { name: '查看详情', exact: true }).first().waitFor()
      await page.reload()
      await page.getByRole('button', { name: '查看详情', exact: true }).first().waitFor()
      let url = new URL(page.url())
      assert.equal(url.searchParams.has('level'), false)
      assert.equal(url.searchParams.has('year'), false)
      assert.equal(url.searchParams.get('keep'), 'ok')
      assert.equal(url.hash, '#list')
      async function select(index, label) {
        await page.locator('.page-actions .ant-select').nth(index).click()
        await page.locator('.ant-select-item-option-content').getByText(label, { exact: true }).click()
      }
      await select(0, summary.exam_level)
      await select(1, `${summary.exam_year} 年`)
      const expected = new URL(page.url()).search
      assert.equal(new URL(page.url()).searchParams.get('level'), summary.exam_level)
      assert.equal(new URL(page.url()).searchParams.get('year'), String(summary.exam_year))
      for (let i = 0; i < 2; i++) {
        await page.getByRole('button', { name: '查看详情', exact: true }).first().click()
        await page.getByRole('link', { name: '返回题库管理' }).click()
        assert.equal(new URL(page.url()).search, expected)
      }
      await page.getByRole('button', { name: '查看详情', exact: true }).first().click()
      await page.goBack()
      await page.getByRole('button', { name: '查看详情', exact: true }).first().waitFor()
      assert.equal(new URL(page.url()).search, expected)
      await page.reload()
      await page.getByRole('button', { name: '查看详情', exact: true }).first().waitFor()
      assert.equal(new URL(page.url()).searchParams.has('level'), false)
      await select(0, summary.exam_level)
      assert.equal(new URL(page.url()).searchParams.get('level'), summary.exam_level)
      return { url: page.url(), preservedUnrelatedQuery: true, repeatedReloadAndReturn: true }
    })
    for (const failedEndpoint of ['checks', 'companion']) {
      await scenario('R2-first-failure-' + failedEndpoint, async page => {
        let retry = false
        const pending = []
        await page.route(API + '/api/v1/listening-papers', r => r.fulfill({ json: wrapped({ items: [summary] }) }))
        page.on('request', r => {
          if (retry && r.url().endsWith(failedEndpoint === 'checks' ? '/companion' : '/checks')) pending.push(r)
        })
        await page.route(new RegExp(`/api/v1/admin/listening-papers/${id}/(checks|companion)$`), async route => {
          const endpoint = route.request().url().split('/').pop()
          if (!retry || endpoint === failedEndpoint) return route.fulfill({ status: 500, json: { code: 500, msg: '受控失败', data: null } })
          await pause(1800)
          try { await route.fulfill({ json: wrapped(endpoint === 'companion' ? companion : { is_passed: true, issues: [], checked_at: new Date().toISOString() }) }) } catch {}
        })
        await page.goto(WEB + '/admin/listening-papers')
        await page.getByText('获取失败', { exact: true }).first().waitFor()
        retry = true
        await page.locator('tbody').getByRole('button', { name: '重试', exact: true }).first().click()
        await waitFor(() => pending.length === 1, '未观察到同组请求')
        await page.getByText('获取失败', { exact: true }).first().waitFor()
        await waitFor(() => Boolean(pending[0].failure()), '首个失败后同组请求未取消')
        await page.getByRole('menuitem', { name: /首页/ }).click()
        return { cancelled: pending[0].failure(), pageAfterLeaving: page.url() }
      })
    }
    await scenario('R2-retry-recovers-after-failure', async page => {
      let healthy = false
      await page.route(API + '/api/v1/listening-papers', r => r.fulfill({ json: wrapped({ items: [summary] }) }))
      await page.route(new RegExp(`/api/v1/admin/listening-papers/${id}/(checks|companion)$`), route => {
        if (!healthy) return route.fulfill({ status: 500, json: { code: 500, msg: '受控失败', data: null } })
        return route.fulfill({ json: wrapped(route.request().url().endsWith('/companion') ? companion : { is_passed: true, issues: [], checked_at: new Date().toISOString() }) })
      })
      await page.goto(WEB + '/admin/listening-papers')
      await page.getByText('获取失败', { exact: true }).first().waitFor()
      healthy = true
      await page.locator('tbody').getByRole('button', { name: '重试', exact: true }).first().click()
      await waitFor(async () =>
        await page.getByText('获取失败', { exact: true }).count() === 0 &&
        await page.getByText('获取中', { exact: true }).count() === 0,
        '重试恢复后仍显示失败或仍在加载')
      return { recovered: true }
    })
  } finally {
    await browser.close()
    if (OUT) fs.writeFileSync(path.join(OUT, 'list-lifecycle-results.json'), JSON.stringify(results, null, 2))
    if (results.some(r => r.status !== 'PASS')) process.exitCode = 1
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
