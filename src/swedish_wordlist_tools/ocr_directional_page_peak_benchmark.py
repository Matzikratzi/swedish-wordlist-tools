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
from .ocr_row_directional import first_glyph_top_down


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
    """Continue from one common leftmost residual start pixel.

    The previous glyph baseline is used only to limit where the next start
    pixel may be searched for.  Every candidate is born once from that same
    page pixel by aligning a leftmost pixel of one of its raster rows to it.
    Candidate placement is therefore determined by the glyph itself, not by
    the previous glyph baseline.

    From the start pixel we walk down and then up.  A candidate may be hidden
    behind another glyph (the page profile may lie further left), but it dies
    as soon as its own left-profile pixel would lie left of the page profile
    or on a blank page row.  No candidates are born from later profile rows.
    Survivors are finally checked against the complete 2-D residual raster.
    """
    if stats is not None:
        stats.calls += 1

    trace = os.environ.get("OCR_FIRST_GLYPH_TRACE") == "1"
    search_bottom = baseline
    if row_bottom is not None:
        search_bottom = min(search_bottom, int(row_bottom) - 1)
    if search_bottom < row_top:
        return None, ()

    # One common start pixel: globally leftmost residual pixel above the
    # previous glyph baseline, and to the right of the glyph just consumed.
    start_x: int | None = None
    start_y: int | None = None
    for page_y in range(row_top, search_bottom + 1):
        eligible = [
            x for x in remaining_by_y.get(page_y, ())
            if after_left < x < column_right
        ]
        if not eligible:
            continue
        x = min(eligible)
        if start_x is None or x < start_x or (x == start_x and page_y < start_y):
            start_x = x
            start_y = page_y

    if start_x is None or start_y is None:
        return None, ()

    # Profile-first candidate search.  The discovery pixel may correspond to
    # any black glyph pixel, so one glyph can have several placements.  Test
    # placements for the previous glyph baseline first as a prior, then the
    # remaining placements.  A placement is run to completion through the
    # glyph's left profile before any full 2-D check is attempted.
    profile_placements = 0
    profile_rejects = 0
    profile_survivors_raw = 0
    same_baseline_placements = 0
    other_baseline_placements = 0
    full_2d_rejects = 0
    full_2d_pixel_checks = 0

    def page_left(page_y: int) -> int | None:
        xs = [
            x for x in remaining_by_y.get(page_y, ())
            if 0 <= x < column_right
        ]
        return min(xs) if xs else None

    def profile_allows(
        item: baseline_up.CompiledGlyph,
        tx: int,
        candidate_baseline: int,
    ) -> bool:
        nonlocal profile_placements, profile_rejects
        profile_placements += 1

        top = candidate_baseline + item.model.min_y
        bottom = candidate_baseline + item.model.max_y
        # Walk down from the anchor, then up, matching the intended search
        # order.  Gaps are implicit model rows with no ink; arbitrary x jumps
        # are naturally represented by the row's leftmost black pixel.
        for page_y in range(start_y, bottom + 1):
            rel_y = page_y - candidate_baseline
            model_row = item.rows.get(rel_y)
            if model_row is None:
                continue
            observed_x = page_left(page_y)
            model_x = tx + model_row[0]
            # Ink further left may belong to another glyph and is harmless.
            # If the candidate requires ink left of the observed envelope, or
            # the page row is blank, this placement is impossible.
            if observed_x is None or observed_x > model_x:
                profile_rejects += 1
                return False

        for page_y in range(start_y - 1, top - 1, -1):
            rel_y = page_y - candidate_baseline
            model_row = item.rows.get(rel_y)
            if model_row is None:
                continue
            observed_x = page_left(page_y)
            model_x = tx + model_row[0]
            if observed_x is None or observed_x > model_x:
                profile_rejects += 1
                return False

        return True

    profile_survivors_map: dict[
        tuple[int, int, int],
        tuple[baseline_up.CompiledGlyph, int, int],
    ] = {}

    for item in library.models:
        placements: dict[
            tuple[int, int, int],
            tuple[baseline_up.CompiledGlyph, int, int],
        ] = {}
        for model_x, model_y in item.model.pixels:
            tx = start_x - model_x
            candidate_baseline = start_y - model_y
            physical_left = tx + item.min_x
            physical_right = tx + item.max_x
            if physical_left < 0 or physical_right >= column_right:
                continue
            key = (id(item.model), tx, candidate_baseline)
            placements[key] = (item, tx, candidate_baseline)

        ordered = sorted(
            placements.values(),
            key=lambda entry: (
                0 if entry[2] == baseline else 1,
                abs(entry[2] - baseline),
                entry[1],
            ),
        )

        for entry in ordered:
            item2, tx, candidate_baseline = entry
            if candidate_baseline == baseline:
                same_baseline_placements += 1
            else:
                other_baseline_placements += 1
            if not profile_allows(item2, tx, candidate_baseline):
                continue
            key = (id(item2.model), tx, candidate_baseline)
            profile_survivors_map[key] = entry
            profile_survivors_raw += 1

    # Only profile survivors receive the expensive full 2-D truth test.
    states: dict[tuple[int, int, int], tuple[baseline_up.CompiledGlyph, int, int]] = {}
    survivors_for_2d = sorted(
        profile_survivors_map.values(),
        key=lambda entry: -len(entry[0].model.pixels),
    )
    for item, tx, candidate_baseline in survivors_for_2d:
        missing: baseline_up.Pixel | None = None
        for model_x, model_y in item.model.pixels:
            full_2d_pixel_checks += 1
            pixel = (tx + model_x, candidate_baseline + model_y)
            if pixel not in remaining:
                missing = pixel
                break
        if missing is not None:
            full_2d_rejects += 1
            continue
        key = (id(item.model), tx, candidate_baseline)
        states[key] = (item, tx, candidate_baseline)

    initial_candidates = len(states)
    live = dict(states)
    profile_survivors = len(live)

    if trace:
        print(
            f"directional-residual-profile: start=({start_x},{start_y}) "
            f"search_y={row_top}..{search_bottom} profile_placements={profile_placements} "
            f"same_baseline={same_baseline_placements} other_baseline={other_baseline_placements} "
            f"profile_rejects={profile_rejects} profile_survivors_raw={profile_survivors_raw} "
            f"full_2d_rejects={full_2d_rejects} full_2d_pixel_checks={full_2d_pixel_checks} "
            f"initial={initial_candidates} profile_survivors={profile_survivors}",
            flush=True,
        )

    # Full 2-D truth test.  Extra page ink is allowed; every glyph pixel must
    # exist.  Candidate placement comes entirely from the start-pixel anchor.
    proposals: dict[tuple[int, int, int], baseline_up.BaselineMatch] = {}
    for key, (item, tx, candidate_baseline) in live.items():
        placed = frozenset(
            (tx + x, candidate_baseline + y)
            for x, y in item.model.pixels
        )
        missing = next((pixel for pixel in placed if pixel not in remaining), None)
        if missing is not None:
            if trace:
                print(
                    f"directional-residual-2d-fail: label={item.model.label!r} "
                    f"style={item.model.style} start=({start_x},{start_y}) "
                    f"tx={tx} candidate_baseline={candidate_baseline} "
                    f"pixels={len(placed)} first_missing={missing}",
                    flush=True,
                )
            continue

        candidate = baseline_up.BaselineMatch(
            model=item.model,
            tx=tx,
            baseline=candidate_baseline,
            pixels=placed,
            discovered_y=start_y,
        )
        proposals[key] = candidate
        if trace:
            print(
                f"directional-residual-2d-pass: label={item.model.label!r} "
                f"style={item.model.style} start=({start_x},{start_y}) "
                f"tx={tx} candidate_baseline={candidate_baseline} "
                f"pixels={len(placed)}",
                flush=True,
            )

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
    hit = baseline_up.pick_anchor_unique_maximal(candidates)

    if trace:
        accepted = repr(hit.model.label) if hit is not None else None
        print(
            f"directional-residual-pick: after_left={after_left} "
            f"previous_baseline={baseline} start=({start_x},{start_y}) "
            f"profile_survivors={profile_survivors} exact={len(candidates)} "
            f"accepted={accepted}",
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
