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
    """Find the first glyph by passively walking down from the row boundary.

    Nothing is born or killed while the observed pixels cannot correspond to a
    glyph origin in one of the allowed row-start x ranges. At the first raster y
    where such evidence exists, only glyphs whose *top visible model row* can
    explain those pixels are proposed. Every proposal is then verified against
    the complete page bitmap.
    """
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges or row_bottom <= row_top:
        return None, FirstGlyphSearch(y=None, candidates=())

    for page_y in range(row_top, row_bottom):
        observed_xs = tuple(black_by_y.get(page_y, ()))
        if not observed_xs:
            continue

        proposals: dict[tuple[int, int, int], BaselineMatch] = {}
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
            # We saw pixels, but none could place a glyph origin in the valid
            # start x ranges. Keep walking down without carrying live state.
            continue

        candidates = tuple(
            sorted(
                proposals.values(),
                key=lambda hit: (
                    hit.left,
                    -len(hit.pixels),
                    -hit.model.sources,
                    hit.model.label,
                    hit.model.style,
                ),
            )
        )
        left = min(hit.left for hit in candidates)
        left_group = tuple(hit for hit in candidates if hit.left == left)
        return _pick_unique_maximal(left_group), FirstGlyphSearch(
            y=page_y,
            candidates=left_group,
        )

    return None, FirstGlyphSearch(y=None, candidates=())
