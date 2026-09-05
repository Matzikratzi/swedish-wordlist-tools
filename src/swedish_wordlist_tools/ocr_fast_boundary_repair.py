from __future__ import annotations

"""Bounded row-boundary repair for fast regression scans.

The cheap path is deliberately geometric before it is glyph-driven:

1. prefer a horizontal cut adjacent to a completely white raster line;
2. otherwise prefer a cut with no 8-connected ink bridge across it;
3. otherwise try cuts suggested by the current upper/lower ink extrema;
4. finally try the old bounded cuts around the geometric separator.

A candidate may move row-owned ink in *either* direction across the old
separator. Nothing is committed unless the same fast-only exact analyser proves
both adjacent rows 100% exact. No exhaustive glyph path is entered here.
"""

from dataclasses import dataclass
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_pair_separator import (
    apply_cut_bidirectional,
    candidate_separator_tiers,
    restore_changed_ownership,
)
from .ocr_priority_fast_path import classify_row_start, set_row_priority_hint


@dataclass(frozen=True)
class FastBoundaryRepair:
    repaired: bool
    cut_y: int | None
    moved_pixels: int
    attempts: int
    elapsed: float
    strategy: str | None = None


def _column_span(context: dict, column: int) -> tuple[int, int]:
    owners = context["pixel_owners"]
    entry = context["row_map"]["columns"][column]
    left = max(0, int(entry.get("crop_left", entry.get("left", 0))))
    content_left = (context.get("column_content_lefts") or {}).get(column)
    if content_left is not None:
        left = max(left, int(content_left))
    right = min(owners.width, int(entry.get("crop_right", entry.get("right", owners.width))))
    return left, right


def _analyse_fast(context: dict, position: tuple[int, int], models) -> dict:
    set_row_priority_hint(classify_row_start(context, position))
    return page_editor._load_owned_row_state(context, position, models)


def try_fast_boundary_repair(
    context: dict,
    position: tuple[int, int],
    models,
    *,
    radius: int = 6,
) -> FastBoundaryRepair:
    column, row_index = map(int, position)
    rows = context["row_map"]["columns"][column].get("rows") or []
    if row_index + 1 >= len(rows):
        return FastBoundaryRepair(False, None, 0, 0, 0.0, None)

    owners = context["pixel_owners"]
    upper_code = owners.row_code(row_index)
    lower_code = owners.row_code(row_index + 1)
    lower_position = (column, row_index + 1)
    boundary = int(rows[row_index]["page_bottom"])
    left, right = _column_span(context, column)
    started = perf_counter()
    attempts = 0

    for strategy, cuts in candidate_separator_tiers(
        owners,
        upper_code=upper_code,
        lower_code=lower_code,
        boundary=boundary,
        left=left,
        right=right,
        radius=radius,
    ):
        for cut_y in cuts:
            changed = apply_cut_bidirectional(
                owners,
                upper_code=upper_code,
                lower_code=lower_code,
                cut_y=cut_y,
                boundary=boundary,
                left=left,
                right=right,
                radius=radius,
            )
            if not changed:
                continue

            attempts += 1
            upper = _analyse_fast(context, position, models)
            if upper.get("fully_exact"):
                lower = _analyse_fast(context, lower_position, models)
                if lower.get("fully_exact"):
                    return FastBoundaryRepair(
                        True,
                        cut_y,
                        len(changed),
                        attempts,
                        perf_counter() - started,
                        strategy,
                    )

            restore_changed_ownership(owners, changed)

    return FastBoundaryRepair(False, None, 0, attempts, perf_counter() - started, None)
