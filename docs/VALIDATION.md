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
