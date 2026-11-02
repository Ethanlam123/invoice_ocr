import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * The Save flow: an OCR run stores nothing by itself; the reviewer clicks
 * "Save to history" to persist it, which also unlocks block corrections.
 * API routes are mocked - the SQL side is covered by backend/tests/test_db.py.
 */

const FIXTURE = join(__dirname, "fixtures", "upload.png");
const FIXTURE_BYTES = readFileSync(FIXTURE);
const FIXTURE_W = FIXTURE_BYTES.readUInt32BE(16);
const FIXTURE_H = FIXTURE_BYTES.readUInt32BE(20);
const DATA_URL = `data:image/png;base64,${FIXTURE_BYTES.toString("base64")}`;

function ocrEnvelope() {
  return {
    success: true,
    data: {
      pages: [
        { index: 0, width: FIXTURE_W, height: FIXTURE_H, mime: "image/png", data_url: DATA_URL },
      ],
      blocks: [
        {
          id: 0, order: 0, label: "text", bbox: [10, 10, 100, 40],
          content: "ACME Corp", content_html: null, page: 0, page_end: 0,
        },
      ],
      markdown: "",
      raw: { marker: "save-e2e" },
    },
    error: null,
    meta: {
      elapsed_ms: 500, model: "stub", mode: "e2e-mock", page_count: 1,
      doc_type: "invoice", quality_flags: [],
    },
  };
}

const historyBody = {
  success: true,
  data: {
    documents: [
      {
        id: 7, filename: "stored.png", doc_type: "invoice", page_count: 1,
        quality_flags: [], created_at: "2026-11-02T11:00:00+00:00",
      },
    ],
  },
  error: null,
  meta: { count: 1 },
};

interface Harness {
  savedBodies: object[];
  historyCalls: () => number;
}

async function setup(page: Page): Promise<Harness> {
  const harness: Harness = { savedBodies: [], historyCalls: () => 0 };
  let historyCalls = 0;
  await page.route("**/api/documents", (route) => {
    // POST = the Save button; GET = history strip
    if (route.request().method() === "POST") {
      harness.savedBodies.push(route.request().postDataJSON() as object);
      return route.fulfill({ json: { success: true, data: null, error: null, meta: { document_id: 7 } } });
    }
    historyCalls += 1;
    return route.fulfill({ json: historyBody });
  });
  await page.route("**/api/ocr", (route) => route.fulfill({ json: ocrEnvelope() }));
  harness.historyCalls = () => historyCalls;
  return harness;
}

async function runOcr(page: Page) {
  await page.goto("/");
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.getByRole("button", { name: "Run OCR" }).click();
  await expect(page.getByText("1 blocks in")).toBeVisible();
}

test("no Save button when the backend has no history (persistence off)", async ({ page }) => {
  await page.route("**/api/documents", (route) =>
    route.fulfill({
      status: 503,
      json: { success: false, data: null, error: { code: "persistence_disabled", message: "off" }, meta: null },
    }),
  );
  await page.route("**/api/ocr", (route) => route.fulfill({ json: ocrEnvelope() }));
  await runOcr(page);

  await expect(page.getByRole("button", { name: "Save to history" })).toHaveCount(0);
});

test("run stores nothing; Save persists, unlocks corrections, then disappears", async ({ page }) => {
  const h = await setup(page);
  await runOcr(page);

  // the run itself wrote nothing
  expect(h.savedBodies).toHaveLength(0);
  await expect(page.locator(".history-item")).toHaveCount(1);
  await expect(page.locator(".history-item").first()).not.toHaveClass(/history-item-active/);

  // unsaved result: no correct affordance yet
  await page.locator(".block-button").first().click();
  await expect(page.locator(".block-toggle-correct")).toHaveCount(0);

  // Save -> POST /api/documents with the run's payload
  await page.getByRole("button", { name: "Save to history" }).click();
  await expect(page.getByRole("button", { name: "Save to history" })).toHaveCount(0);
  expect(h.savedBodies).toHaveLength(1);
  const body = h.savedBodies[0] as Record<string, unknown>;
  expect(body.filename).toBe("upload.png");
  expect(body.doc_type).toBe("invoice");
  expect((body.blocks as unknown[]).length).toBe(1);

  // stored now: history marks it active and corrections are unlocked
  await expect(page.locator(".history-item").first()).toHaveClass(/history-item-active/);
  await expect(page.locator(".block-toggle-correct")).toBeVisible();
});

test("a failed save shows an error and the button stays for retry", async ({ page }) => {
  await page.route("**/api/documents", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 500,
        json: { success: false, data: null, error: { code: "storage_failed", message: "boom" }, meta: null },
      });
    }
    return route.fulfill({ json: historyBody });
  });
  await page.route("**/api/ocr", (route) => route.fulfill({ json: ocrEnvelope() }));
  await runOcr(page);

  await page.getByRole("button", { name: "Save to history" }).click();
  await expect(page.locator(".error-banner")).toContainText("save_failed");
  await expect(page.getByRole("button", { name: "Save to history" })).toBeVisible();
  // no corrections unlocked by a failed save
  await page.locator(".block-button").first().click();
  await expect(page.locator(".block-toggle-correct")).toHaveCount(0);
});

test("a document opened from history is already stored: no Save button", async ({ page }) => {
  await page.route("**/api/documents", (route) => route.fulfill({ json: historyBody }));
  const stored = { ...ocrEnvelope(), meta: { ...ocrEnvelope().meta, document_id: 7, filename: "stored.png" } };
  await page.route("**/api/documents/7", (route) => route.fulfill({ json: stored }));
  await page.goto("/");

  await page.locator(".history-item", { hasText: "stored.png" }).click();
  await expect(page.getByText("1 blocks in")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save to history" })).toHaveCount(0);
  await page.locator(".block-button").first().click();
  await expect(page.locator(".block-toggle-correct")).toBeVisible();
});
