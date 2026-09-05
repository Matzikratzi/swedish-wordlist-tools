from __future__ import annotations

"""Experimental row matching directly against the page pixel array.

Unlike the legacy owned-row fast path, this probe never uses ``page_bottom``
to decide which source pixels the glyph matcher may see.  Geometry supplies a
horizontal column range and a loose vertical search neighbourhood only.  Once
an unambiguous first glyph establishes a baseline, glyph model pixels on that
baseline are followed in the raw thresholded page, including descenders below
the old row boundary.

This is deliberately a diagnostic/prototype path.  It does not mutate pixel
ownership or replace the established scanner yet.
"""

from dataclasses import dataclass

from . import ocr_page_cached_fast_path as cached
from . import ocr_priority_fast_path as priority


@dataclass(frozen=True)
class RawPageMatch:
    label: str
    style: str
    x: int
    baseline: int
    pixels: frozenset[tuple[int, int]]


def _raw_ink(context: dict, *, left: int, right: int, top: int, bottom: int) -> set[tuple[int, int]]:
    """Read black pixels straight from the page-wide threshold array."""
    owners = context["pixel_owners"]
    left = max(0, int(left)); right = min(owners.width, int(right))
    top = max(0, int(top)); bottom = min(owners.height, int(bottom))
    data = owners.data
    # PagePixelArray uses zero for white and non-zero codes for black pixels;
    # unassigned black ink is therefore intentionally visible here too.
    return {
        (x, y)
        for y in range(top, bottom)
        for x in range(left, right)
        if data[y * owners.width + x] != 0
    }


def _candidate_start_x(context: dict, column: int, row: dict) -> tuple[int, int]:
    entry = context["row_map"]["columns"][column]
    left = max(0, int(entry.get("crop_left", entry.get("left", 0))))
    right = min(context["pixel_owners"].width, int(entry.get("crop_right", entry.get("right", context["pixel_owners"].width))))
    content_left = (context.get("column_content_lefts") or {}).get(column)
    if content_left is not None:
        left = max(left, int(content_left) - 18)  # includes homonym/headword starts
    return left, right


def match_row_from_raw_page(context: dict, position: tuple[int, int], models, *, pitch_fraction: float = 0.45) -> dict:
    """Establish a baseline and follow glyphs without consulting page_bottom.

    The old row geometry is used only to choose a loose baseline search band.
    The band's bottom is derived from row pitch / neighbouring row tops, never
    from the target row's ``page_bottom``.  After baseline establishment every
    candidate is tested against raw page ink at its complete model extent.
    """
    column, row_index = position
    rows = context["row_map"]["columns"][column]["rows"]
    row = rows[row_index]
    left, right = _candidate_start_x(context, column, row)

    # Estimate pitch from neighbouring row starts. This locates the baseline
    # neighbourhood but does not define a lower ownership boundary.
    pitches = []
    if row_index > 0:
        pitches.append(int(row["page_top"]) - int(rows[row_index - 1]["page_top"]))
    if row_index + 1 < len(rows):
        pitches.append(int(rows[row_index + 1]["page_top"]) - int(row["page_top"]))
    pitch = max(8, int(round(sum(pitches) / len(pitches)))) if pitches else 16
    search_top = max(0, int(row["page_top"]) - max(3, int(round(pitch * pitch_fraction))))
    search_bottom = min(context["pixel_owners"].height, int(row["page_top"]) + pitch)

    raw = _raw_ink(context, left=left, right=right, top=search_top, bottom=search_bottom)
    page_candidates = cached._bound_page_candidates(models)
    row_kind = str(priority.classify_row_start(context, position))

    # Only anchors close to one of the established lexical starts may create a
    # row. A random glyph far inside the line is not allowed to establish one.
    xs = sorted({x for x, _y in raw})
    if not xs:
        return {"baseline": None, "matches": [], "reason": "no-raw-ink", "search_box": (left, search_top, right, search_bottom)}
    anchor_x = xs[0]
    anchor_y = min(y for x, y in raw if x == anchor_x)

    starts = []
    for model, min_x, left_pixels in cached._iter_candidates(
        page_candidates, first_glyph=True, previous_style=None, row_kind=row_kind,
        leading_homonym_seen=False, baseline_established=False,
    ):
        x0 = anchor_x - min_x
        if x0 < left or x0 + model.width > right:
            continue
        for _mx, my in left_pixels:
            baseline = anchor_y - my
            placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
            if placed and placed.issubset(raw):
                starts.append((baseline, model, x0, placed))

    baselines = sorted({baseline for baseline, _model, _x0, _placed in starts})
    if len(baselines) != 1:
        return {"baseline": None, "matches": [], "reason": "ambiguous-start", "candidate_baselines": baselines, "search_box": (left, search_top, right, search_bottom)}
    baseline = baselines[0]

    # Now the baseline, not a crop bottom, constrains vertical placement. Walk
    # left-to-right through raw pixels that can belong to glyphs on this line.
    remaining = set(raw)
    matches: list[RawPageMatch] = []
    cursor = anchor_x
    previous_style = None
    while True:
        candidates_at_cursor = []
        for model, min_x, _left_pixels in cached._iter_candidates(
            page_candidates, first_glyph=not matches, previous_style=previous_style,
            row_kind=row_kind, leading_homonym_seen=False, baseline_established=True,
        ):
            x0 = cursor - min_x
            if x0 < left or x0 + model.width > right:
                continue
            placed = frozenset((x0 + x, baseline + y) for x, y in model.pixels)
            if placed and placed.issubset(remaining):
                candidates_at_cursor.append((model, x0, placed))
        if not candidates_at_cursor:
            later = sorted(x for x, y in remaining if x > cursor and abs(y - baseline) <= pitch)
            if not later:
                break
            cursor = later[0]
            continue
        model, x0, placed = candidates_at_cursor[0]
        matches.append(RawPageMatch(model.label, str(model.style), x0, baseline, placed))
        remaining.difference_update(placed)
        previous_style = priority._typographic_style(model.style)
        later = sorted(x for x, y in remaining if x > x0 and abs(y - baseline) <= pitch)
        if not later:
            break
        cursor = later[0]

    owned = set().union(*(match.pixels for match in matches)) if matches else set()
    return {
        "baseline": baseline,
        "matches": matches,
        "labels": "".join(match.label for match in matches),
        "matched_pixels": len(owned),
        "matched_bottom": max((y for _x, y in owned), default=None),
        "legacy_page_bottom": int(row["page_bottom"]),
        "search_box": (left, search_top, right, search_bottom),
        "reason": "ok" if matches else "baseline-only",
    }
