from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_baseline_up import BaselineMatch, CompiledGlyph, CompiledGlyphLibrary, Pixel
from .ocr_column_left_profile import ColumnLeftProfile


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
    left_profile: ColumnLeftProfile | None = None,
) -> tuple[BaselineMatch | None, FirstGlyphSearch]:
    """Find the textual first glyph while scanning passively top-down.

    With a prebuilt whole-column left profile, only the one leftmost page x for
    each nonblank raster row is used to *propose* placements.  Candidates are
    still verified against the complete 2D black-pixel set.  This keeps the
    profile as the cheap page-wide directional signal while exact pixels remain
    authoritative.

    A later textual glyph may have an ascender and therefore be the first glyph
    that becomes visible when the raster is scanned from the row boundary.  We
    therefore collect exact row-start candidates over the short row span and
    choose the physically leftmost valid glyph only after all relevant y rows
    have had a chance to contribute.
    """
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges or row_bottom <= row_top:
        return None, FirstGlyphSearch(y=None, candidates=())

    proposals: dict[tuple[int, int, int], BaselineMatch] = {}
    if left_profile is None:
        scan_y: Iterable[int] = range(row_top, row_bottom)
    else:
        scan_y = left_profile.nonblank_y(row_top, row_bottom)

    for page_y in scan_y:
        if left_profile is None:
            observed_xs = tuple(black_by_y.get(page_y, ()))
        else:
            left_x = left_profile.at(page_y)
            observed_xs = () if left_x is None else (left_x,)
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
