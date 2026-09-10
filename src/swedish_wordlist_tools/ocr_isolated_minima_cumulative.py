from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .ocr_baseline_up import ResidualInk
from .ocr_column_left_profile import build_column_left_profile
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_shadow_whole_column import _black_pixels, _column_bounds


def _isolated_profile_segments(left_profile, *, min_height: int) -> list[tuple[int, int, int]]:
    values = left_profile.values
    segments: list[tuple[int, int, int]] = []
    index = 0
    while index < len(values):
        if values[index] is None:
            index += 1
            continue
        start = index
        occupied: list[int] = []
        while index < len(values) and values[index] is not None:
            occupied.append(int(values[index]))
            index += 1
        end = index - 1
        blank_above = start > 0 and values[start - 1] is None
        blank_below = index < len(values) and values[index] is None
        height = end - start + 1
        if blank_above and blank_below and height >= min_height:
            segments.append((left_profile.top + start, left_profile.top + end, min(occupied)))
    return segments


def _hist(values: list[int]) -> Counter[int]:
    return Counter(values)


def _format_hist(hist: Counter[int]) -> str:
    return "{" + ",".join(f"{x}:{hist[x]}" for x in sorted(hist)) + "}"


def _cumulative(hist: Counter[int]) -> list[tuple[int, int]]:
    if not hist:
        return []
    lo = min(hist)
    hi = max(hist)
    return [
        (x, sum(count for value, count in hist.items() if value >= x))
        for x in range(lo, hi + 1)
    ]


def _format_cumulative(rows: list[tuple[int, int]]) -> str:
    return "{" + ",".join(f"{x}:{n}" for x, n in rows) + "}"


def _page_values(jsonl: Path, *, page: int, column: int, threshold: int, min_height: int) -> list[int]:
    context = build_page_context_pixel_array(jsonl, page, threshold)
    bounds = _column_bounds(context, column)
    black = _black_pixels(context, bounds)
    residual = ResidualInk(black)
    left, right, top, bottom = bounds
    profile = build_column_left_profile(
        residual.rows,
        top=top,
        bottom=bottom,
        left=left,
        right=right,
    )
    segments = _isolated_profile_segments(profile, min_height=min_height)
    values = [min_x for _top, _bottom, min_x in segments]
    hist = _hist(values)
    print(
        f"isolated-cumulative-page: page={page} column={column} min_height={min_height} "
        f"segments={len(values)} hist={_format_hist(hist)} cumulative={_format_cumulative(_cumulative(hist))}",
        flush=True,
    )
    return values


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Print isolated left-profile minima histograms and cumulative survival curves for several pages."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, action="append", required=True, help="repeat for each page")
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument(
        "--min-height",
        type=int,
        default=5,
        help="minimum occupied y-run height; default 5 ignores runs of 4 raster rows or fewer",
    )
    args = ap.parse_args()

    combined: list[int] = []
    for page in args.page:
        combined.extend(
            _page_values(
                args.jsonl,
                page=page,
                column=args.column,
                threshold=args.threshold,
                min_height=args.min_height,
            )
        )

    hist = _hist(combined)
    print(
        f"isolated-cumulative-combined: pages={tuple(args.page)} column={args.column} "
        f"min_height={args.min_height} segments={len(combined)} "
        f"hist={_format_hist(hist)} cumulative={_format_cumulative(_cumulative(hist))}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
