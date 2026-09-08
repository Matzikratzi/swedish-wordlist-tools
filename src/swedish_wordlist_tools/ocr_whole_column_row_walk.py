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
    min_baseline_delta: int = 8,
) -> tuple[ShadowRow, ...]:
    """Walk a column top-to-bottom without pre-segmented row boxes.

    A row is established by the first exact known glyph at a legal typographic
    start. The next search begins just below the actual raster extent of that
    establishing glyph. In addition, a following row must have a baseline at
    least ``min_baseline_delta`` pixels lower than the previous accepted row.
    This rejects alternate punctuation/accent placements a few pixels below the
    same physical row while remaining well below the observed SAOL line pitch.
    """
    if end_y < start_y:
        raise ValueError("end_y must be >= start_y")
    if vertical_slack < 0:
        raise ValueError("vertical_slack must be non-negative")
    if min_baseline_delta <= 0:
        raise ValueError("min_baseline_delta must be positive")
    tuple(models)  # keep API stable; no global facit extent is used
    remaining = tuple(hits)
    out: list[ShadowRow] = []
    search_y = int(start_y)
    previous_baseline: int | None = None
    index = 0
    while search_y <= end_y:
        eligible = remaining
        if previous_baseline is not None:
            minimum_baseline = previous_baseline + min_baseline_delta
            eligible = tuple(hit for hit in remaining if hit.baseline >= minimum_baseline)
        found = first_known_row_start(
            eligible,
            geometry=geometry,
            previous_break_y=search_y,
            max_row_distance=max_row_distance,
            min_steps=min_steps,
        )
        if found is None or found.top_y > end_y:
            break
        next_y = max(search_y + 1, found.bottom_y + 1 + vertical_slack)
        out.append(
            ShadowRow(
                index=index,
                start=found,
                search_from_y=search_y,
                next_search_y=next_y,
            )
        )
        index += 1
        previous_baseline = found.baseline
        search_y = next_y
    return tuple(out)
