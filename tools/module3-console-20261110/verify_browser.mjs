// Optional checkout browser verification. Sources and annotations are synthetic.
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
const require = createRequire(process.env.M3_PLAYWRIGHT_PACKAGE || import.meta.url);
const { chromium } = require('playwright');
const base = process.env.M3_CONSOLE_TEST_URL;
const wid = process.env.M3_CONSOLE_TEST_WORKFLOW;
if (!base || !wid) throw Error('Run through verify_checkout.py with M3_CONSOLE_BROWSER_TEST=1');
const browser = await chromium.launch({ channel: process.env.M3_BROWSER_CHANNEL || 'msedge', headless: true });
const checks = [], errors = [];
function check(value, message) { if (!value) throw Error(message); checks.push(message); }
try {
  for (const [name, width] of [['desktop', 1440], ['mobile', 390]]) {
    const page = await browser.newPage({ viewport: { width, height: 1000 } });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    await page.locator('#password').fill('admin123');
    await page.locator('#login-form button').click();
    await page.locator('#logout').waitFor({ state: 'visible' });
    check(await page.locator('[data-example]:visible').count() === 0, name + ' hides unavailable examples');
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), name + ' upload fits viewport');
    if (width < 600) await page.locator('#mobile-history').click();
    await page.locator(`[data-job="${wid}"]`).click();
    await page.locator('[data-q-index]').first().waitFor();
    check(await page.locator('[data-q-index]').count() === 5, name + ' shows five sample questions');
    check(await page.locator('#stage-progress .stage-progress-row').count() === 5, name + ' shows five phase progress bars');
    await page.locator('[data-q-index="4"]').click();
    check((await page.locator('#question-detail').innerText()).includes('Synthetic question 5'), name + ' fifth question is viewable');
    check((await page.locator('#question-detail').innerText()).includes('S21'), name + ' skill is viewable');
    check(await page.locator('#continue-review').isDisabled(), name + ' full annotation waits for explicit review');
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), name + ' result fits viewport');
    if (process.env.M3_CONSOLE_SCREENSHOT_DIR) {
      await page.evaluate(() => { document.querySelector('#global-message').hidden = true; scrollTo(0, 0); });
      await fs.mkdir(process.env.M3_CONSOLE_SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({ path: path.join(process.env.M3_CONSOLE_SCREENSHOT_DIR, `console-${name}.png`), fullPage: true });
    }
    const auth = await page.evaluate(() => sessionStorage.getItem('m3-console-token'));
    const status = await page.request.get(`${base}/console-api/workflows/${wid}`, { headers: { Authorization: `Bearer ${auth}` } });
    const job = (await status.json()).data;
    check(job.phase === 'annotate_sample' && job.task.state === 'awaiting_confirmation', name + ' remains at sample review');
    await page.close();
  }
  check(errors.length === 0, 'no browser script errors');
  console.log(JSON.stringify({ status: 'PASS', checks, count: checks.length, fixture: 'synthetic; no paid calls or human approval' }));
} finally { await browser.close(); }
