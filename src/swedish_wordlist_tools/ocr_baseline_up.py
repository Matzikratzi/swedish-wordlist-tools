from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping

from .ocr_glyph_matcher import GlyphModel


Pixel = tuple[int, int]


@dataclass(frozen=True)
class CompiledGlyph:
    model: GlyphModel
    min_x: int
    max_x: int
    rows: dict[int, tuple[int, ...]]

    @property
    def width(self) -> int:
        return self.max_x - self.min_x + 1


@dataclass(frozen=True)
class BaselineMatch:
    model: GlyphModel
    tx: int
    baseline: int
    pixels: frozenset[Pixel]
    discovered_y: int

    @property
    def left(self) -> int:
        return min(x for x, _y in self.pixels)

    @property
    def right(self) -> int:
        return max(x for x, _y in self.pixels)


@dataclass
class BaselineUpStats:
    calls: int = 0
    y_rows: int = 0
    observed_pixels: int = 0
    model_visits: int = 0
    raw_tx_proposals: int = 0
    in_bounds_tx: int = 0
    duplicate_tx: int = 0
    unique_tx: int = 0
    subset_checks: int = 0
    exact_hits: int = 0


class CompiledGlyphLibrary:
    """Geometry compiled once for cheap repeated row matching.

    ``by_rel_y`` is the important index for the residual-profile walk. With a
    known baseline, every page y maps immediately to a glyph-relative y, so we
    only inspect models that actually contain ink on that relative raster row.
    """

    def __init__(self, models: Iterable[GlyphModel]):
        compiled: list[CompiledGlyph] = []
        by_rel_y: dict[int, list[CompiledGlyph]] = defaultdict(list)
        for model in models:
            xs = [x for x, _y in model.pixels]
            rows_mut: dict[int, list[int]] = defaultdict(list)
            for x, y in model.pixels:
                rows_mut[y].append(x)
            rows = {y: tuple(sorted(row_xs)) for y, row_xs in rows_mut.items()}
            item = CompiledGlyph(
                model=model,
                min_x=min(xs),
                max_x=max(xs),
                rows=rows,
            )
            compiled.append(item)
            for rel_y in rows:
                by_rel_y[rel_y].append(item)

        self.models = tuple(compiled)
        self.by_rel_y = {rel_y: tuple(items) for rel_y, items in by_rel_y.items()}
        self.max_up = max((-item.model.min_y for item in compiled), default=0)
        self.max_down = max((item.model.max_y for item in compiled), default=0)


class ResidualInk:
    """Mutable residual pixels with a page-y index maintained incrementally."""

    def __init__(self, black: Iterable[Pixel]):
        self.pixels: set[Pixel] = set(black)
        rows: dict[int, set[int]] = defaultdict(set)
        for x, y in self.pixels:
            rows[y].add(x)
        self.rows: dict[int, set[int]] = dict(rows)

    def consume(self, pixels: Iterable[Pixel]) -> None:
        for x, y in pixels:
            if (x, y) not in self.pixels:
                continue
            self.pixels.remove((x, y))
            row = self.rows.get(y)
            if row is None:
                continue
            row.discard(x)
            if not row:
                del self.rows[y]

    def row(self, y: int) -> set[int]:
        return self.rows.get(y, set())

    def left_profile(
        self,
        *,
        top: int,
        bottom: int,
        min_x_exclusive: int | None = None,
        max_x_exclusive: int | None = None,
    ) -> dict[int, int]:
        """Return the leftmost still-unexplained x on each raster row.

        This is the dynamic residual profile used after one or more glyphs have
        been consumed. It is intentionally jagged: every raster row owns its own
        leftmost unexplained x. A later white-gap recovery can restart the same
        profile to the right simply by supplying ``min_x_exclusive``.
        """
        result: dict[int, int] = {}
        for y in range(top, bottom):
            xs = self.rows.get(y)
            if not xs:
                continue
            candidates = xs
            if min_x_exclusive is not None or max_x_exclusive is not None:
                candidates = {
                    x
                    for x in xs
                    if (min_x_exclusive is None or x > min_x_exclusive)
                    and (max_x_exclusive is None or x < max_x_exclusive)
                }
                if not candidates:
                    continue
            result[y] = min(candidates)
        return result


def black_by_y(black: Iterable[Pixel]) -> dict[int, tuple[int, ...]]:
    rows: dict[int, list[int]] = defaultdict(list)
    for x, y in black:
        rows[y].append(x)
    return {y: tuple(sorted(xs)) for y, xs in rows.items()}


