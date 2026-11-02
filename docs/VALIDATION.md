# Real-Inference Validation Log

Environment: Apple M2 (8-core, 16 GB), macOS, uv 0.13.0, Node 26.
Versions: paddleocr 3.7.0, paddlepaddle 3.2.1 (CPU), mlx-vlm 0.7.11, mlx 0.32.4,
model mlx-community/PaddleOCR-VL-1.6-4bit. Date: 2026-10-31.

## Full pipeline gate (before any UI work)

`scripts/run_real_inference.py samples/invoice_sample.png` (1240x1600 synthetic invoice):

- pipeline init 19.1 s (includes first-run PP-DocLayoutV3 download), inference 15.7 s
- 12 blocks; `parsing_res_list` fields confirmed: block_id, block_order, block_label,
  block_bbox [x1,y1,x2,y2], block_content (table blocks contain HTML)
- result JSON top-level keys: width, height, input_path, layout_det_res,
  model_settings, page_count, page_index, parsing_res_list (no `markdown` key in this
  version; the API handles its absence)
- all bboxes within image bounds; width/height keys match the input image exactly
- `block_order` is null for header/table/footer blocks; backend falls back to block_id
- saved output: `docs/real_inference_invoice_sample.json`

## API end-to-end (curl, real model)

POST /api/ocr with samples/invoice_sample.png: success, 17418 ms elapsed,
12 blocks, sanitized table HTML present, normalized PNG data URL returned.

## Browser session (Chrome via DevTools, real model)

Verified manually on http://localhost:3000 with samples/invoice_sample.png:

- upload -> preview -> Run OCR -> "12 blocks in 12.6 s" with model name shown
- SVG region buttons for all 12 blocks over the normalized image
- list click -> rect highlight: row 05 (FROM address) selected its region only
- rect click -> row selection: Region 6 (BILL TO address, duplicate text
  "Hong Kong" also in block 4) selected block-opt-6, not block-opt-4
- keyboard: ArrowDown moved selection 6 -> 7 with the rect following
- geometry check: table rect fractions x=0.0629 y=0.3113 map back to the pipeline
  bbox [78, 498, 1171, 916] exactly (0.0629x1240=78, 0.3113x1600=498)
- resize 1440->1200 wide (image 885 px -> 669 px): fractions identical to 6 decimals
- table block rendered 8 rows from sanitized HTML; zero script/img/iframe in DOM
- notes containing `<b>...</b>` and `<per month>` displayed as literal text
- Download JSON produced the full raw pipeline result (8 keys, 12 blocks)
- corrupt file (text bytes named .png): alert "UNDECODABLE - File is not a
  decodable image.", no stale results, no fake success
- console: no errors (only dev-server HMR logs)

## Dataset samples (qualitative only)

5 images from mychen76/invoices-and-receipts_ocr_v1 (train rows 0,1,10,100,101;
fetched via datasets-server rows API into gitignored eval_samples/). All re-run
through the real model via the API - see docs/eval_summary.json:

| image    | blocks | API elapsed | invoice_no found | invoice_date found |
| -------- | ------ | ----------- | ---------------- | ------------------ |
| ds_0     | 13     | 15.2 s      | yes              | yes                |
| ds_1     | 13     | 17.9 s      | yes              | yes                |
| ds_10    | 13     | 18.3 s      | yes              | yes                |
| ds_100   | 13     | 18.9 s      | yes              | yes                |
| ds_101   | 13     | 18.9 s      | yes              | yes                |

"found" means the invoice number / date string from the dataset's stored
parsed_data annotation appears verbatim in our fresh OCR text. This is a
smoke-level agreement signal between our run and the stored annotations
(annotations are not verified ground truth), NOT an accuracy metric.

## Observed OCR behavior (anecdotes, not metrics)

- Synthetic invoice: address blocks truncated in content at ~70 chars preview but
  full in raw JSON; email addresses recognized consistently.
- Dataset receipts (SROIE-style, small fonts): all key header fields recovered;
  store name/number blocks occasionally merged with neighboring text.
- No CJK document has been run yet; no accuracy or latency claims beyond the
  numbers above; no comparison made against other quantizations.

## Automated suites (no model involved)

- backend: 23 pytest tests green (validation, sanitization, envelope, stub API,
  chunked upload cap, input_path strip, 422 envelope)
