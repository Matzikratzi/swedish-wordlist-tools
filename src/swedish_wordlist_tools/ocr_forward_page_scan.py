from __future__ import annotations

"""Fast-first forward scanner for large SAOL facsimile runs.

Each page is handled in two passes:

1. run the bounded page-cached fast regression engine across every row, including
   the cheap horizontal separator repair;
2. run the existing full review/fallback chain only for rows that pass 1 could
   not prove exact.

The cheap pass mutates accepted row ownership in the shared page context, so the
fallback sees the already repaired page.  Exact fast rows are never sent through
the exhaustive fallback merely because another row on the same page is new.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_fast_regression_scan import FastRegressionRow, scan_page_fast
from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography


@dataclass(frozen=True)
class ForwardFallbackRow:
    page: int
    column: int
    row: int
    exact: bool
    covered_pixels: int
    source_pixels: int
    elapsed: float
    text: str


def scan_page_forward(
    context: dict,
    models,
    *,
    boundary_radius: int = 6,
) -> tuple[list[FastRegressionRow], list[ForwardFallbackRow]]:
    """Return fast-pass rows and full-fallback results for only the fast misses."""
    fast_rows = scan_page_fast(context, models, boundary_radius=boundary_radius)
    misses = [row for row in fast_rows if not row.exact]
    fallback_rows: list[ForwardFallbackRow] = []

    for miss in misses:
        position = (miss.column, miss.row)
        started = perf_counter()
        state = page_editor.load_review_state_pixel_array(context, position, models)
        elapsed = perf_counter() - started
        fallback_rows.append(
            ForwardFallbackRow(
                page=int(context["page_number"]),
                column=miss.column,
                row=miss.row,
                exact=bool(state.get("fully_exact")),
                covered_pixels=int(state.get("covered_pixels") or 0),
                source_pixels=int(state.get("source_pixels") or 0),
                elapsed=elapsed,
                text=str(state.get("text") or ""),
            )
        )

    return fast_rows, fallback_rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Fast-first SAOL page scan: page-cached exact + cheap separator for all rows, "
            "then existing expensive fallback only for remaining misses."
        )
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument("--boundary-radius", type=int, default=6)
    args = ap.parse_args()

    pages = _selected_pages(
        _available_pages(args.jsonl),
        pages=args.pages,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    if not pages:
        raise ValueError("no pages selected")

    models = load_facit_with_typography(args.facit)
    total_started = perf_counter()
    total_rows = 0
    total_fast_exact = 0
    total_fallback = 0
    total_final_exact = 0
    total_unresolved = 0
    total_fallback_wall = 0.0

    for page in pages:
        page_started = perf_counter()
        context = page_editor.build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True

        fast_started = perf_counter()
        fast_rows = scan_page_fast(context, models, boundary_radius=args.boundary_radius)
        fast_wall = perf_counter() - fast_started
        misses = [row for row in fast_rows if not row.exact]

        fallback_rows: list[ForwardFallbackRow] = []
        fallback_started = perf_counter()
        for miss in misses:
            position = (miss.column, miss.row)
            row_started = perf_counter()
            state = page_editor.load_review_state_pixel_array(context, position, models)
            row_elapsed = perf_counter() - row_started
            fallback_rows.append(
                ForwardFallbackRow(
                    page=page,
                    column=miss.column,
                    row=miss.row,
                    exact=bool(state.get("fully_exact")),
                    covered_pixels=int(state.get("covered_pixels") or 0),
                    source_pixels=int(state.get("source_pixels") or 0),
                    elapsed=row_elapsed,
                    text=str(state.get("text") or ""),
                )
            )
        fallback_wall = perf_counter() - fallback_started

        fast_exact = sum(row.exact for row in fast_rows)
        fallback_exact = sum(row.exact for row in fallback_rows)
        final_exact = fast_exact + fallback_exact
        unresolved = len(fallback_rows) - fallback_exact
        repaired = sum(row.repaired for row in fast_rows)

        total_rows += len(fast_rows)
        total_fast_exact += fast_exact
        total_fallback += len(fallback_rows)
        total_final_exact += final_exact
        total_unresolved += unresolved
        total_fallback_wall += fallback_wall

        print(
            f"forward-scan: page {page}: rows={len(fast_rows)} "
            f"fast_exact={fast_exact} repaired={repaired} "
            f"fallback={len(fallback_rows)} fallback_exact={fallback_exact} "
            f"final_exact={final_exact}/{len(fast_rows)} unresolved={unresolved} "
            f"fast_wall={fast_wall:.3f}s fallback_wall={fallback_wall:.3f}s "
            f"wall={perf_counter()-page_started:.3f}s",
            flush=True,
        )
        for row in fallback_rows:
            status = "exact" if row.exact else f"{row.covered_pixels}/{row.source_pixels}"
            print(
                f"forward-scan: fallback page {row.page} column {row.column} row {row.row} "
                f"pixels={status} time={row.elapsed:.3f}s text={row.text!r}",
                flush=True,
            )

    wall = perf_counter() - total_started
    print(
        f"forward-scan: pages={len(pages)} rows={total_rows} "
        f"fast_exact={total_fast_exact}/{total_rows} fallback={total_fallback} "
        f"final_exact={total_final_exact}/{total_rows} unresolved={total_unresolved} "
        f"fallback_wall={total_fallback_wall:.3f}s wall={wall:.3f}s",
        flush=True,
    )
    return 0 if total_unresolved == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
