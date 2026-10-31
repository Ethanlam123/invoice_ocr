// Export docs/architecture.html to a single-page PDF.
// Run from the repo root:  node scripts/export_architecture_pdf.mjs
// Uses the frontend's installed playwright chromium; waits for web fonts and
// emulates print media. If the content fits A4 at scale >= 0.8 it uses A4;
// otherwise it emits one continuous 210mm-wide page at full size (a taller
// sheet reads better than 6px text crushed onto A4). Page count is verified
// via macOS Spotlight (mdimport + mdls).

import { chromium } from "../frontend/node_modules/playwright/index.mjs";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const repo = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const src = `file://${repo}/docs/architecture.html`;
const out = path.join(repo, "docs", "architecture.pdf");

const MARGIN_MM = 8;
const PX_PER_MM = 96 / 25.4;
const usableW = (210 - 2 * MARGIN_MM) * PX_PER_MM;
const usableH = (297 - 2 * MARGIN_MM) * PX_PER_MM;
const MIN_A4_SCALE = 0.8;

const pageCount = (file) =>
  Number(execSync(`mdimport ${JSON.stringify(file)}; mdls -raw -name kMDItemNumberOfPages ${JSON.stringify(file)}`).toString().trim());

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: Math.round(usableW), height: 900 } });
await page.goto(src, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.emulateMedia({ media: "print" });

const contentH = await page.evaluate(() => document.documentElement.scrollHeight);
const a4Scale = Math.min(1, usableW / usableW, usableH / contentH); // width fits by viewport construction

const margin = { top: `${MARGIN_MM}mm`, bottom: `${MARGIN_MM}mm`, left: `${MARGIN_MM}mm`, right: `${MARGIN_MM}mm` };
if (a4Scale >= MIN_A4_SCALE) {
  await page.pdf({ path: out, format: "A4", printBackground: true, scale: a4Scale, margin });
  console.log(`A4 single page at scale ${a4Scale.toFixed(3)}`);
} else {
  const heightMm = (contentH / PX_PER_MM + 2 * MARGIN_MM).toFixed(1);
  await page.pdf({ path: out, width: "210mm", height: `${heightMm}mm`, printBackground: true, scale: 1, margin });
  console.log(`custom single page: 210mm x ${heightMm}mm at full scale (A4 would need ${a4Scale.toFixed(2)})`);
}
await browser.close();

const pages = pageCount(out);
console.log(`wrote ${out} (${pages} page(s))`);
if (pages !== 1) process.exit(1);
