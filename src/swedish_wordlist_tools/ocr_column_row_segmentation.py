from __future__ import annotations

import math
from collections import Counter
from statistics import median
from typing import Any

from PIL import Image

from .ocr_row_lattice import ink_extent_between_white_bands, white_horizontal_bands


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def column_blocks(
    page: Image.Image,
    *,
    left: int,
    right: int,
    threshold: int = 210,
    inset_x: int = 2,
    min_ink_pixels: int = 12,
) -> list[dict[str, Any]]:
    """Return non-empty ink blocks bounded by hard horizontal white bands."""
    gaps = white_horizontal_bands(
        page,
        left=left,
        right=right,
        threshold=threshold,
        inset_x=inset_x,
    )
    blocks: list[dict[str, Any]] = []
    for upper, lower in zip(gaps, gaps[1:]):
        block = {
            "upper_gap_top": int(upper["top"]),
            "upper_gap_bottom": int(upper["bottom"]),
            "upper_gap_center_y": float(upper["center_y"]),
            "lower_gap_top": int(lower["top"]),
            "lower_gap_bottom": int(lower["bottom"]),
            "lower_gap_center_y": float(lower["center_y"]),
            "distance": float(lower["center_y"]) - float(upper["center_y"]),
        }
        extent = ink_extent_between_white_bands(
            page,
            block,
            left=left,
            right=right,
            threshold=threshold,
            inset_x=inset_x,
        )
        if int(extent.get("ink_pixels") or 0) < min_ink_pixels:
            continue
        blocks.append({**block, **extent})
    return blocks


def estimate_row_pitch(blocks: list[dict[str, Any]]) -> float | None:
    """Estimate printed row pitch from the modal hard-gap-to-hard-gap distance."""
    distances = [
        float(block["distance"])
        for block in blocks
        if 8.0 <= float(block.get("distance") or 0.0) <= 40.0
        and int(block.get("ink_height") or 0) >= 3
    ]
    if not distances:
        return None
    quantised = [round(distance * 2.0) / 2.0 for distance in distances]
    counts = Counter(quantised)
    return min(counts, key=lambda value: (-counts[value], value))


def estimate_single_row_ink_height(
    blocks: list[dict[str, Any]],
    row_pitch: float,
) -> float | None:
    """Estimate the vertical ink extent of one ordinary printed row.

    Gap-to-gap distance alone can be large because a heading or margin leaves
    extra white space.  Ink height is an independent check: a block should only
    be split into multiple rows when its actual ink also spans multiple pitches.
    """
    heights = [
        float(block["ink_height"])
        for block in blocks
        if 0.70 * row_pitch <= float(block.get("distance") or 0.0) <= 1.30 * row_pitch
        and int(block.get("ink_height") or 0) >= 3
    ]
    if not heights:
        return None
    return float(median(heights))


def _estimated_rows_for_block(
    block: dict[str, Any],
    *,
    row_pitch: float,
    single_row_ink_height: float | None,
) -> int:
    by_gap = max(1, _round_half_up(float(block["distance"]) / row_pitch))
    if by_gap <= 1 or not single_row_ink_height:
        return by_gap

    ink_height = float(block.get("ink_height") or 0.0)
    if ink_height <= single_row_ink_height:
        by_ink = 1
    else:
        by_ink = 1 + _round_half_up((ink_height - single_row_ink_height) / row_pitch)
    return max(1, min(by_gap, by_ink))


def _horizontal_ink_counts(
    page: Image.Image,
    *,
    left: int,
    right: int,
    top: int,
    bottom: int,
    threshold: int,
    inset_x: int = 2,
) -> dict[int, int]:
    gray = page.convert("L")
    x0 = max(0, int(left) + inset_x)
    x1 = min(gray.width, int(right) - inset_x)
    y0 = max(0, int(top))
    y1 = min(gray.height, int(bottom))
    pixels = gray.load()
    return {
        y: sum(1 for x in range(x0, x1) if pixels[x, y] < threshold)
        for y in range(y0, y1)
    }


def _split_positions(
    page: Image.Image,
    block: dict[str, Any],
    *,
    row_count: int,
    row_pitch: float,
    left: int,
    right: int,
    threshold: int,
) -> list[int]:
    if row_count <= 1:
        return []
    top = int(block["upper_gap_bottom"])
    bottom = int(block["lower_gap_top"])
    counts = _horizontal_ink_counts(
        page,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        threshold=threshold,
    )
    positions: list[int] = []
    upper_center = float(block["upper_gap_center_y"])
    radius = max(1, _round_half_up(row_pitch * 0.30))
    for split_index in range(1, row_count):
        expected = _round_half_up(upper_center + split_index * row_pitch)
        lo = max(top + 1, expected - radius)
        hi = min(bottom - 1, expected + radius)
        if hi < lo:
            continue
        position = min(
            range(lo, hi + 1),
            key=lambda y: (counts.get(y, 0), abs(y - expected), y),
        )
        if positions and position <= positions[-1]:
            continue
        positions.append(position)
    return positions


