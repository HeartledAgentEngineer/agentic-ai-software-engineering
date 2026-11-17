import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const validator = path.join(repoRoot, 'scripts', 'verify-showcase.mjs');

// The fixture holds the Sonos project and the demo recorder its README links to.
function copyShowcase(fixtureRoot) {
  for (const part of [['projects', 'sonos-music-drop'], ['scripts', 'demos']]) {
    fs.cpSync(path.join(repoRoot, ...part), path.join(fixtureRoot, ...part), { recursive: true });
  }
}

test('validator rejects remote CSS imports and URL assets in an isolated copy', () => {
  const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'showcase-validator-fixture-'));
  try {
    copyShowcase(fixtureRoot);
    const env = { ...process.env, SHOWCASE_ROOT: fixtureRoot };
    const clean = spawnSync(process.execPath, [validator], { encoding: 'utf8', env });
    assert.equal(clean.status, 0, clean.stderr || clean.stdout);

    const fixtureCss = path.join(fixtureRoot, 'projects', 'sonos-music-drop', 'demo', 'style.css');
    fs.appendFileSync(fixtureCss, '\n@import url("https://example.invalid/theme.css");\n.fixture { background: url("https://example.invalid/font.woff2"); }\n');
    const rejected = spawnSync(process.execPath, [validator], { encoding: 'utf8', env });
    assert.equal(rejected.status, 1, 'remote CSS resources must fail validation');
    assert.match(rejected.stderr, /CSS @import is not allowed/);
    assert.match(rejected.stderr, /CSS url\(\) is not allowed/);
  } finally {
    fs.rmSync(fixtureRoot, { recursive: true, force: true });
  }
});

test('validator rejects demo files that are too large or not linked from the project README', () => {
  const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'showcase-demo-fixture-'));
  try {
    copyShowcase(fixtureRoot);
    const env = { ...process.env, SHOWCASE_ROOT: fixtureRoot };
    const clean = spawnSync(process.execPath, [validator], { encoding: 'utf8', env });
    assert.equal(clean.status, 0, clean.stderr || clean.stdout);

    const docs = path.join(fixtureRoot, 'projects', 'other', 'docs');
    fs.mkdirSync(docs, { recursive: true });
    fs.writeFileSync(path.join(fixtureRoot, 'projects', 'other', 'README.md'), '# Other\n\nNo demo link here.\n');
    fs.writeFileSync(path.join(docs, 'demo.gif'), Buffer.alloc(5 * 1024 * 1024 + 1));
    const rejected = spawnSync(process.execPath, [validator], { encoding: 'utf8', env });
    assert.equal(rejected.status, 1, 'oversized or unlinked demo files must fail validation');
    assert.match(rejected.stderr, /Demo file above 5 MB \(5242881 bytes\): projects\/other\/docs\/demo\.gif/);
    assert.match(rejected.stderr, /Demo file not linked from projects\/other\/README\.md: projects\/other\/docs\/demo\.gif/);

    const toolDocs = path.join(fixtureRoot, 'tools', 'sometool', 'docs');
    fs.mkdirSync(toolDocs, { recursive: true });
    fs.writeFileSync(path.join(fixtureRoot, 'tools', 'sometool', 'README.md'), '# Tool\n\nNo demo link here.\n');
    fs.writeFileSync(path.join(toolDocs, 'demo.mp4'), Buffer.alloc(16));
    const rejectedTool = spawnSync(process.execPath, [validator], { encoding: 'utf8', env });
    assert.equal(rejectedTool.status, 1, 'unlinked demo files under tools/ must fail validation');
    assert.match(rejectedTool.stderr, /Demo file not linked from tools\/sometool\/README\.md: tools\/sometool\/docs\/demo\.mp4/);
  } finally {
    fs.rmSync(fixtureRoot, { recursive: true, force: true });
  }
});
