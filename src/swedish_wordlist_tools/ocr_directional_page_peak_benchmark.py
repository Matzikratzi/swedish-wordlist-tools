from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from . import ocr_baseline_up as baseline_up
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


def _start_range_for_peak(peak: int) -> tuple[int, int]:
    """Return the deliberately broad experimental start window around a peak."""
    return peak - 1, peak + 3


def infer_peak_walk_start_geometry(
    source: ColumnLeftProfile | Mapping[int, Iterable[int]],
    reference_rows: Iterable[dict],
    *,
    tolerance: int = 4,
) -> InferredStartGeometry:
    """Infer OCR start ranges from isolated-profile histogram peaks."""
    del tolerance

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

    ordinary_ranges = [
        _start_range_for_peak(left_peak),
        _start_range_for_peak(right_peak),
    ]
    ranges = list(ordinary_ranges)

    if third_minima:
        third_counts = Counter(third_minima)
        third_peak = max(third_counts, key=lambda x: (third_counts[x], -x))
        if third_peak <= left_peak - 2:
            ranges.append(_start_range_for_peak(third_peak))

    ranges = sorted(set(ranges))
    ranges_tuple = tuple(ranges)
    centers = tuple(sorted({x for lo, hi in ranges_tuple for x in (lo, hi)}))

    print(
        "directional-peak-starts: "
        f"hist={{{','.join(f'{x}:{hist[x]}' for x in sorted(hist))}}} "
        f"ordinary_peaks={(left_peak, right_peak)} "
        f"ordinary_ranges={tuple(ordinary_ranges)} "
        f"third_minima={third_minima} ranges={ranges_tuple}",
        flush=True,
    )

    return InferredStartGeometry(
        centers=centers,
        ranges=ranges_tuple,
        observations=tuple(min_x for _top, _bottom, min_x in segments),
    )


def _candidates_from_observation(
    remaining: set[baseline_up.Pixel],
    library: baseline_up.CompiledGlyphLibrary,
    *,
    baseline: int,
    page_y: int,
    observed_x: int,
    column_right: int,
    stats: baseline_up.BaselineUpStats | None = None,
) -> tuple[baseline_up.BaselineMatch, ...]:
    """Place any model pixel on one observed residual pixel at a known baseline."""
    rel_y = page_y - baseline
    possible_models = library.by_rel_y.get(rel_y, ())
    if stats is not None:
        stats.model_visits += len(possible_models)

    seen: set[tuple[int, int, int]] = set()
    found: list[baseline_up.BaselineMatch] = []

    for item in possible_models:
        model_row = item.rows[rel_y]
        for model_x in model_row:
            if stats is not None:
                stats.raw_tx_proposals += 1
            tx = observed_x - model_x
            physical_right = tx + item.max_x
            if physical_right >= column_right:
                continue
            if stats is not None:
                stats.in_bounds_tx += 1

            key = (id(item.model), tx, baseline)
            if key in seen:
                if stats is not None:
                    stats.duplicate_tx += 1
                continue
            seen.add(key)
            if stats is not None:
                stats.unique_tx += 1

            placed = frozenset((tx + x, baseline + y) for x, y in item.model.pixels)
            if stats is not None:
                stats.subset_checks += 1
            if not placed.issubset(remaining):
                continue
            if stats is not None:
                stats.exact_hits += 1
            found.append(
                baseline_up.BaselineMatch(
                    model=item.model,
                    tx=tx,
                    baseline=baseline,
                    pixels=placed,
                    discovered_y=page_y,
                )
            )

    return tuple(
        sorted(
            found,
            key=lambda hit: (
                hit.left,
                -len(hit.pixels),
                -hit.model.sources,
                hit.model.label,
                hit.model.style,
            ),
        )
    )


def _baseline_upward_candidates(
    remaining: set[baseline_up.Pixel],
    remaining_by_y: Mapping[int, Iterable[int]],
    library: baseline_up.CompiledGlyphLibrary,
    *,
    baseline: int,
    row_top: int,
    after_left: int,
    column_right: int,
    stats: baseline_up.BaselineUpStats | None = None,
) -> tuple[baseline_up.BaselineMatch, ...]:
    """Search from baseline upward and stop at the first productive raster row.

    For every y, only the leftmost unexplained pixel to the right of the already
    accepted glyph is used as the observation.  The observation is not required
    to be the candidate's physical left edge: any model pixel on that model row
    may align with it.  Exact placement checks the entire glyph, including ink
    below the baseline.
    """
    if stats is not None:
        stats.calls += 1

    for page_y in range(baseline, row_top - 1, -1):
        if stats is not None:
            stats.y_rows += 1
        xs = remaining_by_y.get(page_y, ())
        eligible = [x for x in xs if after_left < x < column_right]
        if not eligible:
            continue

        observed_x = min(eligible)
        if stats is not None:
            stats.observed_pixels += 1

        candidates = _candidates_from_observation(
            remaining,
            library,
            baseline=baseline,
            page_y=page_y,
            observed_x=observed_x,
            column_right=column_right,
            stats=stats,
        )
        if candidates:
            return candidates

    return ()


def find_next_residual_leftmost(
    remaining: set[baseline_up.Pixel],
    remaining_by_y: Mapping[int, Iterable[int]],
    library: baseline_up.CompiledGlyphLibrary,
    *,
    baseline: int,
    row_top: int,
    row_bottom: int | None = None,
    profile_bottom: int | None = None,
    after_left: int,
    column_right: int,
    stats: baseline_up.BaselineUpStats | None = None,
) -> tuple[baseline_up.BaselineMatch | None, tuple[baseline_up.BaselineMatch, ...]]:
    """Experimental post-first-glyph search upward from the known baseline."""
    del profile_bottom

    candidates = _baseline_upward_candidates(
        remaining,
        remaining_by_y,
        library,
        baseline=baseline,
        row_top=row_top,
        after_left=after_left,
        column_right=column_right,
        stats=stats,
    )

    known_bottom = (
        int(row_bottom) - 1
        if row_bottom is not None
        else baseline + library.max_down
    )
    return baseline_up._pick_with_live_profile(
        candidates,
        remaining_by_y,
        row_top=row_top,
        known_bottom_before=known_bottom,
        after_left=after_left,
        column_right=column_right,
        stats=stats,
    )


def main() -> int:
    benchmark.infer_page_start_geometry = infer_peak_walk_start_geometry
    benchmark.find_next_baseline_up = find_next_residual_leftmost
    return benchmark.main()


if __name__ == "__main__":
    raise SystemExit(main())
