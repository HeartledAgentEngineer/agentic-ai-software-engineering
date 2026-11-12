import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const demoRoot = path.join(root, 'projects', 'sonos-music-drop', 'demo');
const required = [
  'index.html', 'style.css', 'app.js', 'ducker.js', 'ducker.test.js', 'browser-check.cjs',
];
const forbidden = [
  /\bfetch\s*\(/i,
  /\bWebSocket\b/i,
  /\bXMLHttpRequest\b/i,
  /\bgetUserMedia\b/i,
  /\bAudioContext\b/i,
  /\bwebkitAudioContext\b/i,
  /\bSpeechRecognition\b/i,
  /\bwebkitSpeechRecognition\b/i,
  /\bimport\s*\(/i,
  /\beval\s*\(/i,
  /\bFunction\s*\(/,
  /\bnew\s+(?:Shared)?Worker\b/i,
  /\bServiceWorker\b/i,
  /<\s*iframe\b/i,
];
const conflict = /^(?:<<<<<<<|=======|>>>>>>>)(?:\s|$)/m;
let errors = [];

function fail(message) { errors.push(message); }
function contained(base, candidate) {
  const relative = path.relative(base, candidate);
  return relative !== '' && !relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative);
}

for (const file of required) {
  const absolute = path.join(demoRoot, file);
  if (!fs.existsSync(absolute) || !fs.statSync(absolute).isFile()) {
    fail(`Missing required demo file: projects/sonos-music-drop/demo/${file}`);
    continue;
  }
  const body = fs.readFileSync(absolute, 'utf8');
  if (conflict.test(body)) fail(`Conflict marker found: projects/sonos-music-drop/demo/${file}`);
  if (['index.html', 'style.css', 'app.js', 'ducker.js'].includes(file)) {
    for (const pattern of forbidden) if (pattern.test(body)) fail(`Forbidden browser capability ${pattern}: projects/sonos-music-drop/demo/${file}`);
  }
}

const htmlPath = path.join(demoRoot, 'index.html');
if (fs.existsSync(htmlPath)) {
  const html = fs.readFileSync(htmlPath, 'utf8');
  for (const match of html.matchAll(/\b(?:src|href)\s*=\s*["']([^"']+)["']/gi)) {
    const href = match[1];
    if (/^(?:https?:|\/\/|data:|javascript:)/i.test(href)) {
      fail(`External or executable page asset/link: ${href}`);
      continue;
    }
    const target = path.resolve(path.dirname(htmlPath), decodeURIComponent(href.split(/[?#]/, 1)[0]));
    if (!contained(root, target)) fail(`Local page reference leaves repository: ${href}`);
    else if (!fs.existsSync(target)) fail(`Missing local page reference: ${href}`);
  }
}

const readmePath = path.join(root, 'projects', 'sonos-music-drop', 'README.md');
if (!fs.existsSync(readmePath)) fail('Missing projects/sonos-music-drop/README.md');
else {
  const readme = fs.readFileSync(readmePath, 'utf8');
  if (conflict.test(readme)) fail('Conflict marker found: projects/sonos-music-drop/README.md');
  for (const match of readme.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
    const href = match[1].trim().split(/[?#]/, 1)[0];
    if (!href || /^(?:https?:|mailto:|\/\/)/i.test(href)) continue;
    const target = path.resolve(path.dirname(readmePath), decodeURIComponent(href));
    if (!contained(root, target)) fail(`Local documentation reference leaves repository: ${match[1]}`);
    else if (!fs.existsSync(target)) fail(`Missing local documentation reference: ${match[1]}`);
  }
}

if (errors.length) {
  for (const error of errors) process.stderr.write(`ERROR: ${error}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write('Showcase validation passed: required demo files, local references, and browser capability checks.\n');
}
