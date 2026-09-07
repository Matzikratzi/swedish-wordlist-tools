from __future__ import annotations

"""Experiment with a provisional lower boundary for difficult OCR rows.

The probe deliberately does not change normal editor behaviour.  It starts from
one row's current owned pixels, keeps every pixel explained by an exact glyph,
and provisionally gives *unmatched* ink at/below the deepest exact match to the
following row.  The row is then analysed once more.  Ownership is restored
before returning, so this module is safe for batch experiments.
"""

from dataclasses import dataclass
from time import perf_counter

from . import ocr_review_page_pixel_array_glyphs_html as page_editor


@dataclass(frozen=True)
class ProvisionalBoundaryResult:
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


def _matched_page_pixels(state: dict) -> set[tuple[int, int]]:
    left, top, _right, _bottom = map(int, state.get("crop_box") or (0, 0, 0, 0))
    out: set[tuple[int, int]] = set()
    for match in state.get("matches") or []:
        out.update((left + int(x), top + int(y)) for x, y in match.pixels)
    return out


def _source_page_pixels(state: dict) -> set[tuple[int, int]]:
    left, top, _right, _bottom = map(int, state.get("crop_box") or (0, 0, 0, 0))
    return {
        (left + int(x), top + int(y))
        for x, y in state.get("source_ink_points") or []
    }


def provisional_lower_pixels(state: dict) -> tuple[int | None, set[tuple[int, int]]]:
    """Return the secure lower extent and unmatched ink provisionally below it.

    The boundary is one raster line below the deepest pixel explained by an
    exact glyph.  Only source pixels not explained by any selected glyph are
    candidates for the lower row.  Pixels above that extent remain with the
    current row; this makes the experiment conservative in x and y.
    """
    matched = _matched_page_pixels(state)
    if not matched:
        return None, set()
    secure_bottom = max(y for _x, y in matched) + 1
    residual = _source_page_pixels(state) - matched
    return secure_bottom, {(x, y) for x, y in residual if y >= secure_bottom}


def probe_provisional_boundary(context: dict, position: tuple[int, int], models) -> ProvisionalBoundaryResult:
    """Temporarily move lower residual pixels to N+1 and reanalyse N once."""
    column, row_index = map(int, position)
    rows = context["row_map"]["columns"][column].get("rows") or []

    started = perf_counter()
    before = page_editor._load_owned_row_state(context, position, models)
    before_seconds = perf_counter() - started

    if row_index + 1 >= len(rows) or before.get("fully_exact"):
        return ProvisionalBoundaryResult(
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
    changed: list[tuple[int, int]] = []

    for x, y in sorted(candidates):
        if not (0 <= x < owners.width and 0 <= y < owners.height):
            continue
        offset = y * owners.width + x
        if owners.data[offset] == upper_code:
            owners.data[offset] = lower_code
            changed.append((offset, upper_code))

    try:
        started = perf_counter()
        after = page_editor._load_owned_row_state(context, position, models)
        after_seconds = perf_counter() - started
    finally:
        for offset, old_value in changed:
            owners.data[offset] = old_value

    return ProvisionalBoundaryResult(
        len(changed),
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
