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
    """Continue a row from the leftmost residual-profile anchor.

    First use the strict left-profile sequence to reduce the model set.  For
    each surviving model, place its known-baseline raster on the start sample
    by trying black pixels on that model row in increasing dx order.  Thus the
    first 2-D attempt is always the smallest dx that can cover the start
    sample; later row pixels are tried only if the earlier placement fails.
    Extra black pixels in the page are allowed, but every black model pixel
    must exist in the residual page raster.
    """
    if stats is not None:
        stats.calls += 1

    if profile_bottom is None:
        profile_bottom = baseline
    known_bottom = max(row_top, int(profile_bottom))
    source_bottom = (
        int(row_bottom)
        if row_bottom is not None
        else (max(remaining_by_y) if remaining_by_y else known_bottom)
    )
    trace = os.environ.get("OCR_FIRST_GLYPH_TRACE") == "1"
    profile_deaths_reported: set[tuple[int, int, int]] = set()

    def build_observed(bottom: int) -> tuple[dict[int, int | None], int | None, int | None]:
        observed: dict[int, int | None] = {}
        frontier_x: int | None = None
        anchor_y: int | None = None
        for page_y in range(row_top, bottom + 1):
            xs = tuple(x for x in remaining_by_y.get(page_y, ()) if x < column_right)
            profile_x = min(xs) if xs else None
            observed[page_y] = profile_x
            if profile_x is not None and (frontier_x is None or profile_x < frontier_x):
                frontier_x = profile_x
                anchor_y = page_y
        return observed, frontier_x, anchor_y

    def profile_candidates(
        observed: Mapping[int, int | None],
        frontier_x: int,
        anchor_y: int,
    ) -> list[tuple[baseline_up.CompiledGlyph, int, int, bool]]:
        """Match the observed left-profile fragment anywhere in a glyph profile.

        The observed fragment starts at the newly discovered frontier sample,
        but that sample need not be the top of the glyph (notably for dotted
        letters such as i).  Therefore try every model profile row as the
        vertical alignment for anchor_y.  Baseline is still known and is used
        later for the full 2-D placement.
        """
        survivors: list[tuple[baseline_up.CompiledGlyph, int, int, bool]] = []

        for item in library.models:
            for model_anchor_rel_y, anchor_row in sorted(item.rows.items()):
                tx = frontier_x - anchor_row[0]
                physical_left = tx + item.min_x
                physical_right = tx + item.max_x
                if physical_left <= after_left or physical_right >= column_right:
                    continue

                compatible = True
                complete = False
                for page_y in range(anchor_y, known_bottom + 1):
                    model_rel_y = model_anchor_rel_y + (page_y - anchor_y)
                    model_row = item.rows.get(model_rel_y)

                    if model_row is None:
                        # A gap/end in the model is meaningful only once the
                        # observed fragment has reached/passed the known
                        # baseline.  Above that it may simply be a dot gap.
                        if page_y > baseline:
                            complete = True
                            break
                        continue

                    observed_x = observed.get(page_y)
                    model_x = tx + model_row[0]
                    if observed_x is None or model_x != observed_x:
                        compatible = False
                        if trace:
                            death_key = (id(item), tx, model_anchor_rel_y)
                            if death_key not in profile_deaths_reported:
                                profile_deaths_reported.add(death_key)
                                reason = "page-gap" if observed_x is None else "profile-mismatch"
                                print(
                                    f"directional-residual-profile-death: "
                                    f"label={item.model.label!r} style={item.model.style} "
                                    f"tx={tx} baseline={baseline} anchor_y={anchor_y} "
                                    f"model_anchor_rel_y={model_anchor_rel_y} "
                                    f"y={page_y} model_rel_y={model_rel_y} reason={reason} "
                                    f"observed_x={observed_x if observed_x is not None else '-'} "
                                    f"model_x={model_x} model_dx={model_row[0]}",
                                    flush=True,
                                )
                        break

                if not compatible:
                    continue

                if not complete and known_bottom >= baseline:
                    next_model_rel_y = model_anchor_rel_y + (known_bottom + 1 - anchor_y)
                    if item.rows.get(next_model_rel_y) is None:
                        complete = True

                survivors.append((item, tx, model_anchor_rel_y, complete))

        return survivors

    observed, frontier_x, anchor_y = build_observed(known_bottom)
    if frontier_x is None or anchor_y is None:
        return None, ()

    while True:
        survivors = profile_candidates(observed, frontier_x, anchor_y)
        pending = [entry for entry in survivors if not entry[3]]
        if not pending or known_bottom >= source_bottom:
            break
        known_bottom += 1
        observed, frontier_x, anchor_y = build_observed(known_bottom)
        if frontier_x is None or anchor_y is None:
            return None, ()

    profile_survivors = len(survivors)

    if trace:
        points = " ".join(
            f"{y}:{observed[y] if observed[y] is not None else '-'}"
            for y in range(row_top, known_bottom + 1)
        )
        print(
            f"directional-residual-profile: y={row_top}..{known_bottom} "
            f"frontier={frontier_x} anchor_y={anchor_y} pending={len(pending)} "
            f"profile_survivors={profile_survivors} profile=[{points}]",
            flush=True,
        )

    proposals: dict[tuple[int, int, int], baseline_up.BaselineMatch] = {}
    for item, profile_tx, model_anchor_rel_y, complete in survivors:
        if not complete:
            continue

        # The profile fragment supplied a horizontal placement and a possible
        # vertical sub-profile alignment.  The actual glyph is still placed on
        # the already-known baseline for the 2-D truth test.
        tx = profile_tx
        physical_left = tx + item.min_x
        physical_right = tx + item.max_x
        if physical_left <= after_left or physical_right >= column_right:
            continue

        placed = frozenset((tx + x, baseline + y) for x, y in item.model.pixels)
        if not placed.issubset(remaining):
            if trace:
                print(
                    f"directional-residual-2d-fail: label={item.model.label!r} "
                    f"style={item.model.style} anchor_y={anchor_y} "
                    f"model_anchor_rel_y={model_anchor_rel_y} "
                    f"tx={tx} pixels={len(placed)}",
                    flush=True,
                )
            continue

        candidate = baseline_up.BaselineMatch(
            model=item.model,
            tx=tx,
            baseline=baseline,
            pixels=placed,
            discovered_y=anchor_y,
        )
        proposals[(id(candidate.model), candidate.tx, candidate.baseline)] = candidate
        if trace:
            print(
                f"directional-residual-2d-pass: label={item.model.label!r} "
                f"style={item.model.style} anchor_y={anchor_y} "
                f"model_anchor_rel_y={model_anchor_rel_y} "
                f"tx={tx} pixels={len(placed)}",
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
            f"directional-residual-pick: after_left={after_left} baseline={baseline} "
            f"frontier={frontier_x} anchor_y={anchor_y} profile_bottom={known_bottom} "
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