- frontend: 6 vitest tests green (rect math, id stepping, filename)
- e2e: 4 Playwright tests green against mocked /api/ocr (sync by id with duplicate
  text, escaped HTML, resize alignment, failure clears stale results, upload
  locked during processing)

## Post-review fixes and re-verification

An independent code review flagged 2 HIGH / 1 MEDIUM / 4 LOW issues; all HIGH and
MEDIUM plus three LOWs were fixed and re-verified on 2026-10-31:

- scripts/dev.sh backend launch failed from repo root (ModuleNotFoundError) - now
  runs uvicorn from backend/; re-tested with a full clean start of all three
  services and a real 21.4 s inference through that stack.
- upload/replace stayed live during processing (stale cross-file results, double
  run, orphaned interval) - upload surface now disabled while processing; e2e
  regression test added holding the response and attempting a file swap.
- oversized request bodies were fully buffered before the size cap - now read in
  1 MB chunks with a running cap (413 before buffering).
- API response no longer contains the backend temp-file path (input_path).
- FastAPI 422s (missing file field) now return the standard error envelope.
- frontend request now has a 5 min timeout with a distinct timeout error.
- Remaining accepted risks (documented in README): error messages may embed
  library exception text (localhost-only scope); lazy backend init race made
  negligible via async dependency.

## Post-audit fixes (same day)

A full repo audit found 8 issues (0 must-fix); all fixed:

- normalization failures now return the error envelope (500
  `normalization_failed`) instead of FastAPI's default body; malformed or
  non-object pipeline output is covered by a new pytest case (24 total)
- docs/eval_summary.json scrubbed of dataset-derived field values (booleans
  kept); eval_dataset.py no longer persists them
- OCR_BACKEND=stub documented in README (API without any model)
- module-level imports in main.py; unused generator param removed
- img width/height set from known dimensions (preview and result) to stop
  layout jumps; downloadJson defers revokeObjectURL for Safari
- dev.sh refuses to start when any of its ports is busy

## Multi-page PDF support (2026-11-02)

Design (verified against installed paddlex 3.7.2 source before building): PDF
uploads are rendered page by page with pypdfium2 (already a paddleocr dep, no
new packages) at 150 DPI; each page PNG goes through the exact single-image
path, so block_bbox keeps referring to pixels we also return as page images.
Cross-page merging uses the engine's own `restructure_pages(merge_tables=True)`
(MinerU-derived `merge_tables_across_pages`): the owner table keeps the full
HTML, the continuation fragment is emptied and group-linked; the backend reads
that linkage from JSON (`global_group_id != global_block_id`) and extends the
owner's `page_end`, adds `page_bboxes` (one bbox per page), and drops the
fragment from the list.

Merge conditions (from `merge_table.py`): both tables' widths within 10%,
prev-page table followed only by footer-class blocks, next-page table preceded
only by header/number-class blocks (or "continued" text), and matching column
counts. Conservative by design.

- `samples/multi_page_invoice.pdf` (ours, 2 pages, table straddling the break,
  built to satisfy the conditions): live API run 16.6 s cold / 11-17 s warm,
  8 blocks, table block spans p.1-2, merged HTML = 13 rows (header + 8 + 4
  rows from the two pages), fragment not emitted, both pages' bboxes present.
- Browser session (Chrome via DevTools): pages stacked with captions, page
  count chip, block tags p.1 / p.1-2 / p.2, selecting the span table
  highlights a solid rect on page 1 AND a dashed continuation rect on page 2
  (SVG `fill:none` needs `pointer-events: all` to stay clickable - found by an
  e2e hang, fixed).
- drew-pp/invoice-extraction-benchmark (CC-BY-4.0, fetched, never committed):
  clean-gb-serif / clean-us-clean-simple / clean-nl-two-column all 1 page,
  7-8 blocks, ~8.5 s each; gb-serif fields verified by eye (TAX INVOICE,
  IN0049923, dated items table with Qty / Unit Price / Amount).
- hwyin04/table-cross-page (no license - eval only): first 3 pages of a
  33-page wiki article: 50 blocks in 47.6 s; NO cross-page merge triggered
  (wiki layout violates the prev/next-neighbor conditions). Recorded as the
  honest counter-example: the heuristic is conservative; no false merges
  observed either.
- Limits: max 8 PDF pages (`too_many_pages`, 400) - 8 x ~20 s stays under the
  5 min client timeout; rendered pages obey the same min-side / max-pixel caps.

