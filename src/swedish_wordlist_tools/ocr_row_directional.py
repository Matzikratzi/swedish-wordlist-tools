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
    row_bottom: int | None = None,
    allowed_translate_x_ranges: Iterable[TranslateXRange],
    left_profile: ColumnLeftProfile | None = None,
) -> tuple[BaselineMatch | None, FirstGlyphSearch]:
    """Find the first glyph from the known upper row boundary.

    ``row_top`` is the only required row boundary.  With a whole-column left
    profile we walk downward from it until the profile can actually seed an
    exact glyph placement whose x translation belongs to a known row-start
    interval.  The glyph itself determines how far downward verification must
    look; a pre-known lower text-row boundary is therefore not required.

    ``row_bottom`` remains as an optional compatibility/search limit for older
    callers and focused tests.  New sequential page OCR should leave it unset.
    """
    ranges = tuple((int(lo), int(hi)) for lo, hi in allowed_translate_x_ranges)
    if not ranges:
        return None, FirstGlyphSearch(y=None, candidates=())

    if row_bottom is None:
        if left_profile is not None:
            scan_bottom = left_profile.bottom
        elif black_by_y:
            scan_bottom = max(black_by_y) + 1
        else:
            return None, FirstGlyphSearch(y=None, candidates=())
    else:
        scan_bottom = int(row_bottom)
    if scan_bottom <= row_top:
        return None, FirstGlyphSearch(y=None, candidates=())

    if left_profile is None:
        scan_y: Iterable[int] = range(row_top, scan_bottom)
    else:
        scan_y = left_profile.nonblank_y(row_top, scan_bottom)

    # The first profile raster row that can seed any exact row-start glyph owns
    # the start event.  We do not continue into later text rows looking for a
    # more attractive candidate; all alternatives born from this same event are
    # resolved together.
    for page_y in scan_y:
        if left_profile is None:
            observed_xs = tuple(black_by_y.get(page_y, ()))
        else:
            left_x = left_profile.at(page_y)
            observed_xs = () if left_x is None else (left_x,)
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
