from __future__ import annotations

import argparse
from pathlib import Path

from .ocr_candidate_survival import vertical_blank_columns
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_shadow_whole_column import _black_pixels, _column_bounds


def _runs(xs: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
    if not xs:
        return ()
    out: list[tuple[int, int]] = []
    start = prev = xs[0]
    for x in xs[1:]:
        if x == prev + 1:
            prev = x
            continue
        out.append((start, prev))
        start = prev = x
    out.append((start, prev))
    return tuple(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Shadow experiment: list vertical separator columns that are blank "
            "from a known row top through a known baseline. Ink below baseline "
            "is deliberately ignored."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, default=39)
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--top-y", type=int, required=True)
    ap.add_argument("--baseline", type=int, required=True)
    ap.add_argument("--start-x", type=int, required=True)
    ap.add_argument("--end-x", type=int, required=True)
    ap.add_argument(
        "--show-columns",
        action="store_true",
        help="Also print one line per x column as BLANK or occupied.",
    )
    args = ap.parse_args()

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)

    blank = vertical_blank_columns(
        black,
        start_x=args.start_x,
        end_x=args.end_x,
        top_y=args.top_y,
        baseline=args.baseline,
    )
    blank_set = set(blank)
    runs = _runs(blank)

    print(
        f"vertical-separators: page={args.page} column={args.column} "
        f"top={args.top_y} baseline={args.baseline} x={args.start_x}..{args.end_x} "
        f"blank_columns={len(blank)} blank_runs={len(runs)}"
    )
    for start, end in runs:
        width = end - start + 1
        print(f"separator-run: x={start}..{end} width={width}")

    if args.show_columns:
        for x in range(args.start_x, args.end_x + 1):
            state = "BLANK" if x in blank_set else "occupied"
            print(f"separator-column: x={x} {state}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
