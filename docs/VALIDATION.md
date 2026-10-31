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

- backend: 20 pytest tests green (validation, sanitization, envelope, stub API)
- frontend: 6 vitest tests green (rect math, id stepping, filename)
- e2e: 3 Playwright tests green against mocked /api/ocr (sync by id with duplicate
  text, escaped HTML, resize alignment, failure clears stale results)
