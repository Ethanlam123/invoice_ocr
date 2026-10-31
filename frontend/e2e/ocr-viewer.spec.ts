import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * UI behavior tests against a MOCKED /api/ocr (deterministic, no model).
 * The live image -> model -> API -> UI check is done manually and recorded
 * in docs/VALIDATION.md.
 */

// Serve the actual fixture file as the "normalized image" so the overlay maps
// onto a real-sized <img> (a tiny stub renders at natural size and is unclickable).
const FIXTURE = join(__dirname, "fixtures", "upload.png");
const FIXTURE_BYTES = readFileSync(FIXTURE);
const FIXTURE_W = FIXTURE_BYTES.readUInt32BE(16); // PNG IHDR width
const FIXTURE_H = FIXTURE_BYTES.readUInt32BE(20); // PNG IHDR height
const DATA_URL = `data:image/png;base64,${FIXTURE_BYTES.toString("base64")}`;

function envelope() {
  // bboxes defined on a 200x150 virtual canvas, scaled to the fixture size
  const bx = (x: number) => Math.round((x / 200) * FIXTURE_W);
  const by = (y: number) => Math.round((y / 150) * FIXTURE_H);
  return {
    success: true,
    data: {
      image: { width: FIXTURE_W, height: FIXTURE_H, mime: "image/png", data_url: DATA_URL },
      blocks: [
        {
          id: 0,
          order: 0,
          label: "text",
          bbox: [bx(10), by(10), bx(100), by(40)],
          content: "ACME Corp",
          content_html: null,
        },
        {
          id: 1,
          order: 1,
          label: "text",
          bbox: [bx(10), by(60), bx(100), by(90)],
          content: "Hong Kong", // duplicate text on purpose
          content_html: null,
        },
        {
          id: 2,
          order: 2,
          label: "text",
          bbox: [bx(110), by(60), bx(190), by(90)],
          content: "Hong Kong",
          content_html: null,
        },
        {
          id: 3,
          order: 3,
          label: "table",
          bbox: [bx(10), by(100), bx(190), by(140)],
          content: "<table><tr><td>a</td><td>b</td></tr></table>",
          content_html: "<table><tr><td>a</td><td>b</td></tr></table>",
        },
        {
          id: 4,
          order: 4,
          label: "text",
          bbox: [bx(10), by(145), bx(190), by(149)],
          content: 'evil <script>alert(1)</script> & "quotes"',
          content_html: null,
        },
      ],
      markdown: "",
      raw: { parsing_res_list: [], marker: "mock-raw" },
    },
    error: null,
    meta: { elapsed_ms: 1234, model: "stub", mode: "e2e-mock" },
  };
}

async function runOcrWith(page: Page, payload: object) {
  await page.route("**/api/ocr", (route) => route.fulfill({ json: payload }));
  await page.goto("/");
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.getByRole("button", { name: "Run OCR" }).click();
}

test("results render, selection syncs by id with duplicate text, HTML stays escaped", async ({
  page,
}) => {
  await runOcrWith(page, envelope());

  await expect(page.getByText("5 blocks in")).toBeVisible();
  await expect(page.locator(".overlay-rect")).toHaveCount(5);

  // table rendered from sanitized HTML, no script/img elements injected
  await expect(page.locator(".block-table td")).toHaveCount(2);
  expect(await page.locator(".block-table script, .block-table img").count()).toBe(0);

  // raw content with <script> is shown as literal text, never executed/injected
  await expect(
    page.locator(".block-text", { hasText: 'evil <script>alert(1)</script> & "quotes"' }),
  ).toBeVisible();
  expect(await page.locator("script:has-text('alert')").count()).toBe(0);

  // click the SECOND duplicate-text block in the list; its own rect must select
  await page.locator(".block-button", { hasText: "Hong Kong" }).nth(1).click();
  await expect(page.locator("#block-opt-2 .block-button")).toHaveClass(/block-button-selected/);
  await expect(page.locator('.overlay-rect[aria-label="Region 2: text"]')).toHaveClass(
    /overlay-rect-selected/,
  );

  // clicking a region rect selects the matching row
  await page.locator('.overlay-rect[aria-label="Region 3: table"]').click();
  await expect(page.locator("#block-opt-3 .block-button")).toHaveClass(/block-button-selected/);

  // keyboard: ArrowDown moves to next block
  await page.locator(".block-list").focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.locator("#block-opt-4 .block-button")).toHaveClass(/block-button-selected/);

  // JSON download contains the raw payload
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download JSON" }).click(),
  ]);
  const path = await download.path();
  const saved = JSON.parse(readFileSync(path as string, "utf8"));
  expect(saved.marker).toBe("mock-raw");
});

test("overlay stays aligned with the image after viewport resize", async ({ page }) => {
  await runOcrWith(page, envelope());
  await expect(page.locator(".overlay-rect").first()).toBeVisible();

  const fractions = () =>
    page.evaluate(() => {
      const img = document.querySelector(".image-holder img");
      const svg = document.querySelector(".overlay");
      const rect = document.querySelector('.overlay-rect[aria-label="Region 3: table"]');
      if (!img || !svg || !rect) return null;
      const ir = img.getBoundingClientRect();
      const sr = svg.getBoundingClientRect();
      const tr = rect.getBoundingClientRect();
      return {
        covers: Math.abs(sr.x - ir.x) < 1 && Math.abs(sr.width - ir.width) < 1,
        x: (tr.x - sr.x) / sr.width,
        y: (tr.y - sr.y) / sr.height,
      };
    });

  await page.setViewportSize({ width: 1440, height: 900 });
  const wide = await fractions();
  await page.setViewportSize({ width: 800, height: 700 });
  const narrow = await fractions();

  expect(wide?.covers).toBe(true);
  expect(narrow?.covers).toBe(true);
  expect(Math.abs((wide?.x ?? 9) - (narrow?.x ?? 1))).toBeLessThan(0.001);
  expect(Math.abs((wide?.y ?? 9) - (narrow?.y ?? 1))).toBeLessThan(0.001);
  // 10/200 = 0.05, 100/150 = 0.667 per the virtual-canvas bbox
  expect(wide?.x).toBeCloseTo(0.05, 2);
  expect(wide?.y).toBeCloseTo(100 / 150, 2);
});

test("failed run shows a visible error and no stale results", async ({ page }) => {
  await runOcrWith(page, envelope());
  await expect(page.getByText("5 blocks in")).toBeVisible();

  // next run fails
  await page.route("**/api/ocr", (route) =>
    route.fulfill({
      status: 500,
      json: {
        success: false,
        data: null,
        error: { code: "inference_failed", message: "boom" },
        meta: null,
      },
    }),
  );
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await expect(page.locator(".block-item")).toHaveCount(0); // cleared when new file chosen
  await page.getByRole("button", { name: "Run OCR" }).click();

  await expect(page.locator(".error-banner")).toBeVisible();
  await expect(page.locator(".error-banner")).toContainText("inference_failed");
  await expect(page.locator(".block-item")).toHaveCount(0);
  await expect(page.locator(".overlay-rect")).toHaveCount(0);
  await expect(page.getByText("5 blocks in")).toHaveCount(0);
});
