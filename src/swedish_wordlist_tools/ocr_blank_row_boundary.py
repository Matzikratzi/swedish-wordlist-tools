from __future__ import annotations

from PIL import Image

from .ocr_row_boundary_corrections import page_digest


def _column_x_bounds(
    page_image: Image.Image,
    column_entry: dict,
    upper: dict,
    lower: dict,
) -> tuple[int, int]:
    lefts = [
        int(value)
        for value in (column_entry.get("left"), upper.get("crop_left"), lower.get("crop_left"))
        if value is not None
    ]
    rights = [
        int(value)
        for value in (column_entry.get("right"), upper.get("crop_right"), lower.get("crop_right"))
        if value is not None
    ]
    left = max(0, min(lefts) if lefts else 0)
    right = min(page_image.width, max(rights) if rights else page_image.width)
    if right <= left:
        left, right = 0, page_image.width
    return left, right


def _row_has_ink(gray: Image.Image, left: int, right: int, y: int, threshold: int) -> bool:
    pixels = gray.load()
    return any(int(pixels[x, y]) <= threshold for x in range(left, right))


def find_blank_row_boundary(
    page_image: Image.Image,
    row_map: dict,
    column: int,
    upper_row: int,
    *,
    threshold: int = 210,
    max_shift: int = 4,
    source_digest_value: str | None = None,
    page_number: int | None = None,
) -> dict | None:
    """Find a conservative row cut from a full-width white raster row.

    This deliberately does not use glyph models.  A completely white horizontal
    raster row across the column proves that no connected printed ink crosses it,
    so it is safe evidence even when the facit is missing the glyph immediately
    above or below the gap.

    Only blank bands close to the existing row boundary are considered.  The
    band must have source ink nearby on both sides.  If more than one equally
    near band remains, the evidence is treated as ambiguous.
    """
    columns = row_map.get("columns") or []
    if not 0 <= column < len(columns):
        return None
    column_entry = columns[column]
    rows = column_entry.get("rows") or []
    if not 0 <= upper_row < len(rows) - 1:
        return None

    upper = rows[upper_row]
    lower = rows[upper_row + 1]
    old_upper_bottom = int(upper["page_bottom"])
    old_lower_top = int(lower["page_top"])
    original = int(round((old_upper_bottom + old_lower_top) / 2.0))
    outer_top = int(upper["page_top"])
    outer_bottom = int(lower["page_bottom"])
    if outer_bottom - outer_top < 3:
        return None

    gray = page_image.convert("L")
    left, right = _column_x_bounds(gray, column_entry, upper, lower)
    search_top = max(outer_top + 1, original - int(max_shift))
    search_bottom = min(outer_bottom - 2, original + int(max_shift))
    if search_bottom < search_top:
        return None

    white_rows = [
        y
        for y in range(search_top, search_bottom + 1)
        if not _row_has_ink(gray, left, right, y, threshold)
    ]
    if not white_rows:
        return None

    bands: list[tuple[int, int]] = []
    start = previous = white_rows[0]
    for y in white_rows[1:]:
        if y == previous + 1:
            previous = y
            continue
        bands.append((start, previous))
        start = previous = y
    bands.append((start, previous))

    evidence_radius = int(max_shift) + 1
    candidates = []
    for blank_top, blank_bottom in bands:
        boundary = blank_bottom + 1
        if not outer_top < boundary < outer_bottom:
            continue
        upper_probe_top = max(outer_top, blank_top - evidence_radius)
        lower_probe_bottom = min(outer_bottom, blank_bottom + 1 + evidence_radius)
        ink_above = any(
            _row_has_ink(gray, left, right, y, threshold)
            for y in range(upper_probe_top, blank_top)
        )
        ink_below = any(
            _row_has_ink(gray, left, right, y, threshold)
            for y in range(blank_bottom + 1, lower_probe_bottom)
        )
        if not (ink_above and ink_below):
            continue
        candidates.append(
            {
                "blank_top": blank_top,
                "blank_bottom": blank_bottom,
                "boundary": boundary,
                "distance": abs(boundary - original),
            }
        )

    if not candidates:
        return None
    best_distance = min(item["distance"] for item in candidates)
    best = [item for item in candidates if item["distance"] == best_distance]
    if len(best) != 1:
        return None
    winner = best[0]

    return {
        "status": "accepted-blank-row-horizontal-boundary",
        "page": int(page_number or 0),
        "column": int(column),
        "upper_row": int(upper_row),
        "lower_row": int(upper_row) + 1,
        "threshold": int(threshold),
        "source_digest": source_digest_value or page_digest(page_image),
        "original_upper_bottom": old_upper_bottom,
        "original_lower_top": old_lower_top,
        "original_boundary": original,
        "corrected_boundary": int(winner["boundary"]),
        "shift": int(winner["boundary"] - original),
        "max_shift": int(max_shift),
        "blank_row_top": int(winner["blank_top"]),
        "blank_row_bottom": int(winner["blank_bottom"]),
        "evidence": "full-width-white-raster-row",
    }
