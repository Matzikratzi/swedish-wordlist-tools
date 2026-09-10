from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from . import ocr_directional_page_benchmark as benchmark
from .ocr_column_left_profile import ColumnLeftProfile, build_column_left_profile
from .ocr_isolated_minima_cumulative import _isolated_profile_segments
from .ocr_page_start_geometry import InferredStartGeometry
from .ocr_profile_peak_walk import _segment_profile, _two_main_peaks, _walk_segment


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
    levels.  Each level becomes exactly two adjacent allowed starts: peak and
    peak+1.  A possible third, farther-left level is admitted only when the
    top-down profile walk actually crosses the left ordinary peak by two pixels;
    its most common observed minimum is then treated in the same way.
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

    peaks = [left_peak, right_peak]
    if third_minima:
        third_counts = Counter(third_minima)
        third_peak = max(third_counts, key=lambda x: (third_counts[x], -x))
        if third_peak <= left_peak - 2:
            peaks.append(third_peak)

    peaks = sorted(set(peaks))
    ranges = tuple((peak, peak + 1) for peak in peaks)
    centers = tuple(x for lo, hi in ranges for x in (lo, hi))

    print(
        "directional-peak-starts: "
        f"hist={{{','.join(f'{x}:{hist[x]}' for x in sorted(hist))}}} "
        f"ordinary_peaks={(left_peak, right_peak)} "
        f"third_minima={third_minima} ranges={ranges}",
        flush=True,
    )

    return InferredStartGeometry(
        centers=centers,
        ranges=ranges,
        observations=tuple(min_x for _top, _bottom, min_x in segments),
    )


def main() -> int:
    benchmark.infer_page_start_geometry = infer_peak_walk_start_geometry
    return benchmark.main()


if __name__ == "__main__":
    raise SystemExit(main())
