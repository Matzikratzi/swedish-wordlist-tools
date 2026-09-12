from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import os
from pathlib import Path
from time import perf_counter

from .ocr_baseline_up import CompiledGlyphLibrary, ResidualInk
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_profile_automaton_peel_benchmark import _compile_profile_prefix_trie
from .ocr_profile_leftmost_baseline_seed_benchmark import _reconstruct_rows_from_accepted_streams
from . import ocr_review_five_rows_glyphs_fast_html as fast
from .ocr_column_row_segmentation import segment_page_rows
from .ocr_row_map_words import _persistent_left_rule_x



def _build_minimal_page_context(jsonl: Path, page_number: int, threshold: int) -> dict:
    """Load only data needed by the profile automaton.

    Keep row_map temporarily for reference bounds/comparison, but skip the
    PagePixelArray ownership assignment and all ownership bookkeeping.
    """
    source = fast.source_for_page(fast.read_jsonl(jsonl), page_number)
    if not source:
        raise ValueError(f"no source found for page {page_number}")
    page = fast._load_source_image(source)
    if page is None:
        raise ValueError(f"could not load page image: {source}")
    gray = page if page.mode == "L" else page.convert("L")
    row_map = segment_page_rows(page, threshold=threshold)
    content_lefts: dict[int, int | None] = {}
    for column_index, column_entry in enumerate(row_map.get("columns") or []):
        rule_x = _persistent_left_rule_x(gray, column_entry, threshold=threshold)
        content_lefts[column_index] = rule_x + 2 if rule_x is not None else None
    return {
        "source": source,
        "page": page,
        "gray": gray,
        "row_map": row_map,
        "threshold": threshold,
        "page_number": page_number,
        "column_content_lefts": content_lefts,
    }


def _minimal_column_bounds(context: dict, column_index: int) -> tuple[int, int, int, int]:
    columns = context["row_map"].get("columns") or []
    if not 0 <= column_index < len(columns):
        raise ValueError(f"column {column_index} does not exist")
    column = columns[column_index]
    rows = column.get("rows") or []
    if not rows:
        raise ValueError(f"column {column_index} has no reference rows")
    width, height = context["gray"].size
    left = int(column.get("crop_left", column.get("left", 0)))
    content_left = context["column_content_lefts"].get(column_index)
    if content_left is not None:
        left = max(left, int(content_left))
    right = int(column.get("crop_right", column.get("right", width)))
    top = min(int(row["page_top"]) for row in rows)
    bottom = max(int(row["page_bottom"]) for row in rows)
    return max(0, left), min(width, right), max(0, top), min(height, bottom)


def _minimal_black_pixels(context: dict, bounds: tuple[int, int, int, int]) -> set[tuple[int, int]]:
    left, right, top, bottom = bounds
    gray = context["gray"]
    threshold = int(context["threshold"])
    pixels = gray.load()
    return {
        (x, y)
        for y in range(top, bottom)
        for x in range(left, right)
        if int(pixels[x, y]) < threshold
    }


_SHARED_CONTEXT = None
_SHARED_PREFIX_TRIE = None
_SHARED_TRIE_NODES = 0
_SHARED_TRIE_EDGES = 0


def _run_shared_column(
    column: int,
    rows: int,
    max_steps: int,
) -> dict[str, object]:
    """OCR one column using page/library/trie inherited through fork."""
    context = _SHARED_CONTEXT
    prefix_trie = _SHARED_PREFIX_TRIE
    if context is None or prefix_trie is None:
        raise RuntimeError("shared fork state not initialized")

    started = perf_counter()
    bounds = _minimal_column_bounds(context, column)
    black = _minimal_black_pixels(context, bounds)
    residual = ResidualInk(black)
    column_left, column_right, column_top, column_bottom = bounds

    columns = context["row_map"].get("columns") or []
    reference_rows = columns[column].get("rows") or []
    if rows > 0:
        reference_rows = reference_rows[:rows]

    accepted_streams: dict[
        int,
        list[tuple[int, int, int, int, str, str, int, int]],
    ] = defaultdict(list)

    profile_left: dict[int, int] = {
        y: min(xs)
        for y, xs in residual.rows.items()
        if xs and column_top <= y < column_bottom
    }

    steps = 0
    candidate_spawns = 0
    profile_rows_checked = 0
    checks_2d = 0
    matching_started = perf_counter()

    while residual.pixels and (max_steps == 0 or steps < max_steps):
        if not profile_left:
            break
        min_x = min(profile_left.values())
        min_ys = tuple(sorted(y for y, x in profile_left.items() if x == min_x))

        accepted = None
        for seed_y in min_ys:
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
                    candidate_spawns += 1

                    top = baseline + item.model.min_y
                    bottom = baseline + item.model.max_y
                    if top < column_top or bottom >= column_bottom:
                        continue

                    support = prefix_support
                    contradicted = False
                    for model_y, model_left in left_profile:
                        actual_x = profile_left.get(baseline + model_y)
                        expected_x = tx + model_left
                        profile_rows_checked += 1
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
                    profile_rows_checked += 1
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
            for item, tx, baseline, support in survivors:
                checks_2d += 1
                placed = frozenset(
                    (tx + x, baseline + y)
                    for x, y in item.model.pixels
                )
                if not placed.issubset(residual.pixels):
                    continue
                accepted = (item, tx, baseline, placed)
                break
            if accepted is not None:
                break

        if accepted is None:
            break

        item, tx, baseline, placed = accepted
        left = min(x for x, _y in placed)
        right = max(x for x, _y in placed)
        top = min(y for _x, y in placed)
        bottom = max(y for _x, y in placed)

        affected_ys = {y for _x, y in placed}
        residual.consume(placed)
        for page_y in affected_ys:
            xs = residual.rows.get(page_y)
            if xs:
                profile_left[page_y] = min(xs)
            else:
                profile_left.pop(page_y, None)

        accepted_streams[baseline].append(
            (left, right, steps, min_x, item.model.label, item.model.style, top, bottom)
        )
        steps += 1

    matching_seconds = perf_counter() - matching_started
    reconstructed_rows = _reconstruct_rows_from_accepted_streams(accepted_streams)

    return {
        "column": column,
        "steps": steps,
        "remaining": len(residual.pixels),
        "rows": len(reconstructed_rows),
        "reference_rows": len(reference_rows),
        "candidate_spawns": candidate_spawns,
        "profile_rows_checked": profile_rows_checked,
        "checks_2d": checks_2d,
        "matching": matching_seconds,
        "total": perf_counter() - started,
    }


