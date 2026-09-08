from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

from .ocr_candidate_survival import glyph_left_profile, run_candidate_survival
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array
from .ocr_row_split_left_support import row_start_geometry
from .ocr_shadow_whole_column import _black_pixels, _column_bounds, _start_search_ranges


def _row_page_span(context: dict, column: int, row_index: int) -> tuple[int, int]:
    columns = context["row_map"].get("columns") or []
    if not 0 <= column < len(columns):
        raise ValueError(f"column out of range: {column}")
    rows = columns[column].get("rows") or []
    if not 0 <= row_index < len(rows):
        raise ValueError(f"row out of range: column={column} row={row_index}")
    row = rows[row_index]
    top = int(row["page_top"])
    bottom = int(row["page_bottom"])
    if bottom <= top:
        raise ValueError(f"invalid row span: {top}..{bottom}")
    return top, bottom


def _model_x_bounds(model) -> tuple[int, int]:
    xs = [x for x, _y in model.pixels]
    return min(xs), max(xs)


def _placed_pixels(model, *, tx: int, baseline: int) -> frozenset[tuple[int, int]]:
    return frozenset((tx + x, baseline + y) for x, y in model.pixels)


def _hit_bounds(hit) -> tuple[int, int]:
    min_x, max_x = _model_x_bounds(hit.model)
    return hit.x + min_x, hit.x + max_x


def _hit_pixels(hit) -> frozenset[tuple[int, int]]:
    return _placed_pixels(hit.model, tx=hit.x, baseline=hit.baseline)


def _left_profile_group(completed, *, baseline: int | None = None):
    candidates = list(completed)
    if baseline is not None:
        candidates = [hit for hit in candidates if hit.baseline == baseline]
    if not candidates:
        return [], []
    left_x = min(_hit_bounds(hit)[0] for hit in candidates)
    candidates = [hit for hit in candidates if _hit_bounds(hit)[0] == left_x]
    pixel_sets = {id(hit): _hit_pixels(hit) for hit in candidates}
    maximal = [
        hit
        for hit in candidates
        if not any(
            pixel_sets[id(hit)] < pixel_sets[id(other)]
            for other in candidates
            if other is not hit
        )
    ]
    return candidates, maximal


def _pick_left_anchor(completed, *, baseline: int | None = None):
    candidates, maximal = _left_profile_group(completed, baseline=baseline)
    if not candidates or not maximal:
        return None
    by_pixels: dict[frozenset[tuple[int, int]], list[object]] = defaultdict(list)
    for hit in maximal:
        by_pixels[_hit_pixels(hit)].append(hit)
    if len(by_pixels) != 1:
        return None
    equivalent = next(iter(by_pixels.values()))
    return max(
        equivalent,
        key=lambda hit: (
            len(hit.model.pixels),
            hit.front_rows,
            -hit.hidden_rows,
            hit.model.sources,
            hit.bottom_y - hit.top_y + 1,
        ),
    )


def _print_profile_group(prefix: str, completed, *, baseline: int | None = None) -> None:
    candidates, maximal = _left_profile_group(completed, baseline=baseline)
    if not candidates:
        print(f"{prefix}: candidates=0 maximal=0", flush=True)
        return
    left_x = _hit_bounds(candidates[0])[0]
    maximal_ids = {id(hit) for hit in maximal}
    distinct_maximal = len({_hit_pixels(hit) for hit in maximal})
    print(
        f"{prefix}: left={left_x} candidates={len(candidates)} "
        f"maximal={len(maximal)} distinct_maximal={distinct_maximal}",
        flush=True,
    )
    for hit in sorted(
        candidates,
        key=lambda h: (
            id(h) not in maximal_ids,
            -len(h.model.pixels),
            h.baseline,
            h.model.label,
            h.model.style,
        ),
    ):
        print(
            f"{prefix}-candidate: start={hit.model.label!r}/{hit.model.style} "
            f"x={_hit_bounds(hit)[0]}..{_hit_bounds(hit)[1]} baseline={hit.baseline} "
            f"glyph_pixels={len(hit.model.pixels)} front={hit.front_rows} "
            f"hidden={hit.hidden_rows} maximal={id(hit) in maximal_ids}",
            flush=True,
        )