def _tight_ink_bbox(
    page: Image.Image,
    *,
    left: int,
    right: int,
    top: int,
    bottom: int,
    threshold: int,
    inset_x: int = 2,
) -> list[int] | None:
    gray = page.convert("L")
    x0 = max(0, left + inset_x)
    x1 = min(gray.width, right - inset_x)
    y0 = max(0, top)
    y1 = min(gray.height, bottom)
    pixels = gray.load()
    ink = [(x, y) for y in range(y0, y1) for x in range(x0, x1) if pixels[x, y] < threshold]
    if not ink:
        return None
    xs = [x for x, _ in ink]
    ys = [y for _, y in ink]
    return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]


def rows_from_blocks(
    page: Image.Image,
    blocks: list[dict[str, Any]],
    *,
    left: int,
    right: int,
    row_pitch: float,
    threshold: int = 210,
) -> list[dict[str, Any]]:
    """Turn hard-gap blocks into physical rows, splitting merged blocks cheaply."""
    rows: list[dict[str, Any]] = []
    single_row_ink_height = estimate_single_row_ink_height(blocks, row_pitch)
    for block in blocks:
        estimated = _estimated_rows_for_block(
            block,
            row_pitch=row_pitch,
            single_row_ink_height=single_row_ink_height,
        )
        if estimated == 1:
            bbox = block.get("ink_bbox")
            if not bbox:
                continue
            _, top, _, bottom = map(int, bbox)
            rows.append(
                {
                    "source": "white-gap-single",
                    "page_top": top,
                    "page_bottom": bottom,
                    "center_y": (top + bottom - 1.0) / 2.0,
                    "upper_hard_gap": [int(block["upper_gap_top"]), int(block["upper_gap_bottom"])],
                    "lower_hard_gap": [int(block["lower_gap_top"]), int(block["lower_gap_bottom"])],
                }
            )
            continue

        boundaries = [int(block["upper_gap_bottom"])]
        boundaries.extend(
            _split_positions(
                page,
                block,
                row_count=estimated,
                row_pitch=row_pitch,
                left=left,
                right=right,
                threshold=threshold,
            )
        )
        boundaries.append(int(block["lower_gap_top"]))
        for top, bottom in zip(boundaries, boundaries[1:]):
            bbox = _tight_ink_bbox(
                page,
                left=left,
                right=right,
                top=top,
                bottom=bottom,
                threshold=threshold,
            )
            if not bbox:
                continue
            _, ink_top, _, ink_bottom = bbox
            rows.append(
                {
                    "source": "white-gap-projection-split",
                    "page_top": ink_top,
                    "page_bottom": ink_bottom,
                    "center_y": (ink_top + ink_bottom - 1.0) / 2.0,
                    "parent_estimated_rows": estimated,
                }
            )
    rows.sort(key=lambda row: (float(row["center_y"]), int(row["page_top"])))
    return rows


def segment_page_rows(
    page: Image.Image,
    *,
    columns: int = 3,
    threshold: int = 210,
) -> dict[str, Any]:
    """Segment a SAOL page from pixels alone: columns -> hard-gap blocks -> rows."""
    column_entries: list[dict[str, Any]] = []
    total_blocks = 0
    total_rows = 0
    total_multi_blocks = 0
    for column in range(columns):
        left = column * page.width // columns
        right = (column + 1) * page.width // columns if column + 1 < columns else page.width
        blocks = column_blocks(page, left=left, right=right, threshold=threshold)
        pitch = estimate_row_pitch(blocks)
        single_row_ink_height = estimate_single_row_ink_height(blocks, pitch) if pitch else None
        if pitch is None:
            rows: list[dict[str, Any]] = []
        else:
            rows = rows_from_blocks(
                page,
                blocks,
                left=left,
                right=right,
                row_pitch=pitch,
                threshold=threshold,
            )
        for index, row in enumerate(rows):
            row["index"] = index
        column_multi_blocks = sum(
            1
            for block in blocks
            if pitch
            and _estimated_rows_for_block(
                block,
                row_pitch=pitch,
                single_row_ink_height=single_row_ink_height,
            ) > 1
        )
        total_blocks += len(blocks)
        total_rows += len(rows)
        total_multi_blocks += column_multi_blocks
        column_entries.append(
            {
                "column": column,
                "left": left,
                "right": right,
                "row_pitch": pitch,
                "single_row_ink_height": single_row_ink_height,
                "block_count": len(blocks),
                "multi_row_block_count": column_multi_blocks,
                "rows": rows,
            }
        )
    return {
        "format": "saol-white-gap-row-map-v2",
        "page_size": [page.width, page.height],
        "column_count": columns,
        "block_count": total_blocks,
        "multi_row_block_count": total_multi_blocks,
        "row_count": total_rows,
        "columns": column_entries,
    }
