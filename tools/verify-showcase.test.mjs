import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const validator = path.join(repoRoot, 'tools', 'verify-showcase.mjs');

test('validator rejects remote CSS imports and URL assets in an isolated copy', () => {
  const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'showcase-validator-fixture-'));
  try {
    fs.cpSync(
      path.join(repoRoot, 'projects', 'sonos-music-drop'),
      path.join(fixtureRoot, 'projects', 'sonos-music-drop'),
      { recursive: true },
    );
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
