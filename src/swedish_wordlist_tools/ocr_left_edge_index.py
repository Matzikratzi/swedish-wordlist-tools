from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .ocr_glyph_matcher import GlyphModel
from .ocr_left_edge_signature_analysis import LeftEdgeSignature, left_edge_signature


@dataclass(frozen=True)
class IndexedGlyph:
    model: GlyphModel
    signature: LeftEdgeSignature
    anchor_x: int
    anchor_y: int
    variant: str = "full"

    @property
    def top_left_x(self) -> int:
        """Backward-compatible name for the signature anchor x."""
        return self.anchor_x


def _row_left(model: GlyphModel, y: int) -> int:
    return min(x for x, py in model.pixels if py == y)


def _signature_from_row(model: GlyphModel, start_y: int) -> LeftEdgeSignature:
    """Return the contour fingerprint beginning at one occupied model row."""
    first_left = _row_left(model, start_y)
    by_y: dict[int, int] = {}
    for x, y in model.pixels:
        if y < start_y:
            continue
        previous = by_y.get(y)
        if previous is None or x < previous:
            by_y[y] = x
    return tuple(
        None if y not in by_y else by_y[y] - first_left
        for y in range(start_y, model.max_y + 1)
    )


def _fingerprints(model: GlyphModel) -> tuple[IndexedGlyph, ...]:
    """Build the normal contour plus restart contours after internal white gaps.

    A later tall glyph can put source ink into a raster row where a short/narrow
    glyph has an internal completely white row.  The normal top-down contour can
    then be contaminated.  For exact digital material we can safely add another
    fingerprint beginning at the first occupied row after each such internal
    white run.  The full glyph raster is still verified before accepting a hit.
    """
    if not model.pixels:
        return ()

    occupied = {y for _x, y in model.pixels}
    starts = [model.min_y]
    in_gap = False
    for y in range(model.min_y + 1, model.max_y + 1):
        if y not in occupied:
            in_gap = True
            continue
        if in_gap:
            starts.append(y)
            in_gap = False

    out: list[IndexedGlyph] = []
    for index, start_y in enumerate(starts):
        signature = left_edge_signature(model) if index == 0 else _signature_from_row(model, start_y)
        out.append(
            IndexedGlyph(
                model=model,
                signature=signature,
                anchor_x=_row_left(model, start_y),
                anchor_y=start_y,
                variant="full" if index == 0 else f"after-gap-{start_y}",
            )
        )
    return tuple(out)


class LeftEdgeIndex:
    """Prefix index for exact digital glyph left contours.

    A model may have several fingerprints.  The primary one begins at its topmost
    ink.  Additional fingerprints may begin after internal all-white raster gaps.
    They are candidate-entry points only: callers must verify the complete glyph
    raster against source pixels before accepting a match.
    """

    def __init__(self, models: Iterable[GlyphModel]):
        self.glyphs = tuple(
            glyph
            for model in models
            for glyph in _fingerprints(model)
        )
        buckets: dict[LeftEdgeSignature, list[IndexedGlyph]] = defaultdict(list)
        for glyph in self.glyphs:
            for depth in range(1, len(glyph.signature) + 1):
                buckets[glyph.signature[:depth]].append(glyph)
        self._prefix = {key: tuple(value) for key, value in buckets.items()}

    def candidates(self, signature: LeftEdgeSignature) -> tuple[IndexedGlyph, ...]:
        return self._prefix.get(signature, ())


def source_left_signature(
    black: set[tuple[int, int]],
    *,
    x: int,
    y: int,
    depth: int,
) -> LeftEdgeSignature:
    """Read a normalized left contour downward from one proposed anchor pixel."""
    if depth <= 0:
        raise ValueError("depth must be positive")
    out: list[int | None] = []
    for yy in range(y, y + depth):
        xs = [xx for xx, py in black if py == yy and xx >= x]
        out.append(None if not xs else min(xs) - x)
    return tuple(out)


def exact_model_at(
    black: set[tuple[int, int]],
    indexed: IndexedGlyph,
    *,
    x: int,
    y: int,
) -> bool:
    """Verify the complete glyph raster from any indexed contour anchor."""
    model = indexed.model
    dx = x - indexed.anchor_x
    dy = y - indexed.anchor_y
    return all((px + dx, py + dy) in black for px, py in model.pixels)


def derived_baseline(indexed: IndexedGlyph, *, source_top_y: int) -> int:
    """Return source y coordinate of the model's support baseline."""
    return source_top_y - indexed.anchor_y
