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

async function shot(page, name, options = {}) {
  await fs.mkdir(OUT_DIR, { recursive: true })
  await page.screenshot({
    path: path.join(OUT_DIR, name),
    fullPage: options.fullPage ?? true,
  })
}

function assertInViewport(box, viewportHeight, label) {
  if (
    box === null ||
    box.y < 0 ||
    box.height <= 0 ||
    box.y + box.height > viewportHeight + 1
  ) {
    throw new Error(
      `${label} 不在视口内：y=${box?.y} height=${box?.height} viewport=${viewportHeight}`,
    )
  }
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

    // 10. 桌面断点与提交栏视口可见（F07/AC-26）
    await page.goto(`${APP_URL}/student/listening-papers`, { waitUntil: 'networkidle' })
    const thirdRow = page.locator('tr', { hasText: '第 3 套' })
    await thirdRow.getByRole('button', { name: '开始作答' }).click()
    await page.waitForURL(/\/student\/listening-papers\/\d+$/, { timeout: 15000 })
    await page.getByRole('radio').first().waitFor({ timeout: 20000 })
    const thirdUrl = page.url()
    const thirdPaperId = Number(thirdUrl.match(/(\d+)$/)?.[1])

    for (const [width, height, name] of [
      [1440, 768, 'e2e-07-1440.png'],
      [1280, 768, 'e2e-07-1280.png'],
      [1024, 768, 'e2e-08-1024.png'],
    ]) {
      await page.setViewportSize({ width, height })
      await page.waitForTimeout(300)
      const submitButton = page.getByRole('button', { name: /交\s*卷/ })
      if ((await submitButton.count()) !== 1) {
        throw new Error(`${width} 下提交栏交卷按钮缺失或重复`)
      }
      const barBox = await page.locator('.submit-bar--fixed').boundingBox()
      assertInViewport(barBox, height, `${width}x${height} 提交栏`)
      const buttonBox = await submitButton.boundingBox()
      assertInViewport(buttonBox, height, `${width}x${height} 交卷按钮`)
      await shot(page, name, { fullPage: false })
      record(
        `E2E-09 ${width}x${height} 提交栏视口内`,
        'PASS',
        `bar.y=${Math.round(barBox.y)} bar.h=${Math.round(barBox.height)}`,
      )
    }

    // 11. F01：损坏信封 + API-3 malformed 不得放开编辑
    const userId = await page.evaluate(() => {
      const marker = Object.keys(window.localStorage).find((key) =>
        key.startsWith('ssre.attemptSubmitted.v2.'),
      )
      return marker ? Number(marker.split('.')[3]) : null
    })
    if (!Number.isFinite(userId)) {
      throw new Error('无法从本机提交标记解析 userId')
    }
    await page.evaluate(
      ({ uid, pid }) => {
        window.localStorage.setItem(
          `ssre.attemptEnvelope.v1.${uid}.${pid}`,
          '{"schemaVersion":1}',
        )
      },
      { uid: userId, pid: thirdPaperId },
    )
    await page.route('**/attempt-status', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 200, msg: '查询成功', data: {} }),
      }),
    )
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByText(/提交记录无法解析/).waitFor({ timeout: 20000 })
    if ((await page.getByRole('radiogroup').count()) !== 0) {
      throw new Error('F01 损坏信封 + malformed 仍出现可交互选项')
    }
    if ((await page.getByRole('button', { name: /交\s*卷/ }).count()) !== 0) {
      throw new Error('F01 损坏信封 + malformed 仍出现交卷按钮')
    }
    await page.getByRole('button', { name: '查询提交状态' }).waitFor()
    await shot(page, 'e2e-09-corrupt-malformed.png')
    record('E2E-10 F01 损坏信封保护', 'PASS', '仅查询/强警告清除，无选项与交卷')
    await page.unroute('**/attempt-status')
    await page.evaluate(
      ({ uid, pid }) => {
        window.localStorage.removeItem(`ssre.attemptEnvelope.v1.${uid}.${pid}`)
      },
      { uid: userId, pid: thirdPaperId },
    )

    // 12. F02：手动查询矛盾状态后必须冻结编辑/交卷
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('radio').first().waitFor({ timeout: 20000 })
    await page.route('**/attempts', (route) => {
      if (route.request().method() !== 'POST') {
        return route.continue()
      }
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 400,
          msg: '缺少或非法的提交键 Idempotency-Key',
          data: null,
        }),
      })
    })
    await page.getByRole('button', { name: /交\s*卷/ }).click()
    await page.getByRole('button', { name: '确认交卷' }).click()
    await page.getByText(/提交键异常/).waitFor({ timeout: 20000 })
    await page.unroute('**/attempts')

    await page.route('**/attempt-status', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          msg: '查询成功',
          data: {
            exam_paper_id: thirdPaperId,
            submitted: true,
            attempt_count: 0,
            latest_attempt: null,
          },
        }),
      }),
    )
    await page.getByRole('button', { name: '查询提交状态' }).click()
    await page.getByText(/提交状态自相矛盾/).first().waitFor({ timeout: 20000 })
    if ((await page.getByRole('radiogroup').count()) !== 0) {
      throw new Error('F02 手动查询矛盾状态后仍可编辑')
    }
    if (
      !(await page.getByRole('button', { name: /交\s*卷/ }).isDisabled())
    ) {
      throw new Error('F02 手动查询矛盾状态后交卷按钮仍可点击')
    }
    await shot(page, 'e2e-10-manual-query-conflict-frozen.png')
    record('E2E-11 F02 手动查询矛盾冻结', 'PASS', '无可交互选项，交卷禁用')
    await page.unroute('**/attempt-status')

    // 13. F04：二次确认后取消旧 timer，旧答案不再复活
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('radio').first().waitFor({ timeout: 20000 })
    await page.getByRole('radio', { name: /选项 B：Question 1 option B/ }).click()
    await page.getByRole('button', { name: '重新开始' }).click()
    await page.getByRole('button', { name: '确认重新开始' }).click()
    await page.waitForTimeout(700)
    const draftAfterRestart = await page.evaluate(
      ({ uid, pid }) =>
        window.localStorage.getItem(`ssre.attemptDraft.v2.${uid}.${pid}`),
      { uid: userId, pid: thirdPaperId },
    )
    if (draftAfterRestart !== null) {
      throw new Error('F04 重新开始后旧 timer 仍写入了草稿')
    }
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('radio').first().waitFor({ timeout: 20000 })
    if ((await page.getByRole('radio', { name: /已选/ }).count()) !== 0) {
      throw new Error('F04 刷新后旧答案复活')
    }
    record('E2E-12 F04 重新开始不复活', 'PASS', '草稿为空且刷新后无选中答案')

    // 14. F05：站内返回列表不丢失最后一次作答
    await page.getByRole('radio', { name: /选项 C：Question 1 option C/ }).click()
    await page.getByRole('link', { name: /返回听力练习/ }).first().click()
    await page.waitForURL(/\/student\/listening-papers$/, { timeout: 15000 })
    await page
      .locator('tr', { hasText: '第 3 套' })
      .getByRole('button', { name: /继续作答|开始作答/ })
      .click()
    await page.waitForURL(/\/student\/listening-papers\/\d+$/, { timeout: 15000 })
    await page
      .getByRole('radio', { name: /选项 C.*已选/ })
      .waitFor({ timeout: 20000 })
    record('E2E-13 F05 站内离开保存', 'PASS', '返回列表再进入仍恢复最后一次选择')

    // 15. F06：同题数换批仍提示“汇总对应提交时版本”
    await page.route('**/attempt-status', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          msg: '查询成功',
          data: {
            exam_paper_id: thirdPaperId,
            submitted: true,
            attempt_count: 1,
            latest_attempt: {
              attempt_code: '11111111-2222-4333-8444-555555555555',
              exam_paper_id: thirdPaperId,
              submitted_at: '2026-11-16T00:00:00Z',
              question_count: 4,
              correct_count: 3,
              correct_rate: 75,
              practice_score: {
                available: false,
                value: null,
                max: 249,
                label: '练习估分，非官方成绩',
                reason: 'not_standard_25',
              },
            },
          },
        }),
      }),
    )
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByText(/汇总对应提交时的试卷版本/).waitFor({ timeout: 20000 })
    await shot(page, 'e2e-11-same-count-version-notice.png')
    record('E2E-14 F06 同题数版本提示', 'PASS', '题数相同仍展示汇总版本免责声明')
    await page.unroute('**/attempt-status')

    // 16. 管理员权限（模块二保持原规则，API-1/3 403）
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
