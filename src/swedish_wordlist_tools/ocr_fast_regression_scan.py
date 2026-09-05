from __future__ import annotations

"""Fast regression scan for already-known facsimile pages.

This path is intentionally bounded. It runs the page-cached exact-cover fast
path first, then a one-switch +/-1 baseline fast path. On a miss it may try a
small fixed number of horizontal row-boundary repairs, each verified only with
the same bounded exact paths. It never enters the exhaustive safe-group
fallback. A row that still cannot be proved exact is reported as unresolved.
"""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_fast_boundary_repair import try_fast_boundary_repair
from .ocr_fast_two_baseline import fast_exact_cover_one_baseline_switch
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
    exact_path: str = ""
    baseline_switches: int = 0
    repaired: bool = False
    moved_pixels: int = 0
    repair_attempts: int = 0
    repair_elapsed: float = 0.0
    cut_y: int | None = None


def _miss_result(ink, *, path: str) -> dict:
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
        "baseline_switches": [],
        "exact_fast_path": True,
        "exact_cover_path": path,
    }


def _success_result(
    ink,
    baseline,
    selected,
    placements_tested,
    *,
    path: str,
    baseline_switches=None,
) -> dict:
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
        "baseline_switches": list(baseline_switches or []),
        "exact_fast_path": True,
        "exact_cover_path": path,
    }


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
            "baseline_switches": [],
            "exact_fast_path": True,
            "exact_cover_path": "fast-regression-empty",
        }

    result = page_cached_prioritized_fast_exact_cover(
        ink, crop.width, crop.height, models
    )
    if result is not None:
        baseline, selected, placements_tested = result
        return _success_result(
            ink, baseline, selected, placements_tested, path="fast-regression"
        )

    shifted = fast_exact_cover_one_baseline_switch(
        ink, crop.width, crop.height, models
    )
    if shifted is not None:
        return _success_result(
            ink,
            shifted.baseline,
            shifted.selected,
            shifted.placements_tested,
            path="fast-regression-baseline-switch",
            baseline_switches=shifted.baseline_switches,
        )

    return _miss_result(ink, path="fast-regression-miss")


@contextmanager
def _fast_only_analyser():
    original = page_editor.fast.analyse_row_exact
    page_editor.fast.analyse_row_exact = analyse_row_fast_only
    try:
        yield
    finally:
        page_editor.fast.analyse_row_exact = original


def scan_page_fast(context: dict, models, *, boundary_radius: int = 6) -> list[FastRegressionRow]:
    bind_page_candidates(context, models)
    rows: list[FastRegressionRow] = []
    with _fast_only_analyser():
        for position in context["positions"]:
            set_row_priority_hint(classify_row_start(context, position))
            started = perf_counter()
            state = page_editor._load_owned_row_state(context, position, models)
            initial_elapsed = perf_counter() - started

            repair = None
            if not state.get("fully_exact") and boundary_radius >= 0:
                repair = try_fast_boundary_repair(
                    context, position, models, radius=boundary_radius
                )
                if repair.repaired:
                    set_row_priority_hint(classify_row_start(context, position))
                    state = page_editor._load_owned_row_state(context, position, models)

            repair_elapsed = repair.elapsed if repair is not None else 0.0
            rows.append(
                FastRegressionRow(
                    page=int(context["page_number"]),
                    column=int(position[0]),
                    row=int(position[1]),
                    exact=bool(state.get("fully_exact")),
                    source_pixels=int(state.get("source_pixels") or 0),
                    covered_pixels=int(state.get("covered_pixels") or 0),
                    elapsed=initial_elapsed + repair_elapsed,
                    text=str(state.get("text") or ""),
                    exact_path=str(state.get("exact_cover_path") or ""),
                    baseline_switches=len(state.get("baseline_switches") or []),
                    repaired=bool(repair and repair.repaired),
                    moved_pixels=int(repair.moved_pixels if repair else 0),
                    repair_attempts=int(repair.attempts if repair else 0),
                    repair_elapsed=repair_elapsed,
                    cut_y=repair.cut_y if repair else None,
                )
            )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fast bounded regression scan: exact, one +/-1 baseline switch, cheap boundary repair, or unresolved; never exhaustive."
    )
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--facit", type=Path, required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--page", type=int, action="append", dest="pages")
    ap.add_argument("--start-page", type=int)
    ap.add_argument("--end-page", type=int)
    ap.add_argument(
        "--boundary-radius",
        type=int,
        default=6,
        help="fixed +/- raster lines tried around the geometric lower boundary; -1 disables repair",
    )
    ap.add_argument(
        "--print-unresolved",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = ap.parse_args()
    if args.boundary_radius < -1:
        raise ValueError("--boundary-radius must be >= -1")

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
    baseline_switch_count = 0
    repaired_count = 0
    repaired_pixels = 0
    unresolved: list[FastRegressionRow] = []

    for page in pages:
        page_started = perf_counter()
        context = page_editor.build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        results = scan_page_fast(context, models, boundary_radius=args.boundary_radius)
        page_exact = sum(result.exact for result in results)
        page_switched = sum(result.exact_path == "fast-regression-baseline-switch" for result in results)
        page_repaired = sum(result.repaired for result in results)
        page_unresolved = [result for result in results if not result.exact]
        row_count += len(results)
        exact_count += page_exact
        baseline_switch_count += page_switched
        repaired_count += page_repaired
        repaired_pixels += sum(result.moved_pixels for result in results)
        unresolved.extend(page_unresolved)
        print(
            f"fast-regression: page {page}: exact={page_exact}/{len(results)} "
            f"baseline_switch={page_switched} repaired={page_repaired} unresolved={len(page_unresolved)} "
            f"wall={perf_counter()-page_started:.3f}s",
            flush=True,
        )
        for result in results:
            if result.repaired:
                print(
                    f"fast-regression: repaired page {result.page} column {result.column} row {result.row} "
                    f"moved={result.moved_pixels} cut_y={result.cut_y} attempts={result.repair_attempts} "
                    f"repair_time={result.repair_elapsed:.3f}s",
                    flush=True,
                )
        if args.print_unresolved:
            for result in page_unresolved:
                print(
                    f"fast-regression: unresolved page {result.page} column {result.column} row {result.row} "
                    f"covered={result.covered_pixels}/{result.source_pixels} time={result.elapsed:.3f}s "
                    f"repair_attempts={result.repair_attempts} repair_time={result.repair_elapsed:.3f}s "
                    f"text={result.text!r}",
                    flush=True,
                )

    wall = perf_counter() - total_started
    print(
        f"fast-regression: pages={len(pages)} rows={row_count} exact={exact_count}/{row_count} "
        f"baseline_switch={baseline_switch_count} repaired={repaired_count} repaired_pixels={repaired_pixels} "
        f"unresolved={len(unresolved)} wall={wall:.3f}s",
        flush=True,
    )
    return 0 if not unresolved else 1


if __name__ == "__main__":
    raise SystemExit(main())
