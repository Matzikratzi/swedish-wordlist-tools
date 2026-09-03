from __future__ import annotations

from PIL import Image


def _boundary_bridge_count(
    page: Image.Image,
    *,
    y: int,
    left: int,
    right: int,
    threshold: int = 210,
) -> int:
    """Count 8-connected ink links crossed by a horizontal boundary at y.

    A boundary at y separates source rows y-1 and y.  Sparse descenders often
    make y itself look like a low-ink line even when that split cuts straight
    through a glyph.  Counting links across the split detects that case.
    """
    gray = page.convert("L")
    if y <= 0 or y >= gray.height:
        return 0
    pixels = gray.load()
    left = max(0, int(left))
    right = min(gray.width, int(right))
    bridges = 0
    for x in range(left, right):
        if pixels[x, y - 1] >= threshold:
            continue
        for nx in (x - 1, x, x + 1):
            if left <= nx < right and pixels[nx, y] < threshold:
                bridges += 1
                break
    return bridges


def refine_row_boundaries_by_connectivity(
    page: Image.Image,
    row_map: dict,
    *,
    threshold: int = 210,
    radius: int = 4,
) -> list[dict]:
    """Move only row boundaries that currently cut connected source ink.

    The existing white-gap segmentation remains authoritative when it already
    places a boundary between components.  For a bad split we search only a few
    raster lines around the current boundary and choose the nearest position
    that crosses fewer 8-connected ink links.  This lets a descender stay with
    its row without changing otherwise-good page geometry.
    """
    changes: list[dict] = []
    for column_index, column in enumerate(row_map.get("columns") or []):
        rows = column.get("rows") or []
        left = int(column.get("crop_left", column.get("left", 0)))
        right = int(column.get("crop_right", column.get("right", page.width)))
        for row_index in range(len(rows) - 1):
            upper = rows[row_index]
            lower = rows[row_index + 1]
            old_upper_bottom = int(upper["page_bottom"])
            old_lower_top = int(lower["page_top"])
            old_boundary = (old_upper_bottom + old_lower_top) // 2
            if not (0 < old_boundary < page.height):
                continue

            current = _boundary_bridge_count(
                page,
                y=old_boundary,
                left=left,
                right=right,
                threshold=threshold,
            )
            if current == 0:
                continue

            lo = max(int(upper["page_top"]) + 1, old_boundary - radius)
            hi = min(int(lower["page_bottom"]) - 1, old_boundary + radius)
            candidates = []
            for y in range(lo, hi + 1):
                bridges = _boundary_bridge_count(
                    page,
                    y=y,
                    left=left,
                    right=right,
                    threshold=threshold,
                )
                candidates.append((bridges, abs(y - old_boundary), y))
            if not candidates:
                continue
            best_bridges, _distance, best_y = min(candidates)
            if best_bridges >= current:
                continue

            upper["page_bottom"] = best_y
            lower["page_top"] = best_y
            upper["center_y"] = (int(upper["page_top"]) + best_y - 1.0) / 2.0
            lower["center_y"] = (best_y + int(lower["page_bottom"]) - 1.0) / 2.0
            changes.append(
                {
                    "column": column_index,
                    "upper_row": row_index,
                    "lower_row": row_index + 1,
                    "old_boundary": old_boundary,
                    "new_boundary": best_y,
                    "old_bridges": current,
                    "new_bridges": best_bridges,
                }
            )
    return changes
