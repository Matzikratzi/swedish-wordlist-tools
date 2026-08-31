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

    These are deliberately conservative separators: every pixel across the
    inspected column width must be white.  A missing separator says nothing;
    only a separator that actually exists is treated as hard evidence.
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
    """Return a robust center-to-center row pitch from cached physical rows."""
    centers = sorted(float(row["center_y"]) for row in rows if "center_y" in row)
    diffs = [b - a for a, b in zip(centers, centers[1:]) if b > a]
    if not diffs:
        return None
    med = median(diffs)
    # Large gaps often mean Tesseract missed one or more rows.  Do not let those
    # gaps inflate the pitch we use to detect exactly that situation.
    close = [d for d in diffs if d <= med * 1.5]
    return float(median(close or diffs))


def blocks_between_white_bands(
    bands: Iterable[dict[str, Any]],
    *,
    row_pitch: float | None,
    known_rows: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Describe the text block between each pair of hard white separators.

    The distance between separator centres estimates how many physical rows are
    enclosed.  This is the key property that lets two visible white bands imply
    one, two, three, ... rows between them when intermediate separators are
    absent.
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
                "upper_gap_center_y": upper_y,
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
    return {
        "row_pitch": pitch,
        "white_gaps": gaps,
        "gap_blocks": blocks,
        "hard_gap_count": len(gaps),
        "blocks_with_missing_rows": sum(
            1 for block in blocks if (block.get("missing_row_count") or 0) > 0
        ),
    }
