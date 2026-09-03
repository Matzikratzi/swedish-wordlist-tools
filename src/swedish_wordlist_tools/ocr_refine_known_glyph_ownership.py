from __future__ import annotations

from dataclasses import replace

from PIL import Image

from .ocr_glyph_gap_matcher import max_internal_blank_run, safe_ink_groups
from .ocr_glyph_matcher import exact_matches, select_best_disjoint_exact_for_ink
from .ocr_page_pixel_array import PagePixelArray
from .ocr_probe_row_glyphs import row_ink
from .ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped


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
    # Baseline discovery itself must use the same safe-white-gap partitioning as
    # normal row review.  The old whole-column matcher made the rare boundary
    # fallback unexpectedly expensive.
    result = analyse_row_exact_grouped(crop, models, threshold=threshold)
    baseline = result["baseline"]
    return None if baseline is None else top + int(baseline)


def _boundary_bridge_xs(
    owners: PagePixelArray,
    boundary: int,
    *,
    left: int,
    right: int,
) -> set[int]:
    """Return x positions participating in an 8-connected separator crossing."""
    if boundary <= 0 or boundary >= owners.height:
        return set()
    upper_start = (boundary - 1) * owners.width
    lower_start = boundary * owners.width
    xs: set[int] = set()
    for x in range(left, right):
        if owners.data[upper_start + x] == 0:
            continue
        for nx in (x - 1, x, x + 1):
            if left <= nx < right and owners.data[lower_start + nx] != 0:
                xs.add(x)
                xs.add(nx)
    return xs


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
    bridge_xs: set[int],
    max_internal_gap: int,
):
    """Match only safe x-groups that actually contain a boundary crossing.

    A completely white vertical run wider than every known glyph's internal
    blank run is a proof that no glyph can cross it.  Therefore a bridge near
    one word/group never requires exact matching of the rest of the column.
    """
    crop = gray.crop((left, top, right, bottom))
    ink = row_ink(crop, threshold=threshold)
    selected = []
    for group_left, group_right, local_ink in safe_ink_groups(
        ink,
        max_internal_gap=max_internal_gap,
    ):
        page_group_left = left + group_left
        page_group_right = left + group_right
        if not any(page_group_left - 1 <= x <= page_group_right for x in bridge_xs):
            continue
        candidates = exact_matches(
            local_ink,
            group_right - group_left,
            crop.height,
            models,
            baseline_only=baseline_page - top,
            require_whole_components=False,
        )
        chosen = select_best_disjoint_exact_for_ink(candidates, local_ink)
        selected.extend(
            replace(
                match,
                x=match.x + group_left,
                pixels=frozenset((x + group_left, y) for x, y in match.pixels),
            )
            for match in chosen
        )
    return sorted(selected, key=lambda match: (match.x, match.baseline, match.label, match.style))


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

    The cheap byte-array bridge test runs before any glyph work. Only a
    separator where source ink is actually 8-connected across y-1/y reaches the
    exact matcher. Matching is then restricted horizontally to provably
    independent safe-whitespace groups containing those bridge pixels.
    """
    changes: list[dict] = []
    gray: Image.Image | None = None
    model_rows = list(models)
    internal_gap = max_internal_blank_run(model_rows)

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

            bridge_xs = _boundary_bridge_xs(owners, boundary, left=left, right=right)
            if not bridge_xs:
                continue

            if gray is None:
                gray = page if page.mode == "L" else page.convert("L")

            upper_baseline = _row_baseline_page(
                owners,
                row_index,
                upper,
                left=left,
                right=right,
                models=model_rows,
                threshold=threshold,
            )
            lower_baseline = _row_baseline_page(
                owners,
                row_index + 1,
                lower,
                left=left,
                right=right,
                models=model_rows,
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
                models=model_rows,
                threshold=threshold,
                bridge_xs=bridge_xs,
                max_internal_gap=internal_gap,
            )
            lower_all = _baseline_matches(
                gray,
                left=left,
                top=pair_top,
                right=right,
                bottom=pair_bottom,
                baseline_page=lower_baseline,
                models=model_rows,
                threshold=threshold,
                bridge_xs=bridge_xs,
                max_internal_gap=internal_gap,
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
                        "bridge_x_pixels": len(bridge_xs),
                    }
                )

    return changes
