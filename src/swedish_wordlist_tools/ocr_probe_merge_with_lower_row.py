from __future__ import annotations

"""Probe whether a zero-match physical row belongs to the row below."""

from PIL import Image


def _combined_owner_crop(context: dict, upper_row: int, lower_row: int, box: tuple[int, int, int, int]) -> Image.Image:
    owners = context["pixel_owners"]
    left, top, right, bottom = map(int, box)
    left = max(0, left); top = max(0, top)
    right = min(owners.width, right); bottom = min(owners.height, bottom)
    width = right - left; height = bottom - top
    if width <= 0 or height <= 0:
        raise ValueError(f"empty merge probe box: {box}")
    upper_code = owners.row_code(upper_row)
    lower_code = owners.row_code(lower_row)
    out = bytearray([255]) * (width * height)
    for local_y, page_y in enumerate(range(top, bottom)):
        page_start = page_y * owners.width
        out_start = local_y * width
        for local_x, page_x in enumerate(range(left, right)):
            if owners.data[page_start + page_x] in {upper_code, lower_code}:
                out[out_start + local_x] = 0
    return Image.frombytes("L", (width, height), bytes(out))


def probe_zero_match_merge_down(context: dict, upper_state: dict, lower_state: dict, models) -> dict | None:
    """Return proof when merging a zero-match row improves the lower row.

    The upper physical row must contain ink but have zero accepted exact glyph
    matches.  We analyse the lower row as it stands, then analyse a temporary
    raster containing both ownership rows.  The merge is accepted only when the
    combined raster covers *more* pixels with exact facit glyphs while retaining
    at least as many exact glyph matches as the lower row had before.  No pixel
    ownership is changed by this function.
    """
    if int(upper_state.get("source_pixels") or 0) <= 0:
        return None
    if upper_state.get("matches"):
        return None
    column = int(upper_state["column"])
    upper_row = int(upper_state["row"])
    if int(lower_state.get("column", -1)) != column or int(lower_state.get("row", -1)) != upper_row + 1:
        return None

    lower_covered = int(lower_state.get("covered_pixels") or 0)
    lower_matches = len(lower_state.get("matches") or [])

    uleft, utop, uright, ubottom = map(int, upper_state["crop_box"])
    lleft, ltop, lright, lbottom = map(int, lower_state["crop_box"])
    box = (min(uleft, lleft), min(utop, ltop), max(uright, lright), max(ubottom, lbottom))
    crop = _combined_owner_crop(context, upper_row, upper_row + 1, box)
    result = context["analyse_row_exact"](crop, models, threshold=int(context["threshold"]))
    selected = list(result.get("selected") or [])
    merged_covered = int(result.get("covered_pixels") or 0)
    merged_matches = len(selected)

    if merged_covered <= lower_covered:
        return None
    if merged_matches < lower_matches:
        return None
    if not selected:
        return None
    if result.get("baseline") is None:
        return None

    return {
        "column": column,
        "upper_row": upper_row,
        "lower_row": upper_row + 1,
        "box": box,
        "baseline_page_y": box[1] + int(result["baseline"]),
        "lower_covered_pixels_before": lower_covered,
        "merged_covered_pixels": merged_covered,
        "covered_pixels_gain": merged_covered - lower_covered,
        "lower_matches_before": lower_matches,
        "merged_matches": merged_matches,
        "source_pixels": int(result.get("source_pixels") or 0),
        "fully_exact": bool(result.get("fully_exact")),
        "labels": "".join(match.label for match in selected),
        "decision": "merge-down-improves-exact-coverage",
    }


def apply_merge_down(context: dict, proof: dict) -> int:
    """Move every upper-row-owned ink pixel in the proven merge box downward."""
    owners = context["pixel_owners"]
    column = int(proof["column"])
    upper_row = int(proof["upper_row"])
    lower_row = int(proof["lower_row"])
    left, top, right, bottom = map(int, proof["box"])
    upper_code = owners.row_code(upper_row)
    lower_code = owners.row_code(lower_row)
    changed = 0
    lock = context["known_glyph_ownership_lock"]
    with lock:
        for y in range(max(0, top), min(owners.height, bottom)):
            start = y * owners.width
            for x in range(max(0, left), min(owners.width, right)):
                offset = start + x
                if owners.data[offset] == upper_code:
                    owners.data[offset] = lower_code
                    changed += 1
        if changed:
            context["pixel_owner_revision"] = int(context.get("pixel_owner_revision") or 0) + 1
            revisions = context.setdefault("pixel_owner_row_revisions", {})
            for position in ((column, upper_row), (column, lower_row)):
                revisions[position] = int(revisions.get(position, 0)) + 1
    if changed:
        context.setdefault("merge_down_ownership", []).append({**proof, "moved_pixels": changed})
    return changed