Automated suites after the change: 36 pytest (24 existing + 12 new: PDF magic,
render dims, page cap, corrupt PDF, multi-page normalize, span page_bboxes,
markdown join, PDF envelope, too_many_pages API), 8 vitest (pageLabel added),
5 e2e (multi-page rendering/span/selection added). Also fixed a pre-existing
issue: vitest had been collecting e2e/*.spec.ts and failing the file on every
`npm test` run (visible at the previous HEAD); `frontend/vitest.config.ts` now
scopes vitest to src/.

## Postgres persistence, Phase 0 (2026-11-02)

Local Postgres 17.11 (Homebrew, `brew services`), database `invoice_ocr`.
Schema applied automatically on first use (`backend/app/schema.sql`, idempotent,
verified by `\dt` after the first request). No ORM: four fixed statements
(discussion in README).

- Live stub-mode browser session (backend on :8000 with `DATABASE_URL`,
  frontend on :3000): uploaded `samples/multi_page_invoice.pdf`, run
  persisted as document id 14. `psql` verified all three tables: documents
  row (filename/mime/page_count=2/doc_type=unknown/mode=stub), two
  document_pages rows (1241x1754, paths under `data/documents/14/`), four
  blocks rows including the cross-page table (page=0, page_end=1) and the
  page-2 text block (block_id=11).
- History strip appeared after the run (filename / unknown / 2 pages /
  timestamp). "New document" reset, then clicking the strip entry re-rendered
  the stored document identically to the live result (2 page frames, 5 rects,
  active entry highlighted); pages are re-read from disk and served as the
  same data-URL shape, so the viewer uses one rendering path for live and
  stored documents. Console clean (no errors/warnings).
- One vision review of the live screenshot: strip, highlight, p.1-2 tag and
  layout confirmed correct; reported block/content mismatches are expected
  stub behavior (placeholder blocks over the real page image). One real copy
  fix from it: the page-count tag read "p.2" (looked like "page 2"); now
  "2 pages".
- Test-isolation bug found by the suites: with a real backend running, e2e
  pages fetched the real `/api/documents` and matched a live DB row, breaking
  the multi-page spec (`getByText("2 pages")` strict-mode violation). All e2e
  tests now mock `/api/documents` (`mockEmptyHistory`), verified green with
  the real backend still running.
- Real-model note: the OCR path itself is unchanged since commit cf365f1;
  this phase only appends persistence after a successful run (stub-verified
  live above; the SQL path is exercised by the gated tests with the same
  code). No new latency or accuracy claims.

Suites: 47 pytest with `TEST_DATABASE_URL` (42 without, 5 gated skips),
ruff clean, tsc clean, 8 vitest, 6 e2e, production build clean.

## Phase 1: rule classification + quality flags (2026-11-02)

`app/classify.py` (keyword rules, hard 1.0/0.0 confidence) and
`app/quality.py` (garbled / sparse / ragged-table flags); results stored on
documents (doc_type, quality_flags) and surfaced in meta + the status bar.

Measurement on real inference (MLX-VLM up, real mode, 7 files, ~12-21 s each,
all persisted to Postgres as a side-effect check of real-mode persistence):

| file | doc_type | truth |
| ---- | -------- | ----- |
| ds_0 / ds_1 / ds_10 / ds_100 / ds_101 (mychen76) | invoice | invoice (ds_10/100/101 confirmed by image inspection; the word lands in header/paragraph_title blocks depending on layout) |
| invoice_sample.png | invoice | invoice |
| multi_page_invoice.pdf | invoice | invoice |

7/7 correct in this run. Honest caveats measured along the way:

- Recognition variance is real: ds_1's "Invoice no: 61356291" line was read
  as Thai-garbled text ("ะทีโทรทัศน์: No:...") on one of three runs, and the
  classifier then correctly returned unknown - the keyword was simply not in
  the OCR output. Classification is bounded by recognition quality; this is
  the concrete motivation for Phase 2 verification and, if needed, Phase 4.
- Two input-selection bugs found by measurement and fixed: keywords in text
  blocks were never seen when title blocks existed (now heading-class blocks
  + first 3 text blocks are joined), and label "header" was not in the
  heading set (mychen76 puts "Invoice no" there).
- quality_flags stayed empty on all 7 clean samples (expected); the Thai
  garble does NOT trigger the garbled heuristic (Thai characters count as
  alnum) - recorded as a known limitation of script-agnostic heuristics.

Suites: 12 new classify/quality tests; 59 pytest with TEST_DATABASE_URL
(54 + 5 gated skips without), ruff, tsc, 8 vitest, 6 e2e (doc_type + flag
chip assertions added), production build clean.

## Phase 2: regex field extraction + arithmetic checks (2026-11-02)

`app/extract.py`: per-doc-type schema registry (Python dict; invoice first),
named-group regexes over block text, one joined-text fallback pass for
label/value pairs split across blocks, and arithmetic validation
(subtotal - discount + shipping + tax == total, qty x price == line amount,
items sum == subtotal). Failures mark fields needs_review and merge into
quality_flags; amounts are never auto-corrected.

Measured on the same 7 real-inference files (each round below re-ran the
full pipeline; recognition itself varied slightly between rounds):

- invoice_no 7/7, issue_date 7/7 (after the cross-block fallback pass).
- Totals against dataset annotations (mychen76 prints EU decimals):
  ds_0 "7,50" -> 7.5 == annotated net 7.50; ds_1 -> 192.81 == 192.81;
  ds_10 "$ 1 606,67" -> 1606.67 == 1606.67. All three were wrong before the
  number-format fixes below. ds_100/ds_101 totals extracted self-consistently
  (494.96 / 52257.34) but their annotation rows could not be re-matched by
  offset, so they stay unverified.
- Both self-made invoices pass arithmetic exactly (8600 + 860 == 9460;
  subtotal == total on the no-tax fixture).
- Zero arithmetic false positives across all runs.

Bugs the measurement caught and fixed (each now has a regression test):

1. EU decimal comma read as thousands ("$7,50" -> 7.0): money patterns and
   table-cell numbers now parse US, EU and space-thousands formats
   ("1,606.67" / "1.606,67" / "1 606,67"); a lone separator before exactly
   3 digits is treated as thousands.
2. Labels and values split across blocks ("Date of issue:" + next block):
   single-block misses get one pass over the joined text (block=None).
3. "Tax (10%):" style not matched; currency vocabulary missed HK$/US$/... -
   both added.
4. A "Gross worth" table header grabbed the next row's item quantity (1.0)
   as the total: table flattening now keeps row boundaries (</tr> -> newline,
   trailing spaces stripped) and money labels must have their value on the
   same line.
5. US-style dates (10/15/2012) flagged invalid: both day-first and month-first
   are accepted; the check catches garble (13/45), not reading order.

Known boundary, recorded honestly: mychen76's SUMMARY tables put
net/VAT/gross in aligned columns; the extractor finds the net total line
(values exactly match annotations) but cannot align a column header to its
value - that needs structure-aware parsing or a model extractor, which is
the Phase 4 decision point. mychen76 subtotal/tax are column-aligned too,
so the arithmetic check only fires on documents with line-style totals
(both self-made invoices).

Suites: 70 pytest (+5 gated; 75 with TEST_DATABASE_URL), ruff, tsc,
8 vitest, 6 e2e, production build all green.

## Phase 3: review flow - block corrections (2026-11-02)

`PATCH /api/documents/{id}/blocks/{block_id}` stores `corrected_content` +
`reviewed_at`; `GET /api/documents/{id}` returns the corrected text as the
block content with `reviewed: true` (stale table HTML is dropped for a
corrected block). CORS now allows PATCH (the preflight OPTIONS was rejected
before - caught live, not by any unit test: stub API tests run same-origin).

Frontend: on a stored document, selecting a non-table block shows a
"correct" toggle; the editor (textarea + save/cancel) PATCHes and updates
the block in place with a "reviewed" chip. History items show a flag count
badge. Table blocks are not hand-editable (model HTML).

- Live stub-mode browser session (doc 118, a real earlier inference result):
  correction round trip verified - PATCH -> psql row (`corrected_content`,
  `reviewed_at` set) -> reload page -> reopen from history -> corrected text
  and reviewed chip served from the DB.
- One vision review of the open editor: textarea/buttons/reviewed chip/选中态
  all correct; two notes - the "correct" toggle is hidden while the editor is
  open (by design), and the editor's right border sits flush with the pane
  edge (cosmetic, left as is).
- e2e (mocked API): list badge, select -> correct -> save fires PATCH with
  the exact body, UI shows the reviewed chip and updated text.

Suites: 70 pytest (+7 gated; 77 with TEST_DATABASE_URL), ruff, tsc,
8 vitest, 7 e2e, production build all green.
