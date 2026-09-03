from __future__ import annotations

from PIL import Image

from .ocr_probe_row_glyphs import analyse_row_exact
from .ocr_page_pixel_array import PagePixelArray


def _page_points(match, *, left: int, top: int) -> set[tuple[int, int]]:
    return {(left + x, top + y) for x, y in match.pixels}


def _matches_near_boundary(matches, *, crop_left: int, crop_top: int, boundary: int, radius: int):
    out = []
    lo = boundary - radius
    hi = boundary + radius
    for match in matches:
        points = _page_points(match, left=crop_left, top=crop_top)
        if any(lo <= y <= hi for _x, y in points):
            out.append((match, points))
    return out


def refine_known_glyph_ownership(
    page: Image.Image,
    row_map: dict,
    owners: PagePixelArray,
    models,
    *,
    threshold: int = 210,
    radius: int = 6,
) -> list[dict]:
    """Let exact glyphs override a rectangular split between touching rows.

    Row geometry is only the initial ownership guess.  Around every touching
    boundary we analyse two overlapping raw-source crops: the upper crop ends a
    few pixels below the boundary and the lower crop starts a few pixels above
    it.  Each crop chooses one exact baseline.  Pixels belonging to exact glyphs
    on that baseline are then assigned to that physical row even when the glyph
    crosses the geometric y boundary.

    This is the important case for a descender (for example g) touching an
    ascender (for example b): both complete glyphs may have overlapping vertical
    extents, so no single horizontal cut can preserve both.  Pixel ownership can.
    Ambiguous pixels claimed by exact glyphs from both rows are left untouched.
    """
    gray = page.convert("L")
    changes: list[dict] = []

    for column_index, column in enumerate(row_map.get("columns") or []):
        rows = column.get("rows") or []
        left = max(0, int(column.get("crop_left", column.get("left", 0))))
        right = min(page.width, int(column.get("crop_right", column.get("right", page.width))))
        if right <= left:
            continue

        for row_index in range(len(rows) - 1):
            upper = rows[row_index]
            lower = rows[row_index + 1]
            boundary = (int(upper["page_bottom"]) + int(lower["page_top"])) // 2

            upper_top = max(0, int(upper["page_top"]) - 1)
            upper_bottom = min(page.height, boundary + radius + 1)
            lower_top = max(0, boundary - radius)
            lower_bottom = min(page.height, int(lower["page_bottom"]) + 1)
            if upper_bottom <= upper_top or lower_bottom <= lower_top:
                continue

            upper_crop = gray.crop((left, upper_top, right, upper_bottom))
            lower_crop = gray.crop((left, lower_top, right, lower_bottom))
            upper_result = analyse_row_exact(upper_crop, models, threshold=threshold)
            lower_result = analyse_row_exact(lower_crop, models, threshold=threshold)
            if upper_result["baseline"] is None or lower_result["baseline"] is None:
                continue

            upper_matches = _matches_near_boundary(
                upper_result["selected"],
                crop_left=left,
                crop_top=upper_top,
                boundary=boundary,
                radius=radius,
            )
            lower_matches = _matches_near_boundary(
                lower_result["selected"],
                crop_left=left,
                crop_top=lower_top,
                boundary=boundary,
                radius=radius,
            )
            if not upper_matches or not lower_matches:
                continue

            upper_points = set().union(*(points for _match, points in upper_matches))
            lower_points = set().union(*(points for _match, points in lower_matches))
            conflicts = upper_points & lower_points
            upper_points -= conflicts
            lower_points -= conflicts

            upper_code = PagePixelArray.row_code(row_index)
            lower_code = PagePixelArray.row_code(row_index + 1)
            moved_to_upper = 0
            moved_to_lower = 0

            for x, y in upper_points:
                if not (0 <= x < owners.width and 0 <= y < owners.height):
                    continue
                if gray.getpixel((x, y)) >= threshold:
                    continue
                offset = y * owners.width + x
                if owners.data[offset] != upper_code:
                    owners.data[offset] = upper_code
                    moved_to_upper += 1

            for x, y in lower_points:
                if not (0 <= x < owners.width and 0 <= y < owners.height):
                    continue
                if gray.getpixel((x, y)) >= threshold:
                    continue
                offset = y * owners.width + x
                if owners.data[offset] != lower_code:
                    owners.data[offset] = lower_code
                    moved_to_lower += 1

            if moved_to_upper or moved_to_lower:
                changes.append(
                    {
                        "column": column_index,
                        "upper_row": row_index,
                        "lower_row": row_index + 1,
                        "boundary": boundary,
                        "upper_labels": "".join(match.label for match, _points in upper_matches),
                        "lower_labels": "".join(match.label for match, _points in lower_matches),
                        "moved_to_upper": moved_to_upper,
                        "moved_to_lower": moved_to_lower,
                        "conflict_pixels": len(conflicts),
                    }
                )

    return changes
