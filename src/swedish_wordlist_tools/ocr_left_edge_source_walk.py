from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ocr_left_edge_index import IndexedGlyph, LeftEdgeIndex, exact_model_at
from .ocr_left_edge_signature_analysis import LeftEdgeSignature


@dataclass(frozen=True)
class SourceWalkHit:
    x: int
    y: int
    prefix: LeftEdgeSignature
    candidates: tuple[IndexedGlyph, ...]
    exact: tuple[IndexedGlyph, ...]
    skipped_top_rows: int = 0
    skipped_left_columns: int = 0


@dataclass(frozen=True)
class StableLeftContour:
    first_ink_y: int
    chosen_y: int
    chosen_x: int
    observations: tuple[tuple[int, int], ...]
    skipped_ink_rows: int


def stable_left_contour_start(
    black: set[tuple[int, int]],
    *,
    min_ink_rows: int = 4,
    min_later_rows: int = 3,
    min_left_shift: int = 4,
    x_tolerance: int = 2,
) -> StableLeftContour | None:
    """Estimate where the source's left edge becomes a stable local contour.

    We first collect leftmost x for consecutive ink-bearing raster rows starting
    at the first ink row.  The earliest rows may belong to a taller glyph farther
    right.  A later row becomes the preferred contour start when at least
    ``min_later_rows`` observations from there onward cluster within
    ``x_tolerance`` of that row's x and the original first-row x is at least
    ``min_left_shift`` pixels farther right.

    This is intentionally source geometry only: it does not identify a glyph and
    does not change OCR decisions by itself.
    """
    if min_ink_rows <= 0 or min_later_rows <= 0:
        raise ValueError("row counts must be positive")
    if min_left_shift < 0 or x_tolerance < 0:
        raise ValueError("pixel thresholds must be non-negative")
    if not black:
        return None

    by_y: dict[int, int] = {}
    for x, y in black:
        current = by_y.get(y)
        if current is None or x < current:
            by_y[y] = x
    observations = tuple(sorted(by_y.items()))
    if len(observations) < min_ink_rows:
        y, x = observations[0]
        return StableLeftContour(y, y, x, observations, 0)

    first_y, first_x = observations[0]
    chosen_index = 0
    for index, (_y, x) in enumerate(observations[1:], 1):
        later = observations[index:]
        clustered = sum(1 for _later_y, later_x in later if abs(later_x - x) <= x_tolerance)
        if clustered < min_later_rows:
            continue
        if first_x - x < min_left_shift:
            continue
        chosen_index = index
        break

    chosen_y, chosen_x = observations[chosen_index]
    return StableLeftContour(
        first_ink_y=first_y,
        chosen_y=chosen_y,
        chosen_x=chosen_x,
        observations=observations,
        skipped_ink_rows=chosen_index,
    )


def _next_values(candidates: Iterable[IndexedGlyph], depth: int) -> tuple[int | None, ...]:
    values = {
        glyph.signature[depth]
        for glyph in candidates
        if depth < len(glyph.signature)
    }
    return tuple(sorted(values, key=lambda value: (value is None, 0 if value is None else value)))


def _source_next_value(
    black: set[tuple[int, int]],
    candidates: tuple[IndexedGlyph, ...],
    *,
    x: int,
    y: int,
    depth: int,
) -> int | None | object:
    values = _next_values(candidates, depth)
    numeric = [value for value in values if value is not None]
    present = [value for value in numeric if (x + value, y + depth) in black]
    if present:
        return min(present)
    if None in values:
        return None
    return _NO_BRANCH


_NO_BRANCH = object()


def walk_prefixes_at(
    black: set[tuple[int, int]],
    index: LeftEdgeIndex,
    *,
    x: int,
    y: int,
    max_depth: int = 16,
) -> tuple[tuple[LeftEdgeSignature, tuple[IndexedGlyph, ...]], ...]:
    """Walk the glyph contour index using the source's actual left edge."""
    if max_depth <= 0:
        raise ValueError("max_depth must be positive")
    if (x, y) not in black:
        return ()

    candidates = index.candidates((0,))
    if not candidates:
        return ()

    prefix: LeftEdgeSignature = (0,)
    finished: list[tuple[LeftEdgeSignature, tuple[IndexedGlyph, ...]]] = []

    for depth in range(1, max_depth):
        completed = tuple(glyph for glyph in candidates if len(glyph.signature) == depth)
        if completed:
            finished.append((prefix, completed))

        value = _source_next_value(black, candidates, x=x, y=y, depth=depth)
        if value is _NO_BRANCH:
            break
        prefix = prefix + (value,)  # type: ignore[operator]
        candidates = index.candidates(prefix)
        if not candidates:
            break
    else:
        completed = tuple(glyph for glyph in candidates if len(glyph.signature) <= max_depth)
        if completed:
            finished.append((prefix, completed))

    if candidates and not any(existing_prefix == prefix for existing_prefix, _ in finished):
        finished.append((prefix, candidates))

    return tuple(finished)


