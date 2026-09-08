from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel
from .ocr_left_edge_local_index import LocalExactHit
from .ocr_row_finder_one_at_a_time import FoundRowStart, first_known_row_start
from .ocr_row_split_left_support import RowStartGeometry


@dataclass(frozen=True)
class ShadowRow:
    index: int
    start: FoundRowStart
    search_from_y: int
    next_search_y: int


def model_vertical_extent(models: Iterable[GlyphModel]) -> tuple[int, int]:
    pixels = [(x, y) for model in models for x, y in model.pixels]
    if not pixels:
        raise ValueError("no model pixels")
    ys = [y for _x, y in pixels]
    return min(ys), max(ys)


def walk_row_starts(
    hits: Iterable[LocalExactHit],
    *,
    models: Iterable[GlyphModel],
    geometry: RowStartGeometry,
    start_y: int,
    end_y: int,
    max_row_distance: int = 24,
    min_steps: int = 3,
    vertical_slack: int = 1,
) -> tuple[ShadowRow, ...]:
    """Walk a column strictly top-to-bottom, establishing one row at a time.

    No pre-segmented row boxes participate. A row is established by the first
    exact known glyph at a legal typographic start. Once its baseline is known,
    the next search begins below the maximum facit raster extent for that
    baseline (plus a tiny explicit slack). Unknown glyphs inside that band do
    not prevent the row from being established.
    """
    if end_y < start_y:
        raise ValueError("end_y must be >= start_y")
    if vertical_slack < 0:
        raise ValueError("vertical_slack must be non-negative")
    model_rows = tuple(models)
    _min_rel_y, max_rel_y = model_vertical_extent(model_rows)
    hit_rows = tuple(hits)
    out: list[ShadowRow] = []
    search_y = int(start_y)
    index = 0
    while search_y <= end_y:
        found = first_known_row_start(
            hit_rows,
            geometry=geometry,
            previous_break_y=search_y,
            max_row_distance=max_row_distance,
            min_steps=min_steps,
        )
        if found is None or found.top_y > end_y:
            break
        next_y = max(search_y + 1, found.baseline + max_rel_y + 1 + vertical_slack)
        out.append(ShadowRow(index=index, start=found, search_from_y=search_y, next_search_y=next_y))
        index += 1
        search_y = next_y
    return tuple(out)
