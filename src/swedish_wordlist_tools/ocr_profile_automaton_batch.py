from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing as mp
import os
from pathlib import Path
from time import perf_counter

from .ocr_baseline_up import CompiledGlyphLibrary, ResidualInk
from .ocr_canonical_facit import load_canonical_facit_with_typography
from .ocr_profile_automaton_parallel_benchmark import (
    _build_minimal_page_context,
    _minimal_black_pixels,
    _minimal_column_bounds,
)
from .ocr_profile_automaton_peel_benchmark import _compile_profile_prefix_trie
from .ocr_profile_leftmost_baseline_seed_benchmark import _reconstruct_rows_from_accepted_streams


_WORKER_TRIE = None
_WORKER_TRIE_NODES = 0
_WORKER_TRIE_EDGES = 0
_WORKER_JSONL: Path | None = None
_WORKER_THRESHOLD = 210
_WORKER_DEBUG_DIR: Path | None = None


def _init_worker(
    jsonl: str,
    facit: str,
    threshold: int,
    prefix_len: int,
    debug_dir: str,
) -> None:
    """Compile immutable OCR data once per long-lived worker."""
    global _WORKER_TRIE, _WORKER_TRIE_NODES, _WORKER_TRIE_EDGES
    global _WORKER_JSONL, _WORKER_THRESHOLD, _WORKER_DEBUG_DIR

    models = tuple(load_canonical_facit_with_typography(Path(facit)))
    library = CompiledGlyphLibrary(models)
    (
        _WORKER_TRIE,
        _WORKER_TRIE_NODES,
        _WORKER_TRIE_EDGES,
    ) = _compile_profile_prefix_trie(library, prefix_len=prefix_len)
    _WORKER_JSONL = Path(jsonl)
    _WORKER_THRESHOLD = int(threshold)
    _WORKER_DEBUG_DIR = Path(debug_dir) if debug_dir else None


