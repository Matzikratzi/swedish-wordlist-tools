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


def _next_values(candidates: Iterable[IndexedGlyph], depth: int) -> tuple[int | None, ...]:
    values = {
        glyph.signature[depth]
        for glyph in candidates
        if depth < len(glyph.signature)
    }
    return tuple(sorted(values, key=lambda value: (value is None, 0 if value is None else value)))


def walk_prefixes_at(
    black: set[tuple[int, int]],
    index: LeftEdgeIndex,
    *,
    x: int,
    y: int,
    max_depth: int = 16,
) -> tuple[tuple[LeftEdgeSignature, tuple[IndexedGlyph, ...]], ...]:
    """Walk the glyph contour trie using source pixels instead of a known baseline.

    ``(x, y)`` is treated as the top row's leftmost glyph pixel, so depth 1 is
    always the normalized prefix ``(0,)``.  At each following depth we only try
    left-edge offsets that actually occur among the surviving glyph candidates.
    A numeric offset survives when the corresponding source pixel is black.
    ``None`` survives as the explicit empty-row branch.

    This deliberately allows several branches to survive.  Source pixels from a
    neighbouring glyph can accidentally satisfy one branch; callers therefore
    still perform full exact raster verification before accepting a glyph.
    """
    if max_depth <= 0:
        raise ValueError("max_depth must be positive")
    if (x, y) not in black:
        return ()

    initial = index.candidates((0,))
    if not initial:
        return ()
    states: list[tuple[LeftEdgeSignature, tuple[IndexedGlyph, ...]]] = [((0,), initial)]
    finished: list[tuple[LeftEdgeSignature, tuple[IndexedGlyph, ...]]] = []

    for depth in range(1, max_depth):
        next_states: list[tuple[LeftEdgeSignature, tuple[IndexedGlyph, ...]]] = []
        for prefix, candidates in states:
            # Candidates whose contour ends at the current depth are complete
            # prefix leaves; retain them while taller candidates continue.
            completed = tuple(g for g in candidates if len(g.signature) == depth)
            if completed:
                finished.append((prefix, completed))

            for value in _next_values(candidates, depth):
                if value is not None and (x + value, y + depth) not in black:
                    continue
                extended = prefix + (value,)
                narrowed = index.candidates(extended)
                if narrowed:
                    next_states.append((extended, narrowed))
        if not next_states:
            break
        states = next_states

    finished.extend(states)

    # Deduplicate identical prefix/candidate states while preserving traversal
    # order, which is useful in human-readable diagnostics.
    seen: set[tuple[LeftEdgeSignature, tuple[int, ...]]] = set()
    unique: list[tuple[LeftEdgeSignature, tuple[IndexedGlyph, ...]]] = []
    for prefix, candidates in finished:
        key = (prefix, tuple(id(glyph) for glyph in candidates))
        if key in seen:
            continue
        seen.add(key)
        unique.append((prefix, candidates))
    return tuple(unique)


def source_walk_hits(
    black: set[tuple[int, int]],
    index: LeftEdgeIndex,
    *,
    max_x: int | None = None,
    max_depth: int = 16,
) -> tuple[SourceWalkHit, ...]:
    """Find exact glyphs through source-driven contour-prefix walks.

    Possible starts are source pixels ordered left-to-right then top-to-bottom.
    The contour index narrows candidates before full exact raster verification;
    no baseline is needed to discover a hit.
    """
    hits: list[SourceWalkHit] = []
    for x, y in sorted(black, key=lambda point: (point[0], point[1])):
        if max_x is not None and x > max_x:
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
                hits.append(SourceWalkHit(x, y, prefix, candidates, exact))
    return tuple(hits)
