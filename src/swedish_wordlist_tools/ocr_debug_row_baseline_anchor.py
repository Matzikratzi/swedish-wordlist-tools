from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def _point_set(rows) -> set[tuple[int, int]]:
    return {(int(point[0]), int(point[1])) for point in (rows or [])}


def _print_state(prefix: str, state: dict) -> None:
    print(
        f"{prefix}: c{state['column']} r{state['row']} "
        f"revision={state.get('pixel_owner_row_revision')} "
        f"pixels={state.get('covered_pixels')}/{state.get('source_pixels')} "
        f"exact={state.get('fully_exact')} text={state.get('text')!r}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Show baseline-anchor diagnostics for one OCR row")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument(
        "--warm-through-prior-rows",
        action="store_true",
        help="analyse all earlier rows in the same column first, like the page scanner",
    )
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    position = (args.column, args.row)

    if args.warm_through_prior_rows:
        target_revision = lambda: int(
            (context.get("pixel_owner_row_revisions") or {}).get(position, 0)
        )
        previous_revision = target_revision()
        print(f"target-before: c{args.column} r{args.row} revision={previous_revision}")
        for prior_row in range(args.row):
            prior = (args.column, prior_row)
            prior_state = load_review_state_pixel_array(context, prior, models)
            _print_state("prior", prior_state)
            current_revision = target_revision()
            if current_revision != previous_revision:
                print(
                    f"TARGET OWNER CHANGED while analysing c{args.column} r{prior_row}: "
                    f"revision {previous_revision}->{current_revision}"
                )
                previous_revision = current_revision

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
        "pixel_owner_revision",
        "pixel_owner_row_revision",
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

    ink = _point_set(state.get("source_ink_points"))
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
