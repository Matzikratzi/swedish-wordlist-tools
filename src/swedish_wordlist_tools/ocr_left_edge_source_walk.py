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
    """Return the actual source left edge among offsets the candidates permit.

    A glyph may extend left of its top-row leftmost pixel, so we cannot simply
    scan x..right.  Instead we ask the surviving glyph models which offsets are
    geometrically possible at this depth and choose the leftmost such source
    pixel that is actually black.

    ``None`` is returned only when an explicit empty-row branch exists and none
    of the permitted numeric offsets contains source ink.  ``_NO_BRANCH`` means
    the source cannot continue any surviving contour branch.
    """
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
    """Walk the glyph contour index using the source's actual left edge.

    ``(x, y)`` is treated as the top row's leftmost glyph pixel, so depth 1 is
    ``(0,)``.  At every later raster row the surviving models define the offsets
    that could belong to this glyph.  If several such source pixels are black we
    take the leftmost one; pixels farther right can belong to later glyphs and do
    not create parallel contour branches.

    Completed shorter glyph contours are retained before attempting deeper rows.
    That matters when the following glyph is taller and contributes ink above or
    below a low first glyph.  Full raster verification is still mandatory.
    """
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

    # If traversal stopped exactly on a still-live state, retain it as a useful
    # diagnostic prefix as well.
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
    skipped_top_rows: int = 0,
) -> tuple[SourceWalkHit, ...]:
    """Find exact glyphs through source-driven contour walks, without baseline."""
    hits: list[SourceWalkHit] = []
    for x, y in sorted(black, key=lambda point: (point[0], point[1])):
        if max_x is not None and x > max_x:
            continue
        if min_y is not None and y < min_y:
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
) -> tuple[SourceWalkHit, ...]:
    """Retry after progressively ignoring top source rows until an exact hit exists.

    This handles a low/narrow first glyph followed by a taller glyph.  The taller
    following glyph may contribute the topmost ink in the search area, so a scan
    started at that raster height can describe the wrong glyph.  If no exact
    glyph verifies, ignore one more top raster row and retry.  The first skip
    level that yields exact hits wins.

    No source pixels are modified; ``min_y`` only changes which pixels may act as
    proposed glyph starts.  Exact verification still uses the complete original
    raster.
    """
    if max_skip_rows < 0:
        raise ValueError("max_skip_rows must be non-negative")
    if not black:
        return ()

    top = min(y for _x, y in black)
    for skipped in range(max_skip_rows + 1):
        hits = source_walk_hits(
            black,
            index,
            max_x=max_x,
            max_depth=max_depth,
            min_y=top + skipped,
            skipped_top_rows=skipped,
        )
        if hits:
            return hits
    return ()