def _placed_pixels(item: CompiledGlyph, *, tx: int, baseline: int) -> frozenset[Pixel]:
    return frozenset((tx + x, baseline + y) for x, y in item.model.pixels)


def _candidate_key(item: CompiledGlyph, tx: int, baseline: int) -> tuple[int, int, int]:
    return id(item.model), tx, baseline


def baseline_up_candidates(
    remaining: set[Pixel],
    remaining_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    *,
    baseline: int,
    row_top: int,
    profile_bottom: int,
    after_left: int,
    column_right: int,
    stats: BaselineUpStats | None = None,
) -> tuple[BaselineMatch, ...]:
    """Find exact next-glyph candidates from the residual left profile.

    For every raster row from the known row top through the lowest y reached by
    an already accepted glyph, only the *leftmost still-unexplained* pixel is
    used to propose placements. The complete glyph is still verified against
    the full 2D residual bitmap.

    This is deliberately different from scanning every residual pixel to the
    right. Ownership may move left/right between raster rows, so the profile is
    jagged, but each row contributes at most one observed x. Once OCR has safely
    crossed a true vertical white gap, the same mechanism can be restarted with
    a larger left boundary and thereby form a new local profile.
    """
    if stats is not None:
        stats.calls += 1
    if baseline < row_top:
        return ()

    profile_bottom = max(row_top, int(profile_bottom))
    seen: set[tuple[int, int, int]] = set()
    found: list[BaselineMatch] = []

    # Build the current residual profile without copying the whole page bitmap.
    # Only y rows in the already-established physical row height participate.
    for page_y in range(profile_bottom, row_top - 1, -1):
        if stats is not None:
            stats.y_rows += 1
        row_xs = remaining_by_y.get(page_y, ())
        if not row_xs:
            continue
        eligible = [x for x in row_xs if after_left < x < column_right]
        if not eligible:
            continue
        observed_x = min(eligible)
        if stats is not None:
            stats.observed_pixels += 1

        rel_y = page_y - baseline
        possible_models = library.by_rel_y.get(rel_y, ())
        if stats is not None:
            stats.model_visits += len(possible_models)
        if not possible_models:
            continue

        for item in possible_models:
            model_row = item.rows[rel_y]
            for model_x in model_row:
                if stats is not None:
                    stats.raw_tx_proposals += 1
                tx = observed_x - model_x
                physical_left = tx + item.min_x
                physical_right = tx + item.max_x
                if physical_left <= after_left or physical_right >= column_right:
                    continue
                if stats is not None:
                    stats.in_bounds_tx += 1
                key = _candidate_key(item, tx, baseline)
                if key in seen:
                    if stats is not None:
                        stats.duplicate_tx += 1
                    continue
                seen.add(key)
                if stats is not None:
                    stats.unique_tx += 1
                placed = _placed_pixels(item, tx=tx, baseline=baseline)
                if stats is not None:
                    stats.subset_checks += 1
                if placed.issubset(remaining):
                    if stats is not None:
                        stats.exact_hits += 1
                    found.append(
                        BaselineMatch(
                            model=item.model,
                            tx=tx,
                            baseline=baseline,
                            pixels=placed,
                            discovered_y=page_y,
                        )
                    )

    return tuple(
        sorted(
            found,
            key=lambda hit: (
                hit.left,
                -len(hit.pixels),
                -hit.model.sources,
                hit.model.label,
                hit.model.style,
            ),
        )
    )


def pick_leftmost_unique_maximal(candidates: Iterable[BaselineMatch]) -> BaselineMatch | None:
    rows = list(candidates)
    if not rows:
        return None
    left = min(hit.left for hit in rows)
    rows = [hit for hit in rows if hit.left == left]

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
    return max(
        equivalent,
        key=lambda hit: (len(hit.pixels), hit.model.sources, hit.model.label, hit.model.style),
    )


def find_next_baseline_up(
    remaining: set[Pixel],
    remaining_by_y: Mapping[int, Iterable[int]],
    library: CompiledGlyphLibrary,
    *,
    baseline: int,
    row_top: int,
    profile_bottom: int | None = None,
    after_left: int,
    column_right: int,
    stats: BaselineUpStats | None = None,
) -> tuple[BaselineMatch | None, tuple[BaselineMatch, ...]]:
    if profile_bottom is None:
        profile_bottom = baseline
    candidates = baseline_up_candidates(
        remaining,
        remaining_by_y,
        library,
        baseline=baseline,
        row_top=row_top,
        profile_bottom=profile_bottom,
        after_left=after_left,
        column_right=column_right,
        stats=stats,
    )
    return pick_leftmost_unique_maximal(candidates), candidates
