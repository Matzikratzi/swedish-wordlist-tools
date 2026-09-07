from __future__ import annotations

"""Top-down provisional ownership with adjacent-row pixel closure.

A transfer from row N to N+1 is committed only when it makes N exact and every
transferred page pixel is explained by an exact glyph selected for N+1.  The
lower row may still have unrelated residual ink of its own; that must not make
an otherwise proven transfer fail.  Unproven transfers are reverted
immediately, so unresolved ownership cannot propagate through the column.
"""

from dataclasses import dataclass
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor
from .ocr_probe_provisional_row_boundary import provisional_lower_pixels


@dataclass(frozen=True)
class PairClosureResult:
    upper: tuple[int, int]
    lower: tuple[int, int] | None
    proposed_pixels: int
    committed_pixels: int
    upper_before_exact: bool
    upper_after_exact: bool
    lower_after_exact: bool | None
    transferred_pixels_explained: int | None
    transferred_pixels_total: int | None
    committed: bool
    upper_before_covered: int
    upper_before_source: int
    upper_after_covered: int
    upper_after_source: int
    lower_after_covered: int | None
    lower_after_source: int | None
    upper_before_seconds: float
    upper_after_seconds: float
    lower_after_seconds: float
    secure_bottom_page_y: int | None


def _analyse(context: dict, position: tuple[int, int], models) -> tuple[dict, float]:
    started = perf_counter()
    state = page_editor._load_owned_row_state(context, position, models)
    return state, perf_counter() - started


def _matched_page_pixels(state: dict) -> set[tuple[int, int]]:
    """Translate all exact selected glyph pixels from row-local to page coords."""
    left, top, _right, _bottom = map(int, state.get("crop_box") or (0, 0, 0, 0))
    pixels: set[tuple[int, int]] = set()
    for match in state.get("matches") or []:
        pixels.update((left + int(x), top + int(y)) for x, y in match.pixels)
    return pixels


def probe_pair_closure(context: dict, position: tuple[int, int], models) -> PairClosureResult:
    column, row_index = map(int, position)
    rows = context["row_map"]["columns"][column].get("rows") or []
    before, before_seconds = _analyse(context, position, models)

    if before.get("fully_exact") or row_index + 1 >= len(rows):
        exact = bool(before.get("fully_exact"))
        return PairClosureResult(
            position, None, 0, 0, exact, exact, None, None, None, False,
            int(before.get("covered_pixels") or 0), int(before.get("source_pixels") or 0),
            int(before.get("covered_pixels") or 0), int(before.get("source_pixels") or 0),
            None, None, before_seconds, 0.0, 0.0, None,
        )

    secure_bottom, candidates = provisional_lower_pixels(before)
    owners = context["pixel_owners"]
    upper_code = owners.row_code(row_index)
    lower_code = owners.row_code(row_index + 1)
    changed: list[tuple[int, int, int, int, int]] = []
    for x, y in sorted(candidates):
        if not (0 <= x < owners.width and 0 <= y < owners.height):
            continue
        offset = y * owners.width + x
        if owners.data[offset] == upper_code:
            changed.append((offset, upper_code, lower_code, x, y))
            owners.data[offset] = lower_code

    after, after_seconds = _analyse(context, position, models)
    lower_position = (column, row_index + 1)
    lower_state = None
    lower_seconds = 0.0
    explained = None
    transferred_total = None
    if changed and after.get("fully_exact"):
        lower_state, lower_seconds = _analyse(context, lower_position, models)
        transferred = {(x, y) for _offset, _old, _new, x, y in changed}
        lower_matched = _matched_page_pixels(lower_state)
        explained = len(transferred & lower_matched)
        transferred_total = len(transferred)

    committed = bool(
        changed
        and after.get("fully_exact")
        and lower_state is not None
        and transferred_total is not None
        and explained == transferred_total
    )
    if not committed:
        for offset, old_value, _new_value, _x, _y in changed:
            owners.data[offset] = old_value

    return PairClosureResult(
        position,
        lower_position,
        len(changed),
        len(changed) if committed else 0,
        bool(before.get("fully_exact")),
        bool(after.get("fully_exact")),
        bool(lower_state.get("fully_exact")) if lower_state is not None else None,
        explained,
        transferred_total,
        committed,
        int(before.get("covered_pixels") or 0),
        int(before.get("source_pixels") or 0),
        int(after.get("covered_pixels") or 0),
        int(after.get("source_pixels") or 0),
        int(lower_state.get("covered_pixels") or 0) if lower_state is not None else None,
        int(lower_state.get("source_pixels") or 0) if lower_state is not None else None,
        before_seconds,
        after_seconds,
        lower_seconds,
        secure_bottom,
    )


def process_column_pair_closed(context: dict, column: int, models) -> list[PairClosureResult]:
    rows = context["row_map"]["columns"][column].get("rows") or []
    return [probe_pair_closure(context, (column, row_index), models) for row_index in range(len(rows))]
