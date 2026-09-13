from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from .ocr_baseline_up import CompiledGlyphLibrary, ResidualInk
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_profile_automaton_parallel_benchmark import (
    _build_minimal_page_context,
    _minimal_black_pixels,
    _minimal_column_bounds,
)
from .ocr_profile_automaton_peel_benchmark import _compile_profile_prefix_trie


def _style(model) -> str:
    value = getattr(model.style, "typographic_style", None)
    if value in {"roman", "italic", "bold"}:
        return value
    return str(model.style)


def _candidate_data(entry, residual, deferred):
    item, tx, baseline, support = entry
    placed = frozenset((tx + x, baseline + y) for x, y in item.model.pixels)
    missing = placed - residual.pixels
    return {
        "item": item,
        "tx": tx,
        "baseline": baseline,
        "support": support,
        "placed": placed,
        "missing": missing,
        "missing_deferred": missing & deferred,
    }


def trace_column(
    context: dict,
    library: CompiledGlyphLibrary,
    column: int,
    page_number: int,
    *,
    prefix_len: int,
    frontier_slack: int,
    trace_x: int,
    trace_baseline: int,
) -> int:
    prefix_trie, _nodes, _edges = _compile_profile_prefix_trie(
        library, prefix_len=prefix_len
    )
    bounds = _minimal_column_bounds(context, column)
    black = _minimal_black_pixels(context, bounds)
    residual = ResidualInk(black)
    column_left, column_right, column_top, column_bottom = bounds
    profile_left = {
        y: min(xs)
        for y, xs in residual.rows.items()
        if xs and column_top <= y < column_bottom
    }
    deferred_frontier_pixels: set[tuple[int, int]] = set()
    steps = 0
    seen_target = False

    def next_profile_x(page_y: int) -> int | None:
        xs = residual.rows.get(page_y) or set()
        visible = [x for x in xs if (x, page_y) not in deferred_frontier_pixels]
        return min(visible) if visible else None

    while residual.pixels and profile_left:
        min_x = min(profile_left.values())
        min_ys = tuple(sorted(y for y, x in profile_left.items() if x == min_x))
        trace_here = min_x == trace_x
        if trace_here:
            seen_target = True
            print(
                f"decision-frontier page={page_number} col={column} step={steps} "
                f"min_x={min_x} min_ys={list(min_ys)} residual={len(residual.pixels)} "
                f"deferred_total={len(deferred_frontier_pixels)}",
                flush=True,
            )

        accepted = None
        for seed_index, seed_y in enumerate(min_ys):
            survivors = []
            seen: set[tuple[int, int, int]] = set()
            stack = [(prefix_trie, 0)]
            while stack:
                node, prefix_support = stack.pop()
                for item, left_profile, anchor_y in node["templates"]:
                    tx = min_x - item.min_x
                    if tx + item.max_x >= column_right or tx + item.min_x < column_left:
                        continue
                    baseline = seed_y - anchor_y
                    key = (id(item.model), tx, baseline)
                    if key in seen:
                        continue
                    seen.add(key)
                    top = baseline + item.model.min_y
                    bottom = baseline + item.model.max_y
                    if top < column_top or bottom >= column_bottom:
                        continue
                    support = prefix_support
                    contradicted = False
                    for model_y, model_left in left_profile:
                        actual_x = profile_left.get(baseline + model_y)
                        expected_x = tx + model_left
                        if actual_x is None or actual_x > expected_x:
                            contradicted = True
                            break
                        if actual_x == expected_x:
                            support += 1
                    if not contradicted:
                        survivors.append((item, tx, baseline, support))
                for (dy, dx), child in node["children"].items():
                    actual_x = profile_left.get(seed_y + dy)
                    expected_x = min_x + dx
                    if actual_x is None or actual_x > expected_x:
                        continue
                    child_support = prefix_support + (1 if actual_x == expected_x else 0)
                    stack.append((child, child_support))

            survivors.sort(
                key=lambda entry: (
                    -len(entry[0].model.pixels),
                    -entry[3],
                    entry[2],
                    entry[0].model.label,
                    entry[0].model.style,
                )
            )

            if trace_here:
                contains_target_baseline = any(
                    baseline == trace_baseline for _item, _tx, baseline, _support in survivors
                )
                print(
                    f"decision-seed index={seed_index} seed_y={seed_y} "
                    f"survivors={len(survivors)} contains_baseline_{trace_baseline}="
                    f"{contains_target_baseline}",
                    flush=True,
                )
                for rank, entry in enumerate(survivors, start=1):
                    data = _candidate_data(entry, residual, deferred_frontier_pixels)
                    item = data["item"]
                    print(
                        f"decision-rank seed_index={seed_index} rank={rank} "
                        f"label={item.model.label!r} style={_style(item.model)} "
                        f"tx={data['tx']} baseline={data['baseline']} "
                        f"support={data['support']} px={len(data['placed'])} "
                        f"missing={len(data['missing'])} "
                        f"missing_pixels={sorted(data['missing'])} "
                        f"missing_deferred={sorted(data['missing_deferred'])}",
                        flush=True,
                    )

            for rank, entry in enumerate(survivors, start=1):
                data = _candidate_data(entry, residual, deferred_frontier_pixels)
                item = data["item"]
                if trace_here:
                    print(
                        f"decision-2d seed_index={seed_index} rank={rank} "
                        f"label={item.model.label!r} style={_style(item.model)} "
                        f"tx={data['tx']} baseline={data['baseline']} "
                        f"result={'REJECT_MISSING' if data['missing'] else 'PASS'} "
                        f"missing_pixels={sorted(data['missing'])}",
                        flush=True,
                    )
                if data["missing"]:
                    continue
                accepted = (data, seed_y, rank)
                if trace_here:
                    print(
                        f"decision-select seed_index={seed_index} rank={rank} "
                        f"label={item.model.label!r} style={_style(item.model)} "
                        f"tx={data['tx']} baseline={data['baseline']} "
                        "reason=first_exact_2d_candidate_in_first_accepting_seed",
                        flush=True,
                    )
                break
            if accepted is not None:
                if trace_here and seed_index + 1 < len(min_ys):
                    print(
                        f"decision-stop-seeds accepted_seed_index={seed_index} "
                        f"unexamined_seed_count={len(min_ys) - seed_index - 1}",
                        flush=True,
                    )
                break

        if accepted is None:
            advanced = False
            newly_deferred: list[tuple[int, int]] = []
            if frontier_slack > 0:
                quarantine_right = min_x + frontier_slack
                for page_y in min_ys:
                    xs = residual.rows.get(page_y) or set()
                    blocked = [
                        x for x in xs
                        if min_x <= x <= quarantine_right
                        and (x, page_y) not in deferred_frontier_pixels
                    ]
                    if blocked:
                        points = [(x, page_y) for x in blocked]
                        newly_deferred.extend(points)
                        deferred_frontier_pixels.update(points)
                        next_x = next_profile_x(page_y)
                        if next_x is None:
                            profile_left.pop(page_y, None)
                        else:
                            profile_left[page_y] = next_x
                        advanced = True
                if advanced:
                    if trace_here:
                        print(
                            f"decision-defer frontier_slack={frontier_slack} "
                            f"quarantine_right={quarantine_right} "
                            f"pixels={sorted(newly_deferred)}",
                            flush=True,
                        )
                    continue
            if trace_here:
                print("decision-stall no_exact_2d_candidate_and_no_deferral", flush=True)
            break

        data, accepted_seed_y, accepted_rank = accepted
        item = data["item"]
        placed = data["placed"]
        if trace_here:
            print(
                f"decision-commit label={item.model.label!r} style={_style(item.model)} "
                f"tx={data['tx']} baseline={data['baseline']} seed_y={accepted_seed_y} "
                f"rank={accepted_rank} consume_count={len(placed)} "
                f"consume_pixels={sorted(placed)} "
                f"deferred_overlap={sorted(placed & deferred_frontier_pixels)}",
                flush=True,
            )

        affected_ys = {y for _x, y in placed}
        residual.consume(placed)
        for page_y in affected_ys:
            next_x = next_profile_x(page_y)
            if next_x is None:
                profile_left.pop(page_y, None)
            else:
                profile_left[page_y] = next_x
        steps += 1

        # Once the requested frontier has made its decision, there is no reason
        # to spam later x positions. The exact commit/defer path is now known.
        if trace_here:
            return 0

    if not seen_target:
        print(
            f"decision-target-not-reached page={page_number} col={column} x={trace_x} "
            f"steps={steps} residual={len(residual.pixels)}",
            flush=True,
        )
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Exact decision-chain trace for one profile-automaton frontier."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--column", type=int, required=True)
    ap.add_argument("--x", type=int, required=True)
    ap.add_argument("--baseline", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--prefix-len", type=int, default=5)
    ap.add_argument("--frontier-slack", type=int, default=0)
    args = ap.parse_args()

    context = _build_minimal_page_context(args.jsonl, args.page, args.threshold)
    models = tuple(load_canonical_facit_with_typography(args.facit))
    library = CompiledGlyphLibrary(models)
    return trace_column(
        context,
        library,
        args.column,
        args.page,
        prefix_len=args.prefix_len,
        frontier_slack=args.frontier_slack,
        trace_x=args.x,
        trace_baseline=args.baseline,
    )


if __name__ == "__main__":
    raise SystemExit(main())
