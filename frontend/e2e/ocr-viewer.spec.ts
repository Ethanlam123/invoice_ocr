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
      pages: [
        { index: 0, width: FIXTURE_W, height: FIXTURE_H, mime: "image/png", data_url: DATA_URL },
      ],
      blocks: [
        {
          id: 0,
          order: 0,
          label: "text",
          bbox: [bx(10), by(10), bx(100), by(40)],
          content: "ACME Corp",
          content_html: null,
          page: 0,
          page_end: 0,
        },
        {
          id: 1,
          order: 1,
          label: "text",
          bbox: [bx(10), by(60), bx(100), by(90)],
          content: "Hong Kong", // duplicate text on purpose
          content_html: null,
          page: 0,
          page_end: 0,
        },
        {
          id: 2,
          order: 2,
          label: "text",
          bbox: [bx(110), by(60), bx(190), by(90)],
          content: "Hong Kong",
          content_html: null,
          page: 0,
          page_end: 0,
        },
        {
          id: 3,
          order: 3,
          label: "table",
          bbox: [bx(10), by(100), bx(190), by(140)],
          content: "<table><tr><td>a</td><td>b</td></tr></table>",
          content_html: "<table><tr><td>a</td><td>b</td></tr></table>",
          page: 0,
          page_end: 0,
        },
        {
          id: 4,
          order: 4,
          label: "text",
          bbox: [bx(10), by(145), bx(190), by(149)],
          content: 'evil <script>alert(1)</script> & "quotes"',
          content_html: null,
          page: 0,
          page_end: 0,
        },
      ],
      markdown: "",
      raw: { parsing_res_list: [], marker: "mock-raw" },
    },
    error: null,
    meta: { elapsed_ms: 1234, model: "stub", mode: "e2e-mock", page_count: 1 },
  };
}

function multiPageEnvelope() {
  // two pages sharing the fixture image; table block spans both pages
  const e = envelope();
  return {
    ...e,
    data: {
      ...e.data,
      pages: [e.data.pages[0], { ...e.data.pages[0], index: 1 }],
      blocks: [
        {
          id: 0,
          order: 0,
          label: "text",
          bbox: [10, 10, 100, 40],
          content: "ACME Corp",
          content_html: null,
          page: 0,
          page_end: 0,
        },
        {
          id: 1,
          order: 1,
          label: "table",
          bbox: [10, 60, 190, 140],
          content: "<table><tr><td>a</td><td>b</td></tr></table>",
          content_html: "<table><tr><td>a</td><td>b</td></tr></table>",
          page: 0,
          page_end: 1, // merged cross-page table
          page_bboxes: [
            { page: 0, bbox: [10, 60, 190, 140] },
            { page: 1, bbox: [10, 10, 190, 90] },
          ],
        },
        {
          id: 2,
          order: 2,
          label: "text",
          bbox: [10, 10, 100, 40],
          content: "Total: 99.00",
          content_html: null,
          page: 1,
          page_end: 1,
        },
      ],
    },
    meta: { ...e.meta, page_count: 2 },
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

test("upload stays locked during processing; a file change cannot race the run", async ({
  page,
}) => {
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/ocr", async (route) => {
    await held; // hold the run in "processing" phase
    await route.fulfill({ json: envelope() });
  });
  await page.goto("/");
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.getByRole("button", { name: "Run OCR" }).click();
  await expect(page.locator(".spinner")).toBeVisible();

  // upload surface is locked while a run is in flight
  await expect(page.locator(".dropzone")).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("button", { name: "Choose file" })).toBeDisabled();
  // a programmatic file change fires change but the handler ignores it while disabled
  await page.setInputFiles('input[type="file"]', FIXTURE);

  release?.();
  await expect(page.getByText("5 blocks in")).toBeVisible();
  await expect(page.locator(".block-item")).toHaveCount(5);
});

test("multi-page PDF result: pages stack, span table tags p.1-2, selection crosses pages", async ({
  page,
}) => {
  await runOcrWith(page, multiPageEnvelope());

  // both pages render, stacked, with captions
  await expect(page.locator(".image-frame")).toHaveCount(2);
  await expect(page.getByText("Page 1 / 2")).toBeVisible();
  await expect(page.getByText("Page 2 / 2")).toBeVisible();

  // page count chip in the status bar; span tag in the block list
  await expect(page.getByText("3 blocks in")).toBeVisible();
  await expect(page.getByText("2 pages")).toBeVisible();
  await expect(page.locator(".block-page", { hasText: "p.1-2" })).toBeVisible();

  // rects land on their pages: p1 has 2, p2 has text + the table continuation
  const frames = page.locator(".image-frame");
  await expect(frames.nth(0).locator(".overlay-rect")).toHaveCount(2);
  await expect(frames.nth(1).locator(".overlay-rect")).toHaveCount(2);
  await expect(frames.nth(1).locator(".overlay-rect-continuation")).toHaveCount(1);

  // the continuation rect on page 2 also selects the span table block
  await frames
    .nth(1)
    .locator('.overlay-rect[aria-label="Region 1: table (spans pages)"]')
    .click();
  await expect(page.locator("#block-opt-1 .block-button")).toHaveClass(
    /block-button-selected/,
  );
  await expect(frames.nth(0).locator(".overlay-rect-selected")).toHaveCount(1);

  // selecting a page-2 block from the list highlights its rect on page 2 only
  await page.locator("#block-opt-2 .block-button").click();
  await expect(
    frames.nth(1).locator('.overlay-rect[aria-label="Region 2: text"]'),
  ).toHaveClass(/overlay-rect-selected/);
  expect(
    await frames.nth(0).locator(".overlay-rect-selected").count(),
  ).toBe(0);

  // the span table renders its sanitized HTML and lives in the list once
  await expect(page.locator(".block-table td")).toHaveCount(2);
});
