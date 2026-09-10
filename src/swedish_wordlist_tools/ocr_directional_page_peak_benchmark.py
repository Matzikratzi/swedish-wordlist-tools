from __future__ import annotations

import os
from collections import Counter
from typing import Iterable, Mapping

from . import ocr_baseline_up as baseline_up
from . import ocr_directional_page_benchmark as benchmark
from .ocr_column_left_profile import ColumnLeftProfile, build_column_left_profile
from .ocr_isolated_minima_cumulative import _isolated_profile_segments
from .ocr_page_start_geometry import InferredStartGeometry
from .ocr_profile_peak_walk import _segment_profile, _two_main_peaks, _walk_segment
from .ocr_row_directional import _seed_from_record_row, first_glyph_top_down


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


def find_next_residual_profile(
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
    """Continue the same row from the residual lower envelope.

    The first glyph has already established both the row and its baseline. Do
    not restart the first-glyph state machine at ``row_top``: after consumption
    its early rows may expose arbitrary later glyphs and would be mistaken for
    a fresh row-start record. Instead inspect the residual profile over the
    y-band that is already known for this row, take its globally leftmost
    exposed frontier, and seed from the complete horizontal raster row there.

    Consuming a glyph changes the lower envelope of already-seen y rows, so
    those rows are replayed against the known baseline, but row-start inference
    is never run again. Full 2-D checks remain deferred until profile-compatible
    candidates have survived.
    """
    del row_bottom
    if stats is not None:
        stats.calls += 1

    if profile_bottom is None:
        profile_bottom = baseline
    known_bottom = max(row_top, int(profile_bottom))
    trace = os.environ.get("OCR_FIRST_GLYPH_TRACE") == "1"

    observed: dict[int, int | None] = {}
    frontier_x: int | None = None
    frontier_ys: list[int] = []
    for page_y in range(row_top, known_bottom + 1):
        xs = tuple(x for x in remaining_by_y.get(page_y, ()) if x < column_right)
        profile_x = min(xs) if xs else None
        observed[page_y] = profile_x
        if profile_x is None:
            continue
        if frontier_x is None or profile_x < frontier_x:
            frontier_x = profile_x
            frontier_ys = [page_y]
        elif profile_x == frontier_x:
            frontier_ys.append(page_y)

    if trace:
        points = " ".join(
            f"{y}:{observed[y] if observed[y] is not None else '-'}"
            for y in range(row_top, known_bottom + 1)
        )
        print(
            f"directional-residual-profile: y={row_top}..{known_bottom} "
            f"frontier={frontier_x} ys={tuple(frontier_ys)} profile=[{points}]",
            flush=True,
        )

    if frontier_x is None:
        return None, ()

    start_ranges = ((after_left + 1, column_right - 1),)
    proposals: dict[tuple[int, int, int], baseline_up.BaselineMatch] = {}

    for page_y in frontier_ys:
        seeded = _seed_from_record_row(
            page_y=page_y,
            observed_x=frontier_x,
            observed=observed,
            black=remaining,
            library=library,
            row_top=row_top,
            start_ranges=start_ranges,
        )
        for _item, candidate, _explained, _gaps in seeded:
            if candidate.baseline != baseline:
                continue
            if candidate.left <= after_left or candidate.right >= column_right:
                continue
            if not candidate.pixels.issubset(remaining):
                continue
            proposals[(id(candidate.model), candidate.tx, candidate.baseline)] = candidate

    candidates = tuple(
        sorted(
            proposals.values(),
            key=lambda hit: (
                hit.left,
                -len(hit.pixels),
                -hit.model.sources,
                hit.model.label,
                hit.model.style,
            ),
        )
    )
    hit = baseline_up.pick_leftmost_unique_maximal(candidates)

    if trace:
        accepted = repr(hit.model.label) if hit is not None else None
        print(
            f"directional-residual-pick: after_left={after_left} baseline={baseline} "
            f"frontier={frontier_x} candidates={len(candidates)} accepted={accepted}",
            flush=True,
        )
        for candidate in candidates:
            print(
                f"directional-residual-candidate: label={candidate.model.label!r} "
                f"style={candidate.model.style} left={candidate.left} right={candidate.right} "
                f"baseline={candidate.baseline} pixels={len(candidate.pixels)}",
                flush=True,
            )

    return hit, candidates


def main() -> int:
    benchmark.infer_page_start_geometry = infer_peak_walk_start_geometry
    benchmark.find_next_baseline_up = find_next_residual_profile
    return benchmark.main()


if __name__ == "__main__":
    raise SystemExit(main())
