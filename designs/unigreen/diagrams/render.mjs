// Render every Mermaid source to SVG in a real browser. A diagram that does not parse fails the run.
// Writes out/diagrams/*.svg, copies them to LysControl's public folder, and adds them to the manifest.
import { chromium } from "/home/lystiger/Projects/Unigreen/frontend/node_modules/@playwright/test/index.mjs";
import { readFile, readdir, writeFile, mkdir, copyFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.join(here, "src");
const outDir = path.join(here, "..", "out", "diagrams");
const publicDir = path.join(here, "..", "..", "..", "console", "public", "design", "unigreen", "diagrams");
const manifestPath = path.join(here, "..", "..", "..", "console", "public", "design", "unigreen", "manifest.json");
const mermaidPath = path.join(here, "node_modules", "mermaid", "dist", "mermaid.min.js");

const LABELS = {
  sitemap: "Sitemap (English and Vietnamese routes)",
  "buyer-flow": "Buyer flow: from product to quotation request",
  "staff-flow": "Staff flow: from sign-in to an inquiry",
  "inquiry-status": "Inquiry status lifecycle",
  "submit-sequence": "Submitting an inquiry",
  database: "Database (generated from the staging schema)",
};

await mkdir(outDir, { recursive: true });
await mkdir(publicDir, { recursive: true });
const files = (await readdir(srcDir)).filter((f) => f.endsWith(".mmd")).sort();
const browser = await chromium.launch();
const page = await browser.newPage();
await page.setContent("<!doctype html><html><body></body></html>");
await page.addScriptTag({ content: await readFile(mermaidPath, "utf8") });

const results = [];
let failed = 0;
for (const file of files) {
  const id = path.basename(file, ".mmd");
  const source = await readFile(path.join(srcDir, file), "utf8");
  const result = await page.evaluate(async ({ id, source }) => {
    try {
      window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
      const { svg } = await window.mermaid.render(`d-${id}`, source);
      return { ok: true, svg };
    } catch (e) {
      return { ok: false, error: String(e.message || e).slice(0, 300) };
    }
  }, { id, source });
  if (!result.ok) {
    failed += 1;
    console.log(`FAIL ${file}: ${result.error}`);
    results.push({ id, file, ok: false });
    continue;
  }
  await writeFile(path.join(outDir, `${id}.svg`), result.svg, "utf8");
  await writeFile(path.join(publicDir, `${id}.svg`), result.svg, "utf8");
  console.log(`ok   ${file}`);
  results.push({ id, file, ok: true });
}
await browser.close();

const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
manifest.diagrams = results.filter((r) => r.ok).map((r) => ({ id: r.id, label: LABELS[r.id] ?? r.id, file: `diagrams/${r.id}.svg` }));
await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
console.log(`${results.length - failed} rendered, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
