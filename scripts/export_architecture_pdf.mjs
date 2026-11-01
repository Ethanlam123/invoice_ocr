// Export docs/architecture.html to an A4 PDF at natural size (multi-page).
// Run from the repo root:  node scripts/export_architecture_pdf.mjs
// Uses the frontend's installed playwright chromium; waits for web fonts and
// emulates print media. Page breaks come from the page's @media print rules.

import { chromium } from "../frontend/node_modules/playwright/index.mjs";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const repo = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const src = `file://${repo}/docs/architecture.html`;
const out = path.join(repo, "docs", "architecture.pdf");

const MARGIN_MM = 8;
const usableW = (210 - 2 * MARGIN_MM) * (96 / 25.4);

// page count via ghostscript (mdls/Spotlight proved unreliable for fresh files)
const pageCount = (file) =>
  Number(execSync(`gs -dNODISPLAY -q -dNOSAFER -c "(${file}) (r) file runpdfbegin pdfpagecount = quit"`).toString().trim());

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: Math.round(usableW), height: 900 } });
await page.goto(src, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.emulateMedia({ media: "print" });

await page.pdf({
  path: out,
  format: "A4",
  printBackground: true,
  scale: 1,
  margin: { top: `${MARGIN_MM}mm`, bottom: `${MARGIN_MM}mm`, left: `${MARGIN_MM}mm`, right: `${MARGIN_MM}mm` },
});
await browser.close();

const pages = pageCount(out);
console.log(`wrote ${out} (A4, ${pages} page(s))`);
if (!(pages >= 1)) process.exit(1);
