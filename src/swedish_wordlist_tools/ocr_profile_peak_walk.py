from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .ocr_baseline_up import ResidualInk
from .ocr_column_left_profile import build_column_left_profile
from .ocr_isolated_minima_cumulative import _isolated_profile_segments
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_shadow_whole_column import _black_pixels, _column_bounds


@dataclass(frozen=True)
class PeakGroup:
    xs: tuple[int, ...]
    count: int

    @property
    def peak_x(self) -> int:
        # Use the most common x. On a tie, prefer the rightmost value; this
        # makes a 60/61 group anchor at 61 rather than inventing a midpoint.
        counts = Counter(self.xs)
        return max(counts, key=lambda x: (counts[x], x))


def _group_histogram(hist: Counter[int], *, max_gap: int = 2) -> list[PeakGroup]:
    if not hist:
        return []
    groups: list[list[int]] = []
    current: list[int] = []
    previous: int | None = None
    for x in sorted(hist):
        if previous is None or x - previous <= max_gap:
            current.extend([x] * hist[x])
        else:
            groups.append(current)
            current = [x] * hist[x]
        previous = x
    if current:
        groups.append(current)
    return [PeakGroup(tuple(values), len(values)) for values in groups]


def _two_main_peaks(hist: Counter[int]) -> tuple[int, int]:
    groups = _group_histogram(hist)
    if len(groups) < 2:
        raise ValueError(f"need at least two histogram groups, got {hist}")
    strongest = sorted(groups, key=lambda group: group.count, reverse=True)[:2]
    peaks = sorted(group.peak_x for group in strongest)
    return peaks[0], peaks[1]


def _segment_profile(left_profile, top_y: int, bottom_y: int) -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    for y in range(top_y, bottom_y + 1):
        value = left_profile.values[y - left_profile.top]
        if value is not None:
            rows.append((y, int(value)))
    return rows


def _walk_segment(rows: list[tuple[int, int]], peaks: tuple[int, int], *, left_margin: int) -> tuple[str, list[str]]:
    left_peak, right_peak = peaks
    current = right_peak
    transitions: list[str] = []

    for y, x in rows:
        if current == right_peak and x <= right_peak - left_margin:
            transitions.append(f"y={y}:x={x} right->{left_peak}")
            current = left_peak
            # The same observation may already have passed the left peak too.
            if x <= left_peak - left_margin:
                transitions.append(f"y={y}:x={x} left->third")
                return "third", transitions
            continue
        if current == left_peak and x <= left_peak - left_margin:
            transitions.append(f"y={y}:x={x} left->third")
            return "third", transitions

    if current == right_peak:
        return "right", transitions
    return "left", transitions


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Diagnose row-start levels by finding two strong isolated-minimum histogram peaks "
            "and walking each isolated profile top-down."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--min-height", type=int, default=5)
    ap.add_argument(
        "--left-margin",
        type=int,
        default=2,
        help="move to the next left peak after passing the current peak by this many pixels",
    )
    args = ap.parse_args()

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
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

    segments = _isolated_profile_segments(profile, min_height=args.min_height)
    hist = Counter(min_x for _top, _bottom, min_x in segments)
    peaks = _two_main_peaks(hist)

    print(
        f"peak-walk: page={args.page} column={args.column} min_height={args.min_height} "
        f"left_margin={args.left_margin} hist="
        + "{" + ",".join(f"{x}:{hist[x]}" for x in sorted(hist)) + "} "
        + f"main_peaks={peaks}",
        flush=True,
    )

    counts: Counter[str] = Counter()
    for index, (segment_top, segment_bottom, min_x) in enumerate(segments):
        rows = _segment_profile(profile, segment_top, segment_bottom)
        level, transitions = _walk_segment(rows, peaks, left_margin=args.left_margin)
        counts[level] += 1
        first_y, first_x = rows[0]
        transition_text = ";".join(transitions) if transitions else "-"
        print(
            f"peak-walk-segment: i={index} y={segment_top}..{segment_bottom} "
            f"first={first_y}:{first_x} min_x={min_x} level={level} transitions={transition_text}",
            flush=True,
        )

    print(
        f"peak-walk-done: page={args.page} column={args.column} peaks={peaks} "
        f"right={counts['right']} left={counts['left']} third={counts['third']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
