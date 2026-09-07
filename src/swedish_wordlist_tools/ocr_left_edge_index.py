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
    top_left_x: int


def _top_left_x(model: GlyphModel) -> int:
    top = model.min_y
    return min(x for x, y in model.pixels if y == top)


class LeftEdgeIndex:
    """Prefix index for exact digital glyph left contours.

    The index is deliberately only a candidate filter.  Callers must verify the
    complete glyph raster against source pixels before accepting a match.
    """

    def __init__(self, models: Iterable[GlyphModel]):
        self.glyphs = tuple(
            IndexedGlyph(model, left_edge_signature(model), _top_left_x(model))
            for model in models
            if model.pixels
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
    """Read a normalized left contour downward from one proposed top-left pixel.

    ``(x, y)`` is the topmost row's leftmost pixel and therefore defines zero.
    Empty source rows are preserved as None.  This mirrors glyph signatures and
    assumes exact digital raster data rather than noisy scanned input.
    """
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
    """Verify every glyph pixel exactly at a proposed top-left source point."""
    model = indexed.model
    dx = x - indexed.top_left_x
    dy = y - model.min_y
    return all((px + dx, py + dy) in black for px, py in model.pixels)


def derived_baseline(indexed: IndexedGlyph, *, source_top_y: int) -> int:
    """Return source y coordinate of the model's support baseline."""
    return source_top_y - indexed.model.min_y
