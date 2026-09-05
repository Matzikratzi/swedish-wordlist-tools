from __future__ import annotations

"""Sequential top-down provisional row ownership experiment.

Unlike the one-row probe, this module deliberately keeps provisional pixel
moves while a page is being processed.  Therefore row N+1 is analysed with the
unmatched lower ink handed down by row N.  The page context is experimental and
is discarded after the batch page finishes; facit and editor state are never
written.
"""

from dataclasses import dataclass
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_probe_provisional_row_boundary import provisional_lower_pixels


@dataclass(frozen=True)
class SequentialRowResult:
    position: tuple[int, int]
    incoming_pixels: int
    moved_pixels: int
    secure_bottom_page_y: int | None
    before_exact: bool
    after_exact: bool
    before_source_pixels: int
    before_covered_pixels: int
    after_source_pixels: int
    after_covered_pixels: int
    before_seconds: float
    after_seconds: float


def _owned_page_pixels(context: dict, position: tuple[int, int]) -> set[tuple[int, int]]:
    """Return page ink currently owned by one row inside its column span."""
    column, row_index = map(int, position)
    owners = context["pixel_owners"]
    column_entry = context["row_map"]["columns"][column]
    rows = column_entry.get("rows") or []
    if not 0 <= row_index < len(rows):
        return set()
    left = max(0, int(column_entry.get("crop_left", column_entry.get("left", 0))))
    content_left = (context.get("column_content_lefts") or {}).get(column)
    if content_left is not None:
        left = max(left, int(content_left))
    right = min(owners.width, int(column_entry.get("crop_right", column_entry.get("right", owners.width))))
    top = max(0, int(rows[row_index].get("page_top", 0)) - 8)
    bottom = min(owners.height, int(rows[row_index].get("page_bottom", owners.height)) + 8)
    code = owners.row_code(row_index)
    out: set[tuple[int, int]] = set()
    for y in range(top, bottom):
        start = y * owners.width
        for x in range(left, right):
            if owners.data[start + x] == code:
                out.add((x, y))
    return out


def process_row_sequentially(
    context: dict,
    position: tuple[int, int],
    models,
    *,
    incoming_pixels: int = 0,
) -> SequentialRowResult:
    """Analyse N; hand unmatched lower ink to N+1; keep the move in context."""
    column, row_index = map(int, position)
    rows = context["row_map"]["columns"][column].get("rows") or []

    started = perf_counter()
    before = page_editor._load_owned_row_state(context, position, models)
    before_seconds = perf_counter() - started

    if before.get("fully_exact") or row_index + 1 >= len(rows):
        return SequentialRowResult(
            position,
            int(incoming_pixels),
            0,
            None,
            bool(before.get("fully_exact")),
            bool(before.get("fully_exact")),
            int(before.get("source_pixels") or 0),
            int(before.get("covered_pixels") or 0),
            int(before.get("source_pixels") or 0),
            int(before.get("covered_pixels") or 0),
            before_seconds,
            0.0,
        )

    secure_bottom, candidates = provisional_lower_pixels(before)
    owners = context["pixel_owners"]
    upper_code = owners.row_code(row_index)
    lower_code = owners.row_code(row_index + 1)
    moved = 0
    for x, y in sorted(candidates):
        if not (0 <= x < owners.width and 0 <= y < owners.height):
            continue
        offset = y * owners.width + x
        if owners.data[offset] == upper_code:
            owners.data[offset] = lower_code
            moved += 1

    started = perf_counter()
    after = page_editor._load_owned_row_state(context, position, models)
    after_seconds = perf_counter() - started

    return SequentialRowResult(
        position,
        int(incoming_pixels),
        moved,
        secure_bottom,
        bool(before.get("fully_exact")),
        bool(after.get("fully_exact")),
        int(before.get("source_pixels") or 0),
        int(before.get("covered_pixels") or 0),
        int(after.get("source_pixels") or 0),
        int(after.get("covered_pixels") or 0),
        before_seconds,
        after_seconds,
    )


def process_column_sequentially(context: dict, column: int, models) -> list[SequentialRowResult]:
    """Process one physical column strictly top-to-bottom."""
    rows = context["row_map"]["columns"][column].get("rows") or []
    results: list[SequentialRowResult] = []
    incoming = 0
    for row_index in range(len(rows)):
        result = process_row_sequentially(
            context,
            (column, row_index),
            models,
            incoming_pixels=incoming,
        )
        results.append(result)
        incoming = result.moved_pixels
    return results
