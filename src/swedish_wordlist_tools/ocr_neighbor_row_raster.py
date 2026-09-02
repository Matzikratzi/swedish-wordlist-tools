from __future__ import annotations

import base64
import io
from typing import Any


def _png_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _ascii_raster(image, *, threshold: int, boundaries: list[tuple[int, str]]) -> str:
    """Return a paste-friendly #/. raster with labelled horizontal boundaries."""
    gray = image.convert("L")
    pixels = gray.load()
    marks: dict[int, list[str]] = {}
    for y, label in boundaries:
        marks.setdefault(int(y), []).append(label)
    lines: list[str] = []
    for y in range(gray.height + 1):
        for label in marks.get(y, []):
            lines.append(f"--- {label} y={y} ---")
        if y == gray.height:
            break
        lines.append("".join("#" if pixels[x, y] < threshold else "." for x in range(gray.width)))
    return "\n".join(lines)


def _support_lines(
    state: dict[str, Any],
    rows: list[dict[str, Any]],
    row_index: int,
    *,
    source_top: int,
    image_height: int,
) -> list[tuple[int, str]]:
    """Project the target baseline onto its immediate physical neighbours.

    The target row baseline is measured by the exact-row analyser.  For a
    touching-row failure we still want to inspect/create an unknown glyph before
    the ownership cut has been proven.  Therefore the diagnostic raster carries
    one support line per visible row.  Neighbor support lines are projected by
    the difference between physical row centres; they are visual guides only and
    are never consumed as ownership evidence.
    """
    baseline = state.get("baseline")
    crop_box = state.get("crop_box")
    if baseline is None or not crop_box:
        return []

    target_baseline_page = int(crop_box[1]) + int(baseline)
    target = rows[row_index]
    target_center = float(
        target.get(
            "center_y",
            (int(target["page_top"]) + int(target["page_bottom"]) - 1) / 2.0,
        )
    )

    result: list[tuple[int, str]] = []
    for index in range(max(0, row_index - 1), min(len(rows), row_index + 2)):
        row = rows[index]
        center = float(
            row.get(
                "center_y",
                (int(row["page_top"]) + int(row["page_bottom"]) - 1) / 2.0,
            )
        )
        page_y = int(round(target_baseline_page + center - target_center))
        local_y = max(0, min(int(image_height), page_y - int(source_top)))
        suffix = "exact" if index == row_index else "projected"
        result.append((local_y, f"SUPPORT row {index} ({suffix})"))
    return result


def add_neighbor_row_raster(
    context: dict[str, Any],
    state: dict[str, Any],
    *,
    probe_y: int = 8,
) -> dict[str, Any]:
    """Attach an unfiltered three-physical-row source raster for diagnostics.

    When neighbours exist, include the complete previous/current/next physical
    rows. At a page/column edge fall back to a small probe beyond the target.
    Coordinates and the ASCII dump are relative to this diagnostic raster.
    """
    page = context["page"]
    column = int(state["column"])
    row_index = int(state["row"])
    rows = context["row_map"]["columns"][column]["rows"]
    row = rows[row_index]

    crop_left, _crop_top, crop_right, _crop_bottom = map(int, state["crop_box"])
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
        boundaries.extend(
            [
                (local_y(int(previous["page_top"])), f"row {row_index - 1} top"),
                (local_y(int(previous["page_bottom"])), f"row {row_index - 1} bottom"),
            ]
        )
    boundaries.extend(
        [
            (core_top, f"TARGET row {row_index} top"),
            (core_bottom, f"TARGET row {row_index} bottom"),
        ]
    )
    if following is not None:
        boundaries.extend(
            [
                (local_y(int(following["page_top"])), f"row {row_index + 1} top"),
                (local_y(int(following["page_bottom"])), f"row {row_index + 1} bottom"),
            ]
        )

    support_lines = _support_lines(
        state,
        rows,
        row_index,
        source_top=source_top,
        image_height=image.height,
    )
    display_lines = [*boundaries, *support_lines]

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
            "neighbor_row_boundaries": [[y, label] for y, label in display_lines],
            "neighbor_support_lines": [[y, label] for y, label in support_lines],
            "neighbor_raster_ascii": _ascii_raster(
                image,
                threshold=int(context.get("threshold", 210)),
                boundaries=display_lines,
            ),
        }
    )
    return state