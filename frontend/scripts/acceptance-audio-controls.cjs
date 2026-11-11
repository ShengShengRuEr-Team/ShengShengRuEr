// 鼠标拖动真实滑块并核对 HTMLAudioElement；不写业务数据。
// WEB_URL / API_URL / STUDENT_PASSWORD / ADMIN_PASSWORD 必填。
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const WEB = process.env.WEB_URL
const API = process.env.API_URL
const OUT = process.env.EVIDENCE_DIR
const baseline = process.argv.includes('--baseline')
const results = []
if (!WEB || !API || !process.env.STUDENT_PASSWORD || !process.env.ADMIN_PASSWORD) throw new Error('缺少验收环境参数')
if (OUT) fs.mkdirSync(OUT, { recursive: true })

async function main() {
  const tokens = {}
  for (const role of ['student', 'admin']) {
    const response = await fetch(API + '/api/v1/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: process.env[role.toUpperCase() + '_USER'] || role, password: process.env[role.toUpperCase() + '_PASSWORD'] }),
    })
    assert.equal(response.status, 200)
    tokens[role] = (await response.json()).data.token
  }
  const browser = await chromium.launch({ headless: true })
  try {
    const scenarios = baseline ? [['student', 1196]] : [['student', 1196], ['student', 1440], ['student', 901], ['admin', 1196], ['student', 390]]
    for (const [role, width] of scenarios) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } })
      await context.addInitScript(token => localStorage.setItem('ssre_access_token', token), tokens[role])
      const page = await context.newPage()
      page.setDefaultTimeout(20000)
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      let audioRequests = 0
      page.on('request', request => { if (request.url().endsWith('/audio')) audioRequests++ })
      const name = `${role}-${width}`
      let measured = {}
      try {
        await page.goto(WEB + `/${role}/listening-papers/1`)
        if (role === 'admin') await page.getByRole('button', { name: /试听音频/ }).click()
        await page.waitForFunction(() => document.querySelector('audio')?.readyState >= 1)
        const audio = page.locator('audio')
        const volume = page.locator('.player-volume')
        if (width > 900) {
          const rail = volume.locator('.ant-slider')
          const handle = volume.locator('[role="slider"]')
          const box = await rail.boundingBox()
          measured = { volumeSliderWidth: box?.width }
          if (OUT) await page.screenshot({ path: path.join(OUT, name + '-before-drag.png'), fullPage: true })
          assert.ok(box && box.width >= 60, '音量滑轨宽度不足，无法鼠标拖动：' + JSON.stringify(box))
          const start = await handle.boundingBox()
          await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2)
          await page.mouse.down()
          await page.mouse.move(box.x + box.width * 0.25, box.y + box.height / 2, { steps: 12 })
          await page.mouse.up()
          await page.waitForFunction(() => Math.abs(document.querySelector('audio').volume - 0.25) <= 0.06)
          measured.draggedVolume = await audio.evaluate(element => element.volume)
          assert.ok(Math.abs(Number(await handle.getAttribute('aria-valuenow')) - measured.draggedVolume) < 0.01)
          await handle.focus()
          await handle.press('Home')
          await page.waitForFunction(() => document.querySelector('audio').volume === 0)
          await handle.press('ArrowRight')
          await page.waitForFunction(() => Math.abs(document.querySelector('audio').volume - 0.05) < 0.001)
          await handle.press('End')
          await page.waitForFunction(() => document.querySelector('audio').volume === 1)
          assert.equal(await handle.getAttribute('aria-label'), '音量')
          measured.keyboardMinMax = '0 / 0.05 / 1'
        } else {
          assert.equal(await volume.isVisible(), false)
        }
        const before = audioRequests
        const track = page.locator('.player-track')
        const trackHandle = track.locator('[role="slider"]')
        const box = await track.boundingBox()
        const start = await trackHandle.boundingBox()
        const duration = await audio.evaluate(element => element.duration)
        await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2)
        await page.mouse.down()
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 })
        await page.mouse.up()
        await page.waitForFunction(expected => Math.abs(document.querySelector('audio').currentTime - expected) < 3, duration / 2)
        measured.seekTime = await audio.evaluate(element => element.currentTime)
        measured.expectedSeekTime = duration / 2
        assert.equal(audioRequests, before, '拖动导致重新下载音频')
        assert.deepEqual(errors, [])
        if (OUT) await page.screenshot({ path: path.join(OUT, name + '-after-drag.png'), fullPage: true })
        results.push({ name, status: 'PASS', ...measured, pageErrors: errors, additionalAudioRequests: audioRequests - before })
        console.log('PASS', name, JSON.stringify(measured))
      } catch (error) {
        results.push({ name, status: 'FAIL', ...measured, error: error.stack })
        console.error('FAIL', name, error.message)
      } finally {
        await context.close()
      }
    }
  } finally {
    await browser.close()
    if (OUT) fs.writeFileSync(path.join(OUT, baseline ? 'baseline-results.json' : 'results.json'), JSON.stringify(results, null, 2))
    if (results.some(result => result.status !== 'PASS')) process.exitCode = 1
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
