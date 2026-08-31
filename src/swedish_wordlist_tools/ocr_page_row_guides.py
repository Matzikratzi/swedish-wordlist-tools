from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PIL import Image


def _source_context(row: dict[str, Any]) -> tuple[list[dict[str, Any]], int] | None:
    context = row.get("five_row_context") or {}
    bands = context.get("source_bands") or []
    target = context.get("source_target_index")
    if not bands or not isinstance(target, int) or target < 0 or target >= len(bands):
        return None
    return list(bands), target


def _band_center(band: dict[str, Any]) -> float:
    top = float(band.get("top", 0))
    bottom = float(band.get("bottom", top + 1))
    return (top + bottom - 1.0) / 2.0


def _owner_index(y: int, bands: list[dict[str, Any]]) -> int:
    return min(range(len(bands)), key=lambda i: (abs(float(y) - _band_center(bands[i])), i))


def component_touches_target_row(row: dict[str, Any], points: set[tuple[int, int]]) -> bool:
    source = _source_context(row)
    if source is None:
        return True
    bands, target = source
    return any(_owner_index(int(y), bands) == target for _, y in points)


def target_unknown_groups(row: dict[str, Any]) -> list[set[tuple[int, int]]]:
    """Return unknown groups belonging to the target physical row.

    Filtering happens before x-overlap merging. That is essential: a detached
    accent belonging to the target row may be merged with its body, while an
    unrelated glyph on the next printed row must not be pulled into the target
    merely because it happens to share the same x span.
    """
    from . import ocr_unique_unknown_glyph_review as unique

    points = {tuple(map(int, p)) for p in row.get("unexplained") or []}
    if not points:
        return []
    components = unique._components(points)
    components = [c for c in components if component_touches_target_row(row, c)]
    return unique._merge_overlapping_x(components)


