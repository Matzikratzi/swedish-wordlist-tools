from __future__ import annotations

import base64
import io
from typing import Any


# Glyph matching is CPU-heavy. The review server used to run every visible row
# in a ThreadPoolExecutor, which made a difficult current-row ownership repair
# compete with speculative rows below it. Patch the shared cache class as soon
# as this module is imported: visible rows are now requested in order and every
# completed state still remains in the cache.
#
# The page-byte-array editor imports this module after the fast review module,
# so the class already exists here. Keeping this policy next to the diagnostic
# raster avoids changing the generic fast editor for other entry points.
try:
    from . import ocr_review_five_rows_glyphs_fast_html as _fast_review

    def _sequential_get_many(self, positions):
        return [self.get(position) for position in positions]

    _fast_review.SynchronizedStateCache.get_many = _sequential_get_many
except ImportError:
    pass


def _png_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _ascii_raster(
    image,
    *,
    threshold: int,
    boundaries: list[tuple[int, str]],
    support_lines: list[tuple[int, str]],
) -> str:
    """Return a paste-friendly #/. raster with labelled horizontal guides."""
    gray = image.convert("L")
    pixels = gray.load()
    marks: dict[int, list[str]] = {}
    for y, label in boundaries:
        marks.setdefault(int(y), []).append(f"RADGRÄNS {label}")
    for y, label in support_lines:
        marks.setdefault(int(y), []).append(f"STÖDLINJE {label}")
    lines: list[str] = []
    for y in range(gray.height + 1):
        for label in marks.get(y, []):
            lines.append(f"--- {label} y={y} ---")
        if y == gray.height:
            break
        lines.append("".join("#" if pixels[x, y] < threshold else "." for x in range(gray.width)))
    return "\n".join(lines)


def _known_support_lines(context: dict[str, Any], column: int, row_indexes: set[int]) -> dict[int, int]:
    """Return exact page baselines already established by two-row glyph evidence."""
    out: dict[int, int] = {}
    for item in context.get("known_glyph_ownership_refinements") or []:
        if int(item.get("column", -1)) != column:
            continue
        upper = int(item.get("upper_row", -1))
        lower = int(item.get("lower_row", -1))
        if upper in row_indexes and item.get("upper_baseline") is not None:
            out[upper] = int(item["upper_baseline"])
        if lower in row_indexes and item.get("lower_baseline") is not None:
            out[lower] = int(item["lower_baseline"])
    return out


def _effective_separator_page(
    context: dict[str, Any],
    *,
    column: int,
    upper_row_index: int,
    left: int,
    right: int,
) -> int:
    """Return a horizontal separator that agrees with current pixel ownership.

    Exact glyph refinement may move a descender one or more pixels below the
    provisional geometry. The one-row view then correctly contains the whole
    glyph while a geometry-only three-row guide would appear to cut it. For the
    diagnostic view, move the separator directly below the lowest pixel actually
    owned by the upper row whenever that still leaves every lower-row owned pixel
    below the separator.

    If upper/lower ownership overlaps vertically, no single horizontal line can
    represent the true per-pixel ownership. In that case keep the provisional
    separator; the byte array remains authoritative.
    """
    rows = context["row_map"]["columns"][column]["rows"]
    upper = rows[upper_row_index]
    provisional = int(upper["page_bottom"])
    owners = context.get("pixel_owners")
    if owners is None or upper_row_index + 1 >= len(rows):
        return provisional

    lower_row_index = upper_row_index + 1
    upper_code = owners.row_code(upper_row_index)
    lower_code = owners.row_code(lower_row_index)
    scan_top = max(0, int(upper["page_top"]) - 2)
    scan_bottom = min(owners.height, int(rows[lower_row_index]["page_bottom"]) + 2)
    left = max(0, int(left))
    right = min(owners.width, int(right))

    max_upper_y: int | None = None
    min_lower_y: int | None = None
    data = owners.data
    for y in range(scan_top, scan_bottom):
        start = y * owners.width
        has_upper = False
        has_lower = False
        for x in range(left, right):
            value = data[start + x]
            if value == upper_code:
                has_upper = True
            elif value == lower_code:
                has_lower = True
            if has_upper and has_lower:
                break
        if has_upper:
            max_upper_y = y
        if has_lower and min_lower_y is None:
            min_lower_y = y

    if max_upper_y is None:
        return provisional
    candidate = max_upper_y + 1
    if min_lower_y is None or candidate <= min_lower_y:
        return candidate
    return provisional


