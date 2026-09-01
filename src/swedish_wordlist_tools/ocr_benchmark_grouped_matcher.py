from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from .ocr_column_row_segmentation import segment_page_rows
from .ocr_glyph_gap_matcher import max_internal_blank_run
from .ocr_glyph_matcher import load_facit
from .ocr_prepare_sequential_page import _load_source_image, read_jsonl, source_for_page
from .ocr_probe_row_glyphs import analyse_row_exact
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped
from .ocr_row_map_words import _persistent_left_rule_x, _row_crop_box


def _signature(result: dict) -> tuple:
    selected = tuple(
        (m.label, m.style, m.x, m.baseline, tuple(sorted(m.pixels)))
        for m in result["selected"]
    )
    return (
        result["baseline"],
        result["source_pixels"],
        result["covered_pixels"],
        result["fully_exact"],
        selected,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Benchmark safe-white-gap exact glyph matching against the original full-row matcher."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--page", type=int, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--limit", type=int, help="benchmark only the first N physical rows")
    args = ap.parse_args()

    jsonl_rows = list(read_jsonl(args.jsonl))
    source = source_for_page(jsonl_rows, args.page)
    if not source:
        raise SystemExit(f"no source found for page {args.page}")
    page = _load_source_image(source)
    if page is None:
        raise SystemExit(f"could not load page image: {source}")

    models = load_facit(args.facit)
    row_map = segment_page_rows(page, threshold=args.threshold)
    internal_gap = max_internal_blank_run(models)
    print(f"models={len(models)} max_internal_blank_run={internal_gap}")

    rows_seen = 0
    mismatches = 0
    full_seconds = 0.0
    grouped_seconds = 0.0
    total_candidates_full = 0
    total_candidates_grouped = 0
    total_groups = 0

    for column, column_entry in enumerate(row_map["columns"]):
        rule_x = _persistent_left_rule_x(page, column_entry, threshold=args.threshold)
        content_left = rule_x + 2 if rule_x is not None else None
        for row_index, row in enumerate(column_entry.get("rows") or []):
            if args.limit is not None and rows_seen >= args.limit:
                break
            box = _row_crop_box(
                row,
                column=column,
                page_width=page.width,
                page_height=page.height,
                pad_y=1,
                left_override=content_left,
            )
            crop = page.crop(box).convert("L")

            started = perf_counter()
            full = analyse_row_exact(crop, models, threshold=args.threshold)
            full_seconds += perf_counter() - started

            started = perf_counter()
            grouped = analyse_row_exact_grouped(crop, models, threshold=args.threshold)
            grouped_seconds += perf_counter() - started

            total_candidates_full += full["candidate_count"]
            total_candidates_grouped += grouped["candidate_count"]
            total_groups += grouped["safe_group_count"]
            rows_seen += 1

            if _signature(full) != _signature(grouped):
                mismatches += 1
                print(
                    f"DIFF col={column} row={row_index} "
                    f"full={full['covered_pixels']}/{full['source_pixels']} "
                    f"grouped={grouped['covered_pixels']}/{grouped['source_pixels']} "
                    f"groups={grouped['safe_group_count']}"
                )
        if args.limit is not None and rows_seen >= args.limit:
            break

    speedup = full_seconds / grouped_seconds if grouped_seconds else float("inf")
    average_groups = total_groups / rows_seen if rows_seen else 0.0
    print(
        f"rows={rows_seen} mismatches={mismatches} "
        f"full_seconds={full_seconds:.3f} grouped_seconds={grouped_seconds:.3f} speedup={speedup:.2f}x"
    )
    print(
        f"candidates_full={total_candidates_full} candidates_grouped={total_candidates_grouped} "
        f"average_safe_groups={average_groups:.2f}"
    )
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
