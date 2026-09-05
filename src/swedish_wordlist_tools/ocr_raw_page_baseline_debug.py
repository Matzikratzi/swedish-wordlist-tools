from __future__ import annotations

"""Command-line probe for baseline-first matching against the raw page array."""

import argparse
from pathlib import Path

from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority
from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_raw_page_baseline_row import match_row_from_raw_page


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Match one SAOL row directly in the page pixel array without using page_bottom as an OCR crop."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = page_editor.build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    context["quiet_successful_ownership"] = True
    cached.bind_page_candidates(context, models)

    position = (args.column, args.row)
    if position not in context["positions"]:
        raise ValueError(f"row not found: page={args.page} column={args.column} row={args.row}")

    row_kind = priority.classify_row_start(context, position)
    priority.set_row_priority_hint(row_kind)
    result = match_row_from_raw_page(context, position, models)

    print(
        f"raw-page: page={args.page} column={args.column} row={args.row} "
        f"row_kind={row_kind} search_box={result.get('search_box')}"
    )
    print(
        f"raw-page: reason={result.get('reason')} baseline={result.get('baseline')} "
        f"legacy_page_bottom={result.get('legacy_page_bottom')} "
        f"matched_bottom={result.get('matched_bottom')} matched_pixels={result.get('matched_pixels', 0)}"
    )
    if result.get("candidate_baselines") is not None:
        print(f"raw-page: candidate_baselines={result['candidate_baselines']}")

    matches = result.get("matches") or []
    print(f"raw-page: matches={len(matches)} labels={result.get('labels','')!r}")
    for index, match in enumerate(matches):
        ys = [y for _x, y in match.pixels]
        xs = [x for x, _y in match.pixels]
        print(
            f"  {index:02d} {match.label!r} style={match.style} x={match.x} "
            f"baseline={match.baseline} page_bbox=({min(xs)},{min(ys)})..({max(xs)+1},{max(ys)+1}) "
            f"pixels={len(match.pixels)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
