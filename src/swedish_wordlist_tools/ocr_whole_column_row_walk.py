from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

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


FallbackProvider = Callable[[int, int], Iterable[FoundRowStart]]


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
    fallback_provider: FallbackProvider | None = None,
) -> tuple[ShadowRow, ...]:
    """Walk a column top-to-bottom without pre-segmented row boxes.

    Ordinary strong fingerprint starts and independently full-raster-verified
    mature-prefix starts compete in physical top-to-bottom order. A prefix start
    is therefore allowed to establish a real row before a later ordinary start;
    this is required for shallow starts such as ``~e``.

    ``fallback_provider`` is evaluated only for the current search window and,
    when an ordinary start exists, only up to that start's top y. This avoids a
    whole-column mature-prefix scan while preserving physical ordering.
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
        ordinary = first_known_row_start(
            eligible,
            geometry=geometry,
            previous_break_y=search_y,
            max_row_distance=max_row_distance,
            min_steps=min_steps,
        )
        window_limit = min(end_y, search_y + max_row_distance)
        prefix_limit = window_limit if ordinary is None else min(window_limit, ordinary.top_y)
        prefix_candidates: Iterable[FoundRowStart] = fallback
        if fallback_provider is not None:
            prefix_candidates = tuple(fallback_provider(search_y, prefix_limit))
        prefix = _first_fallback_start(
            prefix_candidates,
            search_y=search_y,
            limit_y=prefix_limit,
            minimum_baseline=minimum_baseline,
        )

        if prefix is not None and (ordinary is None or prefix.top_y < ordinary.top_y):
            found = prefix
            source = "mature-prefix"
        else:
            found = ordinary
            source = "fingerprint"
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
