import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

/**
 * The /history page: browse what is stored, search it, delete, and deep-link
 * back into the viewer. API routes are mocked - the SQL side (counts, cascade
 * delete) is covered by backend/tests/test_db.py.
 */

const FIXTURE = join(__dirname, "fixtures", "upload.png");
const FIXTURE_BYTES = readFileSync(FIXTURE);
const DATA_URL = `data:image/png;base64,${FIXTURE_BYTES.toString("base64")}`;

function storedEnvelope() {
  return {
    success: true,
    data: {
      pages: [
        {
          index: 0,
          width: FIXTURE_BYTES.readUInt32BE(16),
          height: FIXTURE_BYTES.readUInt32BE(20),
          mime: "image/png",
          data_url: DATA_URL,
        },
      ],
      blocks: [
        {
          id: 0, order: 0, label: "text", bbox: [10, 10, 100, 40],
          content: "ACME Corp", content_html: null, page: 0, page_end: 0,
        },
      ],
      markdown: "",
      raw: { marker: "history-e2e" },
    },
    error: null,
    meta: {
      elapsed_ms: 500, model: "stub", mode: "e2e-mock", page_count: 1,
      document_id: 7, filename: "invoice-a.png",
    },
  };
}

const listBody = {
  success: true,
  data: {
    documents: [
      {
        id: 7, filename: "invoice-a.png", doc_type: "invoice", page_count: 1,
        quality_flags: [], created_at: "2026-11-02T11:00:00+00:00",
        block_count: 3, reviewed_count: 1,
      },
      {
        id: 6, filename: "receipt-b.png", doc_type: "receipt", page_count: 2,
        quality_flags: ["garbled_text"], created_at: "2026-11-01T10:00:00+00:00",
        block_count: 5, reviewed_count: 0,
      },
    ],
  },
  error: null,
  meta: { count: 2 },
};

test("lists stored documents with counts and flags; search filters", async ({ page }) => {
  await page.route("**/api/documents", (route) => route.fulfill({ json: listBody }));
  await page.goto("/history");

  await expect(page.locator(".history-table tbody tr")).toHaveCount(2);
  const row = page.locator(".history-table tbody tr").first();
  await expect(row.locator(".history-open")).toHaveText("invoice-a.png");
  await expect(row.locator(".history-open")).toHaveAttribute("href", "/?doc=7");
  await expect(row).toContainText("1/3"); // reviewed / blocks
  await expect(page.locator("tr", { hasText: "receipt-b.png" })).toContainText("garbled_text");

  await page.getByLabel("Search documents").fill("receipt");
  await expect(page.locator(".history-table tbody tr")).toHaveCount(1);
  await page.getByLabel("Search documents").fill("zzz");
  await expect(page.locator(".history-note")).toContainText("No document matches");
});

test("delete asks for confirmation and removes the row only when confirmed", async ({ page }) => {
  let docs = [...listBody.data.documents];
  await page.route("**/api/documents/7", (route) => {
    docs = docs.filter((d) => d.id !== 7);
    return route.fulfill({ json: { success: true, data: null, error: null, meta: null } });
  });
  await page.route("**/api/documents", (route) =>
    route.fulfill({ json: { ...listBody, data: { documents: docs } } }),
  );
  const messages: string[] = [];
  page.on("dialog", (dialog) => {
    messages.push(dialog.message());
    void dialog.dismiss(); // first answer: cancel
  });
  await page.goto("/history");

  const row = page.locator("tr", { hasText: "invoice-a.png" });
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(row).toHaveCount(1); // cancelled: still there

  page.removeAllListeners("dialog");
  page.on("dialog", (dialog) => void dialog.accept());

  await row.getByRole("button", { name: "Delete" }).click();
  await expect(page.locator("tr", { hasText: "invoice-a.png" })).toHaveCount(0);
  await expect(page.locator(".history-table tbody tr")).toHaveCount(1); // receipt-b stays
  expect(messages[0]).toContain("invoice-a.png");
});

test("persistence off shows the notice instead of the table", async ({ page }) => {
  await page.route("**/api/documents", (route) =>
    route.fulfill({
      status: 503,
      json: { success: false, data: null, error: { code: "persistence_disabled", message: "off" }, meta: null },
    }),
  );
  await page.goto("/history");
  await expect(page.locator(".history-note")).toContainText("History is unavailable");
  await expect(page.locator(".history-table")).toHaveCount(0);
});

test("a filename opens the stored document in the viewer via /?doc=", async ({ page }) => {
  await page.route("**/api/documents", (route) => route.fulfill({ json: listBody }));
  await page.route("**/api/documents/7", (route) => route.fulfill({ json: storedEnvelope() }));
  await page.goto("/history");

  await page.locator(".history-open", { hasText: "invoice-a.png" }).click();
  await expect(page).toHaveURL(/\/\?doc=7$/);
  await expect(page.getByText("1 blocks in")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save to history" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "History" })).toBeVisible();
});