def source_walk_hits(
    black: set[tuple[int, int]],
    index: LeftEdgeIndex,
    *,
    max_x: int | None = None,
    max_depth: int = 16,
    min_y: int | None = None,
    only_y: int | None = None,
    only_x: int | None = None,
    skipped_top_rows: int = 0,
    skipped_left_columns: int = 0,
) -> tuple[SourceWalkHit, ...]:
    """Find exact glyphs through source-driven contour walks, without baseline."""
    hits: list[SourceWalkHit] = []
    for x, y in sorted(black, key=lambda point: (point[0], point[1])):
        if max_x is not None and x > max_x:
            continue
        if min_y is not None and y < min_y:
            continue
        if only_y is not None and y != only_y:
            continue
        if only_x is not None and x != only_x:
            continue
        for prefix, candidates in walk_prefixes_at(
            black,
            index,
            x=x,
            y=y,
            max_depth=max_depth,
        ):
            exact = tuple(
                glyph for glyph in candidates if exact_model_at(black, glyph, x=x, y=y)
            )
            if exact:
                hits.append(
                    SourceWalkHit(
                        x=x,
                        y=y,
                        prefix=prefix,
                        candidates=candidates,
                        exact=exact,
                        skipped_top_rows=skipped_top_rows,
                        skipped_left_columns=skipped_left_columns,
                    )
                )
    return tuple(hits)


def source_walk_hits_with_top_retry(
    black: set[tuple[int, int]],
    index: LeftEdgeIndex,
    *,
    max_x: int | None = None,
    max_depth: int = 16,
    max_skip_rows: int = 8,
    only_x: int | None = None,
    skipped_left_columns: int = 0,
) -> tuple[SourceWalkHit, ...]:
    """Retry from the current top ink row, then discard that row if it fails."""
    if max_skip_rows < 0:
        raise ValueError("max_skip_rows must be non-negative")
    if not black:
        return ()

    relevant = black if only_x is None else {(x, y) for x, y in black if x == only_x}
    if not relevant:
        return ()
    top = min(y for _x, y in relevant)
    bottom = max(y for _x, y in relevant)
    for skipped in range(max_skip_rows + 1):
        current_y = top + skipped
        if current_y > bottom:
            break
        if not any(y == current_y for _x, y in relevant):
            continue
        hits = source_walk_hits(
            black,
            index,
            max_x=max_x,
            max_depth=max_depth,
            only_y=current_y,
            only_x=only_x,
            skipped_top_rows=skipped,
            skipped_left_columns=skipped_left_columns,
        )
        if hits:
            return hits
    return ()


def is_strong_anchor(hit: SourceWalkHit) -> bool:
    """Return whether a hit is substantial enough to stop horizontal resync.

    Tiny one-row punctuation rasters such as '-' and '.' are exact matches very
    often inside unrelated source ink.  They are useful observations but poor
    synchronization anchors.  For this diagnostic experiment a strong anchor
    must have a contour of at least three raster rows and at least eight pixels
    in one fully verified glyph model.
    """
    if len(hit.prefix) < 3:
        return False
    return any(len(glyph.model.pixels) >= 8 for glyph in hit.exact)


def source_walk_hits_with_resync(
    black: set[tuple[int, int]],
    index: LeftEdgeIndex,
    *,
    max_x: int | None = None,
    max_depth: int = 16,
    max_skip_rows: int = 8,
) -> tuple[SourceWalkHit, ...]:
    """Search left-to-right until a strong exact glyph anchor is found.

    A leading glyph may be absent from facit, and tiny punctuation rasters may
    occur accidentally inside its pixels.  Therefore each occupied source column
    is tried in order, but weak exact hits do not stop resynchronization.  The
    first column containing at least one strong anchor wins.  If no strong anchor
    exists before ``max_x``, the earliest weak exact hit is returned as a fallback
    so diagnostics still show what was seen.
    """
    if not black:
        return ()
    left = min(x for x, _y in black)
    columns = sorted({x for x, _y in black if max_x is None or x <= max_x})
    weak_fallback: tuple[SourceWalkHit, ...] = ()
    for x in columns:
        hits = source_walk_hits_with_top_retry(
            black,
            index,
            max_x=max_x,
            max_depth=max_depth,
            max_skip_rows=max_skip_rows,
            only_x=x,
            skipped_left_columns=x - left,
        )
        if not hits:
            continue
        strong = tuple(hit for hit in hits if is_strong_anchor(hit))
        if strong:
            return strong
        if not weak_fallback:
            weak_fallback = hits
    return weak_fallback
