'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

async function main() {
  const demoDir = __dirname;
  const screenshotDir = process.env.SONOS_QA_DIR || path.join(os.tmpdir(), 'sonos-demo-preview');
  fs.mkdirSync(screenshotDir, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const blockedProbeRequests = [];
  const unexpectedExternalRequests = [];
  const pageErrors = [];

  async function installLocalOnlyRoutes(context, externalTracker) {
    await context.route('**/*', async route => {
      const url = route.request().url();
      if (url.startsWith('file:') || url.startsWith('data:')) {
        await route.continue();
        return;
      }
      externalTracker.push(url);
      await route.abort('blockedbyclient');
    });
  }

  try {
    const guardContext = await browser.newContext({ permissions: [], serviceWorkers: 'block' });
    await installLocalOnlyRoutes(guardContext, blockedProbeRequests);
    const guardPage = await guardContext.newPage();
    guardPage.on('pageerror', error => pageErrors.push(`guard: ${error.message}`));
    await guardPage.goto('about:blank');
    const probeWasBlocked = await guardPage.evaluate(async () => {
      try {
        await fetch('https://example.invalid/guard-probe');
        return false;
      } catch {
        return true;
      }
    });
    assert.equal(probeWasBlocked, true, 'synthetic external fetch must be blocked');
    assert.deepEqual(blockedProbeRequests, ['https://example.invalid/guard-probe'], 'route handler must intercept exactly the synthetic probe');
    await guardContext.close();

    for (const width of [390, 1280]) {
      const context = await browser.newContext({ viewport: { width, height: 900 }, permissions: [], serviceWorkers: 'block' });
      await installLocalOnlyRoutes(context, unexpectedExternalRequests);
      const page = await context.newPage();
      page.on('pageerror', error => pageErrors.push(`${width}px: ${error.message}`));
      await page.goto(pathToFileURL(path.join(demoDir, 'index.html')).href);
      assert.match(await page.locator('.simulation-note').innerText(), /Simulation with sample data – no microphone or speaker connection/);
      assert.equal(await page.getByRole('slider', { name: 'Starting volume' }).inputValue(), '40');
      assert.equal(await page.getByRole('slider', { name: 'Speaking level' }).inputValue(), '15');

      const volume = page.getByRole('slider', { name: 'Starting volume' });
      await volume.focus();
      await page.keyboard.press('ArrowRight');
      assert.equal(await volume.inputValue(), '41', 'keyboard arrows change the native range control');
      await page.keyboard.press('Home');
      assert.equal(await volume.inputValue(), '0', 'the zero boundary is keyboard reachable');
      await page.keyboard.press('End');
      assert.equal(await volume.inputValue(), '100', 'the upper boundary is keyboard reachable');
      await page.getByRole('button', { name: /Begin speaking/ }).focus();
      await page.keyboard.press('Enter');
      assert.equal(await page.getByRole('img', { name: 'Music volume 15 percent' }).count(), 1);
      assert.equal(await volume.inputValue(), '100', 'starting volume remains the saved original while ducking');
      assert.equal(await page.locator('#volume-output').innerText(), '100%');
      assert.equal(await volume.isDisabled(), true);
      assert.equal(await page.getByRole('slider', { name: 'Speaking level' }).isDisabled(), true);
      assert.equal(await page.getByRole('button', { name: /Begin speaking/ }).isDisabled(), true);
      assert.equal(await page.getByRole('button', { name: /End speaking/ }).isDisabled(), false);
      assert.match(await page.locator('#status-text').innerText(), /Speaking level active/);
      const dimensions = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      assert.ok(dimensions.scrollWidth <= dimensions.clientWidth, `horizontal overflow at ${width}px: ${JSON.stringify(dimensions)}`);
      await page.getByRole('button', { name: /End speaking/ }).click();
      assert.equal(await volume.isDisabled(), false);
      assert.equal(await page.getByRole('img', { name: 'Music volume 100 percent' }).count(), 1);
      await page.getByRole('button', { name: /Reset demo/ }).click();
      assert.equal(await volume.inputValue(), '40');
      assert.equal(await page.getByRole('slider', { name: 'Speaking level' }).inputValue(), '15');
      await page.getByRole('button', { name: /Begin speaking/ }).click();
      assert.equal(await page.getByRole('img', { name: 'Music volume 15 percent' }).count(), 1);
      assert.equal(await volume.inputValue(), '40', 'starting volume remains the saved original while ducking');
      assert.equal(await page.locator('#volume-output').innerText(), '40%');
      await page.screenshot({ path: path.join(screenshotDir, `sonos-demo-${width}.png`), fullPage: true });
      await page.getByRole('button', { name: /End speaking/ }).click();
      assert.equal(await page.getByRole('img', { name: 'Music volume 40 percent' }).count(), 1);
      assert.equal(await volume.inputValue(), '40');
      assert.equal(await page.locator('#volume-output').innerText(), '40%');
      await context.close();
    }
    assert.deepEqual(unexpectedExternalRequests, [], `unexpected external requests were blocked: ${unexpectedExternalRequests.join(', ')}`);
    assert.deepEqual(pageErrors, [], `browser page errors: ${pageErrors.join(' | ')}`);
    process.stdout.write(`Browser QA passed at 390px and 1280px; guard probes blocked: ${blockedProbeRequests.length}; unexpected external requests: ${unexpectedExternalRequests.length}; page errors: ${pageErrors.length}; screenshots: ${screenshotDir}\n`);
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