def _baseline_locked_matches(
    black: set[tuple[int, int]],
    models,
    *,
    baseline: int,
    start_x: int,
    end_x: int,
):
    by_left: dict[int, list[tuple[object, int, int, frozenset[tuple[int, int]]]]] = defaultdict(list)
    for model in models:
        min_x, max_x = _model_x_bounds(model)
        for physical_left in range(start_x, end_x + 1):
            tx = physical_left - min_x
            physical_right = tx + max_x
            if physical_right > end_x:
                continue
            placed = _placed_pixels(model, tx=tx, baseline=baseline)
            if placed.issubset(black):
                by_left[physical_left].append((model, tx, physical_right, placed))
    for rows in by_left.values():
        rows.sort(
            key=lambda row: (
                -len(row[0].pixels),
                -row[0].sources,
                row[2],
                row[0].label,
                row[0].style,
            )
        )
    return dict(sorted(by_left.items()))


def _dominance(rows):
    out = []
    for row in rows:
        placed = row[3]
        strict_subsets = [other for other in rows if other is not row and other[3] < placed]
        strict_supersets = [other for other in rows if other is not row and placed < other[3]]
        out.append((row, len(strict_subsets), len(strict_supersets)))
    return out


def _unique_maximal_at(rows):
    dominance = _dominance(rows)
    maximal = [row for row, _subsets, supersets in dominance if supersets == 0]
    distinct = {row[3] for row in maximal}
    if len(distinct) != 1:
        return None
    target = next(iter(distinct))
    equivalent = [row for row in maximal if row[3] == target]
    return max(equivalent, key=lambda row: (len(row[0].pixels), row[0].sources))


def _blank_through_baseline(
    black: set[tuple[int, int]], *, x: int, top_y: int, baseline: int
) -> bool:
    return all((x, y) not in black for y in range(top_y, baseline + 1))


def _row_lane_ink_to_right(
    black: set[tuple[int, int]],
    *,
    after_x: int,
    end_x: int,
    row_top: int,
    row_bottom: int,
) -> set[tuple[int, int]]:
    """Black pixels still belonging to this row's raster lanes, to the right."""
    return {
        (x, y)
        for x, y in black
        if after_x < x <= end_x and row_top <= y < row_bottom
    }


def _profile_restart(
    black: set[tuple[int, int]],
    models,
    *,
    separator_x: int,
    end_x: int,
    row_top: int,
    row_bottom: int,
):
    right_black = {(x, y) for x, y in black if separator_x < x <= end_x}
    if not right_black:
        return None, None
    result = run_candidate_survival(
        right_black,
        models,
        start_y=row_top,
        end_y=row_bottom - 1,
        allowed_translate_x_ranges=((separator_x + 1, end_x),),
    )
    return result, _pick_left_anchor(result.completed)


