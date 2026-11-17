'use strict';

/*
 * Records the two static browser projects as GIF demos — no screen recording, no network.
 *
 *   sonos     projects/sonos-music-drop/docs/demo.gif   (the volume-ducking simulation)
 *   squirrel  projects/squirrel-game/docs/demo.gif      (climb, steal the nut, new nut)
 *
 * Every frame comes from the real page in a headless browser. Before a frame is kept, the script asserts the state
 * the frame is supposed to show, so a broken page fails the recording instead of producing a misleading GIF.
 * The squirrel game is made deterministic: Math.random is seeded and requestAnimationFrame is stepped frame by
 * frame, so the same input gives the same GIF. (Rendering limits for the Sonos page: see the launch options below.)
 *
 * Setup (same pinned Playwright as CI, no install scripts, nothing added to the repository):
 *   npm install --prefix <dir> --ignore-scripts playwright@1.62.1 gifenc@1.0.3 pngjs@7.0.0
 *   NODE_PATH=<dir>/node_modules node scripts/demos/record-browser-demos.cjs [sonos] [squirrel]
 * Uses the installed Microsoft Edge by default; set DEMO_BROWSER_CHANNEL (e.g. "chrome") to use another channel.
 */

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
const { PNG } = require('pngjs');
const { GIFEncoder, quantize, applyPalette } = require('gifenc');

const ROOT = path.resolve(__dirname, '..', '..');
const MAX_BYTES = 5 * 1024 * 1024;

