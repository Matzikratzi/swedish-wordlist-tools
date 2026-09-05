from __future__ import annotations

"""Fast regression scan for already-known facsimile pages.

This path is intentionally bounded.  It runs the page-cached exact-cover fast
path first.  On a miss it may try a small fixed number of horizontal row-boundary
repairs, each verified only with the same fast exact path.  It never enters the
exhaustive safe-group fallback.  A row that still cannot be proved exact is
reported as unresolved/regression and the scan continues.
"""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_baseline_boundary_hypothesis import baseline_boundary_hypothesis
from .ocr_fast_boundary_repair import try_fast_boundary_repair
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
    repaired: bool = False
    moved_pixels: int = 0
    repair_attempts: int = 0
    repair_elapsed: float = 0.0
    cut_y: int | None = None
    repair_strategy: str | None = None
    baseline_page_y: int | None = None
    geometry_boundary_y: int | None = None
    hypothesis_boundary_y: int | None = None
    hypothesis_upper_candidates: int = 0
    hypothesis_probe_candidates: int = 0
    hypothesis_proofs: int = 0


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


def _probe_baseline_boundary(context: dict, state: dict, models, *, probe_depth: int):
    """Inspect raw page ink below an already trusted row baseline.

    The owned-row crop may end at the bad separator we are investigating, so
    this probe deliberately reads the source page instead of the ownership
    raster and extends far enough to contain the deepest learned glyph.
    """
    baseline = state.get("baseline")
    if baseline is None:
        return None
    left, top, right, _bottom = map(int, state["crop_box"])
    if right <= left:
        return None
    max_lower = max((int(model.max_y) for model in models if model.pixels), default=probe_depth)
    page = context["page"]
    extended_bottom = min(page.height, top + int(baseline) + max(max_lower, probe_depth) + 1)
    if extended_bottom <= top:
        return None
    crop = page.crop((left, top, right, extended_bottom))
    ink = row_ink(crop, threshold=int(context["threshold"]))
    hypothesis = baseline_boundary_hypothesis(
        ink,
        width=crop.width,
        height=crop.height,
        models=models,
        baseline=int(baseline),
        probe_depth=probe_depth,
    )
    return hypothesis, top


def scan_page_fast(
    context: dict,
    models,
    *,
    boundary_radius: int = 6,
    baseline_boundary_probe: bool = False,
    baseline_probe_depth: int = 3,
) -> list[FastRegressionRow]:
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

            baseline_page_y = None
            geometry_boundary_y = int(state.get("effective_row_page_bottom") or state.get("row_page_bottom") or 0)
            hypothesis_boundary_y = None
            hypothesis_upper_candidates = 0
            hypothesis_probe_candidates = 0
            hypothesis_proofs = 0
            if baseline_boundary_probe and state.get("baseline") is not None:
                probed = _probe_baseline_boundary(
                    context, state, models, probe_depth=baseline_probe_depth
                )
                if probed is not None:
                    hypothesis, crop_top = probed
                    baseline_page_y = crop_top + int(hypothesis.baseline)
                    hypothesis_upper_candidates = int(hypothesis.upper_candidates)
                    hypothesis_probe_candidates = int(hypothesis.probe_candidates)
                    hypothesis_proofs = len(hypothesis.proofs)
                    if hypothesis.boundary is not None:
                        hypothesis_boundary_y = crop_top + int(hypothesis.boundary)

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
                    repaired=bool(repair and repair.repaired),
                    moved_pixels=int(repair.moved_pixels if repair else 0),
                    repair_attempts=int(repair.attempts if repair else 0),
                    repair_elapsed=repair_elapsed,
                    cut_y=repair.cut_y if repair else None,
                    repair_strategy=repair.strategy if repair else None,
                    baseline_page_y=baseline_page_y,
                    geometry_boundary_y=geometry_boundary_y,
                    hypothesis_boundary_y=hypothesis_boundary_y,
                    hypothesis_upper_candidates=hypothesis_upper_candidates,
                    hypothesis_probe_candidates=hypothesis_probe_candidates,
                    hypothesis_proofs=hypothesis_proofs,
                )
            )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fast bounded regression scan: exact, cheap boundary repair, or unresolved; never exhaustive."
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
        "--baseline-boundary-probe",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="measure experimental baseline-first descender boundary hypotheses; never changes ownership",
    )
    ap.add_argument(
        "--baseline-probe-depth",
        type=int,
        default=3,
        help="raster lines below the baseline that must agree before following a candidate deeper",
    )
    ap.add_argument(
        "--print-unresolved",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = ap.parse_args()
    if args.boundary_radius < -1:
        raise ValueError("--boundary-radius must be >= -1")
    if args.baseline_probe_depth < 1:
        raise ValueError("--baseline-probe-depth must be >= 1")

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
    repaired_count = 0
    repaired_pixels = 0
    unresolved: list[FastRegressionRow] = []

    for page in pages:
        page_started = perf_counter()
        context = page_editor.build_page_context_pixel_array(args.jsonl, page, args.threshold)
        context["quiet_successful_ownership"] = True
        results = scan_page_fast(
            context,
            models,
            boundary_radius=args.boundary_radius,
            baseline_boundary_probe=args.baseline_boundary_probe,
            baseline_probe_depth=args.baseline_probe_depth,
        )
        page_exact = sum(result.exact for result in results)
        page_repaired = sum(result.repaired for result in results)
        page_unresolved = [result for result in results if not result.exact]
        row_count += len(results)
        exact_count += page_exact
        repaired_count += page_repaired
        repaired_pixels += sum(result.moved_pixels for result in results)
        unresolved.extend(page_unresolved)
        print(
            f"fast-regression: page {page}: exact={page_exact}/{len(results)} "
            f"repaired={page_repaired} unresolved={len(page_unresolved)} "
            f"wall={perf_counter()-page_started:.3f}s",
            flush=True,
        )
        for result in results:
            if result.repaired:
                print(
                    f"fast-regression: repaired page {result.page} column {result.column} row {result.row} "
                    f"strategy={result.repair_strategy} moved={result.moved_pixels} "
                    f"cut_y={result.cut_y} attempts={result.repair_attempts} "
                    f"repair_time={result.repair_elapsed:.3f}s",
                    flush=True,
                )
            if args.baseline_boundary_probe and result.baseline_page_y is not None:
                delta = None
                if result.hypothesis_boundary_y is not None and result.geometry_boundary_y is not None:
                    delta = result.hypothesis_boundary_y - result.geometry_boundary_y
                print(
                    f"baseline-boundary: page {result.page} column {result.column} row {result.row} "
                    f"baseline={result.baseline_page_y} geometry={result.geometry_boundary_y} "
                    f"hypothesis={result.hypothesis_boundary_y} delta={delta} "
                    f"upper_candidates={result.hypothesis_upper_candidates} "
                    f"probe3_candidates={result.hypothesis_probe_candidates} "
                    f"proofs={result.hypothesis_proofs}",
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
        f"repaired={repaired_count} repaired_pixels={repaired_pixels} "
        f"unresolved={len(unresolved)} wall={wall:.3f}s",
        flush=True,
    )
    return 0 if not unresolved else 1


if __name__ == "__main__":
    raise SystemExit(main())
