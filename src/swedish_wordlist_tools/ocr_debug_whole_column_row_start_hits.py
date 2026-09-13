from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_left_edge_local_index import prepare_local_fingerprint_indexes, ranked_exact_local_hits
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_row_split_left_support import row_start_geometry, row_start_is_typographically_plausible
from .ocr_shadow_whole_column import _black_pixels, _column_bounds, _old_row_for_y


def main() -> int:
    ap = argparse.ArgumentParser(description="List exact legal whole-column row-start hits in a vertical window.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--y0", type=int, required=True)
    ap.add_argument("--y1", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--homonym-x", type=int, default=46)
    ap.add_argument("--headword-x", type=int, default=57)
    ap.add_argument("--continuation-x", type=int, default=68)
    ap.add_argument("--min-steps", type=int, default=3)
    args = ap.parse_args()
    if args.y1 < args.y0:
        raise ValueError("--y1 must be >= --y0")

    models = tuple(load_canonical_facit_with_typography(args.facit))
    prepared = prepare_local_fingerprint_indexes(models, max_steps=8, min_steps=args.min_steps, max_row_gap=1)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    geometry = row_start_geometry(args.homonym_x, args.headword_x, args.continuation_x)
    hits = ranked_exact_local_hits(
        black,
        max_steps=8,
        min_steps=args.min_steps,
        max_row_gap=1,
        max_x=geometry.late_start_limit_x,
        include_tiny_fallback=False,
        prepared=prepared,
    )
    old_rows = (context["row_map"].get("columns") or [])[args.column].get("rows") or []
    selected = []
    for hit in hits:
        top = hit.translate_y + hit.model.min_y
        bottom = hit.translate_y + hit.model.max_y + 1
        if bottom <= args.y0 or top > args.y1:
            continue
        if not row_start_is_typographically_plausible(hit.translate_x, geometry):
            continue
        selected.append((top, hit.translate_x, -hit.steps, hit.baseline, bottom, hit))
    selected.sort(key=lambda item: item[:5])

    print(
        f"row-start-hits: page={args.page} column={args.column} y={args.y0}..{args.y1} "
        f"hits={len(selected)} late_limit={geometry.late_start_limit_x}",
        flush=True,
    )
    by_old = Counter()
    by_baseline = Counter()
    for top, x, _neg_steps, baseline, bottom, hit in selected:
        old = _old_row_for_y(old_rows, top)
        by_old[old] += 1
        by_baseline[baseline] += 1
        print(
            f"hit: old={old if old is not None else 'none'} top={top} bottom={bottom} "
            f"baseline={baseline} x={x} steps={hit.steps} pixels={len(hit.model.pixels)} "
            f"glyph={hit.model.label!r}/{hit.model.style}",
            flush=True,
        )
    print("row-start-hits-by-old: " + " ".join(f"{k}:{v}" for k, v in sorted(by_old.items(), key=lambda kv: (-1 if kv[0] is None else kv[0]))), flush=True)
    print("row-start-hits-by-baseline: " + " ".join(f"{k}:{v}" for k, v in sorted(by_baseline.items())), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
