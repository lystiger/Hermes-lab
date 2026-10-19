// usage: node shoot.mjs <outdir> [baseUrl] [waitMs]   -- headless Chromium via CDP, throwaway profile
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
const [out, base = 'http://localhost:3001', waitMs = '6000'] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const profile = mkdtempSync(join(process.env.SCRATCH, 'chrome-'));
const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn('chromium', ['--headless=new', `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
  '--disable-gpu', '--hide-scrollbars', `--remote-debugging-port=${port}`, '--window-size=1600,1000', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) {
  try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page'); } catch { await sleep(200); }
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0; const pending = new Map();
ws.addEventListener('message', (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); } });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
for (const route of ['', 'queue', 'agents', 'execution', 'events', 'usage']) {
  await send('Page.navigate', { url: `${base}/${route}` });
  await sleep(Number(waitMs));
  const { data } = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(out, `${route || 'overview'}.png`), Buffer.from(data, 'base64'));
}
ws.close(); chrome.kill(); await sleep(300); rmSync(profile, { recursive: true, force: true });
console.log('shots in', out);