def _filtered_target_row(
    row: dict[str, Any],
    keep_group: set[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    source = _source_context(row)
    if source is None:
        return row
    bands, target = source
    keep_group = keep_group or set()

    def target_pixel(point: list[int] | tuple[int, int]) -> bool:
        x, y = map(int, point)
        return (x, y) in keep_group or _owner_index(y, bands) == target

    copied = dict(row)
    copied["ink"] = [list(map(int, p)) for p in (row.get("ink") or []) if target_pixel(p)]
    copied["unexplained"] = [
        list(map(int, p)) for p in (row.get("unexplained") or []) if target_pixel(p)
    ]

    exact: list[dict[str, Any]] = []
    for match in row.get("exact") or []:
        pixels = [list(map(int, p)) for p in (match.get("pixels") or [])]
        if not pixels or not any(target_pixel(p) for p in pixels):
            continue
        copied_match = dict(match)
        copied_match["pixels"] = pixels
        exact.append(copied_match)
    copied["exact"] = exact
    return copied


def wrap_review_context(original: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def wrapped(
        row: dict[str, Any],
        group: set[tuple[int, int]],
        baseline: int,
        *,
        margin_y: int = 2,
        free_columns_x: int = 2,
    ) -> dict[str, Any]:
        return original(
            _filtered_target_row(row, group),
            group,
            baseline,
            margin_y=margin_y,
            free_columns_x=free_columns_x,
        )

    return wrapped


def wrap_jsonl_group_suggestions(original: Callable[..., list[str]]) -> Callable[..., list[str]]:
    def wrapped(row: dict[str, Any], groups: list[set[tuple[int, int]]]) -> list[str]:
        return original(_filtered_target_row(row), groups)

    return wrapped


def _decorate_neighbours(rows: list[dict[str, Any]]) -> None:
    rows.sort(key=lambda row: (float(row["center_y"]), int(row["page_top"])))
    for index, row in enumerate(rows):
        row["index"] = index
        previous = rows[index - 1] if index else None
        following = rows[index + 1] if index + 1 < len(rows) else None
        row["previous_center_y"] = previous["center_y"] if previous else None
        row["next_center_y"] = following["center_y"] if following else None
        row["previous_baseline_hint_y"] = previous.get("baseline_hint_y") if previous else None
        row["next_baseline_hint_y"] = following.get("baseline_hint_y") if following else None


def build_page_row_map(debug_dir: Path) -> dict[str, Any]:
    """Collect immutable physical-row geometry from all prepared OCR boxes."""
    by_column: dict[int, dict[tuple[int, int], dict[str, Any]]] = {}
    page: int | None = None
    for path in sorted(debug_dir.glob("saol14-word-debug-*.json")):
        debug = json.loads(path.read_text(encoding="utf-8"))
        if page is None and isinstance(debug.get("page"), int):
            page = int(debug["page"])
        context = debug.get("five_row_context") or {}
        try:
            column = int(context.get("column"))
        except (TypeError, ValueError):
            continue
        source_bands = context.get("source_bands") or []
        col = by_column.setdefault(column, {})
        for band in source_bands:
            try:
                top = int(band["page_top"])
                bottom = int(band["page_bottom"])
            except (KeyError, TypeError, ValueError):
                continue
            if bottom <= top:
                continue
            key = (top, bottom)
            item = col.setdefault(
                key,
                {
                    "source": "tesseract-row",
                    "page_top": top,
                    "page_bottom": bottom,
                    "center_y": (top + bottom - 1.0) / 2.0,
                    "baseline_hint_y": bottom - 1,
                    "texts": [],
                },
            )
            text = str(band.get("text") or "").strip()
            if text and text not in item["texts"]:
                item["texts"].append(text)

    columns: list[dict[str, Any]] = []
    for column in sorted(by_column):
        rows = list(by_column[column].values())
        _decorate_neighbours(rows)
        columns.append({"column": column, "rows": rows})

    tesseract_count = sum(len(column["rows"]) for column in columns)
    return {
        "format": "saol-page-row-map-v2",
        "page": page,
        "columns": columns,
        "row_count": tesseract_count,
        "tesseract_row_count": tesseract_count,
        "proposed_row_count": 0,
    }


def augment_page_row_map_with_lattice(
    page_image: Image.Image,
    row_map: dict[str, Any],
    *,
    threshold: int = 210,
) -> dict[str, Any]:
    """Insert conservative white-gap rows that full-page Tesseract missed."""
    from .ocr_row_lattice import row_lattice_for_column

    proposed_total = 0
    columns = row_map.get("columns") or []
    for column_entry in columns:
        column = int(column_entry["column"])
        left = column * page_image.width // 3
        right = (column + 1) * page_image.width // 3
        rows = list(column_entry.get("rows") or [])
        lattice = row_lattice_for_column(
            page_image,
            rows,
            left=left,
            right=right,
            threshold=threshold,
        )
        existing = {
            (int(row["page_top"]), int(row["page_bottom"]))
            for row in rows
            if "page_top" in row and "page_bottom" in row
        }
        for proposed in lattice.get("proposed_rows") or []:
            top = int(proposed["page_top"])
            bottom = int(proposed["page_bottom"])
            if (top, bottom) in existing:
                continue
            item = dict(proposed)
            item.setdefault("source", "white-gap-ink-island")
            item["baseline_hint_y"] = bottom - 1
            item["texts"] = []
            rows.append(item)
            existing.add((top, bottom))
            proposed_total += 1
        _decorate_neighbours(rows)
        column_entry["rows"] = rows
        column_entry["row_pitch"] = lattice.get("row_pitch")
        column_entry["hard_gap_count"] = lattice.get("hard_gap_count")

    row_map["format"] = "saol-page-row-map-v2"
    row_map["proposed_row_count"] = proposed_total
    row_map["row_count"] = sum(len(column.get("rows") or []) for column in columns)
    return row_map


def write_page_row_map(
    debug_dir: Path,
    destination: Path,
    *,
    page_image: Image.Image | None = None,
    threshold: int = 210,
) -> dict[str, Any]:
    row_map = build_page_row_map(debug_dir)
    if page_image is not None:
        augment_page_row_map_with_lattice(page_image, row_map, threshold=threshold)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(row_map, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return row_map