def _walk_first_row(
    black: set[tuple[int, int]],
    models,
    *,
    first_anchor,
    row_top: int,
    row_bottom: int,
    column_right: int,
    max_glyphs: int = 80,
):
    baseline = first_anchor.baseline
    current = first_anchor
    labels = [first_anchor.model.label]
    print(
        f"column-top-walk-glyph: n=0 via=initial start={first_anchor.model.label!r}/"
        f"{first_anchor.model.style} x={_hit_bounds(first_anchor)[0]}..{_hit_bounds(first_anchor)[1]} "
        f"baseline={baseline}",
        flush=True,
    )

    for n in range(1, max_glyphs):
        _left, right = _hit_bounds(current)
        cursor = right + 1
        if cursor >= column_right:
            print(f"column-top-walk-stop: reason=row-end-column x={cursor}", flush=True)
            break

        if _blank_through_baseline(black, x=cursor, top_y=row_top, baseline=baseline):
            below = sorted(y for x, y in black if x == cursor and baseline < y < row_bottom)
            old_baseline = baseline
            print(
                f"column-top-walk-separator: x={cursor} top={row_top} baseline={old_baseline} "
                f"below_baseline_ink={below}",
                flush=True,
            )

            lane_ink = _row_lane_ink_to_right(
                black,
                after_x=cursor,
                end_x=column_right - 1,
                row_top=row_top,
                row_bottom=row_bottom,
            )
            if not lane_ink:
                print(
                    f"column-top-walk-stop: reason=row-end-empty-lanes separator={cursor} "
                    f"row_y={row_top}..{row_bottom-1}",
                    flush=True,
                )
                break

            restart_result, next_hit = _profile_restart(
                black,
                models,
                separator_x=cursor,
                end_x=column_right - 1,
                row_top=row_top,
                row_bottom=row_bottom,
            )
            if restart_result is None:
                print(
                    f"column-top-walk-stop: reason=row-end-no-ink separator={cursor}",
                    flush=True,
                )
                break

            _print_profile_group("column-top-walk-profile-group", restart_result.completed)
            if next_hit is None:
                candidates, maximal = _left_profile_group(restart_result.completed)
                distinct_maximal = len({_hit_pixels(hit) for hit in maximal})
                print(
                    f"column-top-walk-stop: reason=profile-ambiguous-after-separator "
                    f"separator={cursor} old_baseline={old_baseline} "
                    f"lane_pixels={len(lane_ink)} candidates={len(candidates)} "
                    f"distinct_maximal={distinct_maximal}",
                    flush=True,
                )
                break

            next_left, next_right = _hit_bounds(next_hit)
            baseline = next_hit.baseline
            print(
                f"column-top-walk-glyph: n={n} via=profile separator={cursor} "
                f"start={next_hit.model.label!r}/{next_hit.model.style} "
                f"x={next_left}..{next_right} baseline={baseline} "
                f"baseline_change={baseline-old_baseline:+d} "
                f"front={next_hit.front_rows} hidden={next_hit.hidden_rows} "
                f"glyph_pixels={len(next_hit.model.pixels)}",
                flush=True,
            )
            current = next_hit
            labels.append(next_hit.model.label)
            continue

        horizontal = _baseline_locked_matches(
            black,
            models,
            baseline=baseline,
            start_x=cursor,
            end_x=column_right - 1,
        )
        rows = horizontal.get(cursor, [])
        chosen = _unique_maximal_at(rows)
        if chosen is None:
            maximal = [row for row, _subsets, supersets in _dominance(rows) if supersets == 0]
            print(
                f"column-top-walk-stop: reason=connected-ambiguous x={cursor} "
                f"candidates={len(rows)} distinct_maximal={len({row[3] for row in maximal})} "
                f"baseline={baseline}",
                flush=True,
            )
            break

        model, tx, physical_right, _placed = chosen
        print(
            f"column-top-walk-glyph: n={n} via=2d-connected "
            f"start={model.label!r}/{model.style} x={cursor}..{physical_right} "
            f"baseline={baseline} glyph_pixels={len(model.pixels)} sources={model.sources}",
            flush=True,
        )

        class _PlacedHit:
            pass

        next_hit = _PlacedHit()
        next_hit.model = model
        next_hit.x = tx
        next_hit.baseline = baseline
        current = next_hit
        labels.append(model.label)
    else:
        print(f"column-top-walk-stop: reason=max-glyphs n={max_glyphs}", flush=True)

    print(f"column-top-walk-text: {''.join(labels)!r}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=39)
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--homonym-x", type=int, default=46)
    ap.add_argument("--headword-x", type=int, default=57)
    ap.add_argument("--continuation-x", type=int, default=68)
    ap.add_argument("--start-x-tolerance", type=int, default=7)
    ap.add_argument("--show-steps", action="store_true")
    ap.add_argument("--show-completed", type=int, default=80)
    ap.add_argument("--show-horizontal", type=int, default=0)
    args = ap.parse_args()

    models_started = perf_counter()
    models = tuple(load_canonical_facit_with_typography(args.facit))
    print(f"column-top-models: models={len(models)} load={perf_counter()-models_started:.4f}s", flush=True)

    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    bounds = _column_bounds(context, args.column)
    black = _black_pixels(context, bounds)
    row_top, row_bottom = _row_page_span(context, args.column, 0)

    geometry = row_start_geometry(args.homonym_x, args.headword_x, args.continuation_x)
    ranges = _start_search_ranges(geometry, args.start_x_tolerance)

    print(
        f"column-top-row: page={args.page} column={args.column} row=0 "
        f"top={row_top} bottom={row_bottom} y={row_top}..{row_bottom-1} "
        f"bounds={bounds} ranges={ranges}", flush=True,
    )

    started = perf_counter()
    result = run_candidate_survival(
        black, models, start_y=row_top, end_y=row_bottom - 1,
        allowed_translate_x_ranges=ranges,
    )
    seconds = perf_counter() - started

    total_died = sum(step.died for step in result.steps)
    total_completed = sum(step.completed for step in result.steps)
    peak_live = max((step.after for step in result.steps), default=0)
    print(
        f"column-top-summary: seeded={result.seeded} completed={len(result.completed)} "
        f"completed_events={total_completed} died={total_died} peak_live={peak_live} "
        f"steps={len(result.steps)} search={seconds:.4f}s", flush=True,
    )

    baseline_counts = Counter(hit.baseline for hit in result.completed)
    for baseline, count in sorted(baseline_counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"column-top-baseline: y={baseline} hits={count}", flush=True)

    if args.show_steps:
        for step in result.steps:
            profile = -1 if step.profile_x is None else step.profile_x
            print(
                f"column-top-step: y={step.y} profile={profile} born={step.born} "
                f"before={step.before} after={step.after} died={step.died} "
                f"completed={step.completed}", flush=True,
            )

    for i, hit in enumerate(result.completed[: max(0, args.show_completed)]):
        profile = ",".join("_" if value is None else str(value) for value in glyph_left_profile(hit.model))
        print(
            f"column-top-hit: n={i} seed={hit.seed_y} top={hit.top_y} "
            f"baseline={hit.baseline} bottom={hit.bottom_y} "
            f"start={hit.model.label!r}/{hit.model.style}@x{hit.x} "
            f"front={hit.front_rows} hidden={hit.hidden_rows} "
            f"profile=[{profile}] glyph_pixels={len(hit.model.pixels)}", flush=True,
        )

    _print_profile_group("column-top-anchor-group", result.completed)
    anchor = _pick_left_anchor(result.completed)
    if anchor is None:
        print("column-top-anchor: ambiguous", flush=True)
        return 0

    anchor_left, anchor_right = _hit_bounds(anchor)
    print(
        f"column-top-anchor: start={anchor.model.label!r}/{anchor.model.style} "
        f"x={anchor_left}..{anchor_right} baseline={anchor.baseline} "
        f"front={anchor.front_rows} hidden={anchor.hidden_rows} "
        f"glyph_pixels={len(anchor.model.pixels)}", flush=True,
    )

    _column_left, column_right, _column_top, _column_bottom = bounds
    _walk_first_row(
        black,
        models,
        first_anchor=anchor,
        row_top=row_top,
        row_bottom=row_bottom,
        column_right=column_right,
    )

    if args.show_horizontal > 0:
        horizontal = _baseline_locked_matches(
            black, models, baseline=anchor.baseline,
            start_x=anchor_right + 1, end_x=column_right - 1,
        )
        printed = 0
        for physical_left, rows in horizontal.items():
            dominance_rows = _dominance(rows)
            maximal = sum(1 for _row, _subsets, supersets in dominance_rows if supersets == 0)
            print(
                f"column-top-horizontal-group: left={physical_left} candidates={len(rows)} maximal={maximal}",
                flush=True,
            )
            for (model, tx, physical_right, _placed), dominates, dominated_by in dominance_rows:
                if printed >= args.show_horizontal:
                    break
                print(
                    f"column-top-horizontal: left={physical_left} right={physical_right} "
                    f"start={model.label!r}/{model.style}@x{tx} baseline={anchor.baseline} "
                    f"glyph_pixels={len(model.pixels)} sources={model.sources} "
                    f"dominates={dominates} dominated_by={dominated_by}", flush=True,
                )
                printed += 1
            if printed >= args.show_horizontal:
                break
        print(
            f"column-top-horizontal-summary: positions={len(horizontal)} printed={printed} "
            f"search_x={anchor_right + 1}..{column_right - 1}", flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
