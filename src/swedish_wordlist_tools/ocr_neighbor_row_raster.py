from __future__ import annotations

import base64
import io
from typing import Any


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


def add_neighbor_row_raster(
    context: dict[str, Any],
    state: dict[str, Any],
    *,
    probe_y: int = 8,
) -> dict[str, Any]:
    """Attach an unfiltered three-row source raster for diagnostics.

    The view deliberately shows exactly one separator between adjacent physical
    rows. The separator is the upper row's exclusive ``page_bottom``: anything
    below it belongs geometrically to the following row unless exact glyph
    ownership says otherwise.

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

    # One and only one separator per neighbouring row pair: directly below the
    # upper row's lowest geometrically attributed pixel.
    boundaries: list[tuple[int, str]] = []
    if previous is not None:
        boundaries.append(
            (local_y(int(previous["page_bottom"])), f"row {row_index - 1}/{row_index}")
        )
    if following is not None:
        boundaries.append(
            (local_y(int(row["page_bottom"])), f"row {row_index}/{row_index + 1}")
        )

    visible_rows = {row_index}
    if previous is not None:
        visible_rows.add(row_index - 1)
    if following is not None:
        visible_rows.add(row_index + 1)
    support_by_row = _known_support_lines(context, column, visible_rows)
    if state.get("baseline") is not None:
        support_by_row[row_index] = crop_top + int(state["baseline"])

    # The matcher baseline denotes the glyph support coordinate. On the scaled
    # diagnostic raster the guide belongs immediately below that pixel row.
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
    # Backward-compatible renderer hook: the current UI reads this key. It now
    # receives the intentionally labelled display lines rather than old top/bottom
    # bbox edges.
    state["neighbor_row_boundaries"] = state["neighbor_display_lines"]
    return state
