from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from . import ocr_page_cached_fast_path as page_fast
from . import ocr_priority_fast_path as priority
from .ocr_glyph_matcher import Match
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_review_page_pixel_array_glyphs_html import (
    build_page_context_pixel_array,
    load_review_state_pixel_array,
)


def trace_exact_cover(
    ink: set[tuple[int, int]],
    width: int,
    height: int,
    models,
    *,
    max_states: int = 20000,
) -> dict:
    """Run the page-cached exact cover while collecting backtracking diagnostics."""
    candidates = page_fast._bound_page_candidates(models)
    row_kind = str(getattr(priority._tls, "row_kind", "unknown"))
    target = frozenset(ink)
    failed: set[tuple[frozenset[tuple[int, int]], int | None, bool, int | None]] = set()

    states = 0
    placements_tested = 0
    subset_placements = 0
    recursive_branches = 0
    memo_hits = 0
    max_depth = 0
    states_by_depth: Counter[int] = Counter()
    dead_by_candidate: Counter[tuple[int, str, str, int]] = Counter()
    dead_by_anchor: Counter[int] = Counter()
    branch_by_candidate: Counter[tuple[int, str, str, int]] = Counter()

    def search(
        remaining: frozenset[tuple[int, int]],
        baseline: int | None,
        previous_style: str | None,
        leading_homonym_seen: bool,
        previous_right: int | None,
        depth: int,
    ) -> tuple[Match, ...] | None:
        nonlocal states, placements_tested, subset_placements, recursive_branches, memo_hits, max_depth
        if not remaining:
            return ()
        state = (remaining, baseline, leading_homonym_seen, previous_right)
        if state in failed:
            memo_hits += 1
            return None
        states += 1
        states_by_depth[depth] += 1
        max_depth = max(max_depth, depth)
        if states > max_states:
            return None

        anchor_x = min(x for x, _y in remaining)
        anchor_y = min(y for x, y in remaining if x == anchor_x)
        first_glyph = len(remaining) == len(target)

        for model, min_x, left_pixels in page_fast._iter_candidates(
            candidates,
            first_glyph=first_glyph,
            previous_style=previous_style,
            row_kind=row_kind,
            leading_homonym_seen=leading_homonym_seen,
            baseline_established=baseline is not None,
        ):
            x0 = anchor_x - min_x
            if x0 < 0 or x0 + model.width > width:
                continue
            _mx, my = left_pixels[0]
            candidate_baseline = anchor_y - my
            is_leading_homonym = (
                first_glyph and row_kind == "homonym" and priority._is_homonym_model(model)
            )
            if baseline is not None and candidate_baseline != baseline:
                continue
            if candidate_baseline < -model.min_y:
                continue
            if candidate_baseline > height - 1 - model.max_y:
                continue

            placements_tested += 1
            placed = frozenset((x0 + x, candidate_baseline + y) for x, y in model.pixels)
            if not placed.issubset(remaining):
                continue
            if not page_fast.placement_advances_right(placed, previous_right):
                continue

            subset_placements += 1
            typography = priority._typographic_style(model.style) or str(model.style)
            key = (anchor_x, model.label, str(typography), len(model.pixels))
            branch_by_candidate[key] += 1
            match = Match(
                label=model.label,
                style=model.style,
                x=x0,
                baseline=candidate_baseline,
                pixels=placed,
                model_pixels=len(model.pixels),
                sources=model.sources,
            )
            if is_leading_homonym:
                next_baseline = None
                saw_homonym = True
            else:
                next_baseline = candidate_baseline if baseline is None else baseline
                saw_homonym = leading_homonym_seen

            recursive_branches += 1
            tail = search(
                frozenset(remaining.difference(placed)),
                next_baseline,
                priority._typographic_style(model.style),
                saw_homonym,
                page_fast._placed_right(placed),
                depth + 1,
            )
            if tail is not None:
                return (match,) + tail
            dead_by_candidate[key] += 1
            dead_by_anchor[anchor_x] += 1

        failed.add(state)
        return None

    chosen = search(target, None, None, False, None, 0)
    return {
        "row_kind": row_kind,
        "states": states,
        "placements_tested": placements_tested,
        "subset_placements": subset_placements,
        "recursive_branches": recursive_branches,
        "memo_hits": memo_hits,
        "failed_states": len(failed),
        "max_depth": max_depth,
        "states_by_depth": states_by_depth,
        "dead_by_candidate": dead_by_candidate,
        "dead_by_anchor": dead_by_anchor,
        "branch_by_candidate": branch_by_candidate,
        "chosen": chosen,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Trace exact-cover backtracking for one SAOL OCR row")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    models = load_facit_with_typography(args.facit)
    context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
    position = (args.column, args.row)
    state = load_review_state_pixel_array(context, position, models)

    ink = {(int(x), int(y)) for x, y in state.get("source_ink_points") or []}
    print(
        f"target page={args.page} column={args.column} row={args.row} "
        f"coverage={state.get('covered_pixels')}/{state.get('source_pixels')} "
        f"exact={state.get('fully_exact')} text={state.get('text')!r}"
    )
    print(f"crop={state.get('crop_width')}x{state.get('crop_height')} baseline={state.get('baseline')}")

    trace = trace_exact_cover(
        ink,
        int(state["crop_width"]),
        int(state["crop_height"]),
        models,
    )
    chosen = trace.pop("chosen")
    for key in (
        "row_kind",
        "states",
        "placements_tested",
        "subset_placements",
        "recursive_branches",
        "memo_hits",
        "failed_states",
        "max_depth",
    ):
        print(f"{key}={trace[key]}")
    print("states_by_depth=" + " ".join(f"{depth}:{count}" for depth, count in sorted(trace["states_by_depth"].items())))

    print(f"top_dead_anchors={min(args.top, len(trace['dead_by_anchor']))}")
    for rank, (anchor_x, count) in enumerate(trace["dead_by_anchor"].most_common(args.top), 1):
        print(f"dead-anchor[{rank}] x={anchor_x} dead_branches={count}")

    print(f"top_dead_candidates={min(args.top, len(trace['dead_by_candidate']))}")
    for rank, (key, dead) in enumerate(trace["dead_by_candidate"].most_common(args.top), 1):
        anchor_x, label, style, pixels = key
        branches = trace["branch_by_candidate"][key]
        print(
            f"dead-candidate[{rank}] x={anchor_x} label={label!r} style={style!r} "
            f"pixels={pixels} dead={dead}/{branches}"
        )

    if chosen is None:
        print("chosen=None")
    else:
        print("chosen=" + "".join(match.label for match in chosen))
        print("chosen_pixels=" + ",".join(str(match.model_pixels) for match in chosen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