def add_neighbor_row_raster(
    context: dict[str, Any],
    state: dict[str, Any],
    *,
    probe_y: int = 8,
) -> dict[str, Any]:
    """Attach an unfiltered three-row source raster for diagnostics.

    The view shows one separator between adjacent physical rows. When exact
    glyph ownership has rescued pixels across the provisional geometry, the
    displayed separator follows that effective ownership whenever one horizontal
    line can represent it. This keeps the three-row view consistent with the
    owner-filtered one-row view.

    Exact support baselines are also shown when known. For visual clarity the
    support guide is drawn on the raster line immediately *below* the baseline
    coordinate; the stored/matching baseline itself is unchanged.
    """
    page = context["page"]
    column = int(state["column"])
    row_index = int(state["row"])
    rows = context["row_map"]["columns"][column]["rows"]
    row = rows[row_index]

    crop_left, crop_top, crop_right, _crop_bottom = map(int, state["crop_box"])
    previous = rows[row_index - 1] if row_index > 0 else None
    following = rows[row_index + 1] if row_index + 1 < len(rows) else None

    source_top = (
        int(previous["page_top"])
        if previous is not None
        else max(0, int(row["page_top"]) - max(0, int(probe_y)))
    )
    source_bottom = (
        int(following["page_bottom"])
        if following is not None
        else min(page.height, int(row["page_bottom"]) + max(0, int(probe_y)))
    )
    image = page.crop((crop_left, source_top, crop_right, source_bottom)).convert("L")

    def local_y(value: int) -> int:
        return max(0, min(image.height, int(value) - source_top))

    core_top = local_y(int(row["page_top"]))
    core_bottom = local_y(int(row["page_bottom"]))

    boundaries: list[tuple[int, str]] = []
    if previous is not None:
        separator = _effective_separator_page(
            context,
            column=column,
            upper_row_index=row_index - 1,
            left=crop_left,
            right=crop_right,
        )
        boundaries.append((local_y(separator), f"row {row_index - 1}/{row_index}"))
    if following is not None:
        separator = _effective_separator_page(
            context,
            column=column,
            upper_row_index=row_index,
            left=crop_left,
            right=crop_right,
        )
        boundaries.append((local_y(separator), f"row {row_index}/{row_index + 1}"))

    visible_rows = {row_index}
    if previous is not None:
        visible_rows.add(row_index - 1)
    if following is not None:
        visible_rows.add(row_index + 1)
    support_by_row = _known_support_lines(context, column, visible_rows)
    if state.get("baseline") is not None:
        support_by_row[row_index] = crop_top + int(state["baseline"])

    support_lines = [
        (local_y(page_y + 1), f"row {index}")
        for index, page_y in sorted(support_by_row.items())
        if source_top <= page_y + 1 <= source_bottom
    ]

    state = dict(state)
    state.update(
        {
            "neighbor_raster_image": _png_data_uri(image),
            "neighbor_raster_width": image.width,
            "neighbor_raster_height": image.height,
            "neighbor_core_top": core_top,
            "neighbor_core_bottom": core_bottom,
            "neighbor_probe_y": int(probe_y),
            "neighbor_page_top": source_top,
            "neighbor_page_bottom": source_bottom,
            "neighbor_row_boundaries": [[y, label] for y, label in boundaries],
            "neighbor_support_lines": [[y, label] for y, label in support_lines],
            "neighbor_display_lines": [
                *[[y, f"RADGRÄNS {label}"] for y, label in boundaries],
                *[[y, f"STÖDLINJE {label}"] for y, label in support_lines],
            ],
            "neighbor_raster_ascii": _ascii_raster(
                image,
                threshold=int(context.get("threshold", 210)),
                boundaries=boundaries,
                support_lines=support_lines,
            ),
        }
    )
    state["neighbor_row_boundaries"] = state["neighbor_display_lines"]
    return state
