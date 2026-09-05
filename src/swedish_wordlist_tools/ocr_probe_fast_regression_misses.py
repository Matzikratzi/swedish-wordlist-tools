from __future__ import annotations

"""Classify fast-regression misses without slowing the regression path itself.

The fast regression scan runs first, including its cheap boundary repairs. Only
rows that remain unresolved are then analysed once with the normal exhaustive
row analyser *on the exact same pixel ownership*. This separates two cases:

* search-gap: exhaustive exact cover succeeds on unchanged row ownership;
* still-nonexact: even exhaustive analysis cannot make the current ownership exact.

The probe is diagnostic only. It does not enter the production regression path
and it does not run ownership refinement for unresolved rows.
"""

import argparse
from pathlib import Path
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_fast_regression_scan import scan_page_fast
from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography


def _match_summary(state: dict) -> tuple[str, str, str]:
    matches = list(state.get("matches") or [])
    baselines = ",".join(str(value) for value in sorted({int(m.baseline) for m in matches}))
    labels = "".join(str(m.label) for m in sorted(matches, key=lambda m: (m.x, m.baseline)))
    styles = ",".join(sorted({str(m.style) for m in matches}))
    return baselines or "-", labels, styles or "-"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Classify fast-regression misses using exhaustive analysis only on the misses."
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
    total_misses = 0
    search_gaps = 0
    still_nonexact = 0
    total_started = perf_counter()

    for page in pages:
        context = page_editor.build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        fast_results = scan_page_fast(context, models, boundary_radius=args.boundary_radius)
        misses = [result for result in fast_results if not result.exact]
        total_misses += len(misses)
        print(f"miss-probe: page {page}: fast_misses={len(misses)}", flush=True)

        for miss in misses:
            position = (miss.column, miss.row)
            started = perf_counter()
            state = page_editor._load_owned_row_state(context, position, models)
            elapsed = perf_counter() - started
            exact = bool(state.get("fully_exact"))
            if exact:
                search_gaps += 1
                classification = "search-gap"
            else:
                still_nonexact += 1
                classification = "still-nonexact"
            baselines, labels, styles = _match_summary(state)
            print(
                f"miss-probe: page {page} column {miss.column} row {miss.row} "
                f"class={classification} exhaustive={int(exact)} "
                f"covered={int(state.get('covered_pixels') or 0)}/{int(state.get('source_pixels') or 0)} "
                f"baseline={state.get('baseline')} match_baselines={baselines} "
                f"matches={len(state.get('matches') or [])} styles={styles} "
                f"time={elapsed:.3f}s text={str(state.get('text') or '')!r} labels={labels!r}",
                flush=True,
            )

    print(
        f"miss-probe: misses={total_misses} search_gap={search_gaps} "
        f"still_nonexact={still_nonexact} wall={perf_counter()-total_started:.3f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