def _ocr_column(context: dict, column: int, page_number: int) -> dict[str, object]:
    prefix_trie = _WORKER_TRIE
    if prefix_trie is None:
        raise RuntimeError("worker trie is not initialized")

    started = perf_counter()
    bounds = _minimal_column_bounds(context, column)
    black = _minimal_black_pixels(context, bounds)
    residual = ResidualInk(black)
    column_left, column_right, column_top, column_bottom = bounds

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
    stuck = None
    matching_started = perf_counter()

    while residual.pixels:
        if not profile_left:
            break
        min_x = min(profile_left.values())
        min_ys = tuple(sorted(y for y, x in profile_left.items() if x == min_x))

        accepted = None
        best_survivors = 0
        seed_diagnostics = []
        failure_candidates = []
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

            best_survivors = max(best_survivors, len(survivors))
            seed_diagnostics.append({
                "y": seed_y,
                "survivors": len(survivors),
            })

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
                missing = placed - residual.pixels
                if missing:
                    if len(failure_candidates) < 24:
                        failure_candidates.append({
                            "seed_y": seed_y,
                            "label": str(item.model.label),
                            "style": str(item.model.style),
                            "baseline": baseline,
                            "tx": tx,
                            "support": support,
                            "pixels": len(placed),
                            "missing_count": len(missing),
                            "missing": [list(point) for point in sorted(missing)[:24]],
                        })
                    continue
                accepted = (item, tx, baseline, placed)
                break
            if accepted is not None:
                break

        if accepted is None:
            debug_image = None
            if _WORKER_DEBUG_DIR is not None and min_ys:
                _WORKER_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                y0 = max(column_top, min(min_ys) - 24)
                y1 = min(column_bottom, max(min_ys) + 25)
                x0 = max(column_left, min_x - 12)
                x1 = min(column_right, min_x + 48)
                crop = context["gray"].crop((x0, y0, x1, y1)).convert("RGB")
                from PIL import ImageDraw
                draw = ImageDraw.Draw(crop)
                for y in min_ys:
                    if y0 <= y < y1:
                        draw.rectangle(
                            (min_x - x0 - 1, y - y0 - 1, min_x - x0 + 1, y - y0 + 1),
                            outline=(255, 0, 0),
                        )
                if failure_candidates:
                    for mx, my in failure_candidates[0]["missing"]:
                        if x0 <= mx < x1 and y0 <= my < y1:
                            draw.rectangle(
                                (mx - x0 - 1, my - y0 - 1, mx - x0 + 1, my - y0 + 1),
                                outline=(0, 0, 255),
                            )
                crop = crop.resize((crop.width * 8, crop.height * 8))
                debug_path = _WORKER_DEBUG_DIR / (
                    f"page-{page_number:04d}-col-{column}-x{min_x}-stall.png"
                )
                crop.save(debug_path)
                debug_image = str(debug_path)

            stuck = {
                "x": min_x,
                "ys": list(min_ys[:32]),
                "y_count": len(min_ys),
                "best_survivors": best_survivors,
                "seed_diagnostics": seed_diagnostics[:32],
                "failure_candidates": failure_candidates,
                "remaining": len(residual.pixels),
                "debug_image": debug_image,
            }
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
    reconstructed = _reconstruct_rows_from_accepted_streams(accepted_streams)
    rows = [
        {
            "index": index,
            "baseline": representative,
            "baseline_members": list(members),
            "page_top": top,
            "page_bottom": bottom + 1,
            "glyphs": glyph_count,
            "text": text_value,
        }
        for index, (representative, members, top, bottom, text_value, glyph_count)
        in enumerate(reconstructed)
    ]

    reference_columns = context["row_map"].get("columns") or []
    reference_rows = (
        reference_columns[column].get("rows") or []
        if 0 <= column < len(reference_columns)
        else []
    )

    return {
        "column": column,
        "bounds": list(bounds),
        "steps": steps,
        "remaining": len(residual.pixels),
        "row_count": len(rows),
        "reference_row_count": len(reference_rows),
        "candidate_spawns": candidate_spawns,
        "profile_rows_checked": profile_rows_checked,
        "checks_2d": checks_2d,
        "matching_seconds": matching_seconds,
        "total_seconds": perf_counter() - started,
        "stuck": stuck,
        "rows": rows,
    }


