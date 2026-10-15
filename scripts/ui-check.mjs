// UI check: every page x widths -> screenshot + automated layout scan (headless Chromium via CDP, throwaway profile).
// usage: node scripts/ui-check.mjs <outdir> [baseUrl] [waitMs]   -> writes <outdir>/<width>/<page>.png and <outdir>/report.json
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
const [out, base = 'http://localhost:3001', waitMs = '5000'] = process.argv.slice(2);
const WIDTHS = [900, 1280, 1440, 1920];
const PAGES = ['', 'queue', 'agents', 'execution', 'events', 'usage', 'settings'];
const profile = mkdtempSync(join(process.env.SCRATCH || tmpdir(), 'chrome-'));
const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn('chromium', ['--headless=new', `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
  '--disable-gpu', '--hide-scrollbars', `--remote-debugging-port=${port}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) { try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page'); } catch { await sleep(200); } }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0; const pending = new Map();
ws.addEventListener('message', (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); } });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
// Runs in the page: overlapping text, horizontal overflow, clipped text without a title.
const SCAN = `(() => {
  const issues = [];
  const texts = [...document.querySelectorAll('body *')].filter(el => {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    const s = getComputedStyle(el); const r = el.getBoundingClientRect();
    return own && s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0 && +s.opacity > 0.05;
  });
  const label = el => (el.textContent.trim().slice(0, 40) + ' <' + el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '') + '>');
  const boxes = texts.map(el => ({ el, r: el.getBoundingClientRect() }));
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
    const h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (w > 3 && h > 3) issues.push({ type: 'overlap', a: label(a.el), b: label(b.el) });
  }
  for (const { el } of boxes) {
    const s = getComputedStyle(el);
    if ((el.scrollWidth > el.clientWidth + 1) && (s.overflow.includes('hidden') || s.textOverflow === 'ellipsis') && !el.title && !el.closest('[title]'))
      issues.push({ type: 'clipped-without-tooltip', a: label(el) });
  }
  if (document.documentElement.scrollWidth > window.innerWidth + 1) issues.push({ type: 'horizontal-page-overflow', a: document.documentElement.scrollWidth + 'px > ' + window.innerWidth + 'px' });
  const scrollers = [...document.querySelectorAll('body *')].filter(el => { const s = getComputedStyle(el); return /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 1; });
  return { issues: issues.slice(0, 60), issueCount: issues.length, nestedScrollContainers: scrollers.length };
})()`;
const report = {};
await send('Page.enable');
for (const width of WIDTHS) {
  mkdirSync(join(out, String(width)), { recursive: true });
  await send('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
  for (const page of PAGES) {
    const name = page || 'overview';
    await send('Page.navigate', { url: `${base}/${page}` });
    await sleep(Number(waitMs));
    const { result } = await send('Runtime.evaluate', { expression: SCAN, returnByValue: true });
    report[`${width}/${name}`] = result.value;
    const { data } = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(out, String(width), `${name}.png`), Buffer.from(data, 'base64'));
  }
}
writeFileSync(join(out, 'report.json'), JSON.stringify(report, null, 2));
const total = Object.values(report).reduce((n, r) => n + r.issueCount, 0);
console.log(`ui-check: ${total} issues across ${Object.keys(report).length} page/width combinations -> ${out}/report.json`);
for (const [k, r] of Object.entries(report)) if (r.issueCount) console.log(`  ${k}: ${r.issueCount} (${[...new Set(r.issues.map(i => i.type))].join(', ')}); scroll containers ${r.nestedScrollContainers}`);
ws.close(); chrome.kill(); await sleep(300); rmSync(profile, { recursive: true, force: true });
