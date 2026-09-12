from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter

from .ocr_review_page_pixel_array_glyphs_html import build_page_context_pixel_array


_DONE_RE = re.compile(
    r"profile-auto-done: .*?steps=(?P<steps>\d+) remaining=(?P<remaining>\d+).*?"
    r"matching=(?P<matching>[0-9.]+)s total=(?P<total>[0-9.]+)s"
)
_ROWS_RE = re.compile(
    r"profile-auto-rows-start: rows=(?P<rows>\d+) reference_rows=(?P<reference_rows>\d+)"
)


def _run_column(
    *,
    jsonl: Path,
    facit: Path,
    page: int,
    column: int,
    rows: int,
    threshold: int,
    max_steps: int,
    prefix_len: int,
) -> tuple[int, int, str, float]:
    cmd = [
        sys.executable,
        "-m",
        "swedish_wordlist_tools.ocr_profile_automaton_peel_benchmark",
        str(jsonl),
        "--facit",
        str(facit),
        "--page",
        str(page),
        "--column",
        str(column),
        "--rows",
        str(rows),
        "--threshold",
        str(threshold),
        "--max-steps",
        str(max_steps),
        "--prefix-len",
        str(prefix_len),
    ]
    started = perf_counter()
    proc = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return column, proc.returncode, proc.stdout, perf_counter() - started


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Run one profile-automaton OCR subprocess per page column in parallel, "
            "while leaving one logical CPU free."
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
        help="Comma-separated column indexes. Default: infer all page columns.",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=0,
        help="Worker limit. Default: logical CPUs minus one.",
    )
    ap.add_argument(
        "--show-column-output",
        action="store_true",
        help="Print complete captured output from each column after it finishes.",
    )
    args = ap.parse_args()

    total_started = perf_counter()

    if args.columns.strip():
        columns = tuple(int(part) for part in args.columns.split(",") if part.strip())
    else:
        prep_started = perf_counter()
        context = build_page_context_pixel_array(args.jsonl, args.page, args.threshold)
        page_columns = context["row_map"].get("columns") or []
        columns = tuple(range(len(page_columns)))
        prep_seconds = perf_counter() - prep_started
        print(
            f"parallel-columns-discovery: page={args.page} columns={len(columns)} "
            f"discovery={prep_seconds:.6f}s",
            flush=True,
        )

    if not columns:
        print("parallel-columns-done: no columns", flush=True)
        return 0

    logical_cpus = os.cpu_count() or 1
    default_workers = max(1, logical_cpus - 1)
    requested_workers = args.workers if args.workers > 0 else default_workers
    workers = max(1, min(requested_workers, len(columns)))

    print(
        f"parallel-columns-start: page={args.page} columns={columns} "
        f"logical_cpus={logical_cpus} workers={workers} "
        f"reserved_cpus={max(0, logical_cpus - workers)} prefix_len={args.prefix_len}",
        flush=True,
    )

    results: dict[int, tuple[int, str, float]] = {}
    parallel_started = perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _run_column,
                jsonl=args.jsonl,
                facit=args.facit,
                page=args.page,
                column=column,
                rows=args.rows,
                threshold=args.threshold,
                max_steps=args.max_steps,
                prefix_len=args.prefix_len,
            ): column
            for column in columns
        }
        for future in as_completed(futures):
            column, returncode, output, wall_seconds = future.result()
            results[column] = (returncode, output, wall_seconds)

            done_match = _DONE_RE.search(output)
            rows_match = _ROWS_RE.search(output)
            if done_match and rows_match:
                print(
                    f"parallel-column-done: column={column} rc={returncode} "
                    f"rows={rows_match.group('rows')}/{rows_match.group('reference_rows')} "
                    f"steps={done_match.group('steps')} remaining={done_match.group('remaining')} "
                    f"matching={done_match.group('matching')}s "
                    f"child_total={done_match.group('total')}s wall={wall_seconds:.6f}s",
                    flush=True,
                )
            else:
                print(
                    f"parallel-column-done: column={column} rc={returncode} "
                    f"wall={wall_seconds:.6f}s parse=failed",
                    flush=True,
                )

    parallel_seconds = perf_counter() - parallel_started

    failed = 0
    for column in columns:
        returncode, output, _wall_seconds = results[column]
        if args.show_column_output or returncode != 0:
            print(f"parallel-column-output-start: column={column}", flush=True)
            print(output, end="" if output.endswith("\n") else "\n", flush=True)
            print(f"parallel-column-output-end: column={column}", flush=True)
        if returncode != 0:
            failed += 1

    print(
        f"parallel-columns-done: columns={len(columns)} workers={workers} "
        f"failed={failed} parallel={parallel_seconds:.6f}s "
        f"total={perf_counter()-total_started:.6f}s",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
