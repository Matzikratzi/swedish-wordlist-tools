from __future__ import annotations

"""Exact facit repair for disconnected glyph pieces split between adjacent rows."""

from .ocr_page_pixel_array import WHITE


def _source_component_is_exact(context: dict, placed: set[tuple[int, int]]) -> bool:
    """Require every 4-connected source component touched by a model to be fully owned by it."""
    owners = context["pixel_owners"]
    source = owners.data
    width = owners.width
    height = owners.height
    seen: set[tuple[int, int]] = set()
    stack = list(placed)
    while stack:
        x, y = stack.pop()
        if (x, y) in seen:
            continue
        seen.add((x, y))
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if source[ny * width + nx] == WHITE or (nx, ny) in seen:
                continue
            stack.append((nx, ny))
    return seen.issubset(placed)


def _column_bounds(context: dict, column: int) -> tuple[int, int]:
    owners = context["pixel_owners"]
    entry = context["row_map"]["columns"][column]
    left = max(0, int(entry.get("crop_left", entry.get("left", 0))))
    content_left = (context.get("column_content_lefts") or {}).get(column)
    if content_left is not None:
        left = max(left, int(content_left))
    right = min(owners.width, int(entry.get("crop_right", entry.get("right", owners.width))))
    return left, right


def _row_has_owned_ink(context: dict, column: int, row_index: int) -> bool:
    owners = context["pixel_owners"]
    rows = context["row_map"]["columns"][column].get("rows") or []
    if not 0 <= row_index < len(rows):
        return False
    left, right = _column_bounds(context, column)
    top = max(0, int(rows[row_index]["page_top"]) - 2)
    bottom = min(owners.height, int(rows[min(row_index + 1, len(rows) - 1)]["page_bottom"]) + 2)
    code = owners.row_code(row_index)
    for y in range(top, bottom):
        start = y * owners.width
        if any(owners.data[start + x] == code for x in range(left, right)):
            return True
    return False


def repair_lower_row_disconnected_glyphs(context: dict, state: dict, models) -> list[dict]:
    """Move upper-owned detached pieces when a complete lower-baseline glyph matches exactly.

    This is intentionally label-agnostic.  The evidence is the facit geometry:
    a model placed on the lower row's already established baseline must consist
    entirely of source ink, must touch both adjacent ownership rows, and must
    own every 4-connected source component it touches.  This lets glyphs such
    as dotted/diacritic letters be reconstructed without special-casing their
    character names.
    """
    column = int(state.get("column", -1))
    lower_row = int(state.get("row", -1))
    if lower_row <= 0 or state.get("baseline") is None:
        return []
    upper_row = lower_row - 1
    columns = context.get("row_map", {}).get("columns") or []
    if not 0 <= column < len(columns):
        return []
    rows = columns[column].get("rows") or []
    if not 0 <= upper_row < lower_row < len(rows):
        return []

    owners = context["pixel_owners"]
    upper_code = owners.row_code(upper_row)
    lower_code = owners.row_code(lower_row)
    crop_left, crop_top, crop_right, _crop_bottom = map(int, state["crop_box"])
    baseline_page = crop_top + int(state["baseline"])
    left, right = _column_bounds(context, column)
    left = max(left, crop_left)
    right = min(right, crop_right)
    if right <= left:
        return []

    candidates: dict[frozenset[tuple[int, int]], dict] = {}
    for model in models:
        pixels = getattr(model, "pixels", None)
        if not pixels:
            continue
        min_model_x = min(int(x) for x, _y in pixels)
        max_model_x = max(int(x) for x, _y in pixels)
        start_x = left - min_model_x
        end_x = right - 1 - max_model_x
        for x0 in range(start_x, end_x + 1):
            placed = {(x0 + int(x), baseline_page + int(y)) for x, y in pixels}
            if not placed or any(not (0 <= x < owners.width and 0 <= y < owners.height) for x, y in placed):
                continue
            values = {owners.value(x, y) for x, y in placed}
            if not values.issubset({upper_code, lower_code}):
                continue
            if upper_code not in values or lower_code not in values:
                continue
            if not _source_component_is_exact(context, placed):
                continue
            key = frozenset(placed)
            candidates.setdefault(
                key,
                {
                    "column": column,
                    "upper_row": upper_row,
                    "lower_row": lower_row,
                    "label": getattr(model, "label", "?"),
                    "style": getattr(model, "style", "unknown"),
                    "baseline_page_y": baseline_page,
                    "pixels": len(placed),
                },
            )

    if not candidates:
        return []

    move_points: set[tuple[int, int]] = set()
    for placed in candidates:
        move_points.update((x, y) for x, y in placed if owners.value(x, y) == upper_code)
    if not move_points:
        return []

    lock = context.get("known_glyph_ownership_lock")
    if lock is None:
        class _Noop:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
        lock = _Noop()
    with lock:
        changed = 0
        for x, y in move_points:
            offset = y * owners.width + x
            if owners.data[offset] == upper_code:
                owners.data[offset] = lower_code
                changed += 1
        if not changed:
            return []
        context["pixel_owner_revision"] = int(context.get("pixel_owner_revision") or 0) + 1
        revisions = context.setdefault("pixel_owner_row_revisions", {})
        for position in ((column, upper_row), (column, lower_row)):
            revisions[position] = int(revisions.get(position, 0)) + 1

    # If the upper physical row consisted solely of detached pieces, it was a
    # segmentation artefact.  Collapse its exclusive bottom to the first pixel
    # now owned by the lower row so subsequent crops include the whole glyph.
    if not _row_has_owned_ink(context, column, upper_row):
        lower_points = owners.owner_ink_points(
            row_index=lower_row,
            left=left,
            top=max(0, int(rows[upper_row]["page_top"]) - 2),
            right=right,
            bottom=min(owners.height, int(rows[lower_row]["page_bottom"]) + 2),
        )
        if lower_points:
            rows[upper_row]["page_bottom"] = min(y for _x, y in lower_points)

    records = []
    for placed, record in candidates.items():
        moved = sum((x, y) in move_points for x, y in placed)
        if not moved:
            continue
        records.append({**record, "moved_from_upper": moved, "decision": "lower-from-disconnected-exact-glyph"})
    context.setdefault("disconnected_glyph_ownership", []).extend(records)
    if not context.get("quiet_successful_ownership"):
        labels = ", ".join(sorted({str(item["label"]) for item in records}))
        print(
            f"review: frånkopplad exact-glyph c{column} r{upper_row}/{lower_row}: "
            f"flyttade {changed} px till undre raden (facit {labels})",
            flush=True,
        )
    return records
