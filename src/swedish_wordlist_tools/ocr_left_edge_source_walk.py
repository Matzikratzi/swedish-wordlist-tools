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


def source_walk_hits_with_resync(
    black: set[tuple[int, int]],
    index: LeftEdgeIndex,
    *,
    max_x: int | None = None,
    max_depth: int = 16,
    max_skip_rows: int = 8,
) -> tuple[SourceWalkHit, ...]:
    """Search left-to-right, skipping an unrecognized leading glyph if necessary.

    Each occupied source column is treated as a possible glyph-start column.  At
    that x we apply the top-row retry.  If no complete facit glyph verifies, move
    right to the next occupied column.  This lets OCR regain synchronization when
    a leading glyph is genuinely absent from the current facit.

    Full-raster verification always uses the complete original source set, so
    moving the proposed start boundary never deletes pixels from a candidate.
    """
    if not black:
        return ()
    left = min(x for x, _y in black)
    columns = sorted({x for x, _y in black if max_x is None or x <= max_x})
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
        if hits:
            return hits
    return ()