def main() -> int:
    global _SHARED_CONTEXT, _SHARED_PREFIX_TRIE
    global _SHARED_TRIE_NODES, _SHARED_TRIE_EDGES

    ap = argparse.ArgumentParser(
        description=(
            "Fork profile-automaton workers after loading page, glyph library "
            "and prefix trie once in the parent process."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--page", type=int, default=36)
    ap.add_argument("--rows", type=int, default=0)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--max-steps", type=int, default=0)
    ap.add_argument("--prefix-len", type=int, default=5)
    ap.add_argument(
        "--columns",
        type=str,
        default="",
        help="Comma-separated column indexes. Default: all page columns.",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Worker limit. Default: logical CPUs minus one.",
    )
    args = ap.parse_args()

    total_started = perf_counter()
    setup_started = perf_counter()

    models = tuple(load_canonical_facit_with_typography(args.facit))
    library = CompiledGlyphLibrary(models)
    (
        _SHARED_PREFIX_TRIE,
        _SHARED_TRIE_NODES,
        _SHARED_TRIE_EDGES,
    ) = _compile_profile_prefix_trie(library, prefix_len=args.prefix_len)

    _SHARED_CONTEXT = _build_minimal_page_context(
        args.jsonl,
        args.page,
        args.threshold,
    )
    page_columns = _SHARED_CONTEXT["row_map"].get("columns") or []

    if args.columns.strip():
        columns = tuple(int(part) for part in args.columns.split(",") if part.strip())
    else:
        columns = tuple(range(len(page_columns)))

    setup_seconds = perf_counter() - setup_started

    if not columns:
        print("fork-columns-done: no columns", flush=True)
        return 0

    logical_cpus = os.cpu_count() or 1
    default_workers = max(1, logical_cpus - 1)
    requested_workers = args.workers if args.workers > 0 else default_workers
    workers = max(1, min(requested_workers, len(columns)))

    print(
        f"fork-columns-start: page={args.page} columns={columns} "
        f"logical_cpus={logical_cpus} workers={workers} "
        f"reserved_cpus={max(0, logical_cpus - workers)} "
        f"loader=minimal-no-ownership prefix_len={args.prefix_len} trie_nodes={_SHARED_TRIE_NODES} "
        f"trie_edges={_SHARED_TRIE_EDGES} setup={setup_seconds:.6f}s",
        flush=True,
    )

    fork_context = mp.get_context("fork")
    results: dict[int, dict[str, object]] = {}
    parallel_started = perf_counter()
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=fork_context,
    ) as pool:
        futures = {
            pool.submit(_run_shared_column, column, args.rows, args.max_steps): column
            for column in columns
        }
        for future in as_completed(futures):
            result = future.result()
            column = int(result["column"])
            results[column] = result
            print(
                f"fork-column-done: column={column} "
                f"rows={result['rows']}/{result['reference_rows']} "
                f"steps={result['steps']} remaining={result['remaining']} "
                f"candidate_spawns={result['candidate_spawns']} "
                f"profile_rows_checked={result['profile_rows_checked']} "
                f"checks_2d={result['checks_2d']} "
                f"matching={float(result['matching']):.6f}s "
                f"worker_total={float(result['total']):.6f}s",
                flush=True,
            )

    parallel_seconds = perf_counter() - parallel_started
    failed = sum(
        1
        for result in results.values()
        if int(result["remaining"]) != 0
    )

    print(
        f"fork-columns-done: columns={len(columns)} workers={workers} "
        f"failed={failed} setup={setup_seconds:.6f}s "
        f"parallel={parallel_seconds:.6f}s "
        f"total={perf_counter()-total_started:.6f}s",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
