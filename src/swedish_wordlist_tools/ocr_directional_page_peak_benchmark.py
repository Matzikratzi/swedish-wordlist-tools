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
    """Continue from one leftmost residual start pixel.

    The previous glyph baseline only limits where the new start pixel may be
    searched for.  Once that pixel is found, every candidate is born from it:
    one left-profile pixel of the glyph is aligned to the start pixel.  No new
    candidates are born on later page rows.

    Candidate profile pixels are then checked downward and upward from that
    anchor.  Page ink that the candidate does not need is harmless; a candidate
    dies only when one of *its* required left-profile pixels is absent.  A
    survivor is finally verified against all of its 2-D black pixels.
    """
    if stats is not None:
        stats.calls += 1

    trace = os.environ.get("OCR_FIRST_GLYPH_TRACE") == "1"

    # Baseline is only a search-window hint for the next leftmost start pixel.
    search_bottom = baseline
    if row_bottom is not None:
        search_bottom = min(search_bottom, int(row_bottom) - 1)
    eligible = [
        (x, y)
        for x, y in remaining
        if row_top <= y <= search_bottom and x < column_right and x > after_left
    ]
    if not eligible:
        return None, ()

    frontier_x = min(x for x, _y in eligible)
    anchor_y = min(y for x, y in eligible if x == frontier_x)

    # One candidate placement per (glyph, model anchor row).  The anchor pixel
    # is always the leftmost pixel of that glyph row.
    born: list[tuple[baseline_up.CompiledGlyph, int, int, int]] = []
    for item in library.models:
        for model_anchor_rel_y, anchor_row in sorted(item.rows.items()):
            if not anchor_row:
                continue
            model_dx = anchor_row[0]
            tx = frontier_x - model_dx
            candidate_baseline = anchor_y - model_anchor_rel_y
            physical_left = tx + item.min_x
            physical_right = tx + item.max_x
            if physical_left <= after_left or physical_right >= column_right:
                continue
            born.append((item, tx, candidate_baseline, model_anchor_rel_y))

    if trace:
        print(
            f"directional-residual-seed: after_left={after_left} "
            f"search_y={row_top}..{search_bottom} start=({frontier_x},{anchor_y}) "
            f"born={len(born)}",
            flush=True,
        )

    survivors: list[tuple[baseline_up.CompiledGlyph, int, int, int]] = []
    for item, tx, candidate_baseline, model_anchor_rel_y in born:
        dead = False

        # Walk downward first from the start row.  Only pixels required by this
        # candidate's own left profile matter.
        for model_rel_y in sorted(y for y in item.rows if y >= model_anchor_rel_y):
            model_row = item.rows[model_rel_y]
            model_x = tx + model_row[0]
            page_y = candidate_baseline + model_rel_y
            if (model_x, page_y) not in remaining:
                dead = True
                if trace:
                    print(
                        f"directional-residual-profile-death: "
                        f"label={item.model.label!r} style={item.model.style} "
                        f"direction=down start=({frontier_x},{anchor_y}) "
                        f"tx={tx} candidate_baseline={candidate_baseline} "
                        f"model_anchor_rel_y={model_anchor_rel_y} "
                        f"model_rel_y={model_rel_y} required=({model_x},{page_y}) "
                        f"reason=required-left-pixel-missing",
                        flush=True,
                    )
                break

        if dead:
            continue

        # Then walk upward from the same start pixel.  Still no new page anchor:
        # alternative vertical placements were all born from the original pixel.
        for model_rel_y in sorted(
            (y for y in item.rows if y < model_anchor_rel_y),
            reverse=True,
        ):
            model_row = item.rows[model_rel_y]
            model_x = tx + model_row[0]
            page_y = candidate_baseline + model_rel_y
            if (model_x, page_y) not in remaining:
                dead = True
                if trace:
                    print(
                        f"directional-residual-profile-death: "
                        f"label={item.model.label!r} style={item.model.style} "
                        f"direction=up start=({frontier_x},{anchor_y}) "
                        f"tx={tx} candidate_baseline={candidate_baseline} "
                        f"model_anchor_rel_y={model_anchor_rel_y} "
                        f"model_rel_y={model_rel_y} required=({model_x},{page_y}) "
                        f"reason=required-left-pixel-missing",
                        flush=True,
                    )
                break

        if not dead:
            survivors.append((item, tx, candidate_baseline, model_anchor_rel_y))

    if trace:
        print(
            f"directional-residual-profile: start=({frontier_x},{anchor_y}) "
            f"born={len(born)} profile_survivors={len(survivors)}",
            flush=True,
        )

    proposals: dict[tuple[int, int, int], baseline_up.BaselineMatch] = {}
    for item, tx, candidate_baseline, model_anchor_rel_y in survivors:
        placed = frozenset(
            (tx + x, candidate_baseline + y)
            for x, y in item.model.pixels
        )
        missing = next((pixel for pixel in placed if pixel not in remaining), None)
        if missing is not None:
            if trace:
                print(
                    f"directional-residual-2d-fail: label={item.model.label!r} "
                    f"style={item.model.style} start=({frontier_x},{anchor_y}) "
                    f"model_anchor_rel_y={model_anchor_rel_y} tx={tx} "
                    f"candidate_baseline={candidate_baseline} pixels={len(placed)} "
                    f"first_missing={missing}",
                    flush=True,
                )
            continue

        candidate = baseline_up.BaselineMatch(
            model=item.model,
            tx=tx,
            baseline=candidate_baseline,
            pixels=placed,
            discovered_y=anchor_y,
        )
        proposals[(id(candidate.model), candidate.tx, candidate.baseline)] = candidate
        if trace:
            print(
                f"directional-residual-2d-pass: label={item.model.label!r} "
                f"style={item.model.style} start=({frontier_x},{anchor_y}) "
                f"model_anchor_rel_y={model_anchor_rel_y} tx={tx} "
                f"candidate_baseline={candidate_baseline} pixels={len(placed)}",
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
    hit = baseline_up.pick_leftmost_unique_maximal(candidates)

    if trace:
        accepted = repr(hit.model.label) if hit is not None else None
        print(
            f"directional-residual-pick: after_left={after_left} "
            f"previous_baseline={baseline} start=({frontier_x},{anchor_y}) "
            f"born={len(born)} profile_survivors={len(survivors)} "
            f"exact={len(candidates)} accepted={accepted}",
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
