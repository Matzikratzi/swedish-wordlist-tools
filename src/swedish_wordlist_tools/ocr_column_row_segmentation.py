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
    gaps = white_horizontal_bands(page, left=left, right=right, threshold=threshold, inset_x=inset_x)
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
        extent = ink_extent_between_white_bands(page, block, left=left, right=right, threshold=threshold, inset_x=inset_x)
        if int(extent.get("ink_pixels") or 0) < min_ink_pixels:
            continue
        blocks.append({**block, **extent})
    return blocks


def estimate_row_pitch(blocks: list[dict[str, Any]]) -> float | None:
    distances = [float(block["distance"]) for block in blocks if 8.0 <= float(block.get("distance") or 0.0) <= 40.0 and int(block.get("ink_height") or 0) >= 3]
    if not distances:
        return None
    quantised = [round(distance * 2.0) / 2.0 for distance in distances]
    counts = Counter(quantised)
    return min(counts, key=lambda value: (-counts[value], value))


def estimate_single_row_ink_height(blocks: list[dict[str, Any]], row_pitch: float) -> float | None:
    heights = [float(block["ink_height"]) for block in blocks if 0.70 * row_pitch <= float(block.get("distance") or 0.0) <= 1.30 * row_pitch and int(block.get("ink_height") or 0) >= 3]
    return float(median(heights)) if heights else None


def _estimated_rows_for_block(block: dict[str, Any], *, row_pitch: float, single_row_ink_height: float | None) -> int:
    by_gap = max(1, _round_half_up(float(block["distance"]) / row_pitch))
    if by_gap <= 1 or not single_row_ink_height:
        return by_gap
    ink_height = float(block.get("ink_height") or 0.0)
    by_ink = 1 if ink_height <= single_row_ink_height else 1 + _round_half_up((ink_height - single_row_ink_height) / row_pitch)
    return max(1, min(by_gap, by_ink))


def _chapter_marker_for_block(block: dict[str, Any], *, column: int, left: int, right: int, row_pitch: float | None) -> dict[str, Any] | None:
    if column != 0 or not row_pitch:
        return None
    bbox = block.get("ink_bbox")
    if not bbox:
        return None
    ink_left, ink_top, ink_right, ink_bottom = map(int, bbox)
    width = max(0, ink_right - ink_left)
    height = max(0, ink_bottom - ink_top)
    area = width * height
    if area <= 0:
        return None
    density = float(block.get("ink_pixels") or 0) / area
    column_width = max(1, right - left)
    if width < 0.55 * column_width or height < 2.0 * row_pitch or density < 0.65:
        return None
    return {
        "source": "chapter-marker",
        "page_left": ink_left,
        "page_top": ink_top,
        "page_right": ink_right,
        "page_bottom": ink_bottom,
        "center_y": (ink_top + ink_bottom - 1.0) / 2.0,
        "ink_pixels": int(block.get("ink_pixels") or 0),
        "ink_density": density,
        "upper_hard_gap": [int(block["upper_gap_top"]), int(block["upper_gap_bottom"])],
        "lower_hard_gap": [int(block["lower_gap_top"]), int(block["lower_gap_bottom"])],
    }


def _horizontal_ink_counts(page: Image.Image, *, left: int, right: int, top: int, bottom: int, threshold: int, inset_x: int = 2) -> dict[int, int]:
    gray = page.convert("L")
    x0 = max(0, int(left) + inset_x)
    x1 = min(gray.width, int(right) - inset_x)
    y0 = max(0, int(top))
    y1 = min(gray.height, int(bottom))
    pixels = gray.load()
    return {y: sum(1 for x in range(x0, x1) if pixels[x, y] < threshold) for y in range(y0, y1)}


def _split_positions(page: Image.Image, block: dict[str, Any], *, row_count: int, row_pitch: float, left: int, right: int, threshold: int) -> list[int]:
    if row_count <= 1:
        return []
    top = int(block["upper_gap_bottom"])
    bottom = int(block["lower_gap_top"])
    counts = _horizontal_ink_counts(page, left=left, right=right, top=top, bottom=bottom, threshold=threshold)
    positions: list[int] = []
    ink_bbox = block.get("ink_bbox")
    ink_top = int(ink_bbox[1]) if ink_bbox else top
    radius = max(1, _round_half_up(row_pitch * 0.30))
    for split_index in range(1, row_count):
        expected = _round_half_up(ink_top + split_index * row_pitch)
        lo = max(top + 1, expected - radius)
        hi = min(bottom - 1, expected + radius)
        if hi < lo:
            continue
        position = min(range(lo, hi + 1), key=lambda y: (counts.get(y, 0), abs(y - expected), y))
        if positions and position <= positions[-1]:
            continue
        positions.append(position)
    return positions


