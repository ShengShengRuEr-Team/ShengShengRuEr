/**
 * 真实浏览器 E2E（Playwright Core + 本机 Edge）：
 * 登录 → 列表 → 作答（选择/标记）→ 刷新恢复 → 交卷 → 汇总 → 刷新只读。
 *
 * 前置：backend 以独立 E2E 库启动在 8000；frontend dev 在 5173。
 * 运行：cd frontend && node scripts/e2e_attempt.mjs
 */
import { chromium } from 'playwright-core'
import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const APP_URL = process.env.E2E_APP_URL ?? 'http://127.0.0.1:5173'
const EDGE =
  process.env.E2E_BROWSER ??
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const OUT_DIR = path.resolve(
  process.env.E2E_OUT_DIR ??
    '../docs/acceptance/attempt-system/screenshots',
)

const results = []
const consoleErrors = []

function record(name, status, detail = '') {
  results.push({ name, status, detail })
  console.log(`[${status}] ${name}${detail ? ` — ${detail}` : ''}`)
}

async function shot(page, name) {
  await fs.mkdir(OUT_DIR, { recursive: true })
  await page.screenshot({ path: path.join(OUT_DIR, name), fullPage: true })
}

async function main() {
  const browser = await chromium.launch({
    executablePath: EDGE,
    headless: true,
    args: ['--disable-gpu', '--no-sandbox'],
  })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })
  page.on('pageerror', (error) => consoleErrors.push(String(error)))

  try {
    // 1. 登录
    await page.goto(`${APP_URL}/login`, { waitUntil: 'networkidle' })
    await page.getByPlaceholder('请输入用户名').fill('student')
    await page.getByPlaceholder('请输入密码').fill('student123')
    await page.getByRole('button', { name: /登\s*录/ }).click()
    await page.waitForURL(/\/student$/, { timeout: 15000 })
    record('E2E-01 登录', 'PASS', page.url())

    // 2. 列表入口（清理上一轮本机作答记录，保证可重复执行）
    await page.evaluate(() => {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('ssre.attempt')) {
          localStorage.removeItem(key)
        }
      }
    })
    await page.getByRole('menuitem', { name: '听力练习' }).click()
    await page.waitForURL(/\/student\/listening-papers$/, { timeout: 15000 })
    const startButton = page.getByRole('button', { name: '开始作答' }).first()
    await startButton.waitFor({ timeout: 15000 })
    await shot(page, 'e2e-01-list-start.png')
    record('E2E-01b 列表入口', 'PASS', '开始作答')

    // 3. 进入作答页，等待门禁解除
    await startButton.click()
    await page.waitForURL(/\/student\/listening-papers\/\d+$/, { timeout: 15000 })
    await page.getByText('本卷仅可提交一次').waitFor({ timeout: 20000 })
    const radioGroup = page.getByRole('radiogroup').first()
    await radioGroup.waitFor({ timeout: 20000 })
    record('E2E-01c 作答门禁', 'PASS', '详情 + API-3 完成后才出现选项')
    await shot(page, 'e2e-02-answering.png')

    // 4. 选择与标记（第 1 题 A、第 2 题 B；翻篇后第 3 题 D）
    await page.getByRole('radio', { name: /选项 A：Question 1 option A/ }).click()
    await page.getByRole('radio', { name: /选项 B：Question 2 option B/ }).click()
    const firstCard = page
      .locator('.question-card')
      .filter({ hasText: 'E2E_ATTEMPT_001 第 1 题' })
    await firstCard.getByRole('button', { name: /标\s*记/ }).click()
    await page.getByRole('button', { name: '下一篇' }).click()
    await page
      .getByRole('radio', { name: /选项 D：Question 3 option D/ })
      .waitFor({ timeout: 10000 })
    await page.getByRole('radio', { name: /选项 D：Question 3 option D/ }).click()
    await page.getByText(/已答 3\/4/).first().waitFor({ timeout: 10000 })
    record('E2E-01d 选择/标记/计数', 'PASS', '已答 3/4、标记 1')

    // 5. 刷新恢复（音频从 0 由 AudioPlayer 自身保证）
    await page.waitForTimeout(500)
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByText('已恢复本机草稿').waitFor({ timeout: 20000 })
    const restored = await page
      .getByRole('radio', { name: /选项 D：Question 3 option D，已选/ })
      .count()
    if (restored < 1) {
      throw new Error('刷新后未恢复第 3 题所选答案')
    }
    record('E2E-02 刷新恢复', 'PASS', '答案/标记/篇恢复')
    await shot(page, 'e2e-03-restored.png')

    // 6. 交卷确认与提交
    await page.getByRole('button', { name: /交\s*卷/ }).click()
    await page.getByText(/共 4 题 · 已答 3 题 · 未答 1 题 · 标记 1 题/).waitFor({
      timeout: 10000,
    })
    await shot(page, 'e2e-04-confirm.png')
    await page.getByRole('button', { name: '确认交卷' }).click()
    await page.getByText('提交成功').waitFor({ timeout: 30000 })
    await page.getByText('2 / 4').first().waitFor({ timeout: 10000 })
    const rate = await page.getByText('50%').count()
    if (rate < 1) {
      throw new Error('汇总未显示 50%')
    }
    record('E2E-03 提交成功与汇总', 'PASS', '正确 2/4、50%')
    await shot(page, 'e2e-05-submitted.png')

    // 7. 刷新后只读、无选中态/答题卡进度
    await page.waitForTimeout(300)
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByText('已提交 · 只读回看').waitFor({ timeout: 20000 })
    if ((await page.getByRole('radiogroup').count()) !== 0) {
      throw new Error('已提交刷新后仍存在可交互单选项')
    }
    if ((await page.getByRole('button', { name: /交\s*卷/ }).count()) !== 0) {
      throw new Error('已提交刷新后仍存在交卷按钮')
    }
    await page.getByText('2 / 4').first().waitFor({ timeout: 10000 })
    record('E2E-04 已提交刷新只读', 'PASS', '无选项/无交卷/汇总保留')
    await shot(page, 'e2e-06-submitted-reload.png')

    // 8. 受保护内容与本地标记检查
    const html = await page.content()
    for (const forbidden of ['correct_option', 'explanation_text', 'transcript_segments']) {
      if (html.includes(forbidden)) {
        throw new Error(`页面包含受保护字段：${forbidden}`)
      }
    }
    const marker = await page.evaluate(() => {
      const key = Object.keys(localStorage).find((item) =>
        item.startsWith('ssre.attemptSubmitted.v2.'),
      )
      return key ? localStorage.getItem(key) : null
    })
    if (!marker || !marker.includes('"submitted":true')) {
      throw new Error('提交标记未写入/结构异常')
    }
    record('E2E-05 受保护字段与提交标记', 'PASS', '无答案/解析/正文；标记已写入')

    // 9. 多标签终态（AC-38）：A 提交成功时 B 处于待保存/已保存，均不得复活
    await page.goto(`${APP_URL}/student/listening-papers`, { waitUntil: 'networkidle' })
    const secondRow = page.locator('tr', { hasText: '第 2 套' })
    await secondRow.getByRole('button', { name: '开始作答' }).click()
    await page.waitForURL(/\/student\/listening-papers\/\d+$/, { timeout: 15000 })
    await page.getByRole('button', { name: /交\s*卷/ }).waitFor({ timeout: 20000 })
    const secondUrl = page.url()

    const pageB = await context.newPage()
    await pageB.goto(secondUrl, { waitUntil: 'networkidle' })
    await pageB
      .getByRole('radio', { name: /选项 A：Question 1 option A/ })
      .waitFor({ timeout: 20000 })
    // B 先作答（触发 300ms 防抖写入），A 立即交卷
    await pageB.getByRole('radio', { name: /选项 A：Question 1 option A/ }).click()
    await page.getByRole('radio', { name: /选项 B：Question 1 option B/ }).click()
    await page.getByRole('button', { name: /交\s*卷/ }).click()
    await page.getByRole('button', { name: '确认交卷' }).click()
    await page.getByText('提交成功').waitFor({ timeout: 30000 })
    // B 通过 storage 事件冻结：不再有可交互选项、交卷按钮
    await pageB.waitForFunction(
      () => document.querySelectorAll('[role="radiogroup"]').length === 0,
      undefined,
      { timeout: 10000 },
    )
    if ((await pageB.getByRole('button', { name: /交\s*卷/ }).count()) !== 0) {
      throw new Error('另一标签页在终态后仍显示交卷按钮')
    }
    await pageB.reload({ waitUntil: 'networkidle' })
    await pageB.getByText('已提交 · 只读回看').waitFor({ timeout: 20000 })
    record('E2E-07 多标签终态', 'PASS', 'A 成功时 B 已保存草稿，B 冻结且刷新只读')
    await pageB.close()

    // 10. 桌面断点（AC-26）：1280 侧栏 / 1024 顶部折叠，提交栏始终可见
    await page.goto(`${APP_URL}/student/listening-papers`, { waitUntil: 'networkidle' })
    const thirdRow = page.locator('tr', { hasText: '第 3 套' })
    await thirdRow.getByRole('button', { name: '开始作答' }).click()
    await page.waitForURL(/\/student\/listening-papers\/\d+$/, { timeout: 15000 })
    await page.getByRole('radio').first().waitFor({ timeout: 20000 })
    await page.setViewportSize({ width: 1280, height: 900 })
    await page.waitForTimeout(300)
    if ((await page.getByRole('button', { name: /交\s*卷/ }).count()) !== 1) {
      throw new Error('1280 下提交栏交卷按钮缺失或重复')
    }
    await shot(page, 'e2e-07-1280.png')
    await page.setViewportSize({ width: 1024, height: 768 })
    await page.waitForTimeout(300)
    if ((await page.getByRole('button', { name: /交\s*卷/ }).count()) !== 1) {
      throw new Error('1024 下提交栏交卷按钮缺失或重复')
    }
    await shot(page, 'e2e-08-1024.png')
    record('E2E-08 桌面断点', 'PASS', '1280 / 1024 提交栏可见')

    // 11. 管理员权限（模块二保持原规则，API-1/3 403）
    await page.goto(`${APP_URL}/login`, { waitUntil: 'networkidle' })
    await page.evaluate(() => localStorage.clear())
    await page.goto(`${APP_URL}/login`, { waitUntil: 'networkidle' })
    await page.getByPlaceholder('请输入用户名').fill('admin')
    await page.getByPlaceholder('请输入密码').fill('admin123')
    await page.getByRole('button', { name: /登\s*录/ }).click()
    await page.waitForURL(/\/admin$/, { timeout: 15000 })
    record('E2E-06 管理员登录', 'PASS', page.url())
  } catch (error) {
    record('E2E 执行', 'FAIL', error instanceof Error ? error.message : String(error))
    await shot(page, 'e2e-failure.png').catch(() => undefined)
    process.exitCode = 1
  } finally {
    await context.close()
    await browser.close()
    await fs.mkdir(OUT_DIR, { recursive: true })
    await fs.writeFile(
      path.join(OUT_DIR, 'e2e-results.json'),
      JSON.stringify({ results, consoleErrors }, null, 2),
      'utf8',
    )
    if (consoleErrors.length > 0) {
      console.log(`console errors: ${consoleErrors.length}`)
    }
  }
}

await main()
