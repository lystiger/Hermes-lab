// UI check: every page x widths -> screenshot + automated layout scan (headless Chromium via CDP, throwaway profile).
// usage: node scripts/ui-check.mjs <outdir> [baseUrl] [waitMs]   -> writes <outdir>/<width>/<page>.png and <outdir>/report.json
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
const [out, base = 'http://localhost:3001', waitMs = '5000'] = process.argv.slice(2);
const WIDTHS = [900, 1280, 1440, 1920];
const PAGES = ['', 'queue', 'agents', 'execution', 'events', 'inspector', 'usage', 'settings'];
const profile = mkdtempSync(join(process.env.SCRATCH || tmpdir(), 'chrome-'));
const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn('chromium', ['--headless=new', `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
  '--disable-gpu', '--hide-scrollbars', `--remote-debugging-port=${port}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) { try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page'); } catch { await sleep(200); } }
if (!target) { chrome.kill(); rmSync(profile, { recursive: true, force: true }); throw new Error('Chromium debugging endpoint unavailable; layout check did not run'); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0; const pending = new Map();
ws.addEventListener('message', (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); } });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
// Runs in the page: overlapping text, horizontal overflow, clipped text without a title.
const SCAN = `(() => {
  const issues = [];
  const scanRoot = document.querySelector('[role=dialog]') || document.body;
  const texts = [...scanRoot.querySelectorAll('*')].filter(el => {
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
  // A page still loading or connecting has little text to overlap, so it would pass the layout checks while
  // showing no data. Count it as an issue so that 0 means every page rendered.
  const pending = (document.body.innerText.match(/Loading\\b|not loaded yet|\\bconnecting\\b/gi) || []);
  if (pending.length) issues.push({ type: 'still-loading', a: [...new Set(pending.map(s => s.toLowerCase()))].join(', ') });
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
    await send('Page.navigate', { url: `${base}/${page === 'inspector' ? 'queue' : page}` });
    await sleep(Number(waitMs));
    if (page === 'inspector') {
      await send('Runtime.evaluate', { expression: `(() => {
        const job = [...document.querySelectorAll('button')].find(el => el.title?.startsWith('/home/lystiger/Projects/Hermes-lab/prompts/'));
        job?.click();
      })()` });
      await sleep(1000);
    }
    // A short fixture must never silently pass this long-text regression check.
    if (['', 'queue', 'events', 'inspector'].includes(page)) {
      const fixture = await send('Runtime.evaluate', { expression: `!!document.querySelector('[title^="/home/lystiger/Projects/Hermes-lab/prompts/"]')`, returnByValue: true });
      if (!fixture.result.value) throw new Error(`Long-text mock fixture missing on ${name}; start Vite with VITE_LYSCONTROL_MOCK=1`);
    }
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