/* A browser context that can only load local files: every other request is aborted and recorded. */
async function localOnlyPage(browser, options) {
  const context = await browser.newContext({ permissions: [], serviceWorkers: 'block', ...options });
  const external = [];
  const errors = [];
  await context.route('**/*', async route => {
    const url = route.request().url();
    if (url.startsWith('file:') || url.startsWith('data:')) return route.continue();
    external.push(url);
    return route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  const finish = async () => {
    await context.close();
    assert.deepEqual(external, [], `external requests were blocked: ${external.join(', ')}`);
    assert.deepEqual(errors, [], `page errors: ${errors.join(' | ')}`);
  };
  return { page, finish };
}

/* frames: [{ png: Buffer, delay: ms }] -> GIF with one shared palette (stable colours, no flicker). */
function encodeGif(frames) {
  const decoded = frames.map(frame => PNG.sync.read(frame.png));
  const { width, height } = decoded[0];
  for (const image of decoded) assert.deepEqual([image.width, image.height], [width, height], 'all frames need one size');
  const step = Math.max(1, Math.floor(decoded.length / 24));
  const sample = Buffer.concat(decoded.filter((_, i) => i % step === 0).map(image => image.data));
  const palette = quantize(sample, 256);
  const gif = GIFEncoder();
  decoded.forEach((image, i) => {
    const index = applyPalette(image.data, palette);
    gif.writeFrame(index, width, height, { palette: i === 0 ? palette : undefined, delay: frames[i].delay, repeat: 0 });
  });
  gif.finish();
  return Buffer.from(gif.bytes());
}

/* Optional: DEMO_FRAMES_DIR=<dir> keeps every raw frame as PNG, e.g. for a review of the pictures. */
function keepFrames(name, frames) {
  const dir = process.env.DEMO_FRAMES_DIR;
  if (!dir) return;
  fs.mkdirSync(dir, { recursive: true });
  frames.forEach((frame, i) => fs.writeFileSync(path.join(dir, `${name}-${String(i + 1).padStart(3, '0')}.png`), frame.png));
}

function writeDemo(relative, bytes) {
  assert.ok(bytes.length <= MAX_BYTES, `${relative} is ${bytes.length} bytes, above the 5 MB limit`);
  const target = path.join(ROOT, relative);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, bytes);
  const sha = crypto.createHash('sha256').update(bytes).digest('hex');
  process.stdout.write(`${relative}: ${(bytes.length / 1024).toFixed(0)} KiB, sha256 ${sha}\n`);
}

async function recordSonos(browser) {
  const { page, finish } = await localOnlyPage(browser, { viewport: { width: 760, height: 1100 }, reducedMotion: 'reduce' });
  await page.goto(pathToFileURL(path.join(ROOT, 'projects/sonos-music-drop/demo/index.html')).href);
  const frames = [];
  // From the "Simulation with sample data" note down to the end of the control panel: the label stays in every frame.
  const noteBox = await page.locator('.simulation-note').boundingBox();
  const consoleBox = await page.locator('.console').boundingBox();
  const top = Math.max(0, Math.floor(noteBox.y - 16));
  const clip = { x: 0, y: top, width: 760, height: Math.ceil(consoleBox.y + consoleBox.height + 16 - top) };
  assert.match(await page.locator('.simulation-note').innerText(), /Simulation with sample data – no microphone or speaker connection/);
  // Wait two animation frames so the repaint after focus or input has finished before the frame is taken.
  const settle = () => page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
  const shot = async delay => {
    await settle();
    frames.push({ png: await page.screenshot({ clip, caret: 'hide' }), delay });
  };
  const volume = page.getByRole('slider', { name: 'Starting volume' });
  const meter = percent => page.getByRole('img', { name: `Music volume ${percent} percent` });

  // 1. Sample defaults.
  assert.equal(await volume.inputValue(), '40');
  assert.equal(await page.getByRole('slider', { name: 'Speaking level' }).inputValue(), '15');
  assert.equal(await meter(40).count(), 1);
  await shot(1600);

  // 2. Raise the starting volume to 70 % with the keyboard, in visible steps.
  await volume.focus();
  for (const goal of [50, 60, 70]) {
    for (let i = 0; i < 10; i++) await page.keyboard.press('ArrowRight');
    assert.equal(await volume.inputValue(), String(goal));
    assert.equal(await meter(goal).count(), 1);
    await shot(goal === 70 ? 1300 : 250);
  }

  // 3. Begin speaking: music drops to the speaking level, the original level is kept.
  const begin = page.getByRole('button', { name: /Begin speaking/ });
  await begin.focus();
  await shot(700);
  await page.keyboard.press('Enter');
  assert.equal(await meter(15).count(), 1);
  assert.match(await page.locator('#status-text').innerText(), /Speaking level active/);
  assert.match(await page.locator('#state-caption').innerText(), /Music is at 15%\. End speaking to restore 70%\./);
  await shot(2400);

  // 4. End speaking: the exact starting volume comes back.
  const end = page.getByRole('button', { name: /End speaking/ });
  await end.focus();
  await shot(700);
  await page.keyboard.press('Enter');
  assert.equal(await meter(70).count(), 1);
  assert.equal(await volume.inputValue(), '70');
  assert.match(await page.locator('#status-text').innerText(), /Ready when you are/);
  await shot(2600);

  await finish();
  keepFrames('sonos', frames);
  writeDemo('projects/sonos-music-drop/docs/demo.gif', encodeGif(frames));
}

async function recordSquirrel(browser) {
  // 360x480 shows the fixed 480x640 game canvas at 3/4 size: small GIF, nothing cut off.
  const { page, finish } = await localOnlyPage(browser, { viewport: { width: 360, height: 480 } });
  await page.addInitScript(() => {
    let seed = 20261117;
    Math.random = () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 4294967296;
    };
    let queue = [];
    window.requestAnimationFrame = callback => { queue.push(callback); return queue.length; };
    window.cancelAnimationFrame = () => {};
    window.__demoStep = count => {
      for (let i = 0; i < count; i++) {
        const due = queue;
        queue = [];
        due.forEach(callback => callback(i * (1000 / 60)));
      }
    };
  });
  await page.goto(pathToFileURL(path.join(ROOT, 'projects/squirrel-game/index.html')).href);
  const frames = [];
  const PER_FRAME = 4; // four 60 Hz game frames per GIF frame (GIF stores 70 ms: about real time, 15 fps)
  const play = async gameFrames => {
    for (let done = 0; done < gameFrames; done += PER_FRAME) {
      await page.evaluate(n => window.__demoStep(n), PER_FRAME);
      frames.push({ png: await page.screenshot({ caret: 'hide' }), delay: 67 });
    }
  };
  const game = () => page.evaluate(() => ({ state: window.state, nutCount: window.nutCount, nutOn: window.nut.on }));

  // 1. The squirrel climbs to the crown (about 2.3 s of game time).
  assert.equal((await game()).state, 'climb');
  for (let i = 0; i < 80 && (await game()).state === 'climb'; i++) await play(PER_FRAME);
  assert.equal((await game()).state, 'crown', 'the squirrel reaches the crown');
  await play(56);

  // 2. Tap the nut: it is counted as stolen.
  const target = await page.evaluate(() => {
    const rect = document.getElementById('c').getBoundingClientRect();
    return { x: rect.left + window.nut.x * rect.width / 480, y: rect.top + window.nut.y * rect.height / 640 };
  });
  assert.deepEqual(await game(), { state: 'crown', nutCount: 0, nutOn: true });
  await page.mouse.click(target.x, target.y);
  assert.deepEqual(await game(), { state: 'crown', nutCount: 1, nutOn: false }, 'the tap steals the nut');

  // 3. The squirrel complains, searches, and a new nut appears.
  await play(152);
  assert.deepEqual(await game(), { state: 'crown', nutCount: 1, nutOn: true }, 'a new nut appears');
  await play(48);
  frames[frames.length - 1].delay = 1200;

  await finish();
  keepFrames('squirrel', frames);
  writeDemo('projects/squirrel-game/docs/demo.gif', encodeGif(frames));
}

async function main() {
  const wanted = process.argv.slice(2);
  const all = { sonos: recordSonos, squirrel: recordSquirrel };
  const names = wanted.length ? wanted : Object.keys(all);
  for (const name of names) assert.ok(all[name], `unknown demo "${name}" (choose from: ${Object.keys(all).join(', ')})`);
  // Software rendering in sRGB. With GPU rasterisation, large gradient areas differed by one colour step between
  // runs. Measured on the author's machine afterwards: the squirrel GIF is byte-identical on every run; the Sonos GIF
  // is byte-identical in most runs, the rest differ in a few anti-aliased pixels of the native slider (one step).
  const browser = await chromium.launch({
    channel: process.env.DEMO_BROWSER_CHANNEL || 'msedge',
    headless: true,
    args: ['--disable-gpu', '--force-color-profile=srgb'],
  });
  try {
    for (const name of names) await all[name](browser);
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
