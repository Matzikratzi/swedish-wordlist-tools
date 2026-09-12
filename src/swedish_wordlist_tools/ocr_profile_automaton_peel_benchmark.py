from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

from .ocr_baseline_up import CompiledGlyphLibrary, ResidualInk
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_profile_leftmost_baseline_seed_benchmark import _reconstruct_rows_from_accepted_streams
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_shadow_whole_column import _black_pixels, _column_bounds


def _compile_profile_prefix_index(
    library: CompiledGlyphLibrary,
    *,
    prefix_len: int = 3,
):
    """Group glyph/anchor templates by a short left-profile prefix.

    The prefix is only a subset of the exact 1D checks used by the matcher, so
    rejecting a bucket here cannot change which candidates are valid.
    """
    groups: dict[
        tuple[tuple[int, int], ...],
        list[tuple[object, tuple[tuple[int, int], ...], int]],
    ] = defaultdict(list)

    for item in library.models:
        by_y: dict[int, int] = {}
        for x, y in item.model.pixels:
            old = by_y.get(y)
            if old is None or x < old:
                by_y[y] = x
        left_profile = tuple(sorted(by_y.items()))
        anchor_ys = tuple(sorted(y for y, x in by_y.items() if x == item.min_x))

        for anchor_y in anchor_ys:
            # The seed row itself is guaranteed to match min_x and carries no
            # discrimination.  Prefer the nearest rows above/below it.
            ordered = sorted(
                (
                    (model_y, model_left)
                    for model_y, model_left in left_profile
                    if model_y != anchor_y
                ),
                key=lambda point: (abs(point[0] - anchor_y), point[0]),
            )
            chosen = tuple(ordered[:prefix_len])
            chosen_set = set(chosen)
            signature = tuple(
                (model_y - anchor_y, model_left - item.min_x)
                for model_y, model_left in chosen
            )
            remainder = tuple(
                point for point in left_profile if point not in chosen_set
            )
            groups[signature].append((item, remainder, anchor_y))

    return tuple(
        (signature, tuple(entries))
        for signature, entries in groups.items()
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Experimental left-profile automaton peel. A candidate family is "
            "spawned from one globally-leftmost profile pixel, filtered only by "
            "the 1D left profile, and only completed survivors get a 2D check."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=36)
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--rows", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--max-steps", type=int, default=0, help="0 means until stuck/empty")
    ap.add_argument("--prefix-len", type=int, default=3, help="Number of nearest profile rows used by the prefix index")
    args = ap.parse_args()

    total_started = perf_counter()
    models = tuple(load_canonical_facit_with_typography(args.facit))
    library = CompiledGlyphLibrary(models)
    prefix_index = _compile_profile_prefix_index(library, prefix_len=args.prefix_len)

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    residual = ResidualInk(black)
    column_left, column_right, column_top, column_bottom = bounds

    columns = context["row_map"].get("columns") or []
    reference_rows = columns[args.column].get("rows") or []
    if args.rows > 0:
        reference_rows = reference_rows[: args.rows]

    accepted_streams: dict[int, list[tuple[int, int, int, int, str, str, int, int]]] = defaultdict(list)

    steps = 0
    seed_points = 0
    candidate_spawns = 0
    prefix_groups_checked = 0
    prefix_groups_rejected = 0
    prefix_templates_passed = 0
    profile_rows_checked = 0
    profile_rejects = 0
    profile_survivors = 0
    checks_2d = 0
    hits_2d = 0
    profile_build_seconds = 0.0
    profile_filter_seconds = 0.0
    check_2d_seconds = 0.0
    matching_started = perf_counter()

    # Maintain the residual left profile incrementally.  Removing one glyph can
    # only change rows touched by that glyph, so there is no reason to rescan
    # every page row after every accepted character.
    t0 = perf_counter()
    profile_left: dict[int, int] = {
        y: min(xs)
        for y, xs in residual.rows.items()
        if xs and column_top <= y < column_bottom
    }
    profile_build_seconds += perf_counter() - t0

    while residual.pixels and (args.max_steps == 0 or steps < args.max_steps):
        if not profile_left:
            break
        min_x = min(profile_left.values())
        min_ys = tuple(sorted(y for y, x in profile_left.items() if x == min_x))

        accepted = None
        accepted_seed_y = None
        best_survivor_count = 0

        # Try the globally-leftmost profile pixels in reading order.  As soon as
        # one seed yields a real glyph, consume just that glyph and rebuild the
        # affected profile on the next iteration.
        for seed_y in min_ys:
            seed_points += 1
            survivors = []
            seen: set[tuple[int, int, int]] = set()
            filter_started = perf_counter()

            for signature, templates in prefix_index:
                prefix_groups_checked += 1
                prefix_support = 0
                prefix_ok = True
                for dy, dx in signature:
                    actual_x = profile_left.get(seed_y + dy)
                    profile_rows_checked += 1
                    expected_x = min_x + dx
                    if actual_x is None or actual_x > expected_x:
                        prefix_ok = False
                        break
                    if actual_x == expected_x:
                        prefix_support += 1
                if not prefix_ok:
                    prefix_groups_rejected += 1
                    continue

                prefix_templates_passed += len(templates)
                for item, left_profile, anchor_y in templates:
                    tx = min_x - item.min_x
                    if tx + item.max_x >= column_right or tx + item.min_x < column_left:
                        continue

                    baseline = seed_y - anchor_y
                    key = (id(item.model), tx, baseline)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidate_spawns += 1

                    top = baseline + item.model.min_y
                    bottom = baseline + item.model.max_y
                    if top < column_top or bottom >= column_bottom:
                        continue

                    support = prefix_support
                    contradicted = False
                    for model_y, model_left in left_profile:
                        page_y = baseline + model_y
                        expected_x = tx + model_left
                        actual_x = profile_left.get(page_y)
                        profile_rows_checked += 1
                        # If the current page profile is to the right of the
                        # glyph's required left pixel (or blank), that required
                        # pixel cannot exist.  A smaller page x may simply be
                        # masking this glyph and therefore does not disprove it.
                        if actual_x is None or actual_x > expected_x:
                            contradicted = True
                            profile_rejects += 1
                            break
                        if actual_x == expected_x:
                            support += 1
                    if contradicted:
                        continue
                    survivors.append((item, tx, baseline, support))

            profile_filter_seconds += perf_counter() - filter_started
            profile_survivors += len(survivors)
            best_survivor_count = max(best_survivor_count, len(survivors))

            # Largest completed profile candidate first, just like the working
            # peel prefers the largest exact glyph.  2D checks happen only here.
            survivors.sort(
                key=lambda entry: (
                    -len(entry[0].model.pixels),
                    -entry[3],
                    entry[2],
                    entry[0].model.label,
                    entry[0].model.style,
                )
            )
            check_started = perf_counter()
            for item, tx, baseline, support in survivors:
                checks_2d += 1
                placed = frozenset(
                    (tx + x, baseline + y)
                    for x, y in item.model.pixels
                )
                if not placed.issubset(residual.pixels):
                    continue
                hits_2d += 1
                accepted = (item, tx, baseline, support, placed)
                accepted_seed_y = seed_y
                break
            check_2d_seconds += perf_counter() - check_started

            if accepted is not None:
                break

        if accepted is None:
            print(
                f"profile-auto-stuck: step={steps} x={min_x} seeds={len(min_ys)} "
                f"best_survivors={best_survivor_count} remaining={len(residual.pixels)}",
                flush=True,
            )
            break

        item, tx, baseline, support, placed = accepted
        left = min(x for x, _y in placed)
        right = max(x for x, _y in placed)
        top = min(y for _x, y in placed)
        bottom = max(y for _x, y in placed)
        affected_ys = {y for _x, y in placed}
        update_started = perf_counter()
        residual.consume(placed)
        for page_y in affected_ys:
            xs = residual.rows.get(page_y)
            if xs:
                profile_left[page_y] = min(xs)
            else:
                profile_left.pop(page_y, None)
        profile_build_seconds += perf_counter() - update_started

        accepted_streams[baseline].append(
            (left, right, steps, min_x, item.model.label, item.model.style, top, bottom)
        )

        if steps < 20 or steps % 100 == 0 or not residual.pixels:
            print(
                f"profile-auto-step: step={steps} seed=({min_x},{accepted_seed_y}) "
                f"glyph={item.model.label!r}/{item.model.style} baseline={baseline} "
                f"x={left}..{right} y={top}..{bottom} support={support} "
                f"remaining={len(residual.pixels)}",
                flush=True,
            )
        steps += 1

    matching_seconds = perf_counter() - matching_started

    reconstructed_rows = _reconstruct_rows_from_accepted_streams(accepted_streams)
    print(
        f"profile-auto-rows-start: rows={len(reconstructed_rows)} "
        f"reference_rows={len(reference_rows)}",
        flush=True,
    )
    for row_index, (representative, members, top, bottom, text_value, glyph_count) in enumerate(reconstructed_rows):
        reference = reference_rows[row_index] if row_index < len(reference_rows) else None
        reference_detail = (
            "reference_y=-"
            if reference is None
            else f"reference_y={int(reference['page_top'])}..{int(reference['page_bottom']) - 1}"
        )
        print(
            f"profile-auto-row: row={row_index} baseline={representative} members={members} "
            f"y={top}..{bottom} glyphs={glyph_count} text={text_value!r} {reference_detail}",
            flush=True,
        )
    print("profile-auto-rows-end", flush=True)

    print(
        f"profile-auto-done: prefix_len={args.prefix_len} steps={steps} remaining={len(residual.pixels)} "
        f"seed_points={seed_points} prefix_groups_checked={prefix_groups_checked} "
        f"prefix_groups_rejected={prefix_groups_rejected} "
        f"prefix_templates_passed={prefix_templates_passed} "
        f"candidate_spawns={candidate_spawns} "
        f"profile_rows_checked={profile_rows_checked} profile_rejects={profile_rejects} "
        f"profile_survivors={profile_survivors} checks_2d={checks_2d} hits_2d={hits_2d} "
        f"profile_update={profile_build_seconds:.6f}s "
        f"profile_filter={profile_filter_seconds:.6f}s "
        f"check_2d={check_2d_seconds:.6f}s matching={matching_seconds:.6f}s "
        f"total={perf_counter()-total_started:.6f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
