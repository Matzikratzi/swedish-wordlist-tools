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


def _x_allowed(x: int, ranges: tuple[TranslateXRange, ...]) -> bool:
    return any(lo <= x <= hi for lo, hi in ranges)


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

    ``row_top`` is the only required row boundary.  We walk downward until the
    observed left profile enters a legal row-start interval and can seed an
    exact glyph placement.  That first match gives only a *provisional*
    baseline.  We then keep reading the profile down through that baseline
    before deciding which glyph is textual first.

    This matters when a later tall glyph becomes visible before a short first
    glyph such as '-'.  The tall glyph can supply the initial baseline clue,
    but the short glyph may not appear in the left profile until several raster
    rows later.  Any exact start candidate discovered before the provisional
    baseline is therefore allowed to compete.  If such a candidate implies a
    still lower baseline, the search horizon is extended to that baseline.

    Start intervals are absolute page x coordinates of observed profile pixels,
    not model translation coordinates.

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
        scan_y = tuple(range(row_top, scan_bottom))
    else:
        scan_y = tuple(left_profile.nonblank_y(row_top, scan_bottom))

    all_proposals: dict[tuple[int, int, int], BaselineMatch] = {}
    first_y: int | None = None
    horizon: int | None = None

    for page_y in scan_y:
        if horizon is not None and page_y > horizon:
            break

        if left_profile is None:
            observed_xs = tuple(black_by_y.get(page_y, ()))
        else:
            left_x = left_profile.at(page_y)
            observed_xs = () if left_x is None else (left_x,)
        observed_xs = tuple(x for x in observed_xs if _x_allowed(x, ranges))
        if not observed_xs:
            continue

        row_proposals: dict[tuple[int, int, int], BaselineMatch] = {}
        for item in library.models:
            top_rel_y = item.model.min_y
            top_row = item.rows[top_rel_y]
            baseline = page_y - top_rel_y
            for observed_x in observed_xs:
                for model_x in top_row:
                    tx = observed_x - model_x
                    key = (id(item.model), tx, baseline)
                    if key in all_proposals or key in row_proposals:
                        continue
                    placed = _placed_pixels(item, tx=tx, baseline=baseline)
                    if not placed.issubset(black):
                        continue

                    physical_left = tx + item.min_x
                    physical_right = tx + item.max_x
                    previous = black_by_y.get(page_y - 1, ())
                    if any(physical_left <= x <= physical_right for x in previous):
                        continue

                    row_proposals[key] = BaselineMatch(
                        model=item.model,
                        tx=tx,
                        baseline=baseline,
                        pixels=placed,
                        discovered_y=page_y,
                    )

        if not row_proposals:
            continue

        if first_y is None:
            first_y = page_y
        all_proposals.update(row_proposals)
        row_horizon = max(hit.baseline for hit in row_proposals.values())
        horizon = row_horizon if horizon is None else max(horizon, row_horizon)

    if not all_proposals:
        return None, FirstGlyphSearch(y=None, candidates=())

    candidates = tuple(
        sorted(
            all_proposals.values(),
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
    return _pick_unique_maximal(left_group), FirstGlyphSearch(
        y=first_y,
        candidates=left_group,
    )
