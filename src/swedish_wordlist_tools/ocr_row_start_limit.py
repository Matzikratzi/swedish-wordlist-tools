from __future__ import annotations

"""Reject segmented SAOL rows that start beyond the continuation indent.

The white-gap segmenter can occasionally mistake detached upper glyph parts
(for example the dots of bold i glyphs) for a complete physical row.  Real SAOL
rows start at one of a few repeated x positions.  Learn the rightmost stable
start cluster in each column as the continuation position; a one-off candidate
farther right is not a row.  Preserve its ink by extending the nearest surviving
neighbour row across the rejected candidate's vertical extent.
"""

import math
from statistics import median


def _leftmost_ink(gray, row: dict, *, left: int, right: int, threshold: int) -> int | None:
    pixels = gray.load()
    top = max(0, int(row.get("page_top", 0)))
    bottom = min(gray.height, int(row.get("page_bottom", gray.height)))
    for x in range(max(0, int(left)), min(gray.width, int(right))):
        if any(pixels[x, y] < threshold for y in range(top, bottom)):
            return x
    return None


def _clusters(values: list[int], *, tolerance: int = 2) -> list[list[int]]:
    groups: list[list[int]] = []
    for value in sorted(values):
        if groups and value - groups[-1][-1] <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return groups


def _continuation_cutoff(starts: list[int]) -> int | None:
    if not starts:
        return None
    # A valid SAOL row-start position recurs.  With a normal ~53-row column,
    # require at least three observations; on shorter columns retain the same
    # 5% criterion without ever trusting a singleton/two-off outlier.
    minimum = max(3, int(math.ceil(len(starts) * 0.05)))
    stable = [group for group in _clusters(starts) if len(group) >= minimum]
    if not stable:
        return None
    continuation_x = max(int(round(median(group))) for group in stable)
    return continuation_x + 2


def _absorb_rejected(rows: list[dict], rejected_indexes: set[int]) -> list[dict]:
    if not rejected_indexes:
        return rows
    kept_indexes = [index for index in range(len(rows)) if index not in rejected_indexes]
    if not kept_indexes:
        return rows

    for index in sorted(rejected_indexes):
        row = rows[index]
        previous = max((candidate for candidate in kept_indexes if candidate < index), default=None)
        following = min((candidate for candidate in kept_indexes if candidate > index), default=None)
        if previous is None:
            target = following
        elif following is None:
            target = previous
        else:
            prev_gap = max(0, int(row["page_top"]) - int(rows[previous]["page_bottom"]))
            next_gap = max(0, int(rows[following]["page_top"]) - int(row["page_bottom"]))
            target = following if next_gap <= prev_gap else previous
        if target is None:
            continue
        target_row = rows[target]
        target_row["page_top"] = min(int(target_row["page_top"]), int(row["page_top"]))
        target_row["page_bottom"] = max(int(target_row["page_bottom"]), int(row["page_bottom"]))
        target_row["center_y"] = (
            int(target_row["page_top"]) + int(target_row["page_bottom"]) - 1.0
        ) / 2.0
        target_row.setdefault("absorbed_late_start_rows", []).append(
            {
                "page_top": int(row["page_top"]),
                "page_bottom": int(row["page_bottom"]),
                "start_x": row.get("detected_start_x"),
            }
        )

    kept = [row for index, row in enumerate(rows) if index not in rejected_indexes]
    kept.sort(key=lambda row: (float(row["center_y"]), int(row["page_top"])))
    for index, row in enumerate(kept):
        row["index"] = index
    return kept


def limit_late_row_starts(page, row_map: dict, *, threshold: int = 210) -> dict:
    gray = page if page.mode == "L" else page.convert("L")
    total_rejected = 0
    for entry in row_map.get("columns") or []:
        rows = list(entry.get("rows") or [])
        if not rows:
            continue
        left = int(entry.get("crop_left", entry.get("left", 0)))
        right = int(entry.get("crop_right", entry.get("right", gray.width)))
        starts: list[int] = []
        for row in rows:
            start = _leftmost_ink(gray, row, left=left, right=right, threshold=threshold)
            row["detected_start_x"] = start
            if start is not None:
                starts.append(start)
        cutoff = _continuation_cutoff(starts)
        entry["continuation_start_cutoff"] = cutoff
        if cutoff is None:
            continue
        rejected = {
            index
            for index, row in enumerate(rows)
            if row.get("detected_start_x") is not None
            and int(row["detected_start_x"]) > cutoff
        }
        if rejected:
            entry["rejected_late_start_rows"] = [
                {
                    "index": index,
                    "page_top": int(rows[index]["page_top"]),
                    "page_bottom": int(rows[index]["page_bottom"]),
                    "start_x": int(rows[index]["detected_start_x"]),
                    "cutoff": cutoff,
                }
                for index in sorted(rejected)
            ]
            entry["rows"] = _absorb_rejected(rows, rejected)
            total_rejected += len(rejected)
    row_map["late_start_rejected_count"] = total_rejected
    row_map["row_count"] = sum(len(entry.get("rows") or []) for entry in row_map.get("columns") or [])
    return row_map


def install_row_start_limit() -> None:
    from . import ocr_column_row_segmentation as segmentation

    if getattr(segmentation.segment_page_rows, "_saol_row_start_limit", False):
        return
    original = segmentation.segment_page_rows

    def wrapped(page, *, columns: int = 3, threshold: int = 210):
        row_map = original(page, columns=columns, threshold=threshold)
        return limit_late_row_starts(page, row_map, threshold=threshold)

    wrapped._saol_row_start_limit = True
    wrapped._saol_original = original
    segmentation.segment_page_rows = wrapped
