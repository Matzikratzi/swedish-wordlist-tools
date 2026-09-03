from __future__ import annotations

import base64
import io
from statistics import median
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


_HEADWORD_LEFT_PAD = 15
_HEADWORD_CLUSTER_RADIUS = 3


def _png_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _row_leftmost_ink(gray, row: dict[str, Any], *, left: int, right: int, threshold: int) -> int | None:
    pixels = gray.load()
    top = max(0, int(row["page_top"]))
    bottom = min(gray.height, int(row["page_bottom"]))
    for x in range(max(0, left), min(gray.width, right)):
        if any(pixels[x, y] < threshold for y in range(top, bottom)):
            return x
    return None


def _column_review_left(context: dict[str, Any], column: int) -> int:
    """Choose one compact left edge for every review row in a column.

    SAOL headwords share a stable x anchor while occasional superscript homonym
    digits sit a little to its left. Estimate the dominant first-ink anchor over
    all physical rows, then retain 15 pixels to its left. The edge is also
    clamped before the leftmost actual row ink so the compact view never cuts a
    printed glyph.
    """
    cache = context.setdefault("review_column_lefts", {})
    if column in cache:
        return int(cache[column])

    gray = context.get("pixel_gray_page") or context["page"].convert("L")
    threshold = int(context.get("threshold", 210))
    entry = context["row_map"]["columns"][column]
    crop_left = max(0, int(entry.get("crop_left", entry.get("left", 0))))
    crop_right = min(gray.width, int(entry.get("crop_right", entry.get("right", gray.width))))
    search_right = min(crop_right, crop_left + max(80, (crop_right - crop_left) // 2))
    candidates = [
        x
        for row in entry.get("rows") or []
        if (x := _row_leftmost_ink(gray, row, left=crop_left, right=search_right, threshold=threshold)) is not None
    ]
    if not candidates:
        cache[column] = crop_left
        return crop_left

    def cluster_score(value: int) -> tuple[int, int]:
        return (sum(abs(other - value) <= _HEADWORD_CLUSTER_RADIUS for other in candidates), value)

    center = max(candidates, key=cluster_score)
    members = [value for value in candidates if abs(value - center) <= _HEADWORD_CLUSTER_RADIUS]
    headword_anchor = int(round(median(members))) if members else int(center)
    leftmost_ink = min(candidates)
    review_left = max(crop_left, min(headword_anchor - _HEADWORD_LEFT_PAD, leftmost_ink))
    cache[column] = review_left
    context.setdefault("review_headword_anchors", {})[column] = headword_anchor
    return review_left


def _bbox(points: set[tuple[int, int]]) -> dict[str, int]:
    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    return {"left": min(xs), "top": min(ys), "right": max(xs) + 1, "bottom": max(ys) + 1}


def _compact_review_state(context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Rebase the one-row editor to the shared compact column left edge."""
    old_left, top, right, bottom = map(int, state["crop_box"])
    new_left = _column_review_left(context, int(state["column"]))
    if new_left <= old_left:
        return state
    new_left = min(new_left, right - 1)
    shift = new_left - old_left

    out = dict(state)
    out["crop_box"] = (new_left, top, right, bottom)
    out["crop_width"] = right - new_left
    owners = context.get("pixel_owners")
    if owners is not None:
        image = owners.render_owner_crop(
            row_index=int(state["row"]),
            box=(new_left, top, right, bottom),
        )
        out["image"] = _png_data_uri(image)

    source_ink = {
        (int(x) - shift, int(y))
        for x, y in state.get("source_ink_points") or []
        if int(x) >= shift
    }
    out["source_ink_points"] = [[x, y] for x, y in sorted(source_ink)]

    rebased_sets: dict[str, frozenset[tuple[int, int]]] = {}
    for item_id, points in (state.get("point_sets") or {}).items():
        rebased_sets[item_id] = frozenset(
            (int(x) - shift, int(y))
            for x, y in points
            if int(x) >= shift
        )
    out["point_sets"] = rebased_sets

    items = []
    for item in state.get("items") or []:
        updated = dict(item)
        points = set(rebased_sets.get(str(item.get("id"))) or [])
        if points:
            updated["bbox"] = _bbox(points)
        items.append(updated)
    out["items"] = items
    out["review_page_left"] = new_left
    out["review_headword_anchor"] = (context.get("review_headword_anchors") or {}).get(int(state["column"]))
    return out


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

    The one-row review is first rebased to one shared compact left edge per
    column. That edge is 15 pixels before the estimated headword anchor and is
    kept before all actual row ink, leaving room for superscript homonym digits.

    The view shows one separator between adjacent physical rows. When exact
    glyph ownership has rescued pixels across the provisional geometry, the
    displayed separator follows that effective ownership whenever one horizontal
    line can represent it. This keeps the three-row view consistent with the
    owner-filtered one-row view.

    Exact support baselines are also shown when known. For visual clarity the
    support guide is drawn on the raster line immediately *below* the baseline
    coordinate; the stored/matching baseline itself is unchanged.
    """
    state = _compact_review_state(context, state)
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


# The page-byte-array editor imports this module after ocr_glyph_review_delete,
# whose wrapper has already added review metadata to the item JSON. Add a final
# presentation-only wrapper: labels sit immediately below their glyphs, while
# residuals and unreviewed known glyphs use a deliberately vivid orange.
try:
    from . import ocr_review_row_glyphs_html as _legacy_editor

    _original_review_render_html = _legacy_editor.render_html

    def _render_compact_labels(original_render, state: dict, message: str = "") -> str:
        document = original_render(state, message)
        document = document.replace(
            "const S=", 
            "const S=",
            1,
        )
        document = document.replace(
            "const scale=7, topPad=34;",
            "const scale=7, topPad=4, bottomPad=18;",
            1,
        )
        document = document.replace(
            "canvas.width=S.crop_width*scale; canvas.height=S.crop_height*scale+topPad;",
            "canvas.width=S.crop_width*scale; canvas.height=S.crop_height*scale+topPad+bottomPad;",
            1,
        )
        document = document.replace(
            "if(it.kind!=='match') return '#c77b00';",
            "if(it.kind!=='match' || it.reviewed===false) return '#ff6500';",
            1,
        )
        old_label = "ctx.fillStyle=on?'#1769d2':color;ctx.fillText(it.kind==='match'?it.label:'?',x,topPad-3);"
        new_label = "ctx.fillStyle=on?'#1769d2':color;const label=it.kind==='match'?it.label:'?';const tw=ctx.measureText(label).width;const lx=Math.max(0,Math.min(canvas.width-tw,x+w/2-tw/2));const ly=Math.min(canvas.height-2,y+h+15);ctx.fillText(label,lx,ly);"
        if old_label not in document:
            raise ValueError("could not find glyph canvas label renderer")
        document = document.replace(old_label, new_label, 1)
        style_needle = "</style></head><body>"
        orange_css = "\n.chip.residual,.chip.match.needs-review{border-color:#ff6500!important;color:#d94f00!important}\n"
        if style_needle in document:
            document = document.replace(style_needle, orange_css + style_needle, 1)
        return document

    _legacy_editor.render_html = (
        lambda original: lambda state, message="": _render_compact_labels(original, state, message)
    )(_original_review_render_html)
except ImportError:
    pass
