from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

from .ocr_baseline_up import CompiledGlyphLibrary, ResidualInk
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_column_left_profile import build_column_left_profile
from .ocr_directional_page_benchmark import _isolated_profile_segments
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_shadow_whole_column import _black_pixels, _column_bounds


def _cluster_adjacent_baselines(votes: Counter[int]) -> list[tuple[tuple[int, ...], int, int]]:
    """Collapse only local baseline alternatives into geometric row seeds.

    A one-pixel chain must not bridge a whole 14-pixel ambiguity cloud.  Grow a
    cluster only while every member stays within +/-2 of its weighted centre.
    This keeps the common b/b+1 alternatives together without merging the
    distinct hypotheses produced by unrelated glyph alignments.
    """
    if not votes:
        return []

    result: list[tuple[tuple[int, ...], int, int]] = []
    group: list[int] = []
    weighted_sum = 0
    weight = 0

    def emit() -> None:
        nonlocal group, weighted_sum, weight
        if not group:
            return
        peak = max(votes[b] for b in group)
        peak_members = [b for b in group if votes[b] == peak]
        representative = peak_members[len(peak_members) // 2]
        result.append((tuple(group), representative, weight))
        group = []
        weighted_sum = 0
        weight = 0

    for baseline in sorted(votes):
        baseline_weight = votes[baseline]
        if not group:
            group = [baseline]
            weighted_sum = baseline * baseline_weight
            weight = baseline_weight
            continue
        centre = weighted_sum / weight
        if baseline <= group[-1] + 1 and abs(baseline - centre) <= 2.0:
            group.append(baseline)
            weighted_sum += baseline * baseline_weight
            weight += baseline_weight
        else:
            emit()
            group = [baseline]
            weighted_sum = baseline * baseline_weight
            weight = baseline_weight
    emit()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Experimental whole-column baseline seeding from the leftmost "
            "profile pixels. Only globally-leftmost glyph pixels may anchor."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=36)
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--rows", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--waves", type=int, default=6)
    args = ap.parse_args()

    total_started = perf_counter()
    models = tuple(load_canonical_facit_with_typography(args.facit))
    library = CompiledGlyphLibrary(models)

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    residual = ResidualInk(black)
    column_left, column_right, column_top, column_bottom = bounds

    profile = build_column_left_profile(
        residual.rows,
        top=column_top,
        bottom=column_bottom,
        left=column_left,
        right=column_right,
    )
    segments = _isolated_profile_segments(profile)

    columns = context["row_map"].get("columns") or []
    reference_rows = columns[args.column].get("rows") or []
    if args.rows > 0:
        reference_rows = reference_rows[: args.rows]

    # Compile only globally-leftmost glyph pixels. Multiple y values are useful:
    # an accent, descender or capital shape can make the left edge occur away
    # from the ordinary body row.
    left_anchors: list[tuple[object, int]] = []
    for item in library.models:
        for model_x, model_y in item.model.pixels:
            if model_x == item.min_x:
                left_anchors.append((item, model_y))

    proposals = 0
    exact_checks = 0
    exact_hits = 0
    baseline_hist: Counter[int] = Counter()
    baseline_labels: dict[int, set[str]] = defaultdict(set)
    segment_results: list[tuple[int, int, int, int, tuple[int, ...]]] = []

    match_started = perf_counter()
    for segment_top, segment_bottom, min_x in segments:
        # Only page rows that actually attain the segment's leftmost x are
        # possible anchors for a globally-leftmost glyph pixel.
        anchor_ys = tuple(
            y
            for y in range(segment_top, segment_bottom + 1)
            if profile.at(y) == min_x
        )
        segment_baselines: Counter[int] = Counter()

        seen: set[tuple[int, int, int]] = set()
        for page_y in anchor_ys:
            for item, model_y in left_anchors:
                tx = min_x - item.min_x
                baseline = page_y - model_y
                key = (id(item.model), tx, baseline)
                if key in seen:
                    continue
                seen.add(key)
                proposals += 1

                top = baseline + item.model.min_y
                bottom = baseline + item.model.max_y
                if top < column_top or bottom >= column_bottom:
                    continue
                if tx + item.max_x >= column_right:
                    continue

                exact_checks += 1
                if not all(
                    (tx + x, baseline + y) in black
                    for x, y in item.model.pixels
                ):
                    continue

                exact_hits += 1
                baseline_hist[baseline] += 1
                segment_baselines[baseline] += 1
                baseline_labels[baseline].add(item.model.label)

        # The strongest baselines are useful even when several glyph models are
        # raster homonyms. Keep ties: the whole point is to see whether those
        # homonyms collapse onto the same geometric baseline.
        if segment_baselines:
            peak = max(segment_baselines.values())
            strongest = tuple(sorted(
                baseline for baseline, count in segment_baselines.items()
                if count == peak
            ))
        else:
            strongest = ()
        segment_results.append(
            (segment_top, segment_bottom, min_x, len(anchor_ys), strongest)
        )

    matching_seconds = perf_counter() - match_started

    # Experimental peeling: repeatedly inspect the current residual column
    # profile, match exact glyphs anchored only on that wave's leftmost profile
    # pixels, consume all non-overlapping exact hits, then expose the next wave.
    wave_residual = ResidualInk(black)
    wave_started = perf_counter()
    wave_summaries: list[tuple[int, int, int, int, int]] = []
    all_wave_baseline_votes: Counter[int] = Counter()
    for wave in range(max(0, args.waves)):
        wave_profile = build_column_left_profile(
            wave_residual.rows,
            top=column_top,
            bottom=column_bottom,
            left=column_left,
            right=column_right,
        )
        nonblank = [int(x) for x in wave_profile.values if x is not None]
        if not nonblank:
            break
        wave_x = min(nonblank)
        wave_ys = tuple(
            y for y in wave_profile.nonblank_y()
            if wave_profile.at(y) == wave_x
        )

        wave_hits: list[tuple[int, int, object, frozenset[tuple[int, int]]]] = []
        seen_wave: set[tuple[int, int, int]] = set()
        proposals_wave = 0
        for page_y in wave_ys:
            for item, model_y in left_anchors:
                tx = wave_x - item.min_x
                baseline = page_y - model_y
                key = (id(item.model), tx, baseline)
                if key in seen_wave:
                    continue
                seen_wave.add(key)
                proposals_wave += 1
                top = baseline + item.model.min_y
                bottom = baseline + item.model.max_y
                if top < column_top or bottom >= column_bottom:
                    continue
                if tx + item.max_x >= column_right:
                    continue
                placed = frozenset(
                    (tx + x, baseline + y)
                    for x, y in item.model.pixels
                )
                if placed.issubset(wave_residual.pixels):
                    wave_hits.append((baseline, tx, item, placed))

        # Prefer larger exact glyphs at a wave.  Do not consume overlapping
        # alternatives/homonyms twice; they may still vote for the same baseline.
        wave_hits.sort(key=lambda h: (-len(h[3]), h[0], h[1]))
        consumed: set[tuple[int, int]] = set()
        accepted = 0
        baseline_votes: Counter[int] = Counter()
        for baseline, tx, item, placed in wave_hits:
            baseline_votes[baseline] += 1
            all_wave_baseline_votes[baseline] += 1
            if placed & consumed:
                continue
            consumed.update(placed)
            accepted += 1
        wave_residual.consume(consumed)
        wave_summaries.append(
            (wave, wave_x, len(wave_ys), proposals_wave, accepted)
        )
        strongest = ()
        if baseline_votes:
            peak = max(baseline_votes.values())
            strongest = tuple(
                b for b, n in sorted(baseline_votes.items()) if n == peak
            )
        accepted_baselines: Counter[int] = Counter()
        for baseline, tx, item, placed in wave_hits:
            if placed.issubset(consumed):
                accepted_baselines[baseline] += 1
        accepted_detail = ",".join(
            f"{b}:{accepted_baselines[b]}" for b in sorted(accepted_baselines)
        )
        print(
            f"leftmost-wave: wave={wave} x={wave_x} anchor_rows={len(wave_ys)} "
            f"proposals={proposals_wave} exact_hits={len(wave_hits)} "
            f"accepted={accepted} consumed_pixels={len(consumed)} "
            f"strongest_baselines={strongest} accepted_baselines=[{accepted_detail}] "
            f"remaining={len(wave_residual.pixels)}",
            flush=True,
        )
        if not consumed:
            break

    wave_seconds = perf_counter() - wave_started

    # Diagnostic only: raw exact-hit votes contain many alternative baselines
    # for the same consumed glyph.  The accepted-baseline lists above show the
    # hypotheses that actually survived non-overlapping peeling.
    clustered_wave_baselines = _cluster_adjacent_baselines(all_wave_baseline_votes)
    print(
        "leftmost-wave-row-seeds: "
        + " ".join(
            f"{representative}[{','.join(str(b) for b in members)}]:{total_votes}"
            for members, representative, total_votes in clustered_wave_baselines
        ),
        flush=True,
    )

    print(
        f"leftmost-seed-start: page={args.page} column={args.column} "
        f"models={len(models)} left_anchors={len(left_anchors)} "
        f"segments={len(segments)} reference_rows={len(reference_rows)}",
        flush=True,
    )
    for top, bottom, min_x, anchor_count, strongest in segment_results:
        detail = ",".join(
            f"{baseline}:{'/'.join(sorted(baseline_labels[baseline]))}"
            for baseline in strongest
        )
        print(
            f"leftmost-seed-segment: y={top}..{bottom} min_x={min_x} "
            f"anchor_rows={anchor_count} strongest=[{detail}]",
            flush=True,
        )

    print(
        "leftmost-seed-baselines: "
        + " ".join(
            f"{baseline}:{baseline_hist[baseline]}"
            for baseline in sorted(baseline_hist)
        ),
        flush=True,
    )
    print(
        f"leftmost-seed-done: proposals={proposals} exact_checks={exact_checks} "
        f"exact_hits={exact_hits} distinct_baselines={len(baseline_hist)} "
        f"matching={matching_seconds:.6f}s waves={len(wave_summaries)} "
        f"wave_matching={wave_seconds:.6f}s total={perf_counter()-total_started:.6f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
