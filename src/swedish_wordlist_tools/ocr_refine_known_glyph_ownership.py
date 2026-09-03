from __future__ import annotations

from PIL import Image

from .ocr_glyph_matcher import exact_matches, select_best_disjoint_exact_for_ink
from .ocr_page_pixel_array import PagePixelArray
from .ocr_probe_row_glyphs import analyse_row_exact, row_ink


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
    pairs: set[tuple[int, int]] | None = None,
) -> list[dict]:
    """Let exact glyphs override a touching single row separator.

    The cheap byte-array bridge test runs before any glyph work.  Only a
    separator where source ink is actually 8-connected across y-1/y reaches the
    expensive exact matcher.  The separator itself is the upper row's exclusive
    ``page_bottom`` -- the same single separator used by page ownership.
    """
    changes: list[dict] = []
    gray: Image.Image | None = None

    for column_index, column in enumerate(row_map.get("columns") or []):
        rows = column.get("rows") or []
        left = max(0, int(column.get("crop_left", column.get("left", 0))))
        right = min(page.width, int(column.get("crop_right", column.get("right", page.width))))
        if right <= left:
            continue

        for row_index in range(len(rows) - 1):
            if pairs is not None and (column_index, row_index) not in pairs:
                continue
            upper = rows[row_index]
            lower = rows[row_index + 1]
            boundary = int(upper["page_bottom"])

            # Overwhelmingly common fast path: the already-thresholded page byte
            # array shows that no connected source ink crosses this separator.
            if owners.boundary_bridge_count(boundary, left=left, right=right) == 0:
                continue

            # Convert the source page only after the cheap test says exact glyph
            # evidence is actually needed. One call can contain several pairs,
            # so cache the conversion locally.
            if gray is None:
                gray = page.convert("L")

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
                offset = y * owners.width + x
                if owners.data[offset] != upper_code:
                    owners.data[offset] = upper_code
                    moved_to_upper += 1

            for x, y in lower_points:
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
