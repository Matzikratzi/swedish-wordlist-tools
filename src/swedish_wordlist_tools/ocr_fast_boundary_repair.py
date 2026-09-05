from __future__ import annotations

"""Bounded row-boundary repair for fast regression scans.

This module deliberately avoids every exhaustive glyph path.  For a row that
misses the ordinary fast exact cover, it tries a small fixed set of horizontal
cut positions around the geometric separator.  Ink owned by the upper row at
or below the candidate cut is provisionally handed to the next row.  The move
is accepted only when the same fast-only analyser proves both rows exact.
"""

from dataclasses import dataclass
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_priority_fast_path import classify_row_start, set_row_priority_hint


@dataclass(frozen=True)
class FastBoundaryRepair:
    repaired: bool
    cut_y: int | None
    moved_pixels: int
    attempts: int
    elapsed: float


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


def _candidate_cuts(boundary: int, *, radius: int) -> list[int]:
    # Start conservatively: deepest cuts first, then move upward toward the
    # nominal separator.  The fixed radius makes runtime strictly bounded.
    return list(range(boundary + radius, boundary - radius - 1, -1))


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
        return FastBoundaryRepair(False, None, 0, 0, 0.0)

    owners = context["pixel_owners"]
    upper_code = owners.row_code(row_index)
    lower_code = owners.row_code(row_index + 1)
    lower_position = (column, row_index + 1)
    boundary = int(rows[row_index]["page_bottom"])
    left, right = _column_span(context, column)
    started = perf_counter()
    attempts = 0

    for cut_y in _candidate_cuts(boundary, radius=radius):
        changed: list[int] = []
        y0 = max(0, cut_y)
        y1 = min(owners.height, boundary + radius + 1)
        for y in range(y0, y1):
            start = y * owners.width
            for x in range(left, right):
                offset = start + x
                if owners.data[offset] == upper_code:
                    owners.data[offset] = lower_code
                    changed.append(offset)

        if not changed:
            continue
        attempts += 1
        upper = _analyse_fast(context, position, models)
        if upper.get("fully_exact"):
            lower = _analyse_fast(context, lower_position, models)
            if lower.get("fully_exact"):
                return FastBoundaryRepair(
                    True, cut_y, len(changed), attempts, perf_counter() - started
                )

        for offset in changed:
            owners.data[offset] = upper_code

    return FastBoundaryRepair(False, None, 0, attempts, perf_counter() - started)
