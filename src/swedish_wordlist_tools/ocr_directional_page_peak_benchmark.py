from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from . import ocr_directional_page_benchmark as benchmark
from .ocr_column_left_profile import ColumnLeftProfile, build_column_left_profile
from .ocr_isolated_minima_cumulative import _isolated_profile_segments
from .ocr_page_start_geometry import InferredStartGeometry
from .ocr_profile_peak_walk import _group_histogram, _segment_profile, _two_main_peaks, _walk_segment


def _profile_for_rows(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
) -> ColumnLeftProfile | None:
    reference = list(reference_rows)
    if isinstance(source, ColumnLeftProfile):
        return source
    if not reference:
        return None
    top = min(int(row["page_top"]) for row in reference)
    bottom = max(int(row["page_bottom"]) for row in reference)
    return build_column_left_profile(source, top=top, bottom=bottom)


def _start_pair_for_peak(hist: Counter[int], peak: int) -> tuple[int, int]:
    """Return the best adjacent start pair inside the peak's histogram group.

    Prefer a pair whose two x values are both actually observed.  This matters
    for a group such as {60, 61}: anchoring at the modal 61 must not discard the
    observed 60 start.  If the group contains only one observed x, keep the
    earlier experimental convention of allowing that x and its immediate right
    neighbour.
    """
    group = next((group for group in _group_histogram(hist) if peak in group.xs), None)
    if group is None:
        return peak, peak + 1

    observed = sorted(set(group.xs))
    adjacent = [(x, x + 1) for x in observed if x + 1 in observed]
    if adjacent:
        return max(
            adjacent,
            key=lambda pair: (
                hist[pair[0]] + hist[pair[1]],
                min(hist[pair[0]], hist[pair[1]]),
                -pair[0],
            ),
        )
    return peak, peak + 1


def infer_peak_walk_start_geometry(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    tolerance: int = 4,
) -> InferredStartGeometry:
    """Infer OCR start ranges from isolated-profile histogram peaks.

    This is deliberately an experimental drop-in replacement for
    infer_page_start_geometry.  It does not use glyph labels, styles, row types,
    page numbers, or reference-row classifications.

    Two strong isolated-minimum histogram groups establish the ordinary start
    levels.  Each level becomes exactly two adjacent allowed starts.  When the
    histogram group itself contains an observed adjacent pair, that observed pair
    is used; otherwise the modal peak and its immediate right neighbour are used.
    A possible third, farther-left level is admitted only when the top-down
    profile walk actually crosses the left ordinary peak by two pixels.
    """
    del tolerance  # kept only for compatibility with the benchmark call site

    reference = list(reference_rows)
    profile = _profile_for_rows(source, reference)
    if profile is None:
        return InferredStartGeometry(centers=(), ranges=(), observations=())

    segments = _isolated_profile_segments(profile, min_height=5)
    hist = Counter(min_x for _top, _bottom, min_x in segments)
    if len(hist) < 2:
        return InferredStartGeometry(centers=(), ranges=(), observations=tuple(hist.elements()))

    left_peak, right_peak = _two_main_peaks(hist)

    third_minima: list[int] = []
    for segment_top, segment_bottom, min_x in segments:
        rows = _segment_profile(profile, segment_top, segment_bottom)
        level, _transitions = _walk_segment(rows, (left_peak, right_peak), left_margin=2)
        if level == "third":
            third_minima.append(min_x)

    ordinary_pairs = [
        _start_pair_for_peak(hist, left_peak),
        _start_pair_for_peak(hist, right_peak),
    ]
    ranges = list(ordinary_pairs)

    if third_minima:
        third_counts = Counter(third_minima)
        third_peak = max(third_counts, key=lambda x: (third_counts[x], -x))
        if third_peak <= left_peak - 2:
            ranges.append(_start_pair_for_peak(third_counts, third_peak))

    ranges = sorted(set(ranges))
    ranges_tuple = tuple(ranges)
    centers = tuple(sorted({x for lo, hi in ranges_tuple for x in (lo, hi)}))

    print(
        "directional-peak-starts: "
        f"hist={{{','.join(f'{x}:{hist[x]}' for x in sorted(hist))}}} "
        f"ordinary_peaks={(left_peak, right_peak)} "
        f"ordinary_pairs={tuple(ordinary_pairs)} "
        f"third_minima={third_minima} ranges={ranges_tuple}",
        flush=True,
    )

    return InferredStartGeometry(
        centers=centers,
        ranges=ranges_tuple,
        observations=tuple(min_x for _top, _bottom, min_x in segments),
    )


def main() -> int:
    benchmark.infer_page_start_geometry = infer_peak_walk_start_geometry
    return benchmark.main()


if __name__ == "__main__":
    raise SystemExit(main())
