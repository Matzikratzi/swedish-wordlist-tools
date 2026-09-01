from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_compare_page_text_prefix import (
    _format_duration,
    _reference_headword,
    articles_from_analysed_rows,
    canonical_printed_text,
    compare_page,
)
from .ocr_glyph_matcher import load_facit
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped
from .ocr_row_map_words import _persistent_left_rule_x, _row_crop_box


_WORKER_PAGE = None
_WORKER_COLUMNS = None
_WORKER_MODELS = None
_WORKER_THRESHOLD = 210
_WORKER_CONTENT_LEFTS = None


def _init_worker(page, columns, models, threshold: int, content_lefts) -> None:
    global _WORKER_PAGE, _WORKER_COLUMNS, _WORKER_MODELS, _WORKER_THRESHOLD, _WORKER_CONTENT_LEFTS
    _WORKER_PAGE = page
    _WORKER_COLUMNS = columns
    _WORKER_MODELS = models
    _WORKER_THRESHOLD = threshold
    _WORKER_CONTENT_LEFTS = content_lefts


def _analyse_row_worker(task: tuple[int, int]) -> tuple[int, int, dict]:
    column, row_index = task
    column_entry = _WORKER_COLUMNS[column]
    row = (column_entry.get("rows") or [])[row_index]
    box = _row_crop_box(
        row,
        column=column,
        page_width=_WORKER_PAGE.width,
        page_height=_WORKER_PAGE.height,
        pad_y=1,
        left_override=_WORKER_CONTENT_LEFTS[column],
    )
    crop = _WORKER_PAGE.crop(box).convert("L")
    result = analyse_row_exact_grouped(crop, _WORKER_MODELS, threshold=_WORKER_THRESHOLD)
    return (
        column,
        row_index,
        {
            "row": row_index,
            "matches": result["selected"],
            "ink": result["ink"],
            "fully_exact": result["fully_exact"],
            "covered_pixels": result["covered_pixels"],
            "source_pixels": result["source_pixels"],
        },
    )


def analyse_page_rows_parallel(page, row_map: dict, models, *, threshold: int = 210, jobs: int = 3) -> list[list[dict]]:
    columns = row_map["columns"]
    column_sizes = [len(column.get("rows") or []) for column in columns]
    total_rows = sum(column_sizes)
    content_lefts = []
    for column_entry in columns:
        rule_x = _persistent_left_rule_x(page, column_entry, threshold=threshold)
        content_lefts.append(rule_x + 2 if rule_x is not None else None)

    output: list[list[dict | None]] = [[None] * size for size in column_sizes]
    tasks = [
        (column, row_index)
        for column, size in enumerate(column_sizes)
        for row_index in range(size)
    ]

    jobs = max(1, min(int(jobs), total_rows or 1))
    started = perf_counter()
    next_bucket = 0
    print(
        f"parallell glyphanalys: {total_rows} rader med {jobs} processer ...",
        file=sys.stderr,
        flush=True,
    )
    with ProcessPoolExecutor(
        max_workers=jobs,
        initializer=_init_worker,
        initargs=(page, columns, models, threshold, content_lefts),
    ) as executor:
        futures = [executor.submit(_analyse_row_worker, task) for task in tasks]
        for done, future in enumerate(as_completed(futures), 1):
            column, row_index, result = future.result()
            output[column][row_index] = result
            percent = int(100 * done / total_rows) if total_rows else 100
            bucket = percent // 5
            if done == 1 or done == total_rows or bucket > next_bucket:
                next_bucket = bucket
                elapsed = perf_counter() - started
                rate = done / elapsed if elapsed > 0 else 0.0
                eta = elapsed * (total_rows - done) / done if done else 0.0
                print(
                    f"parallell: {done}/{total_rows} rader ({percent:3d}%) "
                    f"senast=kolumn{column}/rad{row_index + 1} "
                    f"elapsed={_format_duration(elapsed)} eta={_format_duration(eta)} rate={rate:.2f} rad/s",
                    file=sys.stderr,
                    flush=True,
                )

    return [[row for row in column if row is not None] for column in output]


def _print_report(report: dict, *, page: int, show_ok: bool) -> None:
    print(
        f"page={page} references_with_text={report['references_with_text']} "
        f"recovered_articles={report['recovered_articles']} matched_headwords={report['matched_headwords']} "
        f"text_prefix_exact={report['text_prefix_exact']} unmatched_references={report['unmatched_references']}"
    )
    print(
        f"forced_space_before_tilde={report['forced_space_before_tilde']} "
        f"articles_with_forced_tilde_space={report['articles_with_forced_tilde_space']}"
    )
    denominator = report["matched_headwords"]
    if denominator:
        print(f"matched_text_rate={100.0 * report['text_prefix_exact'] / denominator:.1f}%")
    for item in report["results"]:
        spacing_warning = item["forced_space_before_tilde"]
        if item["prefix_exact"] and not show_ok and not spacing_warning:
            continue
        status = "OK+SPACE" if item["prefix_exact"] and spacing_warning else ("OK" if item["prefix_exact"] else "MISS")
        print(
            f"{status}\tcol={item['column']} row={item['row']} exact_pixels={item['fully_exact']} "
            f"forced_tilde_spaces={spacing_warning} head={item['headword']!r}\n"
            f"  jsonl={item['expected']!r}\n"
            f"  ocr  ={item['recovered']!r}"
        )
    if report["unmatched"]:
        print("UNMATCHED HEADWORDS")
        for row in report["unmatched"]:
            print(f"  {_reference_headword(row)!r}\ttext={canonical_printed_text(row.get('text'))!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark process-parallel exact glyph matching on one SAOL page.")
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--jobs", type=int, default=min(3, os.cpu_count() or 1))
    ap.add_argument("--show-ok", action="store_true")
    args = ap.parse_args()

    rows = list(read_jsonl(args.jsonl))
    source = source_for_page(rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    print(f"page={args.page}: segmenterar fysiska rader ...", file=sys.stderr, flush=True)
    row_map = segment_page_rows(page, threshold=args.threshold)
    models = load_facit(args.facit)

    started = perf_counter()
    analysed_columns = analyse_page_rows_parallel(
        page,
        row_map,
        models,
        threshold=args.threshold,
        jobs=args.jobs,
    )
    elapsed = perf_counter() - started
    print(
        f"page={args.page}: parallell glyphanalys klar på {_format_duration(elapsed)}",
        file=sys.stderr,
        flush=True,
    )

    articles = articles_from_analysed_rows(analysed_columns)
    print(f"page={args.page}: jämför {len(articles)} återfunna artiklar med JSONL ...", file=sys.stderr, flush=True)
    report = compare_page(rows, articles, args.page)
    _print_report(report, page=args.page, show_ok=args.show_ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
