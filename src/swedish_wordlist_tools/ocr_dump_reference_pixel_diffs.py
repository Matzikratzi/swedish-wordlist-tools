from __future__ import annotations

"""Dump reference/current OCR row-pixel differences as readable ASCII art.

Diagnostic only.  For each row whose source-pixel count differs from the frozen
reference, print the neighbouring rows and a small raw-page raster around the
row.  The reference JSONL does not contain source-pixel coordinates, so this
report deliberately distinguishes what is proven from what still needs visual
inspection: reference/current counts and current raw-page pixels.
"""

import argparse
import json
from pathlib import Path

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_forward_page_scan import scan_page_forward
from .ocr_glyph_review_delete import load_facit_with_typography


def _load_reference(path: Path) -> dict[tuple[int, int], dict]:
    rows = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                item = json.loads(line)
                rows[(int(item["column"]), int(item["row"]))] = item
    return rows


def _final_rows(fast_rows, fallback_rows):
    fallback = {(r.column, r.row): r for r in fallback_rows}
    return {(r.column, r.row): fallback.get((r.column, r.row), r) for r in fast_rows}


def _crop_for_position(context, key):
    # Use the same crop constructor as the scanner so the ASCII raster is the
    # exact current row image being analysed, not a separately guessed crop.
    position = next(p for p in context["positions"] if tuple(p[:2]) == key)
    crop = page_editor._crop_for_position(context, position)
    return crop


def _ascii_crop(crop, threshold: int, max_width: int = 190) -> list[str]:
    gray = crop.image.convert("L")
    width = min(gray.width, max_width)
    pix = gray.load()
    out = []
    for y in range(gray.height):
        chars = ["#" if pix[x, y] < threshold else " " for x in range(width)]
        line = "".join(chars).rstrip()
        out.append(f"{y:02d} {line}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Dump readable raw-row rasters for OCR reference pixel-count differences.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--reference-dir", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int)
    ap.add_argument("--row", type=int)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--context-rows", type=int, default=1)
    ap.add_argument("--max-width", type=int, default=190)
    args = ap.parse_args()

    reference = _load_reference(args.reference_dir / f"page-{args.page:03d}.jsonl")
    models = load_facit_with_typography(args.facit)
    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    context["quiet_successful_ownership"] = True
    fast_rows, fallback_rows = scan_page_forward(context, models)
    actual = _final_rows(fast_rows, fallback_rows)

    diffs = []
    for key in sorted(set(reference) & set(actual)):
        ref = reference[key]
        cur = actual[key]
        if int(ref["source_pixels"]) != int(cur.source_pixels):
            if args.column is not None and key[0] != args.column:
                continue
            if args.row is not None and key[1] != args.row:
                continue
            diffs.append((key, ref, cur))

    print(f"OCR PIXEL-DIFF DUMP page={args.page} differences={len(diffs)}")
    print("Legend: # = black source pixel in current scanner crop")
    print("NOTE: frozen reference stores pixel COUNT, not pixel coordinates; this dump does not invent reference coordinates.")
    print()

    for index, (key, ref, cur) in enumerate(diffs, 1):
        col, row = key
        print("=" * 100)
        print(f"DIFF {index}/{len(diffs)}  page={args.page} column={col} row={row}")
        print(f"REF {ref['source_pixels']:5d}px  {ref['text']}")
        print(f"NEW {cur.source_pixels:5d}px  {cur.text}")
        print(f"DELTA {int(cur.source_pixels) - int(ref['source_pixels']):+d}px  exact={cur.exact} covered={cur.covered_pixels}")
        print()

        for rr in range(max(0, row - args.context_rows), row + args.context_rows + 1):
            rkey = (col, rr)
            if rkey not in reference or rkey not in actual:
                continue
            marker = ">>>" if rr == row else "   "
            rref = reference[rkey]
            rcur = actual[rkey]
            print(f"{marker} c{col} r{rr:03d}  REF={rref['source_pixels']} NEW={rcur.source_pixels}  {rcur.text}")
        print()

        try:
            crop = _crop_for_position(context, key)
            print(f"CURRENT ROW RASTER  width={crop.width} height={crop.height}  (truncated to {args.max_width} columns)")
            for line in _ascii_crop(crop, args.threshold, args.max_width):
                print(line)
        except Exception as exc:
            print(f"CURRENT ROW RASTER unavailable: {exc}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
