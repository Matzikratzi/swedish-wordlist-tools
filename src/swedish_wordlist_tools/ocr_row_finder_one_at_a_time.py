from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ocr_left_edge_local_index import LocalExactHit
from .ocr_row_split_left_support import RowStartGeometry, row_start_is_typographically_plausible


@dataclass(frozen=True)
class FoundRowStart:
    x: int
    top_y: int
    bottom_y: int
    baseline: int
    label: str
    style: str
    steps: int


@dataclass(frozen=True)
class RowSearchWindow:
    previous_break_y: int
    limit_y: int


def search_window(previous_break_y: int, max_row_distance: int) -> RowSearchWindow:
    if max_row_distance < 0:
        raise ValueError("max_row_distance must be non-negative")
    return RowSearchWindow(previous_break_y, previous_break_y + max_row_distance)


def first_known_row_start(
    hits: Iterable[LocalExactHit],
    *,
    geometry: RowStartGeometry,
    previous_break_y: int,
    max_row_distance: int,
    min_steps: int = 3,
) -> FoundRowStart | None:
    """Establish exactly one next row from its first known start glyph.

    This is intentionally *not* a whole-column segmenter.  The caller supplies
    the previous accepted lower row boundary and receives at most one next row
    start/baseline.  A known exact glyph at a legal typographic start is enough
    to establish the row.  What happens farther right in the row is a separate
    recognition problem and may include unknown glyphs.

    Ordering is physical rather than confidence-first: earliest glyph top wins,
    then leftmost x, then the stronger fingerprint.  Thus an `a` at x=57 wins
    over a later `p` at x=65 on the same physical row.
    """
    window = search_window(previous_break_y, max_row_distance)
    legal: list[LocalExactHit] = []
    for hit in hits:
        top = hit.translate_y + hit.model.min_y
        if top < window.previous_break_y or top > window.limit_y:
            continue
        if hit.steps < min_steps:
            continue
        if not row_start_is_typographically_plausible(hit.translate_x, geometry):
            continue
        legal.append(hit)
    if not legal:
        return None
    legal.sort(
        key=lambda hit: (
            hit.translate_y + hit.model.min_y,
            hit.translate_x,
            -hit.steps,
            -len(hit.model.pixels),
            hit.model.label,
            hit.model.style,
        )
    )
    hit = legal[0]
    return FoundRowStart(
        x=hit.translate_x,
        top_y=hit.translate_y + hit.model.min_y,
        bottom_y=hit.translate_y + hit.model.max_y,
        baseline=hit.baseline,
        label=hit.model.label,
        style=hit.model.style,
        steps=hit.steps,
    )
