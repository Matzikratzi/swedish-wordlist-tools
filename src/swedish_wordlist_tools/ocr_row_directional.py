from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_baseline_up import BaselineMatch, CompiledGlyph, CompiledGlyphLibrary, Pixel


TranslateXRange = tuple[int, int]


@dataclass(frozen=True)
class FirstGlyphSearch:
    y: int | None
    candidates: tuple[BaselineMatch, ...]


def _tx_allowed(tx: int, ranges: tuple[TranslateXRange, ...]) -> bool:
    return any(lo <= tx <= hi for lo, hi in ranges)


def _placed_pixels(item: CompiledGlyph, *, tx: int, baseline: int) -> frozenset[Pixel]:
    return frozenset((tx + x, baseline + y) for x, y in item.model.pixels)


def _pick_unique_maximal(candidates: Iterable[BaselineMatch]) -> BaselineMatch | None:
    rows = list(candidates)
    if not rows:
        return None
    maximal = [
        hit
        for hit in rows
        if not any(hit.pixels < other.pixels for other in rows if other is not hit)
    ]
    distinct = {hit.pixels for hit in maximal}
    if len(distinct) != 1:
        return None
    target = next(iter(distinct))
    equivalent = [hit for hit in maximal if hit.pixels == target]
    return max(equivalent, key=lambda hit: (len(hit.pixels), hit.model.sources))


def first_glyph_top_down(
    black: set[Pixel],
    black_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    *,
    row_top: int,
    row_bottom: int,
    allowed_translate_x_ranges: Iterable[TranslateXRange],
) -> tuple[BaselineMatch | None, FirstGlyphSearch]:
    """Find the textual first glyph while scanning passively top-down.

    A later textual glyph may have an ascender and therefore be the first glyph
    that becomes visible when the raster is scanned from the row boundary.  We
    must not commit to that first *visible* glyph.  Instead we stay stateless,
    collect exact row-start candidates as their own first visible rows are
    encountered, and only after the short row span has been inspected choose
    the physically leftmost valid glyph.

    Nothing is born or killed while observed pixels cannot correspond to a
    glyph origin in one of the allowed row-start x ranges.  A proposal is made
    only from an actual pixel on the model's top visible raster row, and every
    proposal is verified against the complete page bitmap.
    """
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges or row_bottom <= row_top:
        return None, FirstGlyphSearch(y=None, candidates=())

    proposals: dict[tuple[int, int, int], BaselineMatch] = {}

    for page_y in range(row_top, row_bottom):
        observed_xs = tuple(black_by_y.get(page_y, ()))
        if not observed_xs:
            continue

        for item in library.models:
            top_rel_y = item.model.min_y
            top_row = item.rows[top_rel_y]
            baseline = page_y - top_rel_y
            for observed_x in observed_xs:
                for model_x in top_row:
                    tx = observed_x - model_x
                    if not _tx_allowed(tx, ranges):
                        continue
                    key = (id(item.model), tx, baseline)
                    if key in proposals:
                        continue
                    placed = _placed_pixels(item, tx=tx, baseline=baseline)
                    if not placed.issubset(black):
                        continue

                    # This candidate says page_y is its first visible raster
                    # row. Reject it when the immediately preceding row already
                    # contains ink inside the candidate's physical x span.
                    physical_left = tx + item.min_x
                    physical_right = tx + item.max_x
                    previous = black_by_y.get(page_y - 1, ())
                    if any(physical_left <= x <= physical_right for x in previous):
                        continue

                    proposals[key] = BaselineMatch(
                        model=item.model,
                        tx=tx,
                        baseline=baseline,
                        pixels=placed,
                        discovered_y=page_y,
                    )

    if not proposals:
        return None, FirstGlyphSearch(y=None, candidates=())

    candidates = tuple(
        sorted(
            proposals.values(),
            key=lambda hit: (
                hit.left,
                hit.discovered_y,
                -len(hit.pixels),
                -hit.model.sources,
                hit.model.label,
                hit.model.style,
            ),
        )
    )
    left = min(hit.left for hit in candidates)
    left_group = tuple(hit for hit in candidates if hit.left == left)
    first_y = min(hit.discovered_y for hit in left_group)
    return _pick_unique_maximal(left_group), FirstGlyphSearch(
        y=first_y,
        candidates=left_group,
    )