def _ocr_page(page_number: int) -> dict[str, object]:
    if _WORKER_JSONL is None:
        raise RuntimeError("worker JSONL path is not initialized")

    page_started = perf_counter()
    load_started = perf_counter()
    context = _build_minimal_page_context(
        _WORKER_JSONL,
        page_number,
        _WORKER_THRESHOLD,
    )
    load_seconds = perf_counter() - load_started

    columns = context["row_map"].get("columns") or []
    column_results = [
        _ocr_column(context, column, page_number)
        for column in range(len(columns))
    ]

    remaining = sum(int(column["remaining"]) for column in column_results)
    reconstructed_rows = sum(int(column["row_count"]) for column in column_results)
    reference_rows = sum(int(column["reference_row_count"]) for column in column_results)

    return {
        "page": page_number,
        "source": str(context.get("source") or ""),
        "column_count": len(column_results),
        "remaining": remaining,
        "row_count": reconstructed_rows,
        "reference_row_count": reference_rows,
        "load_seconds": load_seconds,
        "ocr_seconds": sum(float(column["matching_seconds"]) for column in column_results),
        "total_seconds": perf_counter() - page_started,
        "columns": column_results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Persistent multi-page SAOL profile-automaton OCR. Each worker "
            "compiles facit/trie once, then processes whole pages so each PNG "
            "is loaded only once."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--start-page", type=int, default=2)
    ap.add_argument("--end-page", type=int, default=11)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--prefix-len", type=int, default=5)
    ap.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Default: logical CPUs minus one.",
    )
    ap.add_argument(
        "--debug-stalls",
        type=Path,
        default=Path("reports/profile-stalls"),
        help="Directory for enlarged pixel crops at the first stall in each column.",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=Path("reports/saol14-profile-automaton-batch.jsonl"),
    )
    args = ap.parse_args()

    if args.end_page < args.start_page:
        raise ValueError("end page must be >= start page")

    pages = tuple(range(args.start_page, args.end_page + 1))
    logical_cpus = os.cpu_count() or 1
    default_workers = max(1, logical_cpus - 1)
    requested_workers = args.workers if args.workers > 0 else default_workers
    workers = max(1, min(requested_workers, len(pages)))

    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"batch-start: pages={args.start_page}..{args.end_page} count={len(pages)} "
        f"logical_cpus={logical_cpus} workers={workers} "
        f"reserved_cpus={max(0, logical_cpus-workers)} prefix_len={args.prefix_len} "
        f"output={args.output}",
        flush=True,
    )

    batch_started = perf_counter()
    results: dict[int, dict[str, object]] = {}

    # fork is deliberate on Linux. Worker initializers compile immutable
    # glyph/trie state once; every worker then reuses it for many pages.
    fork_context = mp.get_context("fork")
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=fork_context,
        initializer=_init_worker,
        initargs=(
            str(args.jsonl),
            str(args.facit),
            args.threshold,
            args.prefix_len,
            str(args.debug_stalls),
        ),
    ) as pool:
        future_to_page = {
            pool.submit(_ocr_page, page): page
            for page in pages
        }
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            result = future.result()
            results[page] = result
            print(
                f"batch-page-done: page={page} columns={result['column_count']} "
                f"rows={result['row_count']}/{result['reference_row_count']} "
                f"remaining={result['remaining']} "
                f"load={float(result['load_seconds']):.3f}s "
                f"ocr={float(result['ocr_seconds']):.3f}s "
                f"total={float(result['total_seconds']):.3f}s",
                flush=True,
            )
            for column in result["columns"]:
                if int(column["remaining"]) == 0:
                    continue
                stuck = column.get("stuck") or {}
                print(
                    f"batch-column-stuck: page={page} column={column['column']} "
                    f"rows={column['row_count']}/{column['reference_row_count']} "
                    f"steps={column['steps']} remaining={column['remaining']} "
                    f"x={stuck.get('x')} ys={stuck.get('ys')} "
                    f"best_survivors={stuck.get('best_survivors')} "
                    f"checks_2d={column['checks_2d']} "
                    f"debug={stuck.get('debug_image')}",
                    flush=True,
                )
                for candidate in (stuck.get("failure_candidates") or [])[:5]:
                    print(
                        f"batch-stall-candidate: page={page} column={column['column']} "
                        f"seed_y={candidate['seed_y']} label={candidate['label']!r}/"
                        f"{candidate['style']} baseline={candidate['baseline']} "
                        f"tx={candidate['tx']} support={candidate['support']} "
                        f"missing={candidate['missing_count']}/{candidate['pixels']} "
                        f"missing_pixels={candidate['missing']}",
                        flush=True,
                    )

    # Deterministic, restart-friendly output: rewrite the requested page packet
    # in page order only after all tasks have completed successfully.
    with args.output.open("w", encoding="utf-8") as handle:
        for page in pages:
            handle.write(json.dumps(results[page], ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    elapsed = perf_counter() - batch_started
    failed_pages = [
        page for page in pages
        if int(results[page]["remaining"]) != 0
    ]
    total_rows = sum(int(results[page]["row_count"]) for page in pages)
    total_remaining = sum(int(results[page]["remaining"]) for page in pages)

    print(
        f"batch-done: pages={len(pages)} failed_pages={failed_pages} "
        f"rows={total_rows} remaining={total_remaining} "
        f"elapsed={elapsed:.3f}s pages_per_second={len(pages)/elapsed:.3f} "
        f"seconds_per_page={elapsed/len(pages):.3f} output={args.output}",
        flush=True,
    )
    return 1 if failed_pages else 0


if __name__ == "__main__":
    raise SystemExit(main())
