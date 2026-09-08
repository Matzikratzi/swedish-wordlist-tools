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
    source: str = "fingerprint"


def _first_fallback_start(
    starts: Iterable[FoundRowStart],
    *,
    search_y: int,
    limit_y: int,
    minimum_baseline: int | None,
) -> FoundRowStart | None:
    legal = [
        start
        for start in starts
        if search_y <= start.top_y <= limit_y
        and (minimum_baseline is None or start.baseline >= minimum_baseline)
    ]
    if not legal:
        return None
    legal.sort(key=lambda start: (start.top_y, start.x, -start.steps, start.label, start.style))
    return legal[0]


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
    fallback_starts: Iterable[FoundRowStart] = (),
) -> tuple[ShadowRow, ...]:
    """Walk a column top-to-bottom without pre-segmented row boxes.

    The ordinary path establishes a row from a known exact glyph with a strong
    left-edge fingerprint at a legal typographic start.  If that path has no
    candidate in the current physical search window, an independently
    full-raster-verified mature-prefix start may establish the row instead.
    This keeps shallow starts such as ``~e`` out of the normal min-steps logic.
    """
    if end_y < start_y:
        raise ValueError("end_y must be >= start_y")
    if vertical_slack < 0:
        raise ValueError("vertical_slack must be non-negative")
    if min_baseline_delta <= 0:
        raise ValueError("min_baseline_delta must be positive")
    tuple(models)  # keep API stable; no global facit extent is used
    remaining = tuple(hits)
    fallback = tuple(fallback_starts)
    out: list[ShadowRow] = []
    search_y = int(start_y)
    previous_baseline: int | None = None
    index = 0
    while search_y <= end_y:
        minimum_baseline = None if previous_baseline is None else previous_baseline + min_baseline_delta
        eligible = remaining
        if minimum_baseline is not None:
            eligible = tuple(hit for hit in remaining if hit.baseline >= minimum_baseline)
        found = first_known_row_start(
            eligible,
            geometry=geometry,
            previous_break_y=search_y,
            max_row_distance=max_row_distance,
            min_steps=min_steps,
        )
        source = "fingerprint"
        if found is None:
            found = _first_fallback_start(
                fallback,
                search_y=search_y,
                limit_y=search_y + max_row_distance,
                minimum_baseline=minimum_baseline,
            )
            source = "mature-prefix"
        if found is None or found.top_y > end_y:
            break
        next_y = max(search_y + 1, found.bottom_y + 1 + vertical_slack)
        out.append(
            ShadowRow(
                index=index,
                start=found,
                search_from_y=search_y,
                next_search_y=next_y,
                source=source,
            )
        )
        index += 1
        previous_baseline = found.baseline
        search_y = next_y
    return tuple(out)
