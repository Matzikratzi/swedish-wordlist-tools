from __future__ import annotations

from PIL import Image

from .ocr_glyph_matcher import exact_matches, select_best_disjoint_exact_for_ink
from .ocr_page_pixel_array import PagePixelArray
from .ocr_probe_row_glyphs import analyse_row_exact, row_ink
from .ocr_refine_row_boundaries import _boundary_bridge_count


def _page_points(match, *, left: int, top: int) -> set[tuple[int, int]]:
    return {(left + x, top + y) for x, y in match.pixels}


def _row_baseline_page(
    owners: PagePixelArray,
    row_index: int,
    row: dict,
    *,
    left: int,
    right: int,
    models,
    threshold: int,
) -> int | None:
    top = max(0, int(row["page_top"]))
    bottom = min(owners.height, int(row["page_bottom"]))
    if bottom <= top:
        return None
    crop = owners.render_owner_crop(row_index=row_index, box=(left, top, right, bottom))
    result = analyse_row_exact(crop, models, threshold=threshold)
    baseline = result["baseline"]
    return None if baseline is None else top + int(baseline)


def _baseline_matches(
    gray: Image.Image,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    baseline_page: int,
    models,
    threshold: int,
):
    crop = gray.crop((left, top, right, bottom))
    ink = row_ink(crop, threshold=threshold)
    candidates = exact_matches(
        ink,
        crop.width,
        crop.height,
        models,
        baseline_only=baseline_page - top,
        require_whole_components=False,
    )
    return select_best_disjoint_exact_for_ink(candidates, ink)


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

    Geometry first assigns every black pixel to a horizontal row rectangle.  At
    a boundary that actually crosses connected ink we estimate the baseline of
    each row from the already-owned glyphs.  We then match the raw two-row source
    at those two *fixed* baselines.  Exact glyph pixels are authoritative and may
    cross the geometric boundary in either direction.

    Thus a known upper-row ``g`` and known lower-row ``b`` may physically touch
    and even overlap vertically.  They do not need a horizontal line capable of
    separating their bounding boxes; their exact, disjoint pixel patterns claim
    the correct row directly.  A pixel claimed by both baselines is deliberately
    left at its old ownership and reported as a conflict.
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
            if _boundary_bridge_count(
                gray,
                y=boundary,
                left=left,
                right=right,
                threshold=threshold,
            ) == 0:
                continue

            upper_baseline = _row_baseline_page(
                owners,
                row_index,
                upper,
                left=left,
                right=right,
                models=models,
                threshold=threshold,
            )
            lower_baseline = _row_baseline_page(
                owners,
                row_index + 1,
                lower,
                left=left,
                right=right,
                models=models,
                threshold=threshold,
            )
            if upper_baseline is None or lower_baseline is None or upper_baseline == lower_baseline:
                continue

            pair_top = max(0, int(upper["page_top"]) - 1)
            pair_bottom = min(page.height, int(lower["page_bottom"]) + 1)
            if pair_bottom <= pair_top:
                continue

            upper_all = _baseline_matches(
                gray,
                left=left,
                top=pair_top,
                right=right,
                bottom=pair_bottom,
                baseline_page=upper_baseline,
                models=models,
                threshold=threshold,
            )
            lower_all = _baseline_matches(
                gray,
                left=left,
                top=pair_top,
                right=right,
                bottom=pair_bottom,
                baseline_page=lower_baseline,
                models=models,
                threshold=threshold,
            )
            upper_matches = _matches_near_boundary(
                upper_all,
                crop_left=left,
                crop_top=pair_top,
                boundary=boundary,
                radius=radius,
            )
            lower_matches = _matches_near_boundary(
                lower_all,
                crop_left=left,
                crop_top=pair_top,
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
                if gray.getpixel((x, y)) >= threshold:
                    continue
                offset = y * owners.width + x
                if owners.data[offset] != upper_code:
                    owners.data[offset] = upper_code
                    moved_to_upper += 1

            for x, y in lower_points:
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
                        "upper_baseline": upper_baseline,
                        "lower_baseline": lower_baseline,
                        "upper_labels": "".join(match.label for match, _points in upper_matches),
                        "lower_labels": "".join(match.label for match, _points in lower_matches),
                        "moved_to_upper": moved_to_upper,
                        "moved_to_lower": moved_to_lower,
                        "conflict_pixels": len(conflicts),
                    }
                )

    return changes