def _tight_ink_bbox(page: Image.Image, *, left: int, right: int, top: int, bottom: int, threshold: int, inset_x: int = 2) -> list[int] | None:
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


def rows_from_blocks(page: Image.Image, blocks: list[dict[str, Any]], *, left: int, right: int, row_pitch: float, threshold: int = 210) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    single_row_ink_height = estimate_single_row_ink_height(blocks, row_pitch)
    for block in blocks:
        estimated = _estimated_rows_for_block(block, row_pitch=row_pitch, single_row_ink_height=single_row_ink_height)
        if estimated == 1:
            bbox = block.get("ink_bbox")
            if not bbox:
                continue
            _, top, _, bottom = map(int, bbox)
            rows.append({"source": "white-gap-single", "page_top": top, "page_bottom": bottom, "center_y": (top + bottom - 1.0) / 2.0, "upper_hard_gap": [int(block["upper_gap_top"]), int(block["upper_gap_bottom"])], "lower_hard_gap": [int(block["lower_gap_top"]), int(block["lower_gap_bottom"])]})
            continue
        boundaries = [int(block["upper_gap_bottom"])]
        boundaries.extend(_split_positions(page, block, row_count=estimated, row_pitch=row_pitch, left=left, right=right, threshold=threshold))
        boundaries.append(int(block["lower_gap_top"]))
        for top, bottom in zip(boundaries, boundaries[1:]):
            bbox = _tight_ink_bbox(page, left=left, right=right, top=top, bottom=bottom, threshold=threshold)
            if not bbox:
                continue
            _, ink_top, _, ink_bottom = bbox
            rows.append({"source": "white-gap-projection-split", "page_top": ink_top, "page_bottom": ink_bottom, "center_y": (ink_top + ink_bottom - 1.0) / 2.0, "parent_estimated_rows": estimated})
    rows.sort(key=lambda row: (float(row["center_y"]), int(row["page_top"])))
    return rows


