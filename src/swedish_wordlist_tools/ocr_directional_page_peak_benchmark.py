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
    """Continue a row from the residual page profile on the known baseline.

    The page profile is the lower envelope of all remaining glyph profiles.
    A candidate may therefore own one observed profile point and be hidden to
    its right on other rows.  Generate anchors only where a model row exactly
    meets an observed profile point; from that fixed placement reject it if it
    would ever create ink to the left of the observed page profile.  Equality
    means the candidate owns that row, while a model front to the right is
    allowed because another glyph owns the page profile there.

    The observed sequence may start in the middle of a glyph (for example
    below the dot of ``i``).  Once the scan has passed the baseline and the
    model profile ends or enters a gap, that placement is complete and can be
    checked in 2-D.
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

    def build_observed(bottom: int) -> dict[int, int | None]:
        observed: dict[int, int | None] = {}
        for page_y in range(row_top, bottom + 1):
            xs = tuple(x for x in remaining_by_y.get(page_y, ()) if x < column_right)
            observed[page_y] = min(xs) if xs else None
        return observed

    def profile_candidates(
        observed: Mapping[int, int | None],
    ) -> list[tuple[baseline_up.CompiledGlyph, int, bool, int]]:
        survivors: dict[
            tuple[int, int],
            tuple[baseline_up.CompiledGlyph, int, bool, int],
        ] = {}

        for item in library.models:
            possible_anchors: set[tuple[int, int]] = set()
            for page_y, observed_x in observed.items():
                if observed_x is None:
                    continue
                rel_y = page_y - baseline
                model_row = item.rows.get(rel_y)
                if model_row is None:
                    continue
                tx = observed_x - model_row[0]
                possible_anchors.add((tx, page_y))

            for tx, anchor_y in possible_anchors:
                physical_left = tx + item.min_x
                physical_right = tx + item.max_x
                if physical_left <= after_left or physical_right >= column_right:
                    continue

                compatible = True
                owns = 0
                for page_y, observed_x in observed.items():
                    rel_y = page_y - baseline
                    model_row = item.rows.get(rel_y)
                    if model_row is None:
                        continue

                    model_x = tx + model_row[0]
                    if observed_x is None or model_x < observed_x:
                        compatible = False
                        break
                    if model_x == observed_x:
                        owns += 1

                if not compatible or owns == 0:
                    continue

                complete = False
                if known_bottom >= baseline:
                    next_rel_y = known_bottom + 1 - baseline
                    if item.rows.get(next_rel_y) is None:
                        complete = True

                key = (id(item), tx)
                previous = survivors.get(key)
                if previous is None or anchor_y < previous[3]:
                    survivors[key] = (item, tx, complete, anchor_y)

        return list(survivors.values())

    observed = build_observed(known_bottom)
    if not any(x is not None for x in observed.values()):
        return None, ()

    while True:
        survivors = profile_candidates(observed)
        pending = [entry for entry in survivors if not entry[2]]
        if not pending or known_bottom >= source_bottom:
            break
        known_bottom += 1
        observed = build_observed(known_bottom)
        if not any(x is not None for x in observed.values()):
            return None, ()

    profile_survivors = len(survivors)
    frontier_x = min(x for x in observed.values() if x is not None)

    if trace:
        points = " ".join(
            f"{y}:{observed[y] if observed[y] is not None else '-'}"
            for y in range(row_top, known_bottom + 1)
        )
        print(
            f"directional-residual-profile: y={row_top}..{known_bottom} "
            f"frontier={frontier_x} pending={len(pending)} "
            f"profile_survivors={profile_survivors} profile=[{points}]",
            flush=True,
        )

    proposals: dict[tuple[int, int, int], baseline_up.BaselineMatch] = {}
    for item, tx, complete, anchor_y in survivors:
        if not complete:
            continue
        placed = frozenset((tx + x, baseline + y) for x, y in item.model.pixels)
        if not placed.issubset(remaining):
            continue
        candidate = baseline_up.BaselineMatch(
            model=item.model,
            tx=tx,
            baseline=baseline,
            pixels=placed,
            discovered_y=anchor_y,
        )
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
            f"frontier={frontier_x} profile_bottom={known_bottom} "
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
