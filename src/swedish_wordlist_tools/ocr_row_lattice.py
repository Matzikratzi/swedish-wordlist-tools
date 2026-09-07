from __future__ import annotations

from statistics import median
from typing import Any, Iterable

from PIL import Image


def _runs(values: Iterable[int]) -> list[tuple[int, int]]:
    values = sorted(set(int(v) for v in values))
    if not values:
        return []
    out: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value != previous + 1:
            out.append((start, previous + 1))
            start = value
        previous = value
    out.append((start, previous + 1))
    return out


def white_horizontal_bands(
    page: Image.Image,
    *,
    left: int,
    right: int,
    threshold: int = 210,
    top: int = 0,
    bottom: int | None = None,
    inset_x: int = 2,
    min_height: int = 1,
) -> list[dict[str, Any]]:
    """Find completely ink-free horizontal bands in one dictionary column.

    These are deliberately conservative separators: every image pixel across
    the inspected column width must be white. A one-image-pixel separator is
    therefore useful evidence even when the later glyph raster is coarser.
    A missing separator says nothing; only a separator that actually exists is
    treated as hard evidence.
    """
    gray = page.convert("L")
    x0 = max(0, int(left) + max(0, int(inset_x)))
    x1 = min(gray.width, int(right) - max(0, int(inset_x)))
    y0 = max(0, int(top))
    y1 = min(gray.height, gray.height if bottom is None else int(bottom))
    if x1 <= x0 or y1 <= y0:
        return []

    pixels = gray.load()
    blank_rows: list[int] = []
    for y in range(y0, y1):
        if all(pixels[x, y] >= threshold for x in range(x0, x1)):
            blank_rows.append(y)

    out: list[dict[str, Any]] = []
    for start, end in _runs(blank_rows):
        if end - start < min_height:
            continue
        out.append(
            {
                "top": start,
                "bottom": end,
                "height": end - start,
                "center_y": (start + end - 1.0) / 2.0,
            }
        )
    return out


