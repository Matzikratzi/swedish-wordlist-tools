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
    """Walk a column top-to-bottom without pre-segmented row boxes.

    The baseline is the row identity. After establishing a row, all exact hits
    on that same (or an earlier) baseline are excluded from the next search.
    This is stronger than advancing by the tallest glyph in the whole facit:
    a rare deep glyph can no longer make us jump across the following row.

    ``models`` and ``vertical_slack`` remain accepted for experiment/API
    compatibility; row advancement deliberately does not use global facit
    height anymore.
    """
    if end_y < start_y:
        raise ValueError("end_y must be >= start_y")
    if vertical_slack < 0:
        raise ValueError("vertical_slack must be non-negative")
    tuple(models)  # validate/consume callers that supply generators; no global extent used
    remaining = tuple(hits)
    out: list[ShadowRow] = []
    search_y = int(start_y)
    previous_baseline: int | None = None
    index = 0
    while search_y <= end_y:
        eligible = remaining
        if previous_baseline is not None:
            eligible = tuple(hit for hit in remaining if hit.baseline > previous_baseline)
        found = first_known_row_start(
            eligible,
            geometry=geometry,
            previous_break_y=search_y,
            max_row_distance=max_row_distance,
            min_steps=min_steps,
        )
        if found is None or found.top_y > end_y:
            break
        # Move only past the establishing glyph's top. Same-row placements are
        # rejected by baseline on the next iteration, while a following row's
        # high ascender/diacritic remains visible even if it starts unusually early.
        next_y = max(search_y + 1, found.top_y + 1)
        out.append(ShadowRow(index=index, start=found, search_from_y=search_y, next_search_y=next_y))
        index += 1
        previous_baseline = found.baseline
        search_y = next_y
    return tuple(out)