def _apply_middle_column_content_start(column_entries: list[dict[str, Any]]) -> tuple[int | None, int]:
    """Drop running heads, with a separate rule for chapter-opening pages."""
    if not column_entries:
        return None, 0
    middle = column_entries[len(column_entries) // 2]
    middle_rows = list(middle.get("rows") or [])
    if not middle_rows:
        return None, 0
    content_top = int(middle_rows[0]["page_top"])
    pitch = float(middle.get("row_pitch") or 0.0)
    guard = max(2, _round_half_up(pitch * 0.35)) if pitch else 2
    ordinary_cutoff = content_top - guard
    chapter_entry = next((entry for entry in column_entries if int(entry.get("chapter_marker_count") or 0)), None)
    chapter_bottom = None
    if chapter_entry:
        markers = list(chapter_entry.get("chapter_markers") or [])
        if markers:
            chapter_bottom = max(int(marker["page_bottom"]) for marker in markers)

    discarded = 0
    for entry in column_entries:
        rows = list(entry.get("rows") or [])
        cutoff = ordinary_cutoff
        if chapter_bottom is not None and int(entry.get("column") or 0) == 0:
            cutoff = chapter_bottom
        kept = [row for row in rows if int(row["page_bottom"]) > cutoff]
        discarded += len(rows) - len(kept)
        for index, row in enumerate(kept):
            row["index"] = index
        entry["rows"] = kept
        entry["header_row_count"] = len(rows) - len(kept)
    return content_top, discarded


def _vertical_ink_counts(page: Image.Image, *, left: int, right: int, top: int, bottom: int, threshold: int) -> dict[int, int]:
    gray = page.convert("L")
    pixels = gray.load()
    left = max(0, int(left))
    right = min(gray.width, int(right))
    top = max(0, int(top))
    bottom = min(gray.height, int(bottom))
    return {x: sum(1 for y in range(top, bottom) if pixels[x, y] < threshold) for x in range(left, right)}


def _longest_low_vertical_run(counts: dict[int, int]) -> tuple[int, int] | None:
    """Find the widest essentially empty vertical corridor in a search window."""
    if not counts:
        return None
    allowed = min(counts.values()) + 1
    best: tuple[int, int] | None = None
    start: int | None = None
    previous: int | None = None
    for x in sorted(counts):
        if counts[x] <= allowed:
            if start is None or previous is None or x != previous + 1:
                start = x
        else:
            if start is not None and previous is not None:
                candidate = (start, previous + 1)
                if best is None or candidate[1] - candidate[0] > best[1] - best[0]:
                    best = candidate
            start = None
        previous = x
    if start is not None and previous is not None:
        candidate = (start, previous + 1)
        if best is None or candidate[1] - candidate[0] > best[1] - best[0]:
            best = candidate
    return best


def _refined_column_boundaries(page: Image.Image, column_entries: list[dict[str, Any]], *, threshold: int) -> list[int]:
    """Measure real printed gutters around the rough one-third page boundaries.

    The one-third split is only bootstrap geometry. Printed SAOL columns can
    cross it by many pixels. The final row crop boundary is placed halfway in
    the widest near-empty vertical corridor around each nominal split.
    """
    if len(column_entries) < 2:
        return []
    body_rows = [row for entry in column_entries for row in entry.get("rows") or []]
    if not body_rows:
        return [int(entry["right"]) for entry in column_entries[:-1]]
    body_top = min(int(row["page_top"]) for row in body_rows)
    body_bottom = max(int(row["page_bottom"]) for row in body_rows)
    boundaries: list[int] = []
    for index, entry in enumerate(column_entries[:-1]):
        nominal = int(entry["right"])
        width = max(1, int(entry["right"]) - int(entry["left"]))
        radius = max(8, width // 4)
        search_left = max(int(entry["left"]) + width // 2, nominal - radius)
        next_entry = column_entries[index + 1]
        search_right = min(page.width, int(next_entry["right"]), nominal + radius)
        counts = _vertical_ink_counts(
            page,
            left=search_left,
            right=search_right,
            top=body_top,
            bottom=body_bottom,
            threshold=threshold,
        )
        run = _longest_low_vertical_run(counts)
        boundary = nominal if run is None else (run[0] + run[1]) // 2
        boundaries.append(boundary)
    return boundaries


def _apply_column_crop_bounds(page: Image.Image, column_entries: list[dict[str, Any]], *, threshold: int) -> list[int]:
    boundaries = _refined_column_boundaries(page, column_entries, threshold=threshold)
    edges = [0, *boundaries, page.width]
    for index, entry in enumerate(column_entries):
        crop_left = edges[index]
        crop_right = edges[index + 1]
        entry["crop_left"] = crop_left
        entry["crop_right"] = crop_right
        for row in entry.get("rows") or []:
            row["crop_left"] = crop_left
            row["crop_right"] = crop_right
    return boundaries


def segment_page_rows(page: Image.Image, *, columns: int = 3, threshold: int = 210) -> dict[str, Any]:
    column_entries: list[dict[str, Any]] = []
    total_blocks = 0
    total_multi_blocks = 0
    total_chapter_markers = 0
    for column in range(columns):
        left = column * page.width // columns
        right = (column + 1) * page.width // columns if column + 1 < columns else page.width
        blocks = column_blocks(page, left=left, right=right, threshold=threshold)
        pitch = estimate_row_pitch(blocks)
        chapter_markers = [marker for block in blocks if (marker := _chapter_marker_for_block(block, column=column, left=left, right=right, row_pitch=pitch)) is not None]
        marker_boxes = {(marker["page_left"], marker["page_top"], marker["page_right"], marker["page_bottom"]) for marker in chapter_markers}
        row_blocks = [block for block in blocks if tuple(map(int, block.get("ink_bbox") or [])) not in marker_boxes]
        single_row_ink_height = estimate_single_row_ink_height(row_blocks, pitch) if pitch else None
        rows = [] if pitch is None else rows_from_blocks(page, row_blocks, left=left, right=right, row_pitch=pitch, threshold=threshold)
        for index, row in enumerate(rows):
            row["index"] = index
        column_multi_blocks = sum(1 for block in row_blocks if pitch and _estimated_rows_for_block(block, row_pitch=pitch, single_row_ink_height=single_row_ink_height) > 1)
        total_blocks += len(blocks)
        total_multi_blocks += column_multi_blocks
        total_chapter_markers += len(chapter_markers)
        column_entries.append({"column": column, "left": left, "right": right, "row_pitch": pitch, "single_row_ink_height": single_row_ink_height, "block_count": len(blocks), "multi_row_block_count": column_multi_blocks, "chapter_marker_count": len(chapter_markers), "chapter_markers": chapter_markers, "rows": rows})

    content_top, header_row_count = _apply_middle_column_content_start(column_entries)
    crop_boundaries = _apply_column_crop_bounds(page, column_entries, threshold=threshold)
    total_rows = sum(len(entry.get("rows") or []) for entry in column_entries)
    return {"format": "saol-white-gap-row-map-v6", "page_size": [page.width, page.height], "column_count": columns, "content_top": content_top, "header_row_count": header_row_count, "block_count": total_blocks, "multi_row_block_count": total_multi_blocks, "chapter_marker_count": total_chapter_markers, "crop_boundaries": crop_boundaries, "row_count": total_rows, "columns": column_entries}