def typical_row_pitch(rows: Iterable[dict[str, Any]]) -> float | None:
    """Return a robust center-to-center row pitch from cached physical rows.

    Missing Tesseract rows turn one normal adjacent distance into roughly two
    row pitches. With only a few known rows that doubled gap can otherwise move
    the ordinary median upward (for example 20, 40 -> 30). Prefer the lower
    half of observed positive gaps, which still represents real adjacent rows
    while deliberately excluding the large gaps we are trying to repair.
    """
    centers = sorted(float(row["center_y"]) for row in rows if "center_y" in row)
    diffs = sorted(b - a for a, b in zip(centers, centers[1:]) if b > a)
    if not diffs:
        return None
    lower_count = max(1, (len(diffs) + 1) // 2)
    return float(median(diffs[:lower_count]))


def blocks_between_white_bands(
    bands: Iterable[dict[str, Any]],
    *,
    row_pitch: float | None,
    known_rows: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Describe the text block between each pair of hard white separators.

    The distance between separator centres estimates how many physical rows are
    enclosed. This lets two visible white bands imply one, two, three, ... rows
    between them when intermediate separators are absent. The exact gap edges
    are retained as hard crop boundaries for subsequent 2D ink inspection.
    """
    ordered = sorted(bands, key=lambda band: float(band["center_y"]))
    centers = sorted(float(row["center_y"]) for row in known_rows if "center_y" in row)
    out: list[dict[str, Any]] = []
    for upper, lower in zip(ordered, ordered[1:]):
        upper_y = float(upper["center_y"])
        lower_y = float(lower["center_y"])
        distance = lower_y - upper_y
        if distance <= 0:
            continue
        known = [center for center in centers if upper_y < center < lower_y]
        estimated = None
        if row_pitch and row_pitch > 0:
            estimated = max(1, int(round(distance / row_pitch)))
        out.append(
            {
                "upper_gap_top": int(upper["top"]),
                "upper_gap_bottom": int(upper["bottom"]),
                "upper_gap_center_y": upper_y,
                "lower_gap_top": int(lower["top"]),
                "lower_gap_bottom": int(lower["bottom"]),
                "lower_gap_center_y": lower_y,
                "distance": distance,
                "estimated_row_count": estimated,
                "known_row_count": len(known),
                "known_row_centers": known,
                "missing_row_count": (
                    max(0, estimated - len(known)) if estimated is not None else None
                ),
            }
        )
    return out


def ink_extent_between_white_bands(
    page: Image.Image,
    block: dict[str, Any],
    *,
    left: int,
    right: int,
    threshold: int = 210,
    inset_x: int = 2,
) -> dict[str, Any]:
    """Measure the 2D ink island enclosed by two hard horizontal white bands.

    The returned bounding box also measures the blank margins to the left and
    right. Thus a Tesseract-missed line can still be recognized as an isolated
    text island when it is separated by white both horizontally and vertically.
    """
    gray = page.convert("L")
    x0 = max(0, int(left) + max(0, int(inset_x)))
    x1 = min(gray.width, int(right) - max(0, int(inset_x)))
    y0 = max(0, int(block["upper_gap_bottom"]))
    y1 = min(gray.height, int(block["lower_gap_top"]))
    if x1 <= x0 or y1 <= y0:
        return {
            "ink_pixels": 0,
            "ink_bbox": None,
            "left_white_margin": max(0, x1 - x0),
            "right_white_margin": max(0, x1 - x0),
        }

    pixels = gray.load()
    ink = [
        (x, y)
        for y in range(y0, y1)
        for x in range(x0, x1)
        if pixels[x, y] < threshold
    ]
    if not ink:
        return {
            "ink_pixels": 0,
            "ink_bbox": None,
            "left_white_margin": x1 - x0,
            "right_white_margin": x1 - x0,
        }

    xs = [x for x, _ in ink]
    ys = [y for _, y in ink]
    ink_left = min(xs)
    ink_right = max(xs) + 1
    ink_top = min(ys)
    ink_bottom = max(ys) + 1
    return {
        "ink_pixels": len(ink),
        "ink_bbox": [ink_left, ink_top, ink_right, ink_bottom],
        "ink_width": ink_right - ink_left,
        "ink_height": ink_bottom - ink_top,
        "left_white_margin": ink_left - x0,
        "right_white_margin": x1 - ink_right,
    }


def proposed_missing_rows(
    page: Image.Image,
    blocks: Iterable[dict[str, Any]],
    *,
    left: int,
    right: int,
    row_pitch: float | None,
    threshold: int = 210,
    min_ink_pixels: int = 12,
) -> list[dict[str, Any]]:
    """Propose clear one-row ink islands that Tesseract failed to report.

    This first conservative step only promotes blocks whose white-gap geometry
    says exactly one row belongs there and for which Tesseract reports none.
    Multi-row recovery is deliberately left for a later lattice-fitting step.
    """
    if not row_pitch or row_pitch <= 0:
        return []

    out: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("estimated_row_count") != 1 or block.get("known_row_count") != 0:
            continue
        extent = ink_extent_between_white_bands(
            page,
            block,
            left=left,
            right=right,
            threshold=threshold,
        )
        bbox = extent.get("ink_bbox")
        if not bbox or int(extent.get("ink_pixels") or 0) < min_ink_pixels:
            continue

        ink_width = int(extent["ink_width"])
        ink_height = int(extent["ink_height"])
        # Reject isolated specks. Real text may be short ("a", punctuation), so
        # keep these bounds intentionally permissive and let later OCR decide.
        if ink_width < max(3, int(row_pitch * 0.35)):
            continue
        if ink_height < max(2, int(row_pitch * 0.20)):
            continue

        ink_left, ink_top, ink_right, ink_bottom = map(int, bbox)
        out.append(
            {
                "source": "white-gap-ink-island",
                "page_top": ink_top,
                "page_bottom": ink_bottom,
                "center_y": (ink_top + ink_bottom - 1.0) / 2.0,
                "ink_left": ink_left,
                "ink_right": ink_right,
                **extent,
                "upper_hard_gap": [
                    int(block["upper_gap_top"]),
                    int(block["upper_gap_bottom"]),
                ],
                "lower_hard_gap": [
                    int(block["lower_gap_top"]),
                    int(block["lower_gap_bottom"]),
                ],
            }
        )
    return out


def row_lattice_for_column(
    page: Image.Image,
    rows: list[dict[str, Any]],
    *,
    left: int,
    right: int,
    threshold: int = 210,
) -> dict[str, Any]:
    """Build the reusable row model that can replace five-row/12-area discovery."""
    pitch = typical_row_pitch(rows)
    gaps = white_horizontal_bands(
        page,
        left=left,
        right=right,
        threshold=threshold,
    )
    blocks = blocks_between_white_bands(gaps, row_pitch=pitch, known_rows=rows)
    proposed = proposed_missing_rows(
        page,
        blocks,
        left=left,
        right=right,
        row_pitch=pitch,
        threshold=threshold,
    )
    return {
        "row_pitch": pitch,
        "white_gaps": gaps,
        "gap_blocks": blocks,
        "hard_gap_count": len(gaps),
        "blocks_with_missing_rows": sum(
            1 for block in blocks if (block.get("missing_row_count") or 0) > 0
        ),
        "proposed_rows": proposed,
        "proposed_row_count": len(proposed),
    }
