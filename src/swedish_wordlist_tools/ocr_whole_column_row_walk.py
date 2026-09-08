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
) -> tuple[ShadowRow, ...]:
    """Walk a column top-to-bottom without pre-segmented row boxes.

    A row is established by the first exact known glyph at a legal typographic
    start. The next search begins just below the *actual raster extent of that
    establishing glyph*, not below the tallest glyph in the facit and not merely
    one pixel below its top. This suppresses same-row accent/punctuation hits
    whose alternate model placement implies a slightly lower fake baseline,
    while avoiding the old mistake where a globally deep glyph could skip a
    genuine following row.
    """
    if end_y < start_y:
        raise ValueError("end_y must be >= start_y")
    if vertical_slack < 0:
        raise ValueError("vertical_slack must be non-negative")
    tuple(models)  # keep API stable; no global facit extent is used
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
        next_y = max(
            search_y + 1,
            found.bottom_y + 1 + vertical_slack,
        )
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
