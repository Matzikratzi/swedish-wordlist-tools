from __future__ import annotations

"""Fast regression scan for already-known facsimile pages.

This path is intentionally bounded: it runs only the page-cached exact-cover
fast path.  It never enters the exhaustive safe-group fallback.  A row that
cannot be proved exact quickly is reported as unresolved/regression and the
scan continues.
"""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_find_unreviewed_glyph_rows import _available_pages, _selected_pages
from .ocr_glyph_review_delete import load_facit_with_typography
from .ocr_page_cached_fast_path import (
    bind_page_candidates,
    page_cached_prioritized_fast_exact_cover,
)
from .ocr_priority_fast_path import classify_row_start, set_row_priority_hint
from .ocr_probe_row_glyphs import row_ink


@dataclass(frozen=True)
class FastRegressionRow:
    page: int
    column: int
    row: int
    exact: bool
    source_pixels: int
    covered_pixels: int
    elapsed: float
    text: str


def analyse_row_fast_only(crop, models, *, threshold: int = 210) -> dict:
    """Return the normal analyser shape without any exhaustive fallback."""
    ink = row_ink(crop, threshold=threshold)
    if not ink:
        return {
            "baseline": None,
            "source_pixels": 0,
            "covered_pixels": 0,
            "unmatched_pixels": 0,
            "unmatched_components": [],
            "fully_exact": True,
            "candidate_count": 0,
            "selected": [],
            "ink": ink,
            "safe_groups": [],
            "safe_group_count": 0,
            "exact_fast_path": True,
            "exact_cover_path": "fast-regression-empty",
        }

    result = page_cached_prioritized_fast_exact_cover(
        ink, crop.width, crop.height, models
    )
    if result is None:
        return {
            "baseline": None,
            "source_pixels": len(ink),
            "covered_pixels": 0,
            "unmatched_pixels": len(ink),
            "unmatched_components": [],
            "fully_exact": False,
            "candidate_count": 0,
            "selected": [],
            "ink": ink,
            "safe_groups": [],
            "safe_group_count": 0,
            "exact_fast_path": True,
            "exact_cover_path": "fast-regression-miss",
        }

    baseline, selected, placements_tested = result
    covered = set().union(*(match.pixels for match in selected)) if selected else set()
    return {
        "baseline": baseline,
        "source_pixels": len(ink),
        "covered_pixels": len(covered),
        "unmatched_pixels": len(ink - covered),
        "unmatched_components": [],
        "fully_exact": covered == ink,
        "candidate_count": placements_tested,
        "selected": selected,
        "ink": ink,
        "safe_groups": [],
        "safe_group_count": 0,
        "exact_fast_path": True,
        "exact_cover_path": "fast-regression",
    }


@contextmanager
def _fast_only_analyser():
    original = page_editor.fast.analyse_row_exact
    page_editor.fast.analyse_row_exact = analyse_row_fast_only
    try:
        yield
    finally:
        page_editor.fast.analyse_row_exact = original


def scan_page_fast(context: dict, models) -> list[FastRegressionRow]:
    bind_page_candidates(context, models)
    rows: list[FastRegressionRow] = []
    with _fast_only_analyser():
        for position in context["positions"]:
            set_row_priority_hint(classify_row_start(context, position))
            started = perf_counter()
            state = page_editor._load_owned_row_state(context, position, models)
            elapsed = perf_counter() - started
            rows.append(
                FastRegressionRow(
                    page=int(context["page_number"]),
                    column=int(position[0]),
                    row=int(position[1]),
                    exact=bool(state.get("fully_exact")),
                    source_pixels=int(state.get("source_pixels") or 0),
                    covered_pixels=int(state.get("covered_pixels") or 0),
                    elapsed=elapsed,
                    text=str(state.get("text") or ""),
                )
            )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fast-only regression scan: exact quickly or report unresolved; never exhaustive."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument(
        "--print-unresolved",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
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
    row_count = 0
    exact_count = 0
    unresolved: list[FastRegressionRow] = []

    for page in pages:
        page_started = perf_counter()
        context = page_editor.build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        results = scan_page_fast(context, models)
        page_exact = sum(result.exact for result in results)
        page_unresolved = [result for result in results if not result.exact]
        row_count += len(results)
        exact_count += page_exact
        unresolved.extend(page_unresolved)
        print(
            f"fast-regression: page {page}: exact={page_exact}/{len(results)} "
            f"unresolved={len(page_unresolved)} wall={perf_counter()-page_started:.3f}s",
            flush=True,
        )
        if args.print_unresolved:
            for result in page_unresolved:
                print(
                    f"fast-regression: unresolved page {result.page} column {result.column} row {result.row} "
                    f"covered={result.covered_pixels}/{result.source_pixels} time={result.elapsed:.3f}s "
                    f"text={result.text!r}",
                    flush=True,
                )

    wall = perf_counter() - total_started
    print(
        f"fast-regression: pages={len(pages)} rows={row_count} exact={exact_count}/{row_count} "
        f"unresolved={len(unresolved)} wall={wall:.3f}s",
        flush=True,
    )
    return 0 if not unresolved else 1


if __name__ == "__main__":
    raise SystemExit(main())
