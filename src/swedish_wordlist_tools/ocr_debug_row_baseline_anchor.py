from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Show baseline-anchor diagnostics for one OCR row")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    position = (args.column, args.row)
    state = load_review_state_pixel_array(context, position, models)

    print(f"page={args.page} column={args.column} row={args.row}")
    for key in (
        "text",
        "baseline",
        "baseline_anchor",
        "covered_pixels",
        "source_pixels",
        "unmatched_pixels",
        "fully_exact",
        "exact_cover_path",
    ):
        print(f"{key}={state.get(key)!r}")

    matches = state.get("matches") or []
    print(f"matches={len(matches)}")
    for index, match in enumerate(matches):
        top = min(y for _x, y in match.pixels)
        bottom = max(y for _x, y in match.pixels)
        left = min(x for x, _y in match.pixels)
        right = max(x for x, _y in match.pixels)
        print(
            f"match[{index}] label={match.label!r} style={match.style!r} "
            f"x={match.x} baseline={match.baseline} bbox=({left},{top})-({right},{bottom}) "
            f"pixels={match.model_pixels} sources={match.sources}"
        )

    ink = set(state.get("source_ink_points") or [])
    covered = set().union(*(set(match.pixels) for match in matches)) if matches else set()
    residual = sorted(ink - covered, key=lambda point: (point[1], point[0]))
    print(f"residual_pixels={len(residual)}")
    if residual:
        by_y: dict[int, list[int]] = {}
        for x, y in residual:
            by_y.setdefault(y, []).append(x)
        for y in sorted(by_y):
            xs = sorted(by_y[y])
            print(f"residual y={y}: x={xs}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
