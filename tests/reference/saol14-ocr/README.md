# SAOL14 OCR reference pages 1–20

This directory freezes exact-glyph OCR output from the older, proven SAOL14 OCR implementation so that the sequential raw-pixel OCR can be compared against a stable oracle while it is rebuilt.

## Provenance

- Historical OCR code commit: `4178de2275987f1b7a4b07467a50577b5321fa5a`
- Facit: `glyphs/saol14-manual-glyph-facit-v2.json`
- Facit SHA-256: `584ea2a720b51022ba31e4f4aa68b0664a8a9bfceac8282c0e0b658e1f165acb`
- Threshold: 210
- Pages: 1–20
- Rows: 3175 total (154 on page 1, 159 on each page 2–20)
- Result at generation: 3175/3175 rows `fully_exact=true`

Each `page-NNN.jsonl` contains the rendered text plus the exact glyph sequence and placement metadata for every row. The corresponding `page-NNN.meta.json` records provenance and the measured generation timings for that page, including page preparation, the ownership-settling pass, reference export pass, total time, and the slowest export rows.

The timing values are historical measurements, not pass/fail thresholds. They are retained as a performance baseline and will naturally vary with machine load and later implementations.

## Generation timing baseline

The 20 recorded page totals sum to approximately 730.16 seconds. The fastest recorded page was page 20 at approximately 19.60 seconds; the slowest was page 10 at approximately 72.02 seconds. See the individual `.meta.json` files for authoritative per-page timings.

## Intended use

The reference is an OCR regression oracle, not a claim that every glyph label is semantically ideal Unicode. In particular, a historical facit label may be unconventional; comparisons should preserve the frozen facit semantics. A new OCR implementation should reproduce the same glyph decomposition/output from the same source pixels and facit, or make any intentional difference explicit and reviewable.

The reference files were generated with `scripts/export_saol14_ocr_reference.py` from the historical checkout and committed separately in `39d8576`.
